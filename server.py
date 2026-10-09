import os
import time
import json
import hmac
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from urllib.parse import parse_qsl
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

app = Flask(__name__, static_folder="web", static_url_path="")
app.config["JSON_AS_ASCII"] = False

DB_PATH = os.getenv("DB_PATH", "nomer_fixed.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
CREATOR_TELEGRAM_ID = int(os.getenv("CREATOR_TELEGRAM_ID", "8518976778"))

SPIN_COST = max(1, int(os.getenv("SPIN_COST", "250")))
DAILY_SPIN_LIMIT = 20
RESCUE_BONUS = 1500
MARKET_FEE_PERCENT = 5
MAX_ACTIVE_LISTINGS = 3

LETTERS = "ABEKMHOPCTYX"
REGIONS = [
    "01", "02", "05", "07", "16", "50",
    "77", "78", "95", "99", "116", "177", "777"
]

RARITIES = [
    ("Обычный", 600),
    ("Необычный", 250),
    ("Редкий", 100),
    ("Эпический", 40),
    ("Легендарный", 9),
    ("Мифический", 1),
]
RARITY_ORDER = {
    "Обычный": 0,
    "Необычный": 1,
    "Редкий": 2,
    "Эпический": 3,
    "Легендарный": 4,
    "Мифический": 5,
}

CAR_CATALOG = [
    {"key": "lada_2107", "name": "LADA 2107", "price": 2500, "icon": "🚘"},
    {"key": "bmw_e34", "name": "BMW E34", "price": 8000, "icon": "🚙"},
    {"key": "mercedes_w124", "name": "Mercedes-Benz W124", "price": 12000, "icon": "🚗"},
    {"key": "skyline_r34", "name": "Nissan Skyline R34", "price": 30000, "icon": "🏎️"},
    {"key": "supra_a80", "name": "Toyota Supra A80", "price": 35000, "icon": "🏁"},
]
CAR_BY_KEY = {x["key"]: x for x in CAR_CATALOG}

TASKS = [
    {"key": "spin_3", "title": "Сгенерируй 3 номера", "stat": "spins", "target": 3, "reward_nc": 350, "reward_xp": 30},
    {"key": "spin_10", "title": "Сгенерируй 10 номеров", "stat": "spins", "target": 10, "reward_nc": 800, "reward_xp": 80},
    {"key": "list_1", "title": "Выставь номер на маркет", "stat": "listings", "target": 1, "reward_nc": 300, "reward_xp": 35},
    {"key": "buy_1", "title": "Купи номер на маркете", "stat": "buys", "target": 1, "reward_nc": 500, "reward_xp": 50},
    {"key": "rare_1", "title": "Найди редкий номер или лучше", "stat": "rare_found", "target": 1, "reward_nc": 700, "reward_xp": 70},
]
TASK_BY_KEY = {x["key"]: x for x in TASKS}

ACHIEVEMENTS = [
    {"key": "first_plate", "title": "Первый номер", "target": 1, "field": "collection"},
    {"key": "collector_10", "title": "Коллекционер", "target": 10, "field": "collection"},
    {"key": "collector_50", "title": "Большой гараж", "target": 50, "field": "collection"},
    {"key": "level_10", "title": "Уровень 10", "target": 10, "field": "level"},
    {"key": "level_25", "title": "Уровень 25", "target": 25, "field": "level"},
]


def db():
    con = sqlite3.connect(DB_PATH, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=20000")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def table_columns(con, table):
    return {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_column(con, table, column, ddl):
    if column not in table_columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            balance INTEGER NOT NULL DEFAULT 10000,
            xp INTEGER NOT NULL DEFAULT 0,
            spins_day TEXT NOT NULL DEFAULT '',
            spins_used INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            rescue_claimed INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS plates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            rarity TEXT NOT NULL,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS listings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_id INTEGER NOT NULL UNIQUE REFERENCES plates(id),
            seller_id INTEGER NOT NULL REFERENCES users(id),
            price INTEGER NOT NULL CHECK(price > 0),
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS trades(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            price INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_stats(
            user_id INTEGER NOT NULL,
            day TEXT NOT NULL,
            spins INTEGER NOT NULL DEFAULT 0,
            listings INTEGER NOT NULL DEFAULT 0,
            buys INTEGER NOT NULL DEFAULT 0,
            sales INTEGER NOT NULL DEFAULT 0,
            rare_found INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, day)
        );

        CREATE TABLE IF NOT EXISTS task_claims(
            user_id INTEGER NOT NULL,
            task_key TEXT NOT NULL,
            day TEXT NOT NULL,
            claimed_at INTEGER NOT NULL,
            PRIMARY KEY(user_id, task_key, day)
        );

        CREATE TABLE IF NOT EXISTS cars(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            car_key TEXT NOT NULL,
            plate_id INTEGER DEFAULT NULL REFERENCES plates(id),
            purchased_at INTEGER NOT NULL,
            UNIQUE(user_id, car_key)
        );

        CREATE TABLE IF NOT EXISTS auctions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_id INTEGER NOT NULL UNIQUE REFERENCES plates(id),
            seller_id INTEGER NOT NULL REFERENCES users(id),
            start_price INTEGER NOT NULL,
            current_price INTEGER NOT NULL,
            bidder_id INTEGER DEFAULT NULL REFERENCES users(id),
            ends_at INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clubs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS club_members(
            club_id INTEGER NOT NULL REFERENCES clubs(id),
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
            role TEXT NOT NULL DEFAULT 'member',
            joined_at INTEGER NOT NULL,
            PRIMARY KEY(club_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS admin_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            created_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_plates_owner ON plates(owner_id);
        CREATE INDEX IF NOT EXISTS idx_listings_seller ON listings(seller_id);
        CREATE INDEX IF NOT EXISTS idx_auctions_status_end ON auctions(status, ends_at);
        """)

        # Миграции для старой nomer_fixed.db — коллекция не удаляется.
        ensure_column(con, "users", "rescue_claimed", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(con, "users", "xp", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(con, "users", "spins_day", "TEXT NOT NULL DEFAULT ''")
        ensure_column(con, "users", "spins_used", "INTEGER NOT NULL DEFAULT 0")


def utc_day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def level_for_xp(xp):
    return min(100, 1 + max(0, int(xp)) // 250)


def tg_user(raw):
    if DEMO_MODE and not raw:
        return {"id": 10001, "first_name": "Demo Player", "username": "demo"}
    if not BOT_TOKEN or not raw:
        return None
    try:
        data = dict(parse_qsl(raw, keep_blank_values=True))
        received_hash = data.pop("hash", "")
        auth_date = int(data["auth_date"])
        now = int(time.time())
        if not received_hash or now - auth_date > 86400 or auth_date > now + 300:
            return None

        check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            return None

        user = json.loads(data["user"])
        return user if type(user.get("id")) is int else None
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = tg_user(request.headers.get("X-Telegram-Init-Data", ""))
        if not user:
            return jsonify(error="Нет авторизации Telegram. Открой Mini App через бота и проверь BOT_TOKEN в Render."), 401

        uid = int(user["id"])
        name = str(user.get("first_name") or "Игрок")[:80]
        username = str(user.get("username") or "")[:80]
        now = int(time.time())

        with db() as con:
            con.execute(
                "INSERT OR IGNORE INTO users(id,name,username,created_at) VALUES(?,?,?,?)",
                (uid, name, username, now),
            )
            con.execute("UPDATE users SET name=?, username=? WHERE id=?", (name, username, uid))

        return fn(uid, *args, **kwargs)
    return wrapped


def creator_only(fn):
    @wraps(fn)
    def wrapped(uid, *args, **kwargs):
        if int(uid) != CREATOR_TELEGRAM_ID:
            return jsonify(error="Нет доступа к админ-панели"), 403
        return fn(uid, *args, **kwargs)
    return wrapped


def payload():
    obj = request.get_json(silent=True)
    return obj if isinstance(obj, dict) else {}


def as_int(obj, *keys, default=None):
    for key in keys:
        if key in obj:
            value = obj.get(key)
            if isinstance(value, bool):
                raise ValueError()
            return int(value)
    if default is not None:
        return int(default)
    raise ValueError()


def generate_plate():
    rng = secrets.SystemRandom()
    rarity = rng.choices([x[0] for x in RARITIES], weights=[x[1] for x in RARITIES])[0]
    a, b, c = (secrets.choice(LETTERS) for _ in range(3))

    if rarity == "Обычный":
        digits = f"{secrets.randbelow(900) + 100:03}"
    elif rarity == "Необычный":
        x = secrets.choice("123456789")
        digits = x + secrets.choice("0123456789") + x
    elif rarity == "Редкий":
        digits = secrets.choice("123456789") * 3
    elif rarity == "Эпический":
        b = c = a
        digits = "00" + secrets.choice("123456789")
    elif rarity == "Легендарный":
        b = c = a
        digits = secrets.choice("123456789") * 3
    else:
        b = c = a
        digits = "777"

    return f"{a}{digits}{b}{c} {secrets.choice(REGIONS)}", rarity


def touch_daily_stats(con, uid):
    today = utc_day()
    con.execute("INSERT OR IGNORE INTO daily_stats(user_id,day) VALUES(?,?)", (uid, today))
    return today


def add_stat(con, uid, field, amount=1):
    allowed = {"spins", "listings", "buys", "sales", "rare_found"}
    if field not in allowed:
        return
    today = touch_daily_stats(con, uid)
    con.execute(f"UPDATE daily_stats SET {field}={field}+? WHERE user_id=? AND day=?", (amount, uid, today))


def maybe_rescue_bonus(con, uid):
    """Одноразовые 1500 NC, если денег на генерацию уже нет и нет редкого+ номера."""
    user = con.execute("SELECT balance,rescue_claimed FROM users WHERE id=?", (uid,)).fetchone()
    if not user or user["rescue_claimed"]:
        return 0
    if int(user["balance"]) >= SPIN_COST:
        return 0

    good = con.execute(
        "SELECT 1 FROM plates WHERE owner_id=? AND rarity IN ('Редкий','Эпический','Легендарный','Мифический') LIMIT 1",
        (uid,),
    ).fetchone()
    if good:
        return 0

    con.execute(
        "UPDATE users SET balance=balance+?, rescue_claimed=1 WHERE id=?",
        (RESCUE_BONUS, uid),
    )
    return RESCUE_BONUS


def user_json(con, uid):
    rescue = maybe_rescue_bonus(con, uid)
    user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    collection = con.execute("SELECT COUNT(*) FROM plates WHERE owner_id=?", (uid,)).fetchone()[0]
    used = user["spins_used"] if user["spins_day"] == utc_day() else 0
    xp = int(user["xp"])
    return {
        "id": uid,
        "name": user["name"],
        "username": user["username"],
        "balance": int(user["balance"]),
        "xp": xp,
        "level": level_for_xp(xp),
        "collection": int(collection),
        "spins_left": max(0, DAILY_SPIN_LIMIT - int(used)),
        "spin_cost": SPIN_COST,
        "rescue_bonus": rescue,
        "creator": uid == CREATOR_TELEGRAM_ID,
        "demo": DEMO_MODE,
    }


def settle_auctions(con):
    now = int(time.time())
    expired = con.execute(
        "SELECT * FROM auctions WHERE status='active' AND ends_at<=?",
        (now,),
    ).fetchall()

    for auction in expired:
        if auction["bidder_id"] is not None:
            plate = con.execute(
                "SELECT owner_id FROM plates WHERE id=?",
                (auction["plate_id"],),
            ).fetchone()
            if plate and plate["owner_id"] == auction["seller_id"]:
                con.execute("DELETE FROM listings WHERE plate_id=?", (auction["plate_id"],))
                con.execute("UPDATE cars SET plate_id=NULL WHERE plate_id=?", (auction["plate_id"],))
                con.execute(
                    "UPDATE plates SET owner_id=? WHERE id=?",
                    (auction["bidder_id"], auction["plate_id"]),
                )
                fee = (int(auction["current_price"]) * MARKET_FEE_PERCENT + 99) // 100
                con.execute(
                    "UPDATE users SET balance=balance+? WHERE id=?",
                    (int(auction["current_price"]) - fee, auction["seller_id"]),
                )
                con.execute(
                    "INSERT INTO trades(plate_id,seller_id,buyer_id,price,created_at) VALUES(?,?,?,?,?)",
                    (auction["plate_id"], auction["seller_id"], auction["bidder_id"], auction["current_price"], now),
                )
        con.execute("UPDATE auctions SET status='finished' WHERE id=?", (auction["id"],))


@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/index.html")
def index_file():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/health")
def health():
    return jsonify(status="ok", db=DB_PATH, version="NOMER CLUB 4.1 FIXED")


@app.get("/api/me")
@auth
def me(uid):
    with db() as con:
        return jsonify(**user_json(con, uid))


@app.get("/api/bootstrap")
@auth
def bootstrap(uid):
    with db() as con:
        settle_auctions(con)
        return jsonify(
            user=user_json(con, uid),
            spin_cost=SPIN_COST,
            daily_spin_limit=DAILY_SPIN_LIMIT,
            creator=uid == CREATOR_TELEGRAM_ID,
        )


@app.post("/api/spin")
@auth
def spin(uid):
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        rescue = maybe_rescue_bonus(con, uid)
        user = con.execute("SELECT balance,spins_day,spins_used FROM users WHERE id=?", (uid,)).fetchone()
        used = int(user["spins_used"]) if user["spins_day"] == utc_day() else 0

        if used >= DAILY_SPIN_LIMIT:
            return jsonify(error="Сегодня попытки закончились"), 400
        if int(user["balance"]) < SPIN_COST:
            return jsonify(error=f"Недостаточно NC. Одна генерация стоит {SPIN_COST} NC"), 400

        plate = None
        for _ in range(200):
            code, rarity = generate_plate()
            try:
                cur = con.execute(
                    "INSERT INTO plates(code,rarity,owner_id,created_at) VALUES(?,?,?,?)",
                    (code, rarity, uid, int(time.time())),
                )
                plate = {"id": cur.lastrowid, "code": code, "rarity": rarity}
                break
            except sqlite3.IntegrityError:
                continue

        if plate is None:
            return jsonify(error="Свободная комбинация не найдена, попробуй ещё раз"), 503

        con.execute(
            "UPDATE users SET balance=balance-?, spins_day=?, spins_used=?, xp=xp+10 WHERE id=?",
            (SPIN_COST, utc_day(), used + 1, uid),
        )
        add_stat(con, uid, "spins", 1)
        if RARITY_ORDER.get(plate["rarity"], 0) >= RARITY_ORDER["Редкий"]:
            add_stat(con, uid, "rare_found", 1)

        new_user = user_json(con, uid)
        return jsonify(
            ok=True,
            plate=plate,
            balance=new_user["balance"],
            spins_left=new_user["spins_left"],
            spin_cost=SPIN_COST,
            rescue_bonus=rescue,
            user=new_user,
        )


@app.get("/api/collection")
@auth
def collection(uid):
    with db() as con:
        rows = con.execute("""
            SELECT p.id,p.code,p.rarity,p.created_at,
                   l.id AS listing_id,
                   a.id AS auction_id,
                   c.id AS installed_car_id,
                   c.car_key AS installed_car_key
            FROM plates p
            LEFT JOIN listings l ON l.plate_id=p.id
            LEFT JOIN auctions a ON a.plate_id=p.id AND a.status='active'
            LEFT JOIN cars c ON c.plate_id=p.id
            WHERE p.owner_id=?
            ORDER BY p.id DESC
            LIMIT 1000
        """, (uid,)).fetchall()
        return jsonify(plates=[dict(r) for r in rows])


@app.get("/api/plate-passport")
@auth
def plate_passport(uid):
    try:
        plate_id = int(request.args.get("plate_id", ""))
    except ValueError:
        return jsonify(error="Неверный ID номера"), 400

    with db() as con:
        row = con.execute("""
            SELECT p.id,p.code,p.rarity,p.owner_id,p.created_at,
                   u.name AS owner_name,u.username AS owner_username,
                   c.id AS car_id,c.car_key
            FROM plates p
            JOIN users u ON u.id=p.owner_id
            LEFT JOIN cars c ON c.plate_id=p.id
            WHERE p.id=?
        """, (plate_id,)).fetchone()
        if not row:
            return jsonify(error="Номер не найден"), 404
        data = dict(row)
        data["mine"] = data["owner_id"] == uid
        data["rarity_index"] = RARITY_ORDER.get(data["rarity"], 0)
        return jsonify(plate=data)


@app.post("/api/list")
@auth
def listing(uid):
    try:
        data = payload()
        plate_id = as_int(data, "plate_id", "id")
        price = as_int(data, "price")
    except (ValueError, TypeError):
        return jsonify(error="Некорректные данные"), 400

    if not 100 <= price <= 100_000_000:
        return jsonify(error="Цена: от 100 до 100 000 000 NC"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT COUNT(*) FROM listings WHERE seller_id=?", (uid,)).fetchone()[0] >= MAX_ACTIVE_LISTINGS:
            return jsonify(error=f"Можно выставить только {MAX_ACTIVE_LISTINGS} номера"), 400

        plate = con.execute("SELECT id FROM plates WHERE id=? AND owner_id=?", (plate_id, uid)).fetchone()
        if not plate:
            return jsonify(error="Номер тебе не принадлежит"), 404
        if con.execute("SELECT 1 FROM listings WHERE plate_id=?", (plate_id,)).fetchone():
            return jsonify(error="Номер уже выставлен"), 400
        if con.execute("SELECT 1 FROM auctions WHERE plate_id=? AND status='active'", (plate_id,)).fetchone():
            return jsonify(error="Номер сейчас на аукционе"), 400

        con.execute("UPDATE cars SET plate_id=NULL WHERE plate_id=?", (plate_id,))
        con.execute(
            "INSERT INTO listings(plate_id,seller_id,price,created_at) VALUES(?,?,?,?)",
            (plate_id, uid, price, int(time.time())),
        )
        add_stat(con, uid, "listings", 1)
        return jsonify(ok=True)


@app.get("/api/market")
@auth
def market(uid):
    with db() as con:
        rows = con.execute("""
            SELECT l.id,l.price,l.seller_id,p.id AS plate_id,p.code,p.rarity,
                   u.name AS seller,u.username AS seller_username
            FROM listings l
            JOIN plates p ON p.id=l.plate_id
            JOIN users u ON u.id=l.seller_id
            ORDER BY l.id DESC
            LIMIT 200
        """).fetchall()
        return jsonify(listings=[dict(r) for r in rows], fee_percent=MARKET_FEE_PERCENT)


@app.post("/api/cancel")
@auth
def cancel(uid):
    try:
        listing_id = as_int(payload(), "listing_id", "id")
    except (ValueError, TypeError):
        return jsonify(error="Неверный ID"), 400

    with db() as con:
        cur = con.execute("DELETE FROM listings WHERE id=? AND seller_id=?", (listing_id, uid))
        if cur.rowcount != 1:
            return jsonify(error="Объявление не найдено"), 404
        return jsonify(ok=True)


@app.post("/api/buy")
@auth
def buy(uid):
    try:
        listing_id = as_int(payload(), "listing_id", "id")
    except (ValueError, TypeError):
        return jsonify(error="Неверный ID"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        item = con.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
        if not item:
            return jsonify(error="Объявление уже закрыто"), 404
        if item["seller_id"] == uid:
            return jsonify(error="Нельзя купить свой номер"), 400

        buyer = con.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()
        plate = con.execute("SELECT owner_id FROM plates WHERE id=?", (item["plate_id"],)).fetchone()
        if not plate or plate["owner_id"] != item["seller_id"]:
            con.execute("DELETE FROM listings WHERE id=?", (listing_id,))
            return jsonify(error="Номер больше не принадлежит продавцу"), 409
        if int(buyer["balance"]) < int(item["price"]):
            return jsonify(error="Недостаточно NC"), 400

        price = int(item["price"])
        fee = (price * MARKET_FEE_PERCENT + 99) // 100
        con.execute("UPDATE users SET balance=balance-? WHERE id=?", (price, uid))
        con.execute("UPDATE users SET balance=balance+? WHERE id=?", (price - fee, item["seller_id"]))
        con.execute("UPDATE cars SET plate_id=NULL WHERE plate_id=?", (item["plate_id"],))
        con.execute("UPDATE plates SET owner_id=? WHERE id=?", (uid, item["plate_id"]))
        con.execute("DELETE FROM listings WHERE id=?", (listing_id,))
        con.execute(
            "INSERT INTO trades(plate_id,seller_id,buyer_id,price,created_at) VALUES(?,?,?,?,?)",
            (item["plate_id"], item["seller_id"], uid, price, int(time.time())),
        )
        add_stat(con, uid, "buys", 1)
        add_stat(con, item["seller_id"], "sales", 1)
        return jsonify(ok=True, fee=fee, user=user_json(con, uid))


@app.post("/api/sell-system")
@auth
def sell_system(uid):
    try:
        plate_id = as_int(payload(), "plate_id", "id")
    except (ValueError, TypeError):
        return jsonify(error="Неверный ID"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        plate = con.execute("SELECT rarity FROM plates WHERE id=? AND owner_id=?", (plate_id, uid)).fetchone()
        if not plate:
            return jsonify(error="Номер не найден"), 404
        if plate["rarity"] != "Обычный":
            return jsonify(error="Системе можно продать только обычный номер"), 400
        if con.execute("SELECT 1 FROM listings WHERE plate_id=?", (plate_id,)).fetchone():
            return jsonify(error="Сначала сними номер с маркета"), 400
        if con.execute("SELECT 1 FROM auctions WHERE plate_id=? AND status='active'", (plate_id,)).fetchone():
            return jsonify(error="Номер сейчас на аукционе"), 400

        con.execute("UPDATE cars SET plate_id=NULL WHERE plate_id=?", (plate_id,))
        con.execute("DELETE FROM plates WHERE id=?", (plate_id,))
        con.execute("UPDATE users SET balance=balance+25 WHERE id=?", (uid,))
        return jsonify(ok=True, reward=25, user=user_json(con, uid))


@app.get("/api/top")
@auth
def top(uid):
    with db() as con:
        rows = con.execute("""
            SELECT u.id,u.name,u.username,u.balance,u.xp,
                   COUNT(p.id) AS collection
            FROM users u
            LEFT JOIN plates p ON p.owner_id=u.id
            GROUP BY u.id
            ORDER BY collection DESC,u.balance DESC,u.xp DESC
            LIMIT 50
        """).fetchall()
        players = []
        for row in rows:
            item = dict(row)
            item["level"] = level_for_xp(item["xp"])
            item["creator"] = item["id"] == CREATOR_TELEGRAM_ID
            players.append(item)
        return jsonify(players=players)


# ------------------------- ЗАДАНИЯ -------------------------

def tasks_payload(con, uid):
    today = touch_daily_stats(con, uid)
    stats = con.execute("SELECT * FROM daily_stats WHERE user_id=? AND day=?", (uid, today)).fetchone()
    claimed = {
        r["task_key"] for r in con.execute(
            "SELECT task_key FROM task_claims WHERE user_id=? AND day=?",
            (uid, today),
        ).fetchall()
    }

    result = []
    for task in TASKS:
        progress = int(stats[task["stat"]]) if stats else 0
        complete = progress >= task["target"]
        result.append({
            "key": task["key"],
            "title": task["title"],
            "progress": min(progress, task["target"]),
            "target": task["target"],
            "reward_nc": task["reward_nc"],
            "reward_xp": task["reward_xp"],
            "completed": complete,
            "claimed": task["key"] in claimed,
        })
    return result


@app.get("/api/tasks")
@auth
def tasks(uid):
    # FIX: маршрут не зависит от старой отсутствующей таблицы quests,
    # поэтому на существующей БД больше не должен давать 500.
    with db() as con:
        return jsonify(tasks=tasks_payload(con, uid), reset_at="00:00 UTC")


@app.get("/api/quests")
@auth
def quests_alias(uid):
    with db() as con:
        data = tasks_payload(con, uid)
        return jsonify(tasks=data, quests=data, reset_at="00:00 UTC")


@app.post("/api/tasks/claim")
@auth
def claim_task(uid):
    data = payload()
    key = str(data.get("task_key") or data.get("key") or "")
    task = TASK_BY_KEY.get(key)
    if not task:
        return jsonify(error="Задание не найдено"), 404

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        today = touch_daily_stats(con, uid)
        stats = con.execute("SELECT * FROM daily_stats WHERE user_id=? AND day=?", (uid, today)).fetchone()
        if int(stats[task["stat"]]) < int(task["target"]):
            return jsonify(error="Задание ещё не выполнено"), 400
        if con.execute(
            "SELECT 1 FROM task_claims WHERE user_id=? AND task_key=? AND day=?",
            (uid, key, today),
        ).fetchone():
            return jsonify(error="Награда уже получена"), 400

        con.execute(
            "INSERT INTO task_claims(user_id,task_key,day,claimed_at) VALUES(?,?,?,?)",
            (uid, key, today, int(time.time())),
        )
        con.execute(
            "UPDATE users SET balance=balance+?, xp=xp+? WHERE id=?",
            (task["reward_nc"], task["reward_xp"], uid),
        )
        return jsonify(ok=True, reward_nc=task["reward_nc"], reward_xp=task["reward_xp"], user=user_json(con, uid))


@app.post("/api/quests/claim")
@auth
def claim_quest_alias(uid):
    return claim_task.__wrapped__(uid)


# ------------------------- ДОСТИЖЕНИЯ -------------------------

@app.get("/api/achievements")
@auth
def achievements(uid):
    with db() as con:
        user = user_json(con, uid)
        out = []
        for ach in ACHIEVEMENTS:
            value = int(user[ach["field"]])
            out.append({
                **ach,
                "progress": min(value, ach["target"]),
                "completed": value >= ach["target"],
            })
        return jsonify(achievements=out)


# ------------------------- ГАРАЖ / МАШИНЫ -------------------------

@app.get("/api/cars/catalog")
@auth
def cars_catalog(uid):
    return jsonify(cars=CAR_CATALOG)


@app.get("/api/cars")
@auth
def cars(uid):
    with db() as con:
        rows = con.execute("""
            SELECT c.id,c.car_key,c.plate_id,c.purchased_at,p.code AS plate_code,p.rarity AS plate_rarity
            FROM cars c
            LEFT JOIN plates p ON p.id=c.plate_id
            WHERE c.user_id=?
            ORDER BY c.id DESC
        """, (uid,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            catalog = CAR_BY_KEY.get(item["car_key"], {"name": item["car_key"], "icon": "🚗", "price": 0})
            item.update({"name": catalog["name"], "icon": catalog["icon"], "price": catalog["price"]})
            result.append(item)
        return jsonify(cars=result)


@app.post("/api/cars/buy")
@auth
def buy_car(uid):
    data = payload()
    key = str(data.get("car_key") or data.get("key") or "")
    car = CAR_BY_KEY.get(key)
    if not car:
        return jsonify(error="Машина не найдена"), 404

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM cars WHERE user_id=? AND car_key=?", (uid, key)).fetchone():
            return jsonify(error="Эта машина уже есть в гараже"), 400
        user = con.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()
        if int(user["balance"]) < car["price"]:
            return jsonify(error="Недостаточно NC"), 400

        con.execute("UPDATE users SET balance=balance-? WHERE id=?", (car["price"], uid))
        cur = con.execute(
            "INSERT INTO cars(user_id,car_key,purchased_at) VALUES(?,?,?)",
            (uid, key, int(time.time())),
        )
        return jsonify(ok=True, car_id=cur.lastrowid, user=user_json(con, uid))


@app.post("/api/cars/install")
@auth
def install_plate(uid):
    try:
        data = payload()
        car_id = as_int(data, "car_id")
        plate_id = as_int(data, "plate_id")
    except (ValueError, TypeError):
        return jsonify(error="Некорректные данные"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        car = con.execute("SELECT id FROM cars WHERE id=? AND user_id=?", (car_id, uid)).fetchone()
        plate = con.execute("SELECT id FROM plates WHERE id=? AND owner_id=?", (plate_id, uid)).fetchone()
        if not car or not plate:
            return jsonify(error="Машина или номер не найден"), 404
        if con.execute("SELECT 1 FROM listings WHERE plate_id=?", (plate_id,)).fetchone():
            return jsonify(error="Номер выставлен на маркет"), 400
        if con.execute("SELECT 1 FROM auctions WHERE plate_id=? AND status='active'", (plate_id,)).fetchone():
            return jsonify(error="Номер находится на аукционе"), 400

        con.execute("UPDATE cars SET plate_id=NULL WHERE user_id=? AND plate_id=?", (uid, plate_id))
        con.execute("UPDATE cars SET plate_id=? WHERE id=? AND user_id=?", (plate_id, car_id, uid))
        return jsonify(ok=True)


@app.post("/api/cars/remove-plate")
@auth
def remove_plate(uid):
    try:
        car_id = as_int(payload(), "car_id", "id")
    except (ValueError, TypeError):
        return jsonify(error="Неверный ID"), 400
    with db() as con:
        cur = con.execute("UPDATE cars SET plate_id=NULL WHERE id=? AND user_id=?", (car_id, uid))
        if cur.rowcount != 1:
            return jsonify(error="Машина не найдена"), 404
        return jsonify(ok=True)


# ------------------------- АУКЦИОНЫ -------------------------

@app.get("/api/auctions")
@auth
def auctions(uid):
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        settle_auctions(con)
        rows = con.execute("""
            SELECT a.id,a.plate_id,a.seller_id,a.start_price,a.current_price,a.bidder_id,a.ends_at,
                   p.code,p.rarity,u.name AS seller
            FROM auctions a
            JOIN plates p ON p.id=a.plate_id
            JOIN users u ON u.id=a.seller_id
            WHERE a.status='active'
            ORDER BY a.ends_at ASC
            LIMIT 100
        """).fetchall()
        return jsonify(auctions=[dict(r) for r in rows], now=int(time.time()))


@app.post("/api/auctions/create")
@auth
def create_auction(uid):
    try:
        data = payload()
        plate_id = as_int(data, "plate_id")
        start_price = as_int(data, "start_price", "price")
        duration = as_int(data, "duration", "duration_seconds", default=3600)
    except (ValueError, TypeError):
        return jsonify(error="Некорректные данные"), 400

    duration = max(300, min(duration, 86400))
    if not 100 <= start_price <= 100_000_000:
        return jsonify(error="Стартовая цена: от 100 до 100 000 000 NC"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if not con.execute("SELECT 1 FROM plates WHERE id=? AND owner_id=?", (plate_id, uid)).fetchone():
            return jsonify(error="Номер тебе не принадлежит"), 404
        if con.execute("SELECT 1 FROM listings WHERE plate_id=?", (plate_id,)).fetchone():
            return jsonify(error="Сначала сними номер с маркета"), 400
        if con.execute("SELECT 1 FROM auctions WHERE plate_id=? AND status='active'", (plate_id,)).fetchone():
            return jsonify(error="Номер уже на аукционе"), 400

        con.execute("UPDATE cars SET plate_id=NULL WHERE plate_id=?", (plate_id,))
        cur = con.execute("""
            INSERT INTO auctions(plate_id,seller_id,start_price,current_price,ends_at,status,created_at)
            VALUES(?,?,?,?,?,'active',?)
        """, (plate_id, uid, start_price, start_price, int(time.time()) + duration, int(time.time())))
        return jsonify(ok=True, auction_id=cur.lastrowid)


@app.post("/api/auctions/bid")
@auth
def bid_auction(uid):
    try:
        data = payload()
        auction_id = as_int(data, "auction_id", "id")
        amount = as_int(data, "amount", "bid")
    except (ValueError, TypeError):
        return jsonify(error="Некорректная ставка"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        settle_auctions(con)
        auction = con.execute("SELECT * FROM auctions WHERE id=? AND status='active'", (auction_id,)).fetchone()
        if not auction:
            return jsonify(error="Аукцион завершён"), 404
        if auction["seller_id"] == uid:
            return jsonify(error="Нельзя ставить на свой номер"), 400

        minimum = int(auction["current_price"]) + max(10, int(auction["current_price"]) // 20)
        if amount < minimum:
            return jsonify(error=f"Минимальная ставка: {minimum} NC"), 400

        user = con.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()
        if int(user["balance"]) < amount:
            return jsonify(error="Недостаточно NC"), 400

        con.execute("UPDATE users SET balance=balance-? WHERE id=?", (amount, uid))
        if auction["bidder_id"] is not None:
            con.execute(
                "UPDATE users SET balance=balance+? WHERE id=?",
                (auction["current_price"], auction["bidder_id"]),
            )
        con.execute(
            "UPDATE auctions SET current_price=?, bidder_id=? WHERE id=?",
            (amount, uid, auction_id),
        )
        return jsonify(ok=True, current_price=amount, user=user_json(con, uid))


@app.post("/api/auctions/cancel")
@auth
def cancel_auction(uid):
    try:
        auction_id = as_int(payload(), "auction_id", "id")
    except (ValueError, TypeError):
        return jsonify(error="Неверный ID"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        auction = con.execute("SELECT * FROM auctions WHERE id=? AND seller_id=? AND status='active'", (auction_id, uid)).fetchone()
        if not auction:
            return jsonify(error="Аукцион не найден"), 404
        if auction["bidder_id"] is not None:
            return jsonify(error="Нельзя отменить аукцион после первой ставки"), 400
        con.execute("UPDATE auctions SET status='cancelled' WHERE id=?", (auction_id,))
        return jsonify(ok=True)


# ------------------------- КЛУБЫ -------------------------

@app.get("/api/clubs")
@auth
def clubs(uid):
    with db() as con:
        mine = con.execute("""
            SELECT c.id,c.name,c.owner_id,m.role,
                   (SELECT COUNT(*) FROM club_members mm WHERE mm.club_id=c.id) AS members
            FROM club_members m
            JOIN clubs c ON c.id=m.club_id
            WHERE m.user_id=?
        """, (uid,)).fetchone()

        rows = con.execute("""
            SELECT c.id,c.name,c.owner_id,u.name AS owner,
                   COUNT(m.user_id) AS members
            FROM clubs c
            JOIN users u ON u.id=c.owner_id
            LEFT JOIN club_members m ON m.club_id=c.id
            GROUP BY c.id
            ORDER BY members DESC,c.id ASC
            LIMIT 50
        """).fetchall()
        return jsonify(my_club=dict(mine) if mine else None, clubs=[dict(r) for r in rows])


@app.post("/api/clubs/create")
@auth
def create_club(uid):
    name = str(payload().get("name") or "").strip()
    if not 3 <= len(name) <= 24:
        return jsonify(error="Название клуба: 3–24 символа"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM club_members WHERE user_id=?", (uid,)).fetchone():
            return jsonify(error="Сначала выйди из текущего клуба"), 400
        try:
            cur = con.execute("INSERT INTO clubs(name,owner_id,created_at) VALUES(?,?,?)", (name, uid, int(time.time())))
        except sqlite3.IntegrityError:
            return jsonify(error="Клуб с таким названием уже есть"), 400
        con.execute(
            "INSERT INTO club_members(club_id,user_id,role,joined_at) VALUES(?,?,?,?)",
            (cur.lastrowid, uid, "owner", int(time.time())),
        )
        return jsonify(ok=True, club_id=cur.lastrowid)


@app.post("/api/clubs/join")
@auth
def join_club(uid):
    try:
        club_id = as_int(payload(), "club_id", "id")
    except (ValueError, TypeError):
        return jsonify(error="Неверный ID клуба"), 400

    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM club_members WHERE user_id=?", (uid,)).fetchone():
            return jsonify(error="Ты уже состоишь в клубе"), 400
        if not con.execute("SELECT 1 FROM clubs WHERE id=?", (club_id,)).fetchone():
            return jsonify(error="Клуб не найден"), 404
        con.execute(
            "INSERT INTO club_members(club_id,user_id,role,joined_at) VALUES(?,?,?,?)",
            (club_id, uid, "member", int(time.time())),
        )
        return jsonify(ok=True)


@app.post("/api/clubs/leave")
@auth
def leave_club(uid):
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        member = con.execute("SELECT club_id,role FROM club_members WHERE user_id=?", (uid,)).fetchone()
        if not member:
            return jsonify(error="Ты не состоишь в клубе"), 400
        if member["role"] == "owner":
            count = con.execute("SELECT COUNT(*) FROM club_members WHERE club_id=?", (member["club_id"],)).fetchone()[0]
            if count > 1:
                return jsonify(error="Владелец не может выйти, пока в клубе есть другие участники"), 400
            con.execute("DELETE FROM club_members WHERE club_id=?", (member["club_id"],))
            con.execute("DELETE FROM clubs WHERE id=?", (member["club_id"],))
        else:
            con.execute("DELETE FROM club_members WHERE user_id=?", (uid,))
        return jsonify(ok=True)


# ------------------------- АДМИН-ПАНЕЛЬ -------------------------

@app.get("/api/admin/players")
@auth
@creator_only
def admin_players(uid):
    query = str(request.args.get("q") or "").strip().lower()
    with db() as con:
        params = []
        where = ""
        if query:
            where = "WHERE CAST(u.id AS TEXT) LIKE ? OR LOWER(u.name) LIKE ? OR LOWER(u.username) LIKE ?"
            like = f"%{query}%"
            params = [like, like, like]

        rows = con.execute(f"""
            SELECT u.id,u.name,u.username,u.balance,u.xp,
                   COUNT(p.id) AS collection
            FROM users u
            LEFT JOIN plates p ON p.owner_id=u.id
            {where}
            GROUP BY u.id
            ORDER BY u.id DESC
            LIMIT 200
        """, params).fetchall()

        players = []
        for row in rows:
            item = dict(row)
            item["level"] = level_for_xp(item["xp"])
            item["creator"] = item["id"] == CREATOR_TELEGRAM_ID
            players.append(item)
        return jsonify(players=players)


@app.post("/api/admin/grant")
@auth
@creator_only
def admin_grant(uid):
    data = payload()
    try:
        target_id = as_int(data, "user_id", "target_id", "id")
    except (ValueError, TypeError):
        return jsonify(error="Не выбран игрок"), 400

    nc = 0
    xp = 0
    try:
        for key in ("nc", "balance", "coins", "money"):
            if key in data:
                nc = int(data[key])
                break
        if "xp" in data:
            xp = int(data["xp"])

        if "amount" in data and not any(k in data for k in ("nc", "balance", "coins", "money", "xp")):
            amount = int(data["amount"])
            kind = str(data.get("type") or data.get("kind") or "nc").lower()
            if kind in ("xp", "experience"):
                xp = amount
            else:
                nc = amount
    except (ValueError, TypeError):
        return jsonify(error="Некорректная сумма"), 400

    if nc == 0 and xp == 0:
        return jsonify(error="Укажи NC или XP"), 400
    if abs(nc) > 100_000_000 or abs(xp) > 10_000_000:
        return jsonify(error="Слишком большое значение"), 400

    reason = str(data.get("reason") or "Админ-панель")[:200]
    with db() as con:
        con.execute("BEGIN IMMEDIATE")
        target = con.execute("SELECT id,balance,xp FROM users WHERE id=?", (target_id,)).fetchone()
        if not target:
            return jsonify(error="Игрок не найден"), 404
        if int(target["balance"]) + nc < 0 or int(target["xp"]) + xp < 0:
            return jsonify(error="Значение не может стать отрицательным"), 400

        con.execute("UPDATE users SET balance=balance+?, xp=xp+? WHERE id=?", (nc, xp, target_id))
        if nc:
            con.execute(
                "INSERT INTO admin_logs(admin_id,target_id,action,amount,reason,created_at) VALUES(?,?,?,?,?,?)",
                (uid, target_id, "nc", nc, reason, int(time.time())),
            )
        if xp:
            con.execute(
                "INSERT INTO admin_logs(admin_id,target_id,action,amount,reason,created_at) VALUES(?,?,?,?,?,?)",
                (uid, target_id, "xp", xp, reason, int(time.time())),
            )
        return jsonify(ok=True, target=user_json(con, target_id))


@app.post("/api/admin/set-balance")
@auth
@creator_only
def admin_set_balance(uid):
    data = payload()
    try:
        target_id = as_int(data, "user_id", "target_id", "id")
        balance = as_int(data, "balance", "nc")
    except (ValueError, TypeError):
        return jsonify(error="Некорректные данные"), 400
    if balance < 0 or balance > 100_000_000:
        return jsonify(error="Баланс вне допустимого диапазона"), 400

    with db() as con:
        cur = con.execute("UPDATE users SET balance=? WHERE id=?", (balance, target_id))
        if cur.rowcount != 1:
            return jsonify(error="Игрок не найден"), 404
        con.execute(
            "INSERT INTO admin_logs(admin_id,target_id,action,amount,reason,created_at) VALUES(?,?,?,?,?,?)",
            (uid, target_id, "set_balance", balance, "Установка баланса", int(time.time())),
        )
        return jsonify(ok=True, target=user_json(con, target_id))


@app.get("/api/admin/logs")
@auth
@creator_only
def admin_logs(uid):
    with db() as con:
        rows = con.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 100").fetchall()
        return jsonify(logs=[dict(r) for r in rows])


@app.errorhandler(sqlite3.Error)
def sqlite_error(error):
    # Не отдаём HTML-страницу 500 фронтенду — UI всегда получит JSON.
    app.logger.exception("SQLite error: %s", error)
    return jsonify(error="Ошибка базы данных. Обнови Mini App и попробуй ещё раз."), 500


@app.errorhandler(Exception)
def unhandled_error(error):
    if isinstance(error, HTTPException):
        return jsonify(error=error.description), error.code
    app.logger.exception("Unhandled error: %s", error)
    return jsonify(error="Внутренняя ошибка сервера"), 500


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
