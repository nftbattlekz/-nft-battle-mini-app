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

SPIN_COST = max(1, int(os.getenv("SPIN_COST", "100")))
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

SYSTEM_SELL_PRICES = {
    "Обычный": 35,
    "Необычный": 75,
    "Редкий": 220,
    "Эпический": 800,
    "Легендарный": 3500,
    "Мифический": 15000,
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

        CREATE TABLE IF NOT EXISTS spin_requests(
            request_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plate_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
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
        ensure_column(con, "users", "mythic_mode", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(con, "users", "mythic_queue", "INTEGER NOT NULL DEFAULT 0")


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


def generate_plate(force_rarity=None):
    rng = secrets.SystemRandom()
    valid_rarities = {x[0] for x in RARITIES}
    rarity = force_rarity if force_rarity in valid_rarities else rng.choices(
        [x[0] for x in RARITIES], weights=[x[1] for x in RARITIES]
    )[0]
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
        digits = secrets.choice(("001", "007", "111", "222", "333", "444", "555", "666", "777", "888", "999"))

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
        "mythic_mode": bool(user["mythic_mode"]),
        "mythic_queue": int(user["mythic_queue"]),
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
    return jsonify(status="ok", db=DB_PATH, version="NOMER CLUB 5.0 REWORK")


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
    data = payload()
    request_id = str(data.get("request_id") or "").strip()[:80]

    with db() as con:
        con.execute("BEGIN IMMEDIATE")

        # Защита от повторного списания при повторе одного и того же запроса.
        if request_id:
            previous = con.execute(
                "SELECT plate_id FROM spin_requests WHERE request_id=? AND user_id=?",
                (request_id, uid),
            ).fetchone()
            if previous:
                row = con.execute(
                    "SELECT id,code,rarity FROM plates WHERE id=? AND owner_id=?",
                    (previous["plate_id"], uid),
                ).fetchone()
                if row:
                    plate = dict(row)
                    plate["sell_price"] = SYSTEM_SELL_PRICES.get(plate["rarity"], 0)
                    current_user = user_json(con, uid)
                    return jsonify(
                        ok=True, repeated=True, plate=plate,
                        balance=current_user["balance"],
                        spins_left=current_user["spins_left"],
                        spin_cost=SPIN_COST, user=current_user,
                    )

        rescue = maybe_rescue_bonus(con, uid)
        user = con.execute(
            "SELECT balance,spins_day,spins_used,mythic_mode,mythic_queue FROM users WHERE id=?",
            (uid,),
        ).fetchone()
        used = int(user["spins_used"]) if user["spins_day"] == utc_day() else 0

        if used >= DAILY_SPIN_LIMIT:
            return jsonify(error="Сегодня попытки закончились"), 400
        if int(user["balance"]) < SPIN_COST:
            return jsonify(error=f"Недостаточно NC. Одна генерация стоит {SPIN_COST} NC"), 400

        force_mythic = bool(user["mythic_mode"]) or int(user["mythic_queue"]) > 0
        forced_rarity = "Мифический" if force_mythic else None

        plate = None
        for _ in range(300):
            code, rarity = generate_plate(forced_rarity)
            try:
                cur = con.execute(
                    "INSERT INTO plates(code,rarity,owner_id,created_at) VALUES(?,?,?,?)",
                    (code, rarity, uid, int(time.time())),
                )
                plate = {
                    "id": cur.lastrowid,
                    "code": code,
                    "rarity": rarity,
                    "sell_price": SYSTEM_SELL_PRICES.get(rarity, 0),
                }
                break
            except sqlite3.IntegrityError:
                continue

        if plate is None:
            return jsonify(error="Свободная комбинация не найдена, попробуй ещё раз"), 503

        con.execute(
            "UPDATE users SET balance=balance-?, spins_day=?, spins_used=?, xp=xp+10 WHERE id=?",
            (SPIN_COST, utc_day(), used + 1, uid),
        )
        if not bool(user["mythic_mode"]) and int(user["mythic_queue"]) > 0:
            con.execute("UPDATE users SET mythic_queue=mythic_queue-1 WHERE id=?", (uid,))

        if request_id:
            con.execute(
                "INSERT OR IGNORE INTO spin_requests(request_id,user_id,plate_id,created_at) VALUES(?,?,?,?)",
                (request_id, uid, plate["id"], int(time.time())),
            )

        # Не разрастаем таблицу idempotency бесконечно.
        con.execute("DELETE FROM spin_requests WHERE created_at<?", (int(time.time()) - 86400 * 7,))

        add_stat(con, uid, "spins", 1)
        if RARITY_ORDER.get(plate["rarity"], 0) >= RARITY_ORDER["Редкий"]:
            add_stat(con, uid, "rare_found", 1)

        new_user = user_json(con, uid)
        return jsonify(
            ok=True,
            plate=plate,
            balance=new_user["balance"],
        
