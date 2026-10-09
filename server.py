
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

app = Flask(__name__, static_folder="web", static_url_path="")

DB_PATH = os.getenv("DB_PATH", "nomer_fixed.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

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
    ("Мифический", 1)
]


# DATABASE

def db():
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            balance INTEGER NOT NULL DEFAULT 10000
                CHECK(balance>=0),
            xp INTEGER NOT NULL DEFAULT 0,
            spins_day TEXT NOT NULL DEFAULT '',
            spins_used INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
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
            plate_id INTEGER NOT NULL UNIQUE
                REFERENCES plates(id),
            seller_id INTEGER NOT NULL REFERENCES users(id),
            price INTEGER NOT NULL CHECK(price>0),
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

        CREATE INDEX IF NOT EXISTS idx_plates_owner
            ON plates(owner_id);

        CREATE INDEX IF NOT EXISTS idx_listings_seller
            ON listings(seller_id);
        """)


# TELEGRAM AUTHORIZATION

def tg_user(raw):
    if DEMO_MODE and not raw:
        return {
            "id": 10001,
            "first_name": "Demo Player",
            "username": "demo"
        }

    if not BOT_TOKEN or not raw:
        return None

    try:
        data = dict(parse_qsl(raw, keep_blank_values=True))
        received = data.pop("hash", "")
        ts = int(data["auth_date"])

        if (
            not received
            or time.time() - ts > 86400
            or ts > time.time() + 300
        ):
            return None

        check = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items())
        )

        secret = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        expected = hmac.new(
            secret,
            check.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, received):
            return None

        u = json.loads(data["user"])

        return u if type(u.get("id")) is int else None

    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None


def auth(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        u = tg_user(
            request.headers.get("X-Telegram-Init-Data", "")
        )

        if not u:
            return jsonify(
                error="Нет авторизации Telegram. "
                      "Открой приложение через кнопку меню бота "
                      "и проверь BOT_TOKEN в Render."
            ), 401

        uid = u["id"]
        name = str(u.get("first_name") or "Игрок")[:80]
        username = str(u.get("username") or "")[:80]

        with db() as c:
            c.execute(
                """INSERT OR IGNORE INTO users
                (id,name,username,created_at)
                VALUES(?,?,?,?)""",
                (uid, name, username, int(time.time()))
            )

            c.execute(
                "UPDATE users SET name=?,username=? WHERE id=?",
                (name, username, uid)
            )

        return fn(uid, *args, **kwargs)

    return wrapped


# GAME FUNCTIONS

def day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def generate():
    rarity = secrets.SystemRandom().choices(
        [x[0] for x in RARITIES],
        weights=[x[1] for x in RARITIES]
    )[0]

    a, b, c = (
        secrets.choice(LETTERS) for _ in range(3)
    )

    if rarity == "Обычный":
        digits = f"{secrets.randbelow(900)+100:03}"

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

    region = secrets.choice(REGIONS)
    return f"{a}{digits}{b}{c} {region}", rarity


def payload():
    obj = request.get_json(silent=True)
    return obj if isinstance(obj, dict) else {}


def integer(obj, key):
    v = obj.get(key)

    if isinstance(v, bool) or not isinstance(v, (int, str)):
        raise ValueError()

    return int(v)


# WEBSITE

@app.get("/")
def home():
    return send_from_directory(
        app.static_folder, "index.html"
    )


@app.get("/health")
def health():
    return jsonify(status="ok")


# PROFILE

@app.get("/api/me")
@auth
def me(uid):
    with db() as c:
        u = c.execute(
            "SELECT * FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        n = c.execute(
            "SELECT COUNT(*) FROM plates WHERE owner_id=?",
            (uid,)
        ).fetchone()[0]

    used = (
        u["spins_used"]
        if u["spins_day"] == day()
        else 0
    )

    return jsonify(
        id=uid,
        name=u["name"],
        username=u["username"],
        balance=u["balance"],
        xp=u["xp"],
        level=min(100, 1 + u["xp"] // 250),
        collection=n,
        spins_left=max(0, 20-used),
        demo=DEMO_MODE
    )


# GENERATOR

@app.post("/api/spin")
@auth
def spin(uid):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        u = c.execute(
            "SELECT spins_day,spins_used FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        used = (
            u["spins_used"]
            if u["spins_day"] == day()
            else 0
        )

        if used >= 20:
            return jsonify(
                error="Сегодня попытки закончились"
            ), 400

        plate = None

        for _ in range(150):
            code, rarity = generate()

            try:
                cur = c.execute(
                    """INSERT INTO plates
                    (code,rarity,owner_id,created_at)
                    VALUES(?,?,?,?)""",
                    (code, rarity, uid, int(time.time()))
                )

                plate = {
                    "id": cur.lastrowid,
                    "code": code,
                    "rarity": rarity
                }
                break

            except sqlite3.IntegrityError:
                continue

        if plate is None:
            return jsonify(
                error="Свободная комбинация не найдена"
            ), 503

        c.execute(
            """UPDATE users
            SET spins_day=?,spins_used=?,xp=xp+10
            WHERE id=?""",
            (day(), used+1, uid)
        )

    return jsonify(
        plate=plate,
        spins_left=19-used
    )


# COLLECTION

@app.get("/api/collection")
@auth
def collection(uid):
    with db() as c:
        rows = c.execute(
            """SELECT
                p.id,p.code,p.rarity,
                l.id AS listing_id
            FROM plates p
            LEFT JOIN listings l ON l.plate_id=p.id
            WHERE p.owner_id=?
            ORDER BY p.id DESC LIMIT 500""",
            (uid,)
        ).fetchall()

    return jsonify(plates=[dict(r) for r in rows])


# CREATE MARKET LISTING

@app.post("/api/list")
@auth
def listing(uid):
    try:
        p = payload()
        pid = integer(p, "plate_id")
        price = integer(p, "price")

    except ValueError:
        return jsonify(error="Некорректные данные"), 400

    if not 100 <= price <= 100000000:
        return jsonify(
            error="Цена от 100 до 100 000 000 NC"
        ), 400

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        count = c.execute(
            "SELECT COUNT(*) FROM listings WHERE seller_id=?",
            (uid,)
        ).fetchone()[0]

        if count >= 3:
            return jsonify(
                error="Можно выставить только 3 номера"
            ), 400

        row = c.execute(
            "SELECT id FROM plates WHERE id=? AND owner_id=?",
            (pid, uid)
        ).fetchone()

        active = c.execute(
            "SELECT 1 FROM listings WHERE plate_id=?",
            (pid,)
        ).fetchone()

        if not row or active:
            return jsonify(
                error="Номер уже продан или выставлен"
            ), 400

        c.execute(
            """INSERT INTO listings
            (plate_id,seller_id,price,created_at)
            VALUES(?,?,?,?)""",
            (pid, uid, price, int(time.time()))
        )

    return jsonify(ok=True)


# MARKET

@app.get("/api/market")
@auth
def market(uid):
    with db() as c:
        rows = c.execute(
            """SELECT
                l.id,l.price,l.seller_id,
                p.code,p.rarity,u.name AS seller
            FROM listings l
            JOIN plates p ON p.id=l.plate_id
            JOIN users u ON u.id=l.seller_id
            ORDER BY l.id DESC LIMIT 100"""
        ).fetchall()

    return jsonify(listings=[dict(r) for r in rows])


# CANCEL LISTING

@app.post("/api/cancel")
@auth
def cancel(uid):
    try:
        lid = integer(payload(), "listing_id")
    except ValueError:
        return jsonify(error="Неверный ID"), 400

    with db() as c:
        cur = c.execute(
            """DELETE FROM listings
            WHERE id=? AND seller_id=?""",
            (lid, uid)
        )

    return jsonify(ok=cur.rowcount > 0)


# BUY PLATE

@app.post("/api/buy")
@auth
def buy(uid):
    try:
        lid = integer(payload(), "listing_id")
    except ValueError:
        return jsonify(error="Неверный ID"), 400

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        item = c.execute(
            "SELECT * FROM listings WHERE id=?",
            (lid,)
        ).fetchone()

        if not item:
            return jsonify(
                error="Объявление уже закрыто"
            ), 404

        if item["seller_id"] == uid:
            return jsonify(
                error="Нельзя купить свой номер"
            ), 400

        price = item["price"]
        fee = (price*5+99)//100

        cur = c.execute(
            """UPDATE users
            SET balance=balance-?
            WHERE id=? AND balance>=?""",
            (price, uid, price)
        )

        if cur.rowcount != 1:
            return jsonify(
                error="Недостаточно NC"
            ), 400

        moved = c.execute(
            """UPDATE plates SET owner_id=?
            WHERE id=? AND owner_id=?""",
            (
                uid,
                item["plate_id"],
                item["seller_id"]
            )
        )

        if moved.rowcount != 1:
            return jsonify(
                error="Номер больше не принадлежит продавцу"
            ), 409

        c.execute(
            """UPDATE users SET balance=balance+?
            WHERE id=?""",
            (price-fee, item["seller_id"])
        )

        c.execute(
            "DELETE FROM listings WHERE id=?",
            (lid,)
        )

        c.execute(
            """INSERT INTO trades
            (plate_id,seller_id,buyer_id,price,created_at)
            VALUES(?,?,?,?,?)""",
            (
                item["plate_id"],
                item["seller_id"],
                uid,
                price,
                int(time.time())
            )
        )

    return jsonify(ok=True)


# SELL ORDINARY PLATE TO SYSTEM

@app.post("/api/sell-system")
@auth
def sell_system(uid):
    try:
        pid = integer(payload(), "plate_id")
    except ValueError:
        return jsonify(error="Неверный ID"), 400

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        p = c.execute(
            """SELECT rarity FROM plates
            WHERE id=? AND owner_id=?""",
            (pid, uid)
        ).fetchone()

        active = c.execute(
            "SELECT 1 FROM listings WHERE plate_id=?",
            (pid,)
        ).fetchone()

        if not p or p["rarity"] != "Обычный" or active:
            return jsonify(
                error="Продать системе можно только "
                      "свободный обычный номер"
            ), 400

        c.execute(
            "DELETE FROM plates WHERE id=?",
            (pid,)
        )

        c.execute(
            """UPDATE users SET balance=balance+25
            WHERE id=?""",
            (uid,)
        )

    return jsonify(ok=True)


# LEADERBOARD

@app.get("/api/top")
@auth
def top(uid):
    with db() as c:
        rows = c.execute(
            """SELECT
                u.id,u.name,u.balance,
                COUNT(p.id) AS collection
            FROM users u
            LEFT JOIN plates p ON p.owner_id=u.id
            GROUP BY u.id
            ORDER BY collection DESC,balance DESC
            LIMIT 30"""
        ).fetchall()

    return jsonify(players=[dict(r) for r in rows])


init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000"))
    )
