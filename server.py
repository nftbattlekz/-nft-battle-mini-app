import os
import json
import time
import random
import sqlite3
import hashlib
import hmac
from functools import wraps
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="")

DB_PATH = os.getenv("DB_PATH", "nexora.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CREATOR_TELEGRAM_ID = os.getenv("CREATOR_TELEGRAM_ID", "8518976778")

MAX_ENERGY = 100
ENERGY_REGEN_SECONDS = 300

app.config["JSON_AS_ASCII"] = False


# =========================================================
# DATABASE
# =========================================================

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    cur = con.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id TEXT UNIQUE NOT NULL,
        username TEXT DEFAULT '',
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        photo_url TEXT DEFAULT '',
        coins INTEGER DEFAULT 1000,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        energy INTEGER DEFAULT 100,
        energy_updated INTEGER DEFAULT 0,
        rating INTEGER DEFAULT 0,
        bank INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT 0,
        last_daily INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_key TEXT NOT NULL,
        quantity INTEGER DEFAULT 0,
        UNIQUE(user_id, item_key)
    );

    CREATE TABLE IF NOT EXISTS cooldowns (
        user_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        last_used INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, action)
    );

    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        business_key TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        last_collect INTEGER DEFAULT 0,
        UNIQUE(user_id, business_key)
    );

    CREATE TABLE IF NOT EXISTS properties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        property_key TEXT NOT NULL,
        UNIQUE(user_id, property_key)
    );

    CREATE TABLE IF NOT EXISTS pets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        pet_key TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        UNIQUE(user_id, pet_key)
    );

    CREATE TABLE IF NOT EXISTS skills (
        user_id INTEGER PRIMARY KEY,
        mining INTEGER DEFAULT 1,
        farming INTEGER DEFAULT 1,
        fishing INTEGER DEFAULT 1,
        business INTEGER DEFAULT 1,
        work INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS market (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        item_key TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        price_each INTEGER NOT NULL,
        created_at INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        multiplier REAL DEFAULT 1,
        ends_at INTEGER NOT NULL,
        title TEXT DEFAULT '',
        description TEXT DEFAULT '',
        active INTEGER DEFAULT 1,
        created_at INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        reason TEXT DEFAULT '',
        created_at INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS quests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quest_key TEXT NOT NULL,
        progress INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        claimed INTEGER DEFAULT 0,
        UNIQUE(user_id, quest_key)
    );

    CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        achievement_key TEXT NOT NULL,
        UNIQUE(user_id, achievement_key)
    );

    CREATE TABLE IF NOT EXISTS prefixes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        prefix_key TEXT NOT NULL,
        UNIQUE(user_id, prefix_key)
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );

    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        coins INTEGER NOT NULL DEFAULT 0,
        xp INTEGER NOT NULL DEFAULT 0,
        active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS promo_redemptions (
        user_id INTEGER NOT NULL,
        code TEXT NOT NULL,
        redeemed_at INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, code)
    );

    CREATE TABLE IF NOT EXISTS business_market (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        business_id INTEGER NOT NULL,
        business_key TEXT NOT NULL,
        title TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        price INTEGER NOT NULL,
        created_at INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    );

    CREATE TABLE IF NOT EXISTS wipe_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id TEXT NOT NULL,
        created_at INTEGER DEFAULT 0,
        affected_users INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creator_id TEXT NOT NULL,
        action TEXT NOT NULL,
        target_telegram_id TEXT DEFAULT '',
        details TEXT DEFAULT '',
        created_at INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS item_catalog (
        item_key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        icon TEXT DEFAULT '',
        base_price INTEGER DEFAULT 0
    );
    """)

    con.commit()
    con.close()


init_db()

# Permanent promo codes. Each account can redeem each code only once.
def seed_promo_codes():
    con = db()
    con.executemany("""
        INSERT OR IGNORE INTO promo_codes(code, coins, xp, active)
        VALUES (?, ?, ?, 1)
    """, [
        ("START", 1500, 20),
        ("BETA TEST", 1500, 20),
        ("GO", 1500, 20)
    ])
    con.commit()
    con.close()

seed_promo_codes()


# =========================================================
# GAME DATA
# =========================================================

JOBS = {
    "courier": {
        "name": "Курьер",
        "level": 1,
        "reward": 80,
        "xp": 20,
        "cooldown": 45
    },
    "loader": {
        "name": "Грузчик",
        "level": 2,
        "reward": 140,
        "xp": 30,
        "cooldown": 60
    },
    "fisher": {
        "name": "Рыбак",
        "level": 4,
        "reward": 230,
        "xp": 45,
        "cooldown": 90
    },
    "miner": {
        "name": "Шахтёр",
        "level": 6,
        "reward": 360,
        "xp": 65,
        "cooldown": 110
    },
    "driver": {
        "name": "Водитель",
        "level": 9,
        "reward": 520,
        "xp": 85,
        "cooldown": 130
    },
    "programmer": {
        "name": "Программист",
        "level": 13,
        "reward": 750,
        "xp": 110,
        "cooldown": 160
    },
    "trader": {
        "name": "Трейдер",
        "level": 18,
        "reward": 1050,
        "xp": 145,
        "cooldown": 190
    },
    "engineer": {
        "name": "Инженер",
        "level": 24,
        "reward": 1450,
        "xp": 185,
        "cooldown": 220
    },
    "director": {
        "name": "Директор",
        "level": 32,
        "reward": 2100,
        "xp": 240,
        "cooldown": 260
    },
    "magnate": {
        "name": "Магнат",
        "level": 45,
        "reward": 3200,
        "xp": 320,
        "cooldown": 320
    }
}


ITEMS = {
    "iron": {
        "name": "Железо",
        "icon": "⛓️",
        "base_price": 35
    },
    "coal": {
        "name": "Уголь",
        "icon": "⬛",
        "base_price": 25
    },
    "gold": {
        "name": "Золото",
        "icon": "🪙",
        "base_price": 120
    },
    "wood": {
        "name": "Древесина",
        "icon": "🪵",
        "base_price": 30
    },
    "wheat": {
        "name": "Пшеница",
        "icon": "🌾",
        "base_price": 20
    },
    "apple": {
        "name": "Яблоко",
        "icon": "🍎",
        "base_price": 25
    },
    "fish": {
        "name": "Рыба",
        "icon": "🐟",
        "base_price": 70
    },
    "rare_fish": {
        "name": "Редкая рыба",
        "icon": "🐠",
        "base_price": 250
    },
    "steel": {
        "name": "Сталь",
        "icon": "🔩",
        "base_price": 180
    },
    "energy_core": {
        "name": "Энергокристалл",
        "icon": "🔷",
        "base_price": 500
    },
    "microchip": {
        "name": "Микрочип",
        "icon": "💾",
        "base_price": 750
    },
    "quantum": {
        "name": "Квантовый модуль",
        "icon": "🧬",
        "base_price": 1800
    }
}


BUSINESS_LIMITS = {
    "farm": 100,
    "mine": 75,
    "factory": 50,
    "tech": 25,
    "space": 10
}

PROPERTY_LIMITS = {
    "room": 500,
    "apartment": 250,
    "penthouse": 50,
    "mansion": 10
}

BUSINESS_UPGRADE_MULTIPLIER = 1.55

BUSINESSES = {
    "farm": {
        "name": "Ферма",
        "price": 5000,
        "income": 300,
        "interval": 3600
    },
    "mine": {
        "name": "Шахта",
        "price": 15000,
        "income": 900,
        "interval": 3600
    },
    "factory": {
        "name": "Завод",
        "price": 50000,
        "income": 3200,
        "interval": 3600
    },
    "tech": {
        "name": "IT-компания",
        "price": 150000,
        "income": 10000,
        "interval": 3600
    },
    "space": {
        "name": "Космическая корпорация",
        "price": 500000,
        "income": 38000,
        "interval": 3600
    }
}


PROPERTIES = {
    "room": {
        "name": "Комната",
        "price": 2500,
        "rating": 5
    },
    "apartment": {
        "name": "Квартира",
        "price": 25000,
        "rating": 30
    },
    "penthouse": {
        "name": "Пентхаус",
        "price": 150000,
        "rating": 100
    },
    "mansion": {
        "name": "Особняк",
        "price": 750000,
        "rating": 300
    }
}


PLANETS = {
    "moon": {
        "name": "Луна",
        "level": 5,
        "price": 500
    },
    "mars": {
        "name": "Марс",
        "level": 15,
        "price": 2500
    },
    "jupiter": {
        "name": "Юпитер",
        "level": 30,
        "price": 10000
    },
    "neptune": {
        "name": "Нептун",
        "level": 50,
        "price": 50000
    }
}


PETS = {
    "cat": {
        "name": "Кибер-кот",
        "price": 5000,
        "bonus": 0.05
    },
    "wolf": {
        "name": "Кибер-волк",
        "price": 25000,
        "bonus": 0.10
    },
    "dragon": {
        "name": "Дракон NEXORA",
        "price": 150000,
        "bonus": 0.20
    }
}


QUESTS = {
    "work3": {
        "name": "Рабочая смена",
        "description": "Выполнить 3 работы",
        "target": 3,
        "reward": 500
    },
    "mine10": {
        "name": "Шахтёр",
        "description": "Добыть 10 ресурсов",
        "target": 10,
        "reward": 1000
    },
    "market1": {
        "name": "Торговец",
        "description": "Продать предмет на рынке",
        "target": 1,
        "reward": 1500
    }
}


# =========================================================
# HELPERS
# =========================================================

def now():
    return int(time.time())


def is_creator(user):
    return str(user["telegram_id"]) == str(CREATOR_TELEGRAM_ID)


def level_from_xp(xp):
    level = 1
    need = 100

    while xp >= need and level < 100:
        xp -= need
        level += 1
        need = int(100 * (1.18 ** (level - 1)))

    return level


def add_xp(con, user_id, amount):
    user = con.execute(
        "SELECT xp, level, rating FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:
        return

    new_xp = user["xp"] + amount
    new_level = level_from_xp(new_xp)

    rating_add = max(1, amount // 5)

    con.execute("""
        UPDATE users
        SET xp=?, level=?, rating=rating+?
        WHERE id=?
    """, (new_xp, new_level, rating_add, user_id))


def add_coins(con, user_id, amount, reason=""):
    con.execute(
        "UPDATE users SET coins=coins+? WHERE id=?",
        (amount, user_id)
    )

    con.execute("""
        INSERT INTO transactions(user_id, amount, reason, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, amount, reason, now()))


def get_multiplier(con, event_type):
    active = con.execute("""
        SELECT multiplier
        FROM events
        WHERE active=1
        AND ends_at>?
        AND (event_type=? OR event_type='all')
        ORDER BY multiplier DESC
        LIMIT 1
    """, (now(), event_type)).fetchone()

    if active:
        return float(active["multiplier"])

    return 1.0


def get_discount(con, event_type):
    """Return the largest active percentage discount (0..0.90)."""
    row = con.execute("""
        SELECT multiplier
        FROM events
        WHERE active=1
          AND ends_at>?
          AND (event_type=? OR event_type='all')
        ORDER BY multiplier DESC
        LIMIT 1
    """, (now(), event_type)).fetchone()
    if row:
        return max(0.0, min(0.90, float(row["multiplier"]) / 100.0))
    return 0.0


def discounted_price(con, event_type, base_price):
    return max(1, int(round(base_price * (1.0 - get_discount(con, event_type)))))


def log_admin(con, creator_id, action, target_telegram_id="", details=""):
    con.execute("""
        INSERT INTO admin_logs(creator_id, action, target_telegram_id, details, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (str(creator_id), action, str(target_telegram_id), details, now()))


def restore_energy(con, user):
    current = user["energy"]
    updated = user["energy_updated"] or now()

    elapsed = now() - updated

    if elapsed < ENERGY_REGEN_SECONDS:
        return current

    gained = elapsed // ENERGY_REGEN_SECONDS
    new_energy = min(MAX_ENERGY, current + gained)

    if new_energy != current:
        con.execute("""
            UPDATE users
            SET energy=?, energy_updated=?
            WHERE id=?
        """, (new_energy, now(), user["id"]))

    return new_energy


def use_energy(con, user_id, amount=10):
    user = con.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    energy = restore_energy(con, user)

    if energy < amount:
        return False

    con.execute("""
        UPDATE users
        SET energy=?, energy_updated=?
        WHERE id=?
    """, (energy - amount, now(), user_id))

    return True


def cooldown_remaining(con, user_id, action, cooldown):
    row = con.execute("""
        SELECT last_used
        FROM cooldowns
        WHERE user_id=? AND action=?
    """, (user_id, action)).fetchone()

    if not row:
        return 0

    remaining = cooldown - (now() - row["last_used"])
    return max(0, remaining)


def set_cooldown(con, user_id, action):
    con.execute("""
        INSERT INTO cooldowns(user_id, action, last_used)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, action)
        DO UPDATE SET last_used=excluded.last_used
    """, (user_id, action, now()))


def add_item(con, user_id, item_key, quantity=1):
    if item_key not in ITEMS:
        return

    con.execute("""
        INSERT INTO inventory(user_id, item_key, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, item_key)
        DO UPDATE SET quantity=quantity+excluded.quantity
    """, (user_id, item_key, quantity))


def remove_item(con, user_id, item_key, quantity):
    row = con.execute("""
        SELECT quantity FROM inventory
        WHERE user_id=? AND item_key=?
    """, (user_id, item_key)).fetchone()

    if not row or row["quantity"] < quantity:
        return False

    con.execute("""
        UPDATE inventory
        SET quantity=quantity-?
        WHERE user_id=? AND item_key=?
    """, (quantity, user_id, item_key))

    return True


def ensure_user(telegram_user):
    con = db()

    tg_id = str(telegram_user["id"])

    user = con.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if not user:
        con.execute("""
            INSERT INTO users(
                telegram_id,
                username,
                first_name,
                last_name,
                photo_url,
                coins,
                xp,
                level,
                energy,
                energy_updated,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, 1000, 0, 1, 100, ?, ?)
        """, (
            tg_id,
            telegram_user.get("username", ""),
            telegram_user.get("first_name", ""),
            telegram_user.get("last_name", ""),
            telegram_user.get("photo_url", ""),
            now(),
            now()
        ))

        con.commit()

        user = con.execute(
            "SELECT * FROM users WHERE telegram_id=?",
            (tg_id,)
        ).fetchone()

    else:
        con.execute("""
            UPDATE users
            SET username=?,
                first_name=?,
                last_name=?,
                photo_url=?
            WHERE telegram_id=?
        """, (
            telegram_user.get("username", ""),
            telegram_user.get("first_name", ""),
            telegram_user.get("last_name", ""),
            telegram_user.get("photo_url", ""),
            tg_id
        ))

        con.commit()

    # Creator always gets special prefix.
    if tg_id == str(CREATOR_TELEGRAM_ID):
        con.execute("""
            INSERT OR IGNORE INTO prefixes(user_id, prefix_key)
            VALUES (?, 'creator')
        """, (user["id"],))
        con.commit()

    # Skills.
    con.execute("""
        INSERT OR IGNORE INTO skills(user_id)
        VALUES (?)
    """, (user["id"],))

    # Quests.
    for key in QUESTS:
        con.execute("""
            INSERT OR IGNORE INTO quests(user_id, quest_key)
            VALUES (?, ?)
        """, (user["id"], key))

    con.commit()
    con.close()

    return get_user_by_tg(tg_id)


def get_user_by_tg(tg_id):
    con = db()
    user = con.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (str(tg_id),)
    ).fetchone()
    con.close()
    return user


def telegram_auth():
    header = request.headers.get("X-Telegram-Init-Data", "")

    # Local/demo mode if BOT_TOKEN is not configured.
    if not BOT_TOKEN:
        return {
            "id": "8518976778",
            "username": "creator",
            "first_name": "Creator",
            "last_name": "NEXORA",
            "photo_url": ""
        }

    if not header:
        return None

    try:
        data = dict(parse_qsl(header, keep_blank_values=True))

        received_hash = data.pop("hash", None)

        if not received_hash:
            return None

        auth_date = int(data.get("auth_date", "0"))

        if now() - auth_date > 86400:
            return None

        data_check_string = "\n".join(
            f"{key}={data[key]}"
            for key in sorted(data)
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user_data = json.loads(data.get("user", "{}"))

        return user_data

    except Exception:
        return None


def current_user():
    tg = telegram_auth()

    if not tg:
        return None

    ensure_user(tg)
    return get_user_by_tg(str(tg["id"]))


def require_user(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user:
            return jsonify({
                "ok": False,
                "error": "Telegram авторизация не прошла"
            }), 401

        return fn(user, *args, **kwargs)

    return wrapper


def require_creator(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user:
            return jsonify({
                "ok": False,
                "error": "Авторизация не прошла"
            }), 401

        if not is_creator(user):
            return jsonify({
                "ok": False,
                "error": "Доступ только для создателя"
            }), 403

        return fn(user, *args, **kwargs)

    return wrapper


# =========================================================
# SERIALIZATION
# =========================================================

def user_json(user, con):
    energy = restore_energy(con, user)

    prefix = "Игрок"

    if is_creator(user):
        prefix = "Создатель"

    inv = con.execute("""
        SELECT item_key, quantity
        FROM inventory
        WHERE user_id=? AND quantity>0
        ORDER BY quantity DESC
    """, (user["id"],)).fetchall()

    inventory = []

    for row in inv:
        item = ITEMS.get(row["item_key"])

        if item:
            inventory.append({
                "key": row["item_key"],
                "name": item["name"],
                "icon": item["icon"],
                "quantity": row["quantity"],
                "price": item["base_price"]
            })

    return {
        "id": user["id"],
        "telegram_id": user["telegram_id"],
        "username": user["username"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "photo_url": user["photo_url"],
        "coins": user["coins"],
        "bank": user["bank"],
        "xp": user["xp"],
        "level": user["level"],
        "energy": energy,
        "max_energy": MAX_ENERGY,
        "rating": user["rating"],
        "prefix": prefix,
        "creator": is_creator(user),
        "inventory": inventory
    }


# =========================================================
# MAIN DATA
# =========================================================

@app.get("/")
def index():
    return send_from_directory("web", "index.html")


@app.get("/api/bootstrap")
@require_user
def bootstrap(user):
    con = db()

    data = user_json(user, con)

    active_events = con.execute("""
        SELECT id, event_type, multiplier, ends_at, title, description
        FROM events
        WHERE active=1 AND ends_at>?
        ORDER BY id DESC
    """, (now(),)).fetchall()

    events = [dict(x) for x in active_events]

    market = con.execute("""
        SELECT
            m.*,
            u.username,
            u.first_name
        FROM market m
        JOIN users u ON u.id=m.seller_id
        WHERE m.status='active'
        ORDER BY m.id DESC
        LIMIT 50
    """).fetchall()

    market_data = []

    for row in market:
        item = ITEMS.get(row["item_key"])

        if item:
            market_data.append({
                "id": row["id"],
                "item_key": row["item_key"],
                "name": item["name"],
                "icon": item["icon"],
                "quantity": row["quantity"],
                "price_each": row["price_each"],
                "total": row["quantity"] * row["price_each"],
                "seller": row["username"] or row["first_name"] or "Игрок",
                "mine": row["seller_id"] == user["id"]
            })

    business_market_rows = con.execute("""
        SELECT bm.*, u.username, u.first_name
        FROM business_market bm
        JOIN users u ON u.id=bm.seller_id
        WHERE bm.status='active'
        ORDER BY bm.id DESC
        LIMIT 50
    """).fetchall()

    business_market_data = []
    for row in business_market_rows:
        business_market_data.append({
            "id": row["id"],
            "business_key": row["business_key"],
            "name": row["title"],
            "level": row["level"],
            "price": row["price"],
            "seller": row["username"] or row["first_name"] or "Игрок",
            "mine": row["seller_id"] == user["id"]
        })

    businesses = []

    owned = con.execute("""
        SELECT business_key, level, last_collect
        FROM businesses
        WHERE user_id=?
    """, (user["id"],)).fetchall()

    owned_dict = {x["business_key"]: dict(x) for x in owned}

    for key, value in BUSINESSES.items():
        own = owned_dict.get(key)

        global_count = con.execute(
            "SELECT COUNT(*) AS c FROM businesses WHERE business_key=?",
            (key,)
        ).fetchone()["c"]
        custom_name_row = con.execute(
            "SELECT value FROM settings WHERE key=?",
            (f"business_name:{user['id']}:{key}",)
        ).fetchone()
        display_name = custom_name_row["value"] if custom_name_row else value["name"]
        businesses.append({
            "key": key,
            **value,
            "name": display_name,
            "price": discounted_price(con, "business_discount", value["price"]),
            "base_price": value["price"],
            "discount": int(get_discount(con, "business_discount") * 100),
            "limit": BUSINESS_LIMITS.get(key, 0),
            "owned_count": global_count,
            "available": global_count < BUSINESS_LIMITS.get(key, 10**9),
            "owned": bool(own),
            "level_owned": own["level"] if own else 0,
            "last_collect": own["last_collect"] if own else 0
        })

    properties = []

    owned_props = con.execute("""
        SELECT property_key
        FROM properties
        WHERE user_id=?
    """, (user["id"],)).fetchall()

    owned_prop_keys = {x["property_key"] for x in owned_props}

    for key, value in PROPERTIES.items():
        global_count = con.execute(
            "SELECT COUNT(*) AS c FROM properties WHERE property_key=?",
            (key,)
        ).fetchone()["c"]
        properties.append({
            "key": key,
            **value,
            "price": discounted_price(con, "property_discount", value["price"]),
            "base_price": value["price"],
            "discount": int(get_discount(con, "property_discount") * 100),
            "limit": PROPERTY_LIMITS.get(key, 0),
            "owned_count": global_count,
            "available": global_count < PROPERTY_LIMITS.get(key, 10**9),
            "owned": key in owned_prop_keys
        })

    pets = []

    owned_pets = con.execute("""
        SELECT pet_key, level
        FROM pets
        WHERE user_id=?
    """, (user["id"],)).fetchall()

    owned_pet_dict = {
        x["pet_key"]: x["level"]
        for x in owned_pets
    }

    for key, value in PETS.items():
        pets.append({
            "key": key,
            **value,
            "owned": key in owned_pet_dict,
            "level_owned": owned_pet_dict.get(key, 0)
        })

    quests = []

    quest_rows = con.execute("""
        SELECT quest_key, progress, completed, claimed
        FROM quests
        WHERE user_id=?
    """, (user["id"],)).fetchall()

    for row in quest_rows:
        q = QUESTS.get(row["quest_key"])

        if q:
            quests.append({
                "key": row["quest_key"],
                **q,
                "progress": row["progress"],
                "completed": bool(row["completed"]),
                "claimed": bool(row["claimed"])
            })

    skills_row = con.execute("""
        SELECT *
        FROM skills
        WHERE user_id=?
    """, (user["id"],)).fetchone()

    skills = dict(skills_row) if skills_row else {}

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "user": data,
        "jobs": [
            {"key": k, **v}
            for k, v in JOBS.items()
        ],
        "items": ITEMS,
        "businesses": businesses,
        "properties": properties,
        "pets": pets,
        "planets": [
            {"key": k, **v}
            for k, v in PLANETS.items()
        ],
        "quests": quests,
        "skills": skills,
        "market": market_data,
        "business_market": business_market_data,
        "events": events,
        "promo_codes": ["START", "BETA TEST", "GO"],
        "creator": is_creator(user)
    })


# =========================================================
# WORK
# =========================================================

@app.post("/api/work")
@require_user
def work(user):
    data = request.get_json(silent=True) or {}
    job_key = data.get("job")

    job = JOBS.get(job_key)

    if not job:
        return jsonify({"ok": False, "error": "Работа не найдена"}), 400

    if user["level"] < job["level"]:
        return jsonify({
            "ok": False,
            "error": f"Нужен уровень {job['level']}"
        }), 400

    con = db()

    remaining = cooldown_remaining(
        con,
        user["id"],
        "job_" + job_key,
        job["cooldown"]
    )

    if remaining > 0:
        con.close()
        return jsonify({
            "ok": False,
            "error": f"Подожди {remaining} сек."
        }), 400

    if not use_energy(con, user["id"], 10):
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно энергии"
        }), 400

    multiplier = get_multiplier(con, "jobs")

    reward = int(job["reward"] * multiplier)

    add_coins(
        con,
        user["id"],
        reward,
        f"Работа: {job['name']}"
    )

    add_xp(con, user["id"], job["xp"])
    set_cooldown(con, user["id"], "job_" + job_key)

    quest = con.execute("""
        SELECT progress FROM quests
        WHERE user_id=? AND quest_key='work3'
    """, (user["id"],)).fetchone()

    if quest and quest["progress"] < 3:
        new_progress = quest["progress"] + 1

        con.execute("""
            UPDATE quests
            SET progress=?,
                completed=CASE WHEN ?>=3 THEN 1 ELSE 0 END
            WHERE user_id=? AND quest_key='work3'
        """, (new_progress, new_progress, user["id"]))

    con.commit()

    updated = con.execute(
        "SELECT * FROM users WHERE id=?",
        (user["id"],)
    ).fetchone()

    con.close()

    return jsonify({
        "ok": True,
        "reward": reward,
        "multiplier": multiplier,
        "user": {
            "coins": updated["coins"],
            "xp": updated["xp"],
            "level": updated["level"]
        }
    })


# =========================================================
# MINING
# =========================================================

@app.post("/api/mining")
@require_user
def mining(user):
    con = db()

    if not use_energy(con, user["id"], 15):
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно энергии"
        }), 400

    remaining = cooldown_remaining(
        con,
        user["id"],
        "mining",
        30
    )

    if remaining:
        con.close()
        return jsonify({
            "ok": False,
            "error": f"Шахта перезаряжается: {remaining} сек."
        }), 400

    skill = con.execute("""
        SELECT mining FROM skills WHERE user_id=?
    """, (user["id"],)).fetchone()

    skill_level = skill["mining"] if skill else 1

    possible = ["iron", "coal", "wood"]

    if skill_level >= 3:
        possible.append("gold")

    if skill_level >= 6:
        possible.append("steel")

    if skill_level >= 10:
        possible.append("energy_core")

    item_key = random.choice(possible)

    quantity = 1 + min(3, skill_level // 3)

    add_item(con, user["id"], item_key, quantity)
    add_xp(con, user["id"], 35 + skill_level * 2)
    set_cooldown(con, user["id"], "mining")

    con.execute("""
        UPDATE skills
        SET mining=mining+1
        WHERE user_id=? AND mining<20
    """, (user["id"],))

    con.commit()
    con.close()

    item = ITEMS[item_key]

    return jsonify({
        "ok": True,
        "item": item["name"],
        "icon": item["icon"],
        "quantity": quantity
    })


# =========================================================
# FARM
# =========================================================

@app.post("/api/farm")
@require_user
def farm(user):
    con = db()

    if not use_energy(con, user["id"], 12):
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно энергии"
        }), 400

    remaining = cooldown_remaining(
        con,
        user["id"],
        "farm",
        40
    )

    if remaining:
        con.close()
        return jsonify({
            "ok": False,
            "error": f"Ферма готовится: {remaining} сек."
        }), 400

    skill = con.execute("""
        SELECT farming FROM skills WHERE user_id=?
    """, (user["id"],)).fetchone()

    farming_level = skill["farming"] if skill else 1

    add_item(con, user["id"], "wheat", 2 + farming_level // 3)
    add_item(con, user["id"], "apple", 1 + farming_level // 5)

    add_xp(con, user["id"], 30)

    con.execute("""
        UPDATE skills
        SET farming=farming+1
        WHERE user_id=? AND farming<20
    """, (user["id"],))

    set_cooldown(con, user["id"], "farm")

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "message": "Урожай собран"
    })


# =========================================================
# FISHING
# =========================================================

@app.post("/api/fishing")
@require_user
def fishing(user):
    con = db()

    if not use_energy(con, user["id"], 10):
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно энергии"
        }), 400

    remaining = cooldown_remaining(
        con,
        user["id"],
        "fishing",
        35
    )

    if remaining:
        con.close()
        return jsonify({
            "ok": False,
            "error": f"Рыбалка недоступна ещё {remaining} сек."
        }), 400

    skill = con.execute("""
        SELECT fishing FROM skills WHERE user_id=?
    """, (user["id"],)).fetchone()

    fishing_level = skill["fishing"] if skill else 1

    if fishing_level >= 7 and random.random() < 0.2:
        item_key = "rare_fish"
    else:
        item_key = "fish"

    quantity = 1 + fishing_level // 5

    add_item(con, user["id"], item_key, quantity)
    add_xp(con, user["id"], 40)

    con.execute("""
        UPDATE skills
        SET fishing=fishing+1
        WHERE user_id=? AND fishing<20
    """, (user["id"],))

    set_cooldown(con, user["id"], "fishing")

    con.commit()
    con.close()

    item = ITEMS[item_key]

    return jsonify({
        "ok": True,
        "item": item["name"],
        "icon": item["icon"],
        "quantity": quantity
    })


# =========================================================
# BUSINESSES
# =========================================================

@app.post("/api/businesses/buy")
@require_user
def buy_business(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")

    business = BUSINESSES.get(key)

    if not business:
        return jsonify({
            "ok": False,
            "error": "Предприятие не найдено"
        }), 400

    con = db()

    exists = con.execute("""
        SELECT id FROM businesses
        WHERE user_id=? AND business_key=?
    """, (user["id"], key)).fetchone()

    if exists:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Предприятие уже куплено"
        }), 400

    global_count = con.execute(
        "SELECT COUNT(*) AS c FROM businesses WHERE business_key=?",
        (key,)
    ).fetchone()["c"]

    limit = BUSINESS_LIMITS.get(key, 10**9)
    if global_count >= limit:
        con.close()
        return jsonify({
            "ok": False,
            "error": f"Лимит предприятия достигнут: {limit} шт."
        }), 400

    price = discounted_price(con, "business_discount", business["price"])

    if user["coins"] < price:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    add_coins(
        con,
        user["id"],
        -price,
        f"Покупка предприятия: {business['name']}"
    )

    con.execute("""
        INSERT INTO businesses(
            user_id,
            business_key,
            level,
            last_collect
        )
        VALUES (?, ?, 1, ?)
    """, (user["id"], key, now()))

    add_xp(con, user["id"], 150)

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "message": "Предприятие приобретено"
    })


@app.post("/api/businesses/collect")
@require_user
def collect_business(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")

    business = BUSINESSES.get(key)

    if not business:
        return jsonify({
            "ok": False,
            "error": "Предприятие не найдено"
        }), 400

    con = db()

    owned = con.execute("""
        SELECT level, last_collect
        FROM businesses
        WHERE user_id=? AND business_key=?
    """, (user["id"], key)).fetchone()

    if not owned:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Сначала купи предприятие"
        }), 400

    elapsed = now() - owned["last_collect"]

    if elapsed < business["interval"]:
        remaining = business["interval"] - elapsed
        con.close()

        return jsonify({
            "ok": False,
            "error": f"Доход будет готов через {remaining // 60} мин."
        }), 400

    cycles = min(24, elapsed // business["interval"])

    multiplier = get_multiplier(con, "businesses")

    income = int(
        business["income"]
        * owned["level"]
        * cycles
        * multiplier
    )

    add_coins(
        con,
        user["id"],
        income,
        f"Доход: {business['name']}"
    )

    con.execute("""
        UPDATE businesses
        SET last_collect=?
        WHERE user_id=? AND business_key=?
    """, (now(), user["id"], key))

    add_xp(con, user["id"], 100 * cycles)

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "income": income,
        "multiplier": multiplier
    })



# =========================================================
# BUSINESS MANAGEMENT / TRADING
# =========================================================

@app.post("/api/businesses/upgrade")
@require_user
def upgrade_business(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")
    business = BUSINESSES.get(key)
    if not business:
        return jsonify({"ok": False, "error": "Предприятие не найдено"}), 400

    con = db()
    owned = con.execute("""
        SELECT id, level FROM businesses
        WHERE user_id=? AND business_key=?
    """, (user["id"], key)).fetchone()

    if not owned:
        con.close()
        return jsonify({"ok": False, "error": "Предприятие не куплено"}), 400

    new_level = owned["level"] + 1
    cost = int(business["price"] * (BUSINESS_UPGRADE_MULTIPLIER ** owned["level"]))

    if user["coins"] < cost:
        con.close()
        return jsonify({"ok": False, "error": f"Нужно {cost:,} 💎".replace(",", " ")}), 400

    add_coins(con, user["id"], -cost, f"Улучшение предприятия: {business['name']} Lv.{new_level}")
    con.execute("UPDATE businesses SET level=? WHERE id=?", (new_level, owned["id"]))
    add_xp(con, user["id"], 200 + new_level * 25)
    con.commit()
    con.close()
    return jsonify({"ok": True, "level": new_level, "cost": cost})


@app.post("/api/businesses/rename")
@require_user
def rename_business(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")
    title = str(data.get("title", "")).strip()

    if key not in BUSINESSES or not title:
        return jsonify({"ok": False, "error": "Введите корректное название"}), 400
    if len(title) > 32:
        return jsonify({"ok": False, "error": "Название максимум 32 символа"}), 400

    # Custom names are stored in settings with user/key scope.
    setting_key = f"business_name:{user['id']}:{key}"
    con = db()
    con.execute("""
        INSERT INTO settings(key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (setting_key, title))
    con.commit()
    con.close()
    return jsonify({"ok": True, "name": title})


@app.post("/api/businesses/list")
@require_user
def list_business_for_sale(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")
    price = int(data.get("price", 0))
    title = str(data.get("title", "")).strip()

    if key not in BUSINESSES or price <= 0:
        return jsonify({"ok": False, "error": "Неверные данные"}), 400

    con = db()
    owned = con.execute("""
        SELECT id, level FROM businesses
        WHERE user_id=? AND business_key=?
    """, (user["id"], key)).fetchone()

    if not owned:
        con.close()
        return jsonify({"ok": False, "error": "Предприятие не найдено"}), 400

    already = con.execute("""
        SELECT id FROM business_market
        WHERE business_id=? AND status='active'
    """, (owned["id"],)).fetchone()
    if already:
        con.close()
        return jsonify({"ok": False, "error": "Предприятие уже выставлено"}), 400

    if not title:
        setting = con.execute(
            "SELECT value FROM settings WHERE key=?",
            (f"business_name:{user['id']}:{key}",)
        ).fetchone()
        title = setting["value"] if setting else BUSINESSES[key]["name"]

    con.execute("""
        INSERT INTO business_market(
            seller_id, business_id, business_key, title, level, price, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user["id"], owned["id"], key, title, owned["level"], price, now()))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.post("/api/businesses/market/buy")
@require_user
def buy_business_from_market(user):
    data = request.get_json(silent=True) or {}
    listing_id = int(data.get("id", 0))
    con = db()

    listing = con.execute("""
        SELECT * FROM business_market
        WHERE id=? AND status='active'
    """, (listing_id,)).fetchone()

    if not listing:
        con.close()
        return jsonify({"ok": False, "error": "Предприятие уже продано"}), 404

    if listing["seller_id"] == user["id"]:
        con.close()
        return jsonify({"ok": False, "error": "Нельзя купить своё предприятие"}), 400

    if user["coins"] < listing["price"]:
        con.close()
        return jsonify({"ok": False, "error": "Недостаточно 💎"}), 400

    already = con.execute("""
        SELECT id FROM businesses
        WHERE user_id=? AND business_key=?
    """, (user["id"], listing["business_key"])).fetchone()
    if already:
        con.close()
        return jsonify({"ok": False, "error": "У тебя уже есть это предприятие"}), 400

    # Transfer the existing business row to the buyer.
    add_coins(con, user["id"], -listing["price"], "Покупка предприятия на рынке")
    add_coins(con, listing["seller_id"], listing["price"], "Продажа предприятия на рынке")
    con.execute("UPDATE businesses SET user_id=? WHERE id=?", (user["id"], listing["business_id"]))
    con.execute("UPDATE business_market SET status='sold' WHERE id=?", (listing_id,))
    add_xp(con, user["id"], 300)
    add_xp(con, listing["seller_id"], 300)
    con.commit()
    con.close()
    return jsonify({"ok": True, "price": listing["price"]})


@app.post("/api/businesses/market/cancel")
@require_user
def cancel_business_listing(user):
    data = request.get_json(silent=True) or {}
    listing_id = int(data.get("id", 0))
    con = db()
    row = con.execute("""
        SELECT id FROM business_market
        WHERE id=? AND seller_id=? AND status='active'
    """, (listing_id, user["id"])).fetchone()
    if not row:
        con.close()
        return jsonify({"ok": False, "error": "Лот не найден"}), 404
    con.execute("UPDATE business_market SET status='cancelled' WHERE id=?", (listing_id,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


# =========================================================
# PROPERTIES
# =========================================================

@app.post("/api/properties/buy")
@require_user
def buy_property(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")

    prop = PROPERTIES.get(key)

    if not prop:
        return jsonify({
            "ok": False,
            "error": "Недвижимость не найдена"
        }), 400

    con = db()

    exists = con.execute("""
        SELECT id FROM properties
        WHERE user_id=? AND property_key=?
    """, (user["id"], key)).fetchone()

    if exists:
        con.close()
        return jsonify({
            "ok": False,
            "error": "У тебя уже есть эта недвижимость"
        }), 400

    global_count = con.execute(
        "SELECT COUNT(*) AS c FROM properties WHERE property_key=?",
        (key,)
    ).fetchone()["c"]
    limit = PROPERTY_LIMITS.get(key, 10**9)
    if global_count >= limit:
        con.close()
        return jsonify({"ok": False, "error": f"Лимит достигнут: {limit} шт."}), 400

    price = discounted_price(con, "property_discount", prop["price"])

    if user["coins"] < price:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    add_coins(
        con,
        user["id"],
        -price,
        f"Покупка недвижимости: {prop['name']}"
    )

    con.execute("""
        INSERT INTO properties(user_id, property_key)
        VALUES (?, ?)
    """, (user["id"], key))

    con.execute("""
        UPDATE users
        SET rating=rating+?
        WHERE id=?
    """, (prop["rating"], user["id"]))

    con.commit()
    con.close()

    return jsonify({
        "ok": True
    })


# =========================================================
# PETS
# =========================================================

@app.post("/api/pets/buy")
@require_user
def buy_pet(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")

    pet = PETS.get(key)

    if not pet:
        return jsonify({
            "ok": False,
            "error": "Питомец не найден"
        }), 400

    con = db()

    exists = con.execute("""
        SELECT id FROM pets
        WHERE user_id=? AND pet_key=?
    """, (user["id"], key)).fetchone()

    if exists:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Этот питомец уже есть"
        }), 400

    if user["coins"] < pet["price"]:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    add_coins(
        con,
        user["id"],
        -pet["price"],
        f"Питомец: {pet['name']}"
    )

    con.execute("""
        INSERT INTO pets(user_id, pet_key)
        VALUES (?, ?)
    """, (user["id"], key))

    add_xp(con, user["id"], 100)

    con.commit()
    con.close()

    return jsonify({
        "ok": True
    })


# =========================================================
# PLANETS
# =========================================================

@app.post("/api/planets/travel")
@require_user
def travel(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")

    planet = PLANETS.get(key)

    if not planet:
        return jsonify({
            "ok": False,
            "error": "Планета не найдена"
        }), 400

    if user["level"] < planet["level"]:
        return jsonify({
            "ok": False,
            "error": f"Нужен уровень {planet['level']}"
        }), 400

    con = db()

    if user["coins"] < planet["price"]:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    add_coins(
        con,
        user["id"],
        -planet["price"],
        f"Путешествие: {planet['name']}"
    )

    add_xp(con, user["id"], 250)

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "planet": planet["name"]
    })


# =========================================================
# INVENTORY
# =========================================================

@app.get("/api/inventory")
@require_user
def inventory(user):
    con = db()

    rows = con.execute("""
        SELECT item_key, quantity
        FROM inventory
        WHERE user_id=? AND quantity>0
        ORDER BY item_key
    """, (user["id"],)).fetchall()

    result = []

    for row in rows:
        item = ITEMS.get(row["item_key"])

        if item:
            result.append({
                "key": row["item_key"],
                "name": item["name"],
                "icon": item["icon"],
                "quantity": row["quantity"],
                "price": item["base_price"]
            })

    con.close()

    return jsonify({
        "ok": True,
        "inventory": result
    })


# =========================================================
# MARKET
# =========================================================

@app.post("/api/market/create")
@require_user
def market_create(user):
    data = request.get_json(silent=True) or {}

    item_key = data.get("item_key")
    quantity = int(data.get("quantity", 0))
    price_each = int(data.get("price_each", 0))

    if item_key not in ITEMS:
        return jsonify({
            "ok": False,
            "error": "Предмет не найден"
        }), 400

    if quantity <= 0 or price_each <= 0:
        return jsonify({
            "ok": False,
            "error": "Неверное количество или цена"
        }), 400

    if price_each > 100000000:
        return jsonify({
            "ok": False,
            "error": "Слишком высокая цена"
        }), 400

    con = db()

    if not remove_item(
        con,
        user["id"],
        item_key,
        quantity
    ):
        con.close()
        return jsonify({
            "ok": False,
            "error": "У тебя нет такого количества предмета"
        }), 400

    con.execute("""
        INSERT INTO market(
            seller_id,
            item_key,
            quantity,
            price_each,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        user["id"],
        item_key,
        quantity,
        price_each,
        now()
    ))

    quest = con.execute("""
        SELECT progress
        FROM quests
        WHERE user_id=? AND quest_key='market1'
    """, (user["id"],)).fetchone()

    if quest and quest["progress"] < 1:
        con.execute("""
            UPDATE quests
            SET progress=1,
                completed=1
            WHERE user_id=? AND quest_key='market1'
        """, (user["id"],))

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "message": "Лот выставлен"
    })


@app.post("/api/market/buy")
@require_user
def market_buy(user):
    data = request.get_json(silent=True) or {}
    listing_id = int(data.get("id", 0))

    con = db()

    listing = con.execute("""
        SELECT *
        FROM market
        WHERE id=? AND status='active'
    """, (listing_id,)).fetchone()

    if not listing:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Лот уже продан или удалён"
        }), 404

    if listing["seller_id"] == user["id"]:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Нельзя купить собственный лот"
        }), 400

    total = listing["quantity"] * listing["price_each"]

    if user["coins"] < total:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    seller = con.execute("""
        SELECT id FROM users WHERE id=?
    """, (listing["seller_id"],)).fetchone()

    if not seller:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Продавец не найден"
        }), 400

    add_coins(
        con,
        user["id"],
        -total,
        "Покупка на рынке"
    )

    add_coins(
        con,
        listing["seller_id"],
        total,
        "Продажа на рынке"
    )

    add_item(
        con,
        user["id"],
        listing["item_key"],
        listing["quantity"]
    )

    con.execute("""
        UPDATE market
        SET status='sold'
        WHERE id=?
    """, (listing_id,))

    add_xp(con, user["id"], 50)
    add_xp(con, listing["seller_id"], 50)

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "total": total
    })


@app.post("/api/market/cancel")
@require_user
def market_cancel(user):
    data = request.get_json(silent=True) or {}
    listing_id = int(data.get("id", 0))

    con = db()

    listing = con.execute("""
        SELECT *
        FROM market
        WHERE id=? AND status='active' AND seller_id=?
    """, (listing_id, user["id"])).fetchone()

    if not listing:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Лот не найден"
        }), 404

    add_item(
        con,
        user["id"],
        listing["item_key"],
        listing["quantity"]
    )

    con.execute("""
        UPDATE market
        SET status='cancelled'
        WHERE id=?
    """, (listing_id,))

    con.commit()
    con.close()

    return jsonify({
        "ok": True
    })


# =========================================================
# QUESTS
# =========================================================

@app.post("/api/quests/claim")
@require_user
def quest_claim(user):
    data = request.get_json(silent=True) or {}
    key = data.get("key")

    quest = QUESTS.get(key)

    if not quest:
        return jsonify({
            "ok": False,
            "error": "Задание не найдено"
        }), 400

    con = db()

    row = con.execute("""
        SELECT *
        FROM quests
        WHERE user_id=? AND quest_key=?
    """, (user["id"], key)).fetchone()

    if not row or not row["completed"]:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Задание ещё не выполнено"
        }), 400

    if row["claimed"]:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Награда уже получена"
        }), 400

    add_coins(
        con,
        user["id"],
        quest["reward"],
        f"Награда: {quest['name']}"
    )

    con.execute("""
        UPDATE quests
        SET claimed=1
        WHERE user_id=? AND quest_key=?
    """, (user["id"], key))

    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "reward": quest["reward"]
    })



# =========================================================
# PROMO CODES
# =========================================================

@app.post("/api/promo/redeem")
@require_user
def redeem_promo(user):
    data = request.get_json(silent=True) or {}
    code = " ".join(str(data.get("code", "")).strip().upper().split())

    con = db()
    promo = con.execute("""
        SELECT * FROM promo_codes
        WHERE code=? AND active=1
    """, (code,)).fetchone()

    if not promo:
        con.close()
        return jsonify({"ok": False, "error": "Промокод не найден"}), 400

    used = con.execute("""
        SELECT 1 FROM promo_redemptions
        WHERE user_id=? AND code=?
    """, (user["id"], code)).fetchone()

    if used:
        con.close()
        return jsonify({"ok": False, "error": "Ты уже использовал этот промокод"}), 400

    add_coins(con, user["id"], promo["coins"], f"Промокод {code}")
    add_xp(con, user["id"], promo["xp"])
    con.execute("""
        INSERT INTO promo_redemptions(user_id, code, redeemed_at)
        VALUES (?, ?, ?)
    """, (user["id"], code, now()))
    con.commit()
    con.close()

    return jsonify({
        "ok": True,
        "coins": promo["coins"],
        "xp": promo["xp"],
        "code": code
    })


# =========================================================
# BANK
# =========================================================

@app.post("/api/bank")
@require_user
def bank(user):
    data = request.get_json(silent=True) or {}

    action = data.get("action")
    amount = int(data.get("amount", 0))

    if amount <= 0:
        return jsonify({
            "ok": False,
            "error": "Введите сумму"
        }), 400

    con = db()

    fresh = con.execute(
        "SELECT * FROM users WHERE id=?",
        (user["id"],)
    ).fetchone()

    if action == "deposit":
        if fresh["coins"] < amount:
            con.close()
            return jsonify({
                "ok": False,
                "error": "Недостаточно 💎"
            }), 400

        con.execute("""
            UPDATE users
            SET coins=coins-?,
                bank=bank+?
            WHERE id=?
        """, (amount, amount, user["id"]))

    elif action == "withdraw":
        if fresh["bank"] < amount:
            con.close()
            return jsonify({
                "ok": False,
                "error": "Недостаточно средств в банке"
            }), 400

        con.execute("""
            UPDATE users
            SET bank=bank-?,
                coins=coins+?
            WHERE id=?
        """, (amount, amount, user["id"]))

    else:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Неизвестное действие"
        }), 400

    con.commit()
    con.close()

    return jsonify({
        "ok": True
    })


# =========================================================
# LEADERBOARD
# =========================================================

@app.get("/api/leaderboard")
@require_user
def leaderboard(user):
    con = db()

    rows = con.execute("""
        SELECT
            telegram_id,
            username,
            first_name,
            photo_url,
            level,
            rating,
            coins
        FROM users
        ORDER BY rating DESC, level DESC
        LIMIT 50
    """).fetchall()

    result = []

    for i, row in enumerate(rows, 1):
        result.append({
            "place": i,
            "telegram_id": row["telegram_id"],
            "username": row["username"],
            "name": row["first_name"] or row["username"] or "Игрок",
            "photo_url": row["photo_url"],
            "level": row["level"],
            "rating": row["rating"],
            "coins": row["coins"],
            "creator": str(row["telegram_id"]) == str(CREATOR_TELEGRAM_ID)
        })

    con.close()

    return jsonify({
        "ok": True,
        "players": result
    })



# =========================================================
# RICHEST PLAYERS
# =========================================================

@app.get("/api/richest")
@require_user
def richest(user):
    con = db()
    rows = con.execute("""
        SELECT telegram_id, username, first_name, photo_url, coins, bank, level
        FROM users
        ORDER BY (coins + bank) DESC, level DESC
        LIMIT 50
    """).fetchall()
    result = []
    for i, row in enumerate(rows, 1):
        result.append({
            "place": i,
            "telegram_id": row["telegram_id"],
            "username": row["username"],
            "name": row["first_name"] or row["username"] or "Игрок",
            "photo_url": row["photo_url"],
            "coins": row["coins"],
            "bank": row["bank"],
            "total": row["coins"] + row["bank"],
            "level": row["level"],
            "creator": str(row["telegram_id"]) == str(CREATOR_TELEGRAM_ID)
        })
    con.close()
    return jsonify({"ok": True, "players": result})


# =========================================================
# CREATOR PANEL
# =========================================================


@app.post("/api/admin/xp")
@require_creator
def admin_xp(user):
    data = request.get_json(silent=True) or {}
    target_tg_id = str(data.get("telegram_id", "")).strip()
    amount = int(data.get("amount", 0))
    if not target_tg_id or amount <= 0:
        return jsonify({"ok": False, "error": "Неверные данные"}), 400
    con = db()
    target = con.execute("SELECT * FROM users WHERE telegram_id=?", (target_tg_id,)).fetchone()
    if not target:
        con.close()
        return jsonify({"ok": False, "error": "Игрок не найден"}), 404
    add_xp(con, target["id"], amount)
    log_admin(con, user["telegram_id"], "give_xp", target_tg_id, f"+{amount} XP")
    con.commit()
    fresh = con.execute("SELECT xp, level FROM users WHERE id=?", (target["id"],)).fetchone()
    con.close()
    return jsonify({"ok": True, "xp": fresh["xp"], "level": fresh["level"]})


@app.post("/api/admin/level")
@require_creator
def admin_level(user):
    data = request.get_json(silent=True) or {}
    target_tg_id = str(data.get("telegram_id", "")).strip()
    level = int(data.get("level", 0))
    if not target_tg_id or level < 1 or level > 100:
        return jsonify({"ok": False, "error": "Уровень должен быть 1-100"}), 400
    con = db()
    target = con.execute("SELECT * FROM users WHERE telegram_id=?", (target_tg_id,)).fetchone()
    if not target:
        con.close()
        return jsonify({"ok": False, "error": "Игрок не найден"}), 404
    # Find minimum cumulative XP needed for requested level.
    xp = 0
    for lv in range(1, level):
        xp += int(100 * (1.18 ** (lv - 1)))
    con.execute("UPDATE users SET level=?, xp=? WHERE id=?", (level, xp, target["id"]))
    log_admin(con, user["telegram_id"], "set_level", target_tg_id, f"level={level}")
    con.commit()
    con.close()
    return jsonify({"ok": True, "level": level})


@app.post("/api/admin/item")
@require_creator
def admin_item(user):
    data = request.get_json(silent=True) or {}
    target_tg_id = str(data.get("telegram_id", "")).strip()
    item_key = str(data.get("item_key", "")).strip()
    quantity = int(data.get("quantity", 0))
    if not target_tg_id or item_key not in ITEMS or quantity <= 0 or quantity > 100000:
        return jsonify({"ok": False, "error": "Неверные данные"}), 400
    con = db()
    target = con.execute("SELECT * FROM users WHERE telegram_id=?", (target_tg_id,)).fetchone()
    if not target:
        con.close()
        return jsonify({"ok": False, "error": "Игрок не найден"}), 404
    add_item(con, target["id"], item_key, quantity)
    log_admin(con, user["telegram_id"], "give_item", target_tg_id, f"{item_key} x{quantity}")
    con.commit()
    con.close()
    return jsonify({"ok": True, "item_key": item_key, "quantity": quantity})


@app.get("/api/admin/items")
@require_creator
def admin_items(user):
    return jsonify({
        "ok": True,
        "items": [{"key": k, **v} for k, v in ITEMS.items()]
    })


@app.get("/api/admin/logs")
@require_creator
def admin_logs(user):
    con = db()
    rows = con.execute("""
        SELECT * FROM admin_logs
        ORDER BY id DESC
        LIMIT 100
    """).fetchall()
    result = [dict(x) for x in rows]
    con.close()
    return jsonify({"ok": True, "logs": result})


@app.post("/api/admin/wipe")
@require_creator
def admin_wipe(user):
    data = request.get_json(silent=True) or {}
    if str(data.get("confirm", "")).upper() != "WIPE":
        return jsonify({"ok": False, "error": "Для вайпа отправь confirm=WIPE"}), 400

    con = db()
    users = con.execute("SELECT id FROM users").fetchall()

    # Preserve Telegram accounts and promo redemption history, but reset all game progress.
    for row in users:
        uid = row["id"]
        con.execute("""
            UPDATE users
            SET coins=1000, xp=0, level=1, energy=100,
                energy_updated=?, rating=0, bank=0, last_daily=0
            WHERE id=?
        """, (now(), uid))
        con.execute("DELETE FROM inventory WHERE user_id=?", (uid,))
        con.execute("DELETE FROM cooldowns WHERE user_id=?", (uid,))
        con.execute("DELETE FROM businesses WHERE user_id=?", (uid,))
        con.execute("DELETE FROM properties WHERE user_id=?", (uid,))
        con.execute("DELETE FROM pets WHERE user_id=?", (uid,))
        con.execute("""
            UPDATE skills
            SET mining=1, farming=1, fishing=1, business=1, work=1
            WHERE user_id=?
        """, (uid,))
        con.execute("DELETE FROM quests WHERE user_id=?", (uid,))
        for key in QUESTS:
            con.execute("INSERT OR IGNORE INTO quests(user_id, quest_key) VALUES (?, ?)", (uid, key))
        con.execute("DELETE FROM achievements WHERE user_id=?", (uid,))
        # Creator prefix is restored for creator below.
        if str(con.execute("SELECT telegram_id FROM users WHERE id=?", (uid,)).fetchone()["telegram_id"]) != str(CREATOR_TELEGRAM_ID):
            con.execute("DELETE FROM prefixes WHERE user_id=?", (uid,))
        else:
            con.execute("DELETE FROM prefixes WHERE user_id=? AND prefix_key!='creator'", (uid,))

    # Return active item listings to sellers before clearing them.
    listings = con.execute("SELECT seller_id, item_key, quantity FROM market WHERE status='active'").fetchall()
    for row in listings:
        add_item(con, row["seller_id"], row["item_key"], row["quantity"])
    con.execute("UPDATE market SET status='wiped' WHERE status='active'")

    con.execute("UPDATE business_market SET status='wiped' WHERE status='active'")
    con.execute("UPDATE events SET active=0 WHERE active=1")

    affected = len(users)
    con.execute("""
        INSERT INTO wipe_history(creator_id, created_at, affected_users)
        VALUES (?, ?, ?)
    """, (user["telegram_id"], now(), affected))
    log_admin(con, user["telegram_id"], "WIPE", "", f"{affected} players reset; each received 1000 coins")
    con.commit()
    con.close()

    return jsonify({"ok": True, "affected_users": affected, "start_balance": 1000})


@app.get("/api/admin/players")
@require_creator
def admin_players(user):
    con = db()

    q = str(request.args.get("q", "")).strip()
    if q:
        like = f"%{q}%"
        rows = con.execute("""
            SELECT
                id, telegram_id, username, first_name, last_name,
                coins, bank, level, xp, rating
            FROM users
            WHERE telegram_id LIKE ? OR username LIKE ? OR first_name LIKE ?
            ORDER BY id DESC
            LIMIT 200
        """, (like, like, like)).fetchall()
    else:
        rows = con.execute("""
            SELECT
                id, telegram_id, username, first_name, last_name,
                coins, bank, level, xp, rating
            FROM users
            ORDER BY id DESC
            LIMIT 200
        """).fetchall()

    players = [dict(x) for x in rows]

    con.close()

    return jsonify({
        "ok": True,
        "players": players
    })


@app.post("/api/admin/money")
@require_creator
def admin_money(user):
    data = request.get_json(silent=True) or {}

    target_tg_id = str(data.get("telegram_id", ""))
    amount = int(data.get("amount", 0))
    action = data.get("action")
    reason = data.get("reason", "Создатель NEXORA")

    if not target_tg_id or amount <= 0:
        return jsonify({
            "ok": False,
            "error": "Неверные данные"
        }), 400

    con = db()

    target = con.execute("""
        SELECT *
        FROM users
        WHERE telegram_id=?
    """, (target_tg_id,)).fetchone()

    if not target:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Игрок не найден"
        }), 404

    if action == "give":
        add_coins(
            con,
            target["id"],
            amount,
            reason
        )

    elif action == "take":
        actual = min(amount, target["coins"])

        add_coins(
            con,
            target["id"],
            -actual,
            reason
        )

        amount = actual

    else:
        con.close()
        return jsonify({
            "ok": False,
            "error": "Неизвестное действие"
        }), 400

    log_admin(
        con,
        user["telegram_id"],
        f"money_{action}",
        target_tg_id,
        f"amount={amount}; reason={reason}"
    )
    con.commit()

    new_user = con.execute("""
        SELECT coins
        FROM users
        WHERE id=?
    """, (target["id"],)).fetchone()

    con.close()

    return jsonify({
        "ok": True,
        "coins": new_user["coins"],
        "amount": amount
    })


@app.post("/api/admin/event")
@require_creator
def admin_event(user):
    data = request.get_json(silent=True) or {}

    event_type = data.get("event_type", "all")
    multiplier = float(data.get("multiplier", 2))
    duration_minutes = int(data.get("duration_minutes", 60))
    title = str(data.get("title", "Событие NEXORA")).strip()[:80]
    description = str(data.get(
        "description",
        "Временный бонус для экономики NEXORA"
    )).strip()[:200]

    allowed = [
        "jobs", "businesses", "all",
        "business_discount", "property_discount"
    ]
    if event_type not in allowed:
        return jsonify({"ok": False, "error": "Неизвестный тип события"}), 400

    if event_type.endswith("_discount"):
        if multiplier <= 0 or multiplier > 90:
            return jsonify({"ok": False, "error": "Скидка должна быть от 1% до 90%"}), 400
    else:
        if multiplier < 1 or multiplier > 10:
            return jsonify({"ok": False, "error": "Множитель должен быть от x1 до x10"}), 400

    if duration_minutes < 1 or duration_minutes > 10080:
        return jsonify({"ok": False, "error": "Неверная длительность"}), 400

    con = db()
    con.execute("UPDATE events SET active=0 WHERE active=1 AND event_type=?", (event_type,))
    ends_at = now() + duration_minutes * 60

    con.execute("""
        INSERT INTO events(
            creator_id, event_type, multiplier, ends_at,
            title, description, active, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    """, (
        user["telegram_id"], event_type, multiplier, ends_at,
        title, description, now()
    ))
    log_admin(
        con, user["telegram_id"], "event_create", "",
        f"type={event_type}; value={multiplier}; duration={duration_minutes}m"
    )
    con.commit()
    con.close()

    return jsonify({"ok": True, "ends_at": ends_at, "multiplier": multiplier})


@app.get("/api/admin/events")
@require_creator
def admin_events(user):
    con = db()

    rows = con.execute("""
        SELECT *
        FROM events
        ORDER BY id DESC
        LIMIT 50
    """).fetchall()

    result = [dict(x) for x in rows]

    con.close()

    return jsonify({
        "ok": True,
        "events": result
    })


@app.post("/api/admin/event/stop")
@require_creator
def admin_event_stop(user):
    data = request.get_json(silent=True) or {}
    event_id = int(data.get("id", 0))

    con = db()

    con.execute("""
        UPDATE events
        SET active=0
        WHERE id=?
    """, (event_id,))

    con.commit()
    con.close()

    return jsonify({
        "ok": True
    })



# =========================================================
# TRANSACTION HISTORY
# =========================================================

@app.get("/api/history")
@require_user
def history(user):
    con = db()
    rows = con.execute("""
        SELECT amount, reason, created_at
        FROM transactions
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 50
    """, (user["id"],)).fetchall()
    con.close()
    return jsonify({"ok": True, "history": [dict(x) for x in rows]})


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        "ok": False,
        "error": "Маршрут не найден"
    }), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "ok": False,
        "error": "Внутренняя ошибка сервера"
    }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )
