import os
import json
import time
import hmac
import hashlib
import sqlite3
import random
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="")

DB_PATH = os.environ.get("DB_PATH", "nexora.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CREATOR_ID = int(os.environ.get("CREATOR_TELEGRAM_ID", "8518976778"))

START_BALANCE = 500
MAX_LEVEL = 100


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db():
    conn = db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        username TEXT DEFAULT '',
        photo_url TEXT DEFAULT '',
        balance INTEGER DEFAULT 500,
        bank INTEGER DEFAULT 0,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        rating INTEGER DEFAULT 0,
        reputation INTEGER DEFAULT 50,
        energy INTEGER DEFAULT 100,
        storage INTEGER DEFAULT 500,
        population INTEGER DEFAULT 0,
        income_hour INTEGER DEFAULT 0,
        expenses_hour INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT 0,
        last_work INTEGER DEFAULT 0,
        last_mine INTEGER DEFAULT 0,
        last_farm INTEGER DEFAULT 0,
        last_fish INTEGER DEFAULT 0,
        last_claim INTEGER DEFAULT 0,
        last_login INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS resources (
        user_id INTEGER PRIMARY KEY,
        iron INTEGER DEFAULT 0,
        coal INTEGER DEFAULT 0,
        wood INTEGER DEFAULT 0,
        grain INTEGER DEFAULT 0,
        stone INTEGER DEFAULT 0,
        oil INTEGER DEFAULT 0,
        steel INTEGER DEFAULT 0,
        food INTEGER DEFAULT 0,
        electronics INTEGER DEFAULT 0,
        fuel INTEGER DEFAULT 0,
        fish INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        workers INTEGER DEFAULT 1,
        condition INTEGER DEFAULT 100,
        created_at INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS properties (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        level INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS pets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        type TEXT NOT NULL,
        level INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS technologies (
        user_id INTEGER PRIMARY KEY,
        mining INTEGER DEFAULT 0,
        agriculture INTEGER DEFAULT 0,
        industry INTEGER DEFAULT 0,
        energy INTEGER DEFAULT 0,
        logistics INTEGER DEFAULT 0,
        automation INTEGER DEFAULT 0,
        space INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item TEXT NOT NULL,
        amount INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS market (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL,
        seller_name TEXT DEFAULT '',
        item TEXT NOT NULL,
        amount INTEGER NOT NULL,
        price INTEGER NOT NULL,
        created_at INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS prefixes (
        user_id INTEGER NOT NULL,
        prefix TEXT NOT NULL,
        PRIMARY KEY(user_id, prefix)
    );

    CREATE TABLE IF NOT EXISTS equipped_prefix (
        user_id INTEGER PRIMARY KEY,
        prefix TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS planets (
        user_id INTEGER NOT NULL,
        planet TEXT NOT NULL,
        unlocked INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, planet)
    );

    CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item TEXT NOT NULL,
        required INTEGER NOT NULL,
        reward INTEGER NOT NULL,
        progress INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS achievements (
        user_id INTEGER NOT NULL,
        achievement TEXT NOT NULL,
        created_at INTEGER DEFAULT 0,
        PRIMARY KEY(user_id, achievement)
    );

    CREATE TABLE IF NOT EXISTS corporations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        capital INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS corporation_members (
        corporation_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        PRIMARY KEY(corporation_id, user_id)
    );

    CREATE INDEX IF NOT EXISTS idx_market_item ON market(item);
    CREATE INDEX IF NOT EXISTS idx_market_seller ON market(seller_id);
    CREATE INDEX IF NOT EXISTS idx_business_user ON businesses(user_id);
    CREATE INDEX IF NOT EXISTS idx_property_user ON properties(user_id);
    CREATE INDEX IF NOT EXISTS idx_inventory_user ON inventory(user_id);
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# AUTH
# =========================================================

def verify_telegram(init_data):
    if not BOT_TOKEN:
        return None

    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = data.pop("hash", None)

        if not received_hash:
            return None

        check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated = hmac.new(
            secret_key,
            check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated, received_hash):
            return None

        auth_date = int(data.get("auth_date", 0))

        if time.time() - auth_date > 86400:
            return None

        return json.loads(data.get("user", "{}"))

    except Exception:
        return None


def current_user():
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    tg = verify_telegram(init_data)

    if tg:
        return tg

    # Demo mode if BOT_TOKEN is not configured.
    # Useful for testing the Mini App before connecting BotFather.
    if not BOT_TOKEN:
        return {
            "id": CREATOR_ID,
            "first_name": "Aleksandr",
            "last_name": "",
            "username": "nexora_creator",
            "photo_url": ""
        }

    return None


def require_user():
    user = current_user()

    if not user:
        return None, jsonify({
            "ok": False,
            "error": "Telegram authentication required"
        }), 401

    return user, None, None


# =========================================================
# HELPERS
# =========================================================

def now():
    return int(time.time())


def get_user(conn, uid):
    return conn.execute(
        "SELECT * FROM users WHERE id=?",
        (uid,)
    ).fetchone()


def ensure_user(tg):
    conn = db()
    uid = int(tg["id"])

    row = get_user(conn, uid)

    if not row:
        conn.execute("""
            INSERT INTO users
            (id, first_name, last_name, username, photo_url,
             balance, created_at, last_login)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uid,
            tg.get("first_name", ""),
            tg.get("last_name", ""),
            tg.get("username", ""),
            tg.get("photo_url", ""),
            START_BALANCE,
            now(),
            now()
        ))

        conn.execute("""
            INSERT INTO resources(user_id)
            VALUES(?)
        """, (uid,))

        conn.execute("""
            INSERT INTO technologies(user_id)
            VALUES(?)
        """, (uid,))

        # Basic planets
        for planet in ["Земля", "Луна", "Марс", "Юпитер"]:
            conn.execute("""
                INSERT OR IGNORE INTO planets(user_id, planet, unlocked)
                VALUES(?, ?, ?)
            """, (
                uid,
                planet,
                1 if planet == "Земля" else 0
            ))

        # Creator prefix
        if uid == CREATOR_ID:
            conn.execute("""
                INSERT OR IGNORE INTO prefixes(user_id, prefix)
                VALUES(?, ?)
            """, (uid, "Создатель"))

            conn.execute("""
                INSERT OR REPLACE INTO equipped_prefix(user_id, prefix)
                VALUES(?, ?)
            """, (uid, "Создатель"))

        # Starter contract
        conn.execute("""
            INSERT INTO contracts(user_id, item, required, reward)
            VALUES (?, ?, ?, ?)
        """, (uid, "iron", 100, 1000))

    else:
        conn.execute("""
            UPDATE users
            SET first_name=?,
                last_name=?,
                username=?,
                photo_url=?,
                last_login=?
            WHERE id=?
        """, (
            tg.get("first_name", ""),
            tg.get("last_name", ""),
            tg.get("username", ""),
            tg.get("photo_url", ""),
            now(),
            uid
        ))

        if uid == CREATOR_ID:
            conn.execute("""
                INSERT OR IGNORE INTO prefixes(user_id, prefix)
                VALUES(?, ?)
            """, (uid, "Создатель"))

            conn.execute("""
                INSERT OR REPLACE INTO equipped_prefix(user_id, prefix)
                VALUES(?, ?)
            """, (uid, "Создатель"))

    conn.commit()
    conn.close()


def add_xp(conn, uid, amount):
    row = get_user(conn, uid)

    if not row:
        return

    xp = row["xp"] + amount
    level = row["level"]

    while level < MAX_LEVEL and xp >= level * 1000:
        xp -= level * 1000
        level += 1

    conn.execute("""
        UPDATE users
        SET xp=?, level=?
        WHERE id=?
    """, (xp, level, uid))


def add_balance(conn, uid, amount):
    conn.execute("""
        UPDATE users
        SET balance = MAX(0, balance + ?)
        WHERE id=?
    """, (amount, uid))


def resource(conn, uid, name):
    row = conn.execute(
        "SELECT * FROM resources WHERE user_id=?",
        (uid,)
    ).fetchone()

    return row[name] if row and name in row.keys() else 0


def add_resource(conn, uid, name, amount):
    allowed = {
        "iron", "coal", "wood", "grain", "stone",
        "oil", "steel", "food", "electronics",
        "fuel", "fish"
    }

    if name not in allowed:
        return

    conn.execute(
        f"UPDATE resources SET {name}=MAX(0,{name}+?) WHERE user_id=?",
        (amount, uid)
    )


def remove_resource(conn, uid, name, amount):
    if resource(conn, uid, name) < amount:
        return False

    conn.execute(
        f"UPDATE resources SET {name}={name}-? WHERE user_id=?",
        (amount, uid)
    )

    return True


def safe_user_payload(conn, uid):
    u = get_user(conn, uid)

    res = conn.execute(
        "SELECT * FROM resources WHERE user_id=?",
        (uid,)
    ).fetchone()

    tech = conn.execute(
        "SELECT * FROM technologies WHERE user_id=?",
        (uid,)
    ).fetchone()

    prefix = conn.execute(
        "SELECT prefix FROM equipped_prefix WHERE user_id=?",
        (uid,)
    ).fetchone()

    businesses = conn.execute("""
        SELECT COUNT(*) AS c
        FROM businesses
        WHERE user_id=?
    """, (uid,)).fetchone()["c"]

    properties = conn.execute("""
        SELECT COUNT(*) AS c
        FROM properties
        WHERE user_id=?
    """, (uid,)).fetchone()["c"]

    pets = conn.execute("""
        SELECT COUNT(*) AS c
        FROM pets
        WHERE user_id=?
    """, (uid,)).fetchone()["c"]

    return {
        "id": u["id"],
        "first_name": u["first_name"],
        "last_name": u["last_name"],
        "username": u["username"],
        "photo_url": u["photo_url"],
        "balance": u["balance"],
        "bank": u["bank"],
        "xp": u["xp"],
        "level": u["level"],
        "rating": u["rating"],
        "reputation": u["reputation"],
        "energy": u["energy"],
        "storage": u["storage"],
        "population": u["population"],
        "income_hour": u["income_hour"],
        "expenses_hour": u["expenses_hour"],
        "prefix": prefix["prefix"] if prefix else "",
        "businesses": businesses,
        "properties": properties,
        "pets": pets,
        "resources": dict(res) if res else {},
        "technologies": dict(tech) if tech else {}
    }


def calculate_income(conn, uid):
    business_income = 0
    business_expenses = 0

    rows = conn.execute("""
        SELECT type, level, workers, condition
        FROM businesses
        WHERE user_id=?
    """, (uid,)).fetchall()

    income_table = {
        "mine": 250,
        "farm": 180,
        "factory": 500,
        "electronics": 850,
        "oil": 700,
        "power": 400,
        "logistics": 350
    }

    for row in rows:
        base = income_table.get(row["type"], 100)
        business_income += base * row["level"] * max(1, row["condition"]) // 100
        business_expenses += row["workers"] * 40 * row["level"]

    property_income = conn.execute("""
        SELECT COALESCE(SUM(
            CASE type
                WHEN 'room' THEN 50
                WHEN 'house' THEN 150
                WHEN 'office' THEN 500
                WHEN 'building' THEN 1800
                WHEN 'skyscraper' THEN 7000
                ELSE 0
            END * level
        ),0) AS income
        FROM properties
        WHERE user_id=?
    """, (uid,)).fetchone()["income"]

    income = business_income + property_income
    expenses = business_expenses

    conn.execute("""
        UPDATE users
        SET income_hour=?, expenses_hour=?
        WHERE id=?
    """, (income, expenses))

    return income, expenses


# =========================================================
# MAIN
# =========================================================

@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory("web", path)


# =========================================================
# AUTH / PROFILE
# =========================================================

@app.route("/api/me")
def api_me():
    tg = current_user()

    if not tg:
        return jsonify({
            "ok": False,
            "error": "Telegram authentication required"
        }), 401

    ensure_user(tg)

    conn = db()
    payload = safe_user_payload(conn, int(tg["id"]))
    conn.close()

    return jsonify({
        "ok": True,
        "user": payload
    })


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/api/dashboard")
def dashboard():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)

    uid = int(tg["id"])
    conn = db()

    calculate_income(conn, uid)

    user = safe_user_payload(conn, uid)

    events = [
        {
            "title": "🌍 Мировой рынок",
            "text": "Спрос на промышленную продукцию повышен."
        },
        {
            "title": "⚡ Энергетический цикл",
            "text": "Энергетические предприятия работают стабильно."
        }
    ]

    contracts = conn.execute("""
        SELECT *
        FROM contracts
        WHERE user_id=? AND completed=0
        ORDER BY id DESC
        LIMIT 5
    """, (uid,)).fetchall()

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "user": user,
        "events": events,
        "contracts": [dict(x) for x in contracts]
    })


# =========================================================
# WORK
# =========================================================

@app.route("/api/work", methods=["POST"])
def work():
    tg, err, status = require_user()

    if err:
        return err, status

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()
    u = get_user(conn, uid)

    cooldown = 60

    if now() - u["last_work"] < cooldown:
        remaining = cooldown - (now() - u["last_work"])
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Работа будет доступна через {remaining} сек."
        }), 400

    jobs = [
        ("💼 Курьер", 180, 80),
        ("🔧 Механик", 260, 120),
        ("👨‍💻 Разработчик", 420, 180),
        ("📈 Менеджер", 550, 250)
    ]

    job = jobs[random.randrange(len(jobs))]

    add_balance(conn, uid, job[1])
    add_xp(conn, uid, job[2])

    conn.execute("""
        UPDATE users
        SET last_work=?, rating=rating+?
        WHERE id=?
    """, (now(), job[1] // 10, uid))

    conn.commit()
    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "job": job[0],
        "reward": job[1],
        "xp": job[2],
        "user": result
    })


# =========================================================
# MINING
# =========================================================

@app.route("/api/mining", methods=["POST"])
def mining():
    tg, err, status = require_user()

    if err:
        return err, status

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()
    u = get_user(conn, uid)

    cooldown = 30

    if now() - u["last_mine"] < cooldown:
        remaining = cooldown - (now() - u["last_mine"])
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Шахта перезаряжается: {remaining} сек."
        }), 400

    tech = conn.execute("""
        SELECT mining
        FROM technologies
        WHERE user_id=?
    """, (uid,)).fetchone()

    level = tech["mining"] if tech else 0

    iron = 15 + level * 5
    coal = 10 + level * 3
    stone = 20 + level * 5

    add_resource(conn, uid, "iron", iron)
    add_resource(conn, uid, "coal", coal)
    add_resource(conn, uid, "stone", stone)
    add_xp(conn, uid, 80)

    conn.execute("""
        UPDATE users
        SET last_mine=?, rating=rating+10
        WHERE id=?
    """, (now(), uid))

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "rewards": {
            "iron": iron,
            "coal": coal,
            "stone": stone
        },
        "user": result
    })


# =========================================================
# FARM
# =========================================================

@app.route("/api/farm", methods=["POST"])
def farm():
    tg, err, status = require_user()

    if err:
        return err, status

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()
    u = get_user(conn, uid)

    cooldown = 45

    if now() - u["last_farm"] < cooldown:
        remaining = cooldown - (now() - u["last_farm"])
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Ферма готовится: {remaining} сек."
        }), 400

    tech = conn.execute("""
        SELECT agriculture
        FROM technologies
        WHERE user_id=?
    """, (uid,)).fetchone()

    level = tech["agriculture"] if tech else 0

    grain = 30 + level * 8
    food = 15 + level * 4

    add_resource(conn, uid, "grain", grain)
    add_resource(conn, uid, "food", food)
    add_xp(conn, uid, 70)

    conn.execute("""
        UPDATE users
        SET last_farm=?, rating=rating+8
        WHERE id=?
    """, (now(), uid))

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "rewards": {
            "grain": grain,
            "food": food
        },
        "user": result
    })


# =========================================================
# FISHING
# =========================================================

@app.route("/api/fishing", methods=["POST"])
def fishing():
    tg, err, status = require_user()

    if err:
        return err, status

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()
    u = get_user(conn, uid)

    cooldown = 40

    if now() - u["last_fish"] < cooldown:
        remaining = cooldown - (now() - u["last_fish"])
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Рыбалка доступна через {remaining} сек."
        }), 400

    fish_types = [
        ("Окунь", 8),
        ("Карп", 12),
        ("Щука", 18),
        ("Судак", 25)
    ]

    fish, amount = random.choice(fish_types)

    add_resource(conn, uid, "fish", amount)
    add_xp(conn, uid, 60)

    conn.execute("""
        UPDATE users
        SET last_fish=?, rating=rating+5
        WHERE id=?
    """, (now(), uid))

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "fish": fish,
        "amount": amount,
        "user": result
    })


# =========================================================
# BUSINESSES
# =========================================================

BUSINESSES = {
    "mine": {
        "name": "⛏️ Железная шахта",
        "price": 2500
    },
    "farm": {
        "name": "🌾 Ферма",
        "price": 1800
    },
    "factory": {
        "name": "🏭 Завод",
        "price": 10000
    },
    "electronics": {
        "name": "💻 Электронный завод",
        "price": 30000
    },
    "oil": {
        "name": "🛢️ Нефтяная компания",
        "price": 50000
    },
    "power": {
        "name": "⚡ Электростанция",
        "price": 20000
    },
    "logistics": {
        "name": "🚚 Логистический центр",
        "price": 15000
    }
}


@app.route("/api/businesses")
def businesses():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM businesses
        WHERE user_id=?
        ORDER BY id DESC
    """, (uid,)).fetchall()

    calculate_income(conn, uid)
    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "catalog": BUSINESSES,
        "owned": [dict(x) for x in rows]
    })


@app.route("/api/businesses/buy", methods=["POST"])
def buy_business():
    tg, err, status = require_user()

    if err:
        return err, status

    ensure_user(tg)

    data = request.get_json(silent=True) or {}
    business_type = data.get("type")

    if business_type not in BUSINESSES:
        return jsonify({
            "ok": False,
            "error": "Неизвестное предприятие"
        }), 400

    uid = int(tg["id"])
    price = BUSINESSES[business_type]["price"]

    conn = db()
    u = get_user(conn, uid)

    if u["balance"] < price:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (price, uid))

    conn.execute("""
        INSERT INTO businesses
        (user_id, type, level, workers, condition, created_at)
        VALUES (?, ?, 1, 1, 100, ?)
    """, (uid, business_type, now()))

    add_xp(conn, uid, price // 20)

    calculate_income(conn, uid)

    conn.commit()
    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "user": result
    })


@app.route("/api/businesses/upgrade", methods=["POST"])
def upgrade_business():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    business_id = int(data.get("id", 0))

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    business = conn.execute("""
        SELECT *
        FROM businesses
        WHERE id=? AND user_id=?
    """, (business_id, uid)).fetchone()

    if not business:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Предприятие не найдено"
        }), 404

    price = 1000 * business["level"] ** 2

    u = get_user(conn, uid)

    if u["balance"] < price:
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Нужно {price:,} 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (price, uid))

    conn.execute("""
        UPDATE businesses
        SET level=level+1,
            condition=100
        WHERE id=?
    """, (business_id,))

    add_xp(conn, uid, 150)

    calculate_income(conn, uid)

    conn.commit()
    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "price": price,
        "user": result
    })


# =========================================================
# PROPERTIES
# =========================================================

PROPERTIES = {
    "room": ("🏚️ Комната", 5000),
    "house": ("🏠 Дом", 15000),
    "office": ("🏢 Офис", 60000),
    "building": ("🏙️ Бизнес-центр", 250000),
    "skyscraper": ("🌆 Небоскрёб", 1500000)
}


@app.route("/api/properties")
def properties():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM properties
        WHERE user_id=?
        ORDER BY id DESC
    """, (uid,)).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "catalog": {
            k: {
                "name": v[0],
                "price": v[1]
            }
            for k, v in PROPERTIES.items()
        },
        "owned": [dict(x) for x in rows]
    })


@app.route("/api/properties/buy", methods=["POST"])
def buy_property():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    property_type = data.get("type")

    if property_type not in PROPERTIES:
        return jsonify({
            "ok": False,
            "error": "Неизвестная недвижимость"
        }), 400

    ensure_user(tg)
    uid = int(tg["id"])

    price = PROPERTIES[property_type][1]

    conn = db()
    u = get_user(conn, uid)

    if u["balance"] < price:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (price, uid))

    conn.execute("""
        INSERT INTO properties(user_id, type, level)
        VALUES (?, ?, 1)
    """, (uid, property_type))

    add_xp(conn, uid, price // 30)
    calculate_income(conn, uid)

    conn.commit()
    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "user": result
    })


# =========================================================
# BANK
# =========================================================

@app.route("/api/bank", methods=["POST"])
def bank():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    action = data.get("action")
    amount = max(0, int(data.get("amount", 0)))

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()
    u = get_user(conn, uid)

    if amount <= 0:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "Некорректная сумма"
        }), 400

    if action == "deposit":
        if u["balance"] < amount:
            conn.close()

            return jsonify({
                "ok": False,
                "error": "Недостаточно средств"
            }), 400

        conn.execute("""
            UPDATE users
            SET balance=balance-?,
                bank=bank+?
            WHERE id=?
        """, (amount, amount, uid))

    elif action == "withdraw":
        if u["bank"] < amount:
            conn.close()

            return jsonify({
                "ok": False,
                "error": "Недостаточно средств в банке"
            }), 400

        conn.execute("""
            UPDATE users
            SET balance=balance+?,
                bank=bank-?
            WHERE id=?
        """, (amount, amount, uid))

    else:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Неизвестная операция"
        }), 400

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "user": result
    })


# =========================================================
# INVENTORY
# =========================================================

@app.route("/api/inventory")
def inventory():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    res = conn.execute("""
        SELECT *
        FROM resources
        WHERE user_id=?
    """, (uid,)).fetchone()

    inv = conn.execute("""
        SELECT item, amount
        FROM inventory
        WHERE user_id=?
        ORDER BY id DESC
    """, (uid,)).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "resources": dict(res) if res else {},
        "items": [dict(x) for x in inv]
    })


# =========================================================
# TECHNOLOGIES
# =========================================================

TECHS = {
    "mining": {
        "name": "⛏️ Горное дело",
        "base": 1000
    },
    "agriculture": {
        "name": "🌾 Агрономия",
        "base": 1000
    },
    "industry": {
        "name": "🏭 Промышленность",
        "base": 2500
    },
    "energy": {
        "name": "⚡ Энергетика",
        "base": 3000
    },
    "logistics": {
        "name": "🚚 Логистика",
        "base": 3000
    },
    "automation": {
        "name": "🤖 Автоматизация",
        "base": 5000
    },
    "space": {
        "name": "🚀 Космос",
        "base": 15000
    }
}


@app.route("/api/technologies")
def technologies():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    row = conn.execute("""
        SELECT *
        FROM technologies
        WHERE user_id=?
    """, (uid,)).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "catalog": TECHS,
        "technologies": dict(row)
    })


@app.route("/api/technologies/upgrade", methods=["POST"])
def upgrade_technology():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    tech = data.get("technology")

    if tech not in TECHS:
        return jsonify({
            "ok": False,
            "error": "Неизвестная технология"
        }), 400

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    row = conn.execute("""
        SELECT *
        FROM technologies
        WHERE user_id=?
    """, (uid,)).fetchone()

    current = row[tech]

    if current >= 10:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Максимальный уровень"
        }), 400

    price = TECHS[tech]["base"] * (current + 1) ** 2

    u = get_user(conn, uid)

    if u["balance"] < price:
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Нужно {price:,} 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (price, uid))

    conn.execute(
        f"UPDATE technologies SET {tech}={tech}+1 WHERE user_id=?",
        (uid,)
    )

    add_xp(conn, uid, price // 20)

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "price": price,
        "user": result
    })


# =========================================================
# PETS
# =========================================================

PETS = {
    "wolf": ("🐺 Волк", 10000),
    "robot": ("🤖 Робот", 50000),
    "dragon": ("🐉 Дракон", 250000)
}


@app.route("/api/pets")
def pets():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    owned = conn.execute("""
        SELECT *
        FROM pets
        WHERE user_id=?
    """, (uid,)).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "catalog": {
            k: {
                "name": v[0],
                "price": v[1]
            }
            for k, v in PETS.items()
        },
        "owned": [dict(x) for x in owned]
    })


@app.route("/api/pets/buy", methods=["POST"])
def buy_pet():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    pet_type = data.get("type")

    if pet_type not in PETS:
        return jsonify({
            "ok": False,
            "error": "Неизвестный питомец"
        }), 400

    ensure_user(tg)
    uid = int(tg["id"])
    price = PETS[pet_type][1]

    conn = db()
    u = get_user(conn, uid)

    if u["balance"] < price:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (price, uid))

    conn.execute("""
        INSERT INTO pets(user_id, type, level)
        VALUES (?, ?, 1)
    """, (uid, pet_type))

    add_xp(conn, uid, price // 25)

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "user": result
    })


# =========================================================
# MARKET
# =========================================================

@app.route("/api/market")
def market():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM market
        ORDER BY id DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "items": [dict(x) for x in rows]
    })


@app.route("/api/market/create", methods=["POST"])
def market_create():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}

    item = str(data.get("item", "")).strip()
    amount = int(data.get("amount", 0))
    price = int(data.get("price", 0))

    allowed = {
        "iron", "coal", "wood", "grain",
        "stone", "oil", "steel", "food",
        "electronics", "fuel", "fish"
    }

    if item not in allowed or amount <= 0 or price <= 0:
        return jsonify({
            "ok": False,
            "error": "Некорректное объявление"
        }), 400

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    if resource(conn, uid, item) < amount:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Недостаточно ресурса"
        }), 400

    remove_resource(conn, uid, item, amount)

    u = get_user(conn, uid)

    conn.execute("""
        INSERT INTO market
        (seller_id, seller_name, item, amount, price, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        uid,
        u["first_name"],
        item,
        amount,
        price,
        now()
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True
    })


@app.route("/api/market/buy", methods=["POST"])
def market_buy():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    listing_id = int(data.get("id", 0))

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    listing = conn.execute("""
        SELECT *
        FROM market
        WHERE id=?
    """, (listing_id,)).fetchone()

    if not listing:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Объявление уже продано"
        }), 404

    if listing["seller_id"] == uid:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Нельзя купить своё объявление"
        }), 400

    buyer = get_user(conn, uid)

    if buyer["balance"] < listing["price"]:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (listing["price"], uid))

    conn.execute("""
        UPDATE users
        SET balance=balance+?
        WHERE id=?
    """, (listing["price"], listing["seller_id"]))

    add_resource(
        conn,
        uid,
        listing["item"],
        listing["amount"]
    )

    conn.execute("""
        DELETE FROM market
        WHERE id=?
    """, (listing_id,))

    add_xp(conn, uid, 50)

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "user": result
    })


@app.route("/api/market/cancel", methods=["POST"])
def market_cancel():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    listing_id = int(data.get("id", 0))

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    listing = conn.execute("""
        SELECT *
        FROM market
        WHERE id=? AND seller_id=?
    """, (listing_id, uid)).fetchone()

    if not listing:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Объявление не найдено"
        }), 404

    add_resource(
        conn,
        uid,
        listing["item"],
        listing["amount"]
    )

    conn.execute("""
        DELETE FROM market
        WHERE id=?
    """, (listing_id,))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================================================
# PLANETS
# =========================================================

PLANETS = {
    "Земля": {
        "price": 0,
        "level": 1
    },
    "Луна": {
        "price": 50000,
        "level": 10
    },
    "Марс": {
        "price": 500000,
        "level": 25
    },
    "Юпитер": {
        "price": 5000000,
        "level": 50
    }
}


@app.route("/api/planets")
def planets():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    owned = conn.execute("""
        SELECT *
        FROM planets
        WHERE user_id=?
    """, (uid,)).fetchall()

    user = get_user(conn, uid)

    result = []

    for name, info in PLANETS.items():
        row = next(
            (x for x in owned if x["planet"] == name),
            None
        )

        result.append({
            "planet": name,
            "price": info["price"],
            "required_level": info["level"],
            "unlocked": bool(row and row["unlocked"]),
            "user_level": user["level"]
        })

    conn.close()

    return jsonify({
        "ok": True,
        "planets": result
    })


@app.route("/api/planets/travel", methods=["POST"])
def planet_travel():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    planet = data.get("planet")

    if planet not in PLANETS:
        return jsonify({
            "ok": False,
            "error": "Планета не найдена"
        }), 400

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    u = get_user(conn, uid)

    if u["level"] < PLANETS[planet]["level"]:
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Нужен уровень {PLANETS[planet]['level']}"
        }), 400

    row = conn.execute("""
        SELECT *
        FROM planets
        WHERE user_id=? AND planet=?
    """, (uid, planet)).fetchone()

    price = PLANETS[planet]["price"]

    if not row or not row["unlocked"]:
        if u["balance"] < price:
            conn.close()

            return jsonify({
                "ok": False,
                "error": "Недостаточно 💎"
            }), 400

        conn.execute("""
            UPDATE users
            SET balance=balance-?
            WHERE id=?
        """, (price, uid))

        conn.execute("""
            INSERT OR REPLACE INTO planets
            (user_id, planet, unlocked)
            VALUES (?, ?, 1)
        """, (uid, planet))

    add_xp(conn, uid, 250)

    conn.commit()
    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "planet": planet,
        "user": result
    })


# =========================================================
# CONTRACTS
# =========================================================

@app.route("/api/contracts")
def contracts():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM contracts
        WHERE user_id=?
        ORDER BY id DESC
    """, (uid,)).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "contracts": [dict(x) for x in rows]
    })


@app.route("/api/contracts/complete", methods=["POST"])
def contract_complete():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    contract_id = int(data.get("id", 0))

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    contract = conn.execute("""
        SELECT *
        FROM contracts
        WHERE id=? AND user_id=?
    """, (contract_id, uid)).fetchone()

    if not contract or contract["completed"]:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Контракт недоступен"
        }), 400

    current = resource(conn, uid, contract["item"])

    if current < contract["required"]:
        conn.close()

        return jsonify({
            "ok": False,
            "error": f"Нужно ещё {contract['required'] - current}"
        }), 400

    remove_resource(
        conn,
        uid,
        contract["item"],
        contract["required"]
    )

    add_balance(conn, uid, contract["reward"])
    add_xp(conn, uid, contract["reward"] // 10)

    conn.execute("""
        UPDATE contracts
        SET completed=1,
            progress=?
        WHERE id=?
    """, (
        contract["required"],
        contract_id
    ))

    conn.commit()

    result = safe_user_payload(conn, uid)
    conn.close()

    return jsonify({
        "ok": True,
        "reward": contract["reward"],
        "user": result
    })


# =========================================================
# PREFIXES
# =========================================================

PREFIXES = {
    "Новичок": 0,
    "Работяга": 1000,
    "Шахтёр": 5000,
    "Предприниматель": 15000,
    "Промышленник": 50000,
    "Магнат": 150000,
    "Миллиардер": 1000000,
    "Император": 5000000
}


@app.route("/api/prefixes")
def prefixes():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    owned = conn.execute("""
        SELECT prefix
        FROM prefixes
        WHERE user_id=?
    """, (uid,)).fetchall()

    equipped = conn.execute("""
        SELECT prefix
        FROM equipped_prefix
        WHERE user_id=?
    """, (uid,)).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "catalog": PREFIXES,
        "owned": [x["prefix"] for x in owned],
        "equipped": equipped["prefix"] if equipped else ""
    })


@app.route("/api/prefixes/buy", methods=["POST"])
def buy_prefix():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    prefix = data.get("prefix")

    if prefix not in PREFIXES:
        return jsonify({
            "ok": False,
            "error": "Префикс не найден"
        }), 400

    if prefix == "Новичок":
        price = 0
    else:
        price = PREFIXES[prefix]

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    exists = conn.execute("""
        SELECT 1
        FROM prefixes
        WHERE user_id=? AND prefix=?
    """, (uid, prefix)).fetchone()

    if exists:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Префикс уже куплен"
        }), 400

    u = get_user(conn, uid)

    if u["balance"] < price:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (price, uid))

    conn.execute("""
        INSERT INTO prefixes(user_id, prefix)
        VALUES (?, ?)
    """, (uid, prefix))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/prefixes/equip", methods=["POST"])
def equip_prefix():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    prefix = data.get("prefix")

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    exists = conn.execute("""
        SELECT 1
        FROM prefixes
        WHERE user_id=? AND prefix=?
    """, (uid, prefix)).fetchone()

    if not exists:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Префикс не принадлежит игроку"
        }), 400

    conn.execute("""
        INSERT OR REPLACE INTO equipped_prefix(user_id, prefix)
        VALUES (?, ?)
    """, (uid, prefix))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================================================
# RATING
# =========================================================

@app.route("/api/leaderboard")
def leaderboard():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)

    conn = db()

    rows = conn.execute("""
        SELECT
            id,
            first_name,
            username,
            photo_url,
            level,
            balance,
            rating,
            population
        FROM users
        ORDER BY
            rating DESC,
            balance DESC
        LIMIT 100
    """).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "players": [dict(x) for x in rows]
    })


# =========================================================
# CORPORATIONS
# =========================================================

@app.route("/api/corporation")
def corporation():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    corp = conn.execute("""
        SELECT c.*
        FROM corporations c
        JOIN corporation_members cm
          ON cm.corporation_id=c.id
        WHERE cm.user_id=?
        LIMIT 1
    """, (uid,)).fetchone()

    members = []

    if corp:
        members = conn.execute("""
            SELECT u.id, u.first_name, u.username, u.level, u.balance
            FROM users u
            JOIN corporation_members cm
              ON cm.user_id=u.id
            WHERE cm.corporation_id=?
            ORDER BY u.level DESC
        """, (corp["id"],)).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "corporation": dict(corp) if corp else None,
        "members": [dict(x) for x in members]
    })


@app.route("/api/corporation/create", methods=["POST"])
def corporation_create():
    tg, err, status = require_user()

    if err:
        return err, status

    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()

    if len(name) < 3 or len(name) > 32:
        return jsonify({
            "ok": False,
            "error": "Название: от 3 до 32 символов"
        }), 400

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    existing = conn.execute("""
        SELECT c.id
        FROM corporations c
        JOIN corporation_members cm
          ON cm.corporation_id=c.id
        WHERE cm.user_id=?
    """, (uid,)).fetchone()

    if existing:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Вы уже состоите в корпорации"
        }), 400

    u = get_user(conn, uid)

    price = 100000

    if u["balance"] < price:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "Нужно 100 000 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET balance=balance-?
        WHERE id=?
    """, (price, uid))

    cursor = conn.execute("""
        INSERT INTO corporations
        (owner_id, name, level, capital)
        VALUES (?, ?, 1, ?)
    """, (uid, name, price))

    corp_id = cursor.lastrowid

    conn.execute("""
        INSERT INTO corporation_members
        (corporation_id, user_id)
        VALUES (?, ?)
    """, (corp_id, uid))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================================================
# ACHIEVEMENTS
# =========================================================

@app.route("/api/achievements")
def achievements():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    ensure_user(tg)
    uid = int(tg["id"])

    conn = db()

    u = get_user(conn, uid)

    achievements_list = [
        {
            "id": "level10",
            "name": "⭐ Развитие",
            "description": "Достичь 10 уровня",
            "done": u["level"] >= 10
        },
        {
            "id": "money100k",
            "name": "💎 Капитал",
            "description": "Накопить 100 000 💎",
            "done": u["balance"] >= 100000
        },
        {
            "id": "business5",
            "name": "🏭 Промышленник",
            "description": "Владеть 5 предприятиями",
            "done": u["id"] is not None and
                    conn.execute(
                        "SELECT COUNT(*) c FROM businesses WHERE user_id=?",
                        (uid,)
                    ).fetchone()["c"] >= 5
        },
        {
            "id": "population10k",
            "name": "👥 Город",
            "description": "Население 10 000",
            "done": u["population"] >= 10000
        }
    ]

    conn.close()

    return jsonify({
        "ok": True,
        "achievements": achievements_list
    })


# =========================================================
# ADMIN / CREATOR
# =========================================================

@app.route("/api/creator")
def creator():
    tg = current_user()

    if not tg:
        return jsonify({"ok": False}), 401

    uid = int(tg["id"])

    if uid != CREATOR_ID:
        return jsonify({
            "ok": False,
            "error": "Доступ запрещён"
        }), 403

    conn = db()

    users = conn.execute(
        "SELECT COUNT(*) c FROM users"
    ).fetchone()["c"]

    market = conn.execute(
        "SELECT COUNT(*) c FROM market"
    ).fetchone()["c"]

    businesses = conn.execute(
        "SELECT COUNT(*) c FROM businesses"
    ).fetchone()["c"]

    conn.close()

    return jsonify({
        "ok": True,
        "statistics": {
            "players": users,
            "market_listings": market,
            "businesses": businesses
        }
    })


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "game": "NEXORA"
    })


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
