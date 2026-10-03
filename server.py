import os
import random
import sqlite3
import time
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="")

DB = "nexora.db"

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Твой Telegram ID
CREATOR_ID = 8518976778

CURRENCY = "💎"


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            balance INTEGER DEFAULT 5000,
            bank INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            energy INTEGER DEFAULT 100,
            rating INTEGER DEFAULT 0,
            created_at INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            item_type TEXT,
            item_name TEXT,
            amount INTEGER DEFAULT 1,
            value INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            business_type TEXT,
            level INTEGER DEFAULT 1,
            income INTEGER DEFAULT 0,
            last_collect INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS farms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            crop TEXT,
            level INTEGER DEFAULT 1,
            last_harvest INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            name TEXT,
            level INTEGER DEFAULT 1,
            happiness INTEGER DEFAULT 100
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            mine_type TEXT,
            level INTEGER DEFAULT 1,
            last_mine INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            telegram_id INTEGER PRIMARY KEY,
            job TEXT DEFAULT 'Безработный',
            salary INTEGER DEFAULT 100,
            last_work INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS fishing (
            telegram_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            fish INTEGER DEFAULT 0,
            last_fish INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            property_name TEXT,
            level INTEGER DEFAULT 1,
            income INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER,
            item_type TEXT,
            item_name TEXT,
            amount INTEGER,
            price INTEGER,
            created_at INTEGER
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# HELPERS
# =========================================================

def get_user(tg_id):
    conn = db()
    user = conn.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()
    conn.close()
    return user


def create_user(tg_id, username="", first_name=""):
    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if not user:
        conn.execute("""
            INSERT INTO users
            (telegram_id, username, first_name, balance, bank, xp, level, energy, rating, created_at)
            VALUES (?, ?, ?, 5000, 0, 0, 1, 100, 0, ?)
        """, (
            tg_id,
            username,
            first_name,
            int(time.time())
        ))

        # Стартовые предметы
        conn.execute("""
            INSERT INTO inventory
            (telegram_id, item_type, item_name, amount, value)
            VALUES (?, 'resource', 'Железо', 10, 20)
        """, (tg_id,))

        conn.execute("""
            INSERT INTO inventory
            (telegram_id, item_type, item_name, amount, value)
            VALUES (?, 'resource', 'Кристалл', 5, 100)
        """, (tg_id,))

        conn.execute("""
            INSERT INTO businesses
            (telegram_id, business_type, level, income, last_collect)
            VALUES (?, 'Малый магазин', 1, 250, ?)
        """, (tg_id, int(time.time())))

        conn.execute("""
            INSERT INTO jobs
            (telegram_id, job, salary, last_work)
            VALUES (?, 'Стажёр', 150, 0)
        """, (tg_id,))

        conn.execute("""
            INSERT INTO fishing
            (telegram_id, level, fish, last_fish)
            VALUES (?, 1, 0, 0)
        """, (tg_id,))

        conn.execute("""
            INSERT INTO farms
            (telegram_id, crop, level, last_harvest)
            VALUES (?, 'Пшеница', 1, ?)
        """, (tg_id, int(time.time())))

        conn.execute("""
            INSERT INTO mines
            (telegram_id, mine_type, level, last_mine)
            VALUES (?, 'Железная шахта', 1, ?)
        """, (tg_id, int(time.time())))

        conn.commit()

    conn.close()


def auth():
    tg_id = request.headers.get("X-Telegram-ID")

    # Для разработки разрешаем demo-пользователя
    if not tg_id:
        tg_id = request.args.get("telegram_id")

    try:
        tg_id = int(tg_id)
    except:
        tg_id = 100000001

    username = request.headers.get("X-Telegram-Username", "")
    first_name = request.headers.get("X-Telegram-Name", "Игрок")

    create_user(tg_id, username, first_name)

    return tg_id


def add_balance(tg_id, amount):
    conn = db()
    conn.execute(
        "UPDATE users SET balance = balance + ? WHERE telegram_id=?",
        (amount, tg_id)
    )
    conn.commit()
    conn.close()


def add_xp(tg_id, amount):
    conn = db()

    user = conn.execute(
        "SELECT xp, level FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if not user:
        conn.close()
        return

    xp = user["xp"] + amount
    level = user["level"]

    needed = level * 1000

    while xp >= needed:
        xp -= needed
        level += 1
        needed = level * 1000

    conn.execute("""
        UPDATE users
        SET xp=?, level=?, rating=rating+?
        WHERE telegram_id=?
    """, (
        xp,
        level,
        amount // 10,
        tg_id
    ))

    conn.commit()
    conn.close()


def is_creator(tg_id):
    return tg_id == CREATOR_ID


# =========================================================
# MAIN
# =========================================================

@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/api/me")
def me():
    tg_id = auth()

    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    businesses = conn.execute(
        "SELECT * FROM businesses WHERE telegram_id=?",
        (tg_id,)
    ).fetchall()

    farms = conn.execute(
        "SELECT * FROM farms WHERE telegram_id=?",
        (tg_id,)
    ).fetchall()

    pets = conn.execute(
        "SELECT * FROM pets WHERE telegram_id=?",
        (tg_id,)
    ).fetchall()

    mines = conn.execute(
        "SELECT * FROM mines WHERE telegram_id=?",
        (tg_id,)
    ).fetchall()

    fishing = conn.execute(
        "SELECT * FROM fishing WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    job = conn.execute(
        "SELECT * FROM jobs WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    properties = conn.execute(
        "SELECT * FROM properties WHERE telegram_id=?",
        (tg_id,)
    ).fetchall()

    conn.close()

    return jsonify({
        "user": dict(user),
        "creator": is_creator(tg_id),
        "businesses": [dict(x) for x in businesses],
        "farms": [dict(x) for x in farms],
        "pets": [dict(x) for x in pets],
        "mines": [dict(x) for x in mines],
        "fishing": dict(fishing) if fishing else {},
        "job": dict(job) if job else {},
        "properties": [dict(x) for x in properties]
    })


# =========================================================
# DAILY REWARD
# =========================================================

@app.route("/api/reward", methods=["POST"])
def reward():
    tg_id = auth()

    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    now = int(time.time())

    last = conn.execute("""
        SELECT amount FROM inventory
        WHERE telegram_id=? AND item_type='daily'
        ORDER BY id DESC LIMIT 1
    """, (tg_id,)).fetchone()

    # Ограничение раз в 24 часа
    if last:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Награда уже получена"
        })

    amount = 1000 + user["level"] * 250

    conn.execute("""
        INSERT INTO inventory
        (telegram_id, item_type, item_name, amount, value)
        VALUES (?, 'daily', 'Ежедневная награда', ?, ?)
    """, (
        tg_id,
        1,
        amount
    ))

    conn.execute(
        "UPDATE users SET balance=balance+? WHERE telegram_id=?",
        (amount, tg_id)
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 100)

    return jsonify({
        "ok": True,
        "amount": amount
    })


# =========================================================
# BUSINESS
# =========================================================

@app.route("/api/business/collect", methods=["POST"])
def collect_business():
    tg_id = auth()

    conn = db()

    business = conn.execute(
        "SELECT * FROM businesses WHERE telegram_id=? LIMIT 1",
        (tg_id,)
    ).fetchone()

    if not business:
        conn.close()
        return jsonify({"ok": False})

    now = int(time.time())
    elapsed = now - business["last_collect"]

    # Доход каждые 60 секунд
    cycles = min(elapsed // 60, 100)

    if cycles <= 0:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Доход ещё не накопился"
        })

    amount = cycles * business["income"] * business["level"]

    conn.execute(
        "UPDATE users SET balance=balance+? WHERE telegram_id=?",
        (amount, tg_id)
    )

    conn.execute(
        "UPDATE businesses SET last_collect=? WHERE id=?",
        (now, business["id"])
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 50)

    return jsonify({
        "ok": True,
        "amount": amount
    })


@app.route("/api/business/upgrade", methods=["POST"])
def upgrade_business():
    tg_id = auth()

    conn = db()

    business = conn.execute(
        "SELECT * FROM businesses WHERE telegram_id=? LIMIT 1",
        (tg_id,)
    ).fetchone()

    user = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if not business:
        conn.close()
        return jsonify({"ok": False})

    price = 3000 * business["level"]

    if user["balance"] < price:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно 💎"
        })

    conn.execute(
        "UPDATE users SET balance=balance-? WHERE telegram_id=?",
        (price, tg_id)
    )

    conn.execute(
        "UPDATE businesses SET level=level+1 WHERE id=?",
        (business["id"],)
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 200)

    return jsonify({
        "ok": True
    })


# =========================================================
# MINING
# =========================================================

@app.route("/api/mine", methods=["POST"])
def mine():
    tg_id = auth()

    conn = db()

    mine_data = conn.execute(
        "SELECT * FROM mines WHERE telegram_id=? LIMIT 1",
        (tg_id,)
    ).fetchone()

    if not mine_data:
        conn.close()
        return jsonify({"ok": False})

    now = int(time.time())

    if now - mine_data["last_mine"] < 20:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Шахта перезаряжается"
        })

    amount = random.randint(
        3 + mine_data["level"],
        8 + mine_data["level"] * 2
    )

    item = random.choice([
        ("Железо", 20),
        ("Уголь", 30),
        ("Кристалл", 100),
        ("Золото", 250)
    ])

    existing = conn.execute("""
        SELECT * FROM inventory
        WHERE telegram_id=? AND item_type='resource' AND item_name=?
    """, (
        tg_id,
        item[0]
    )).fetchone()

    if existing:
        conn.execute(
            "UPDATE inventory SET amount=amount+? WHERE id=?",
            (amount, existing["id"])
        )
    else:
        conn.execute("""
            INSERT INTO inventory
            (telegram_id,item_type,item_name,amount,value)
            VALUES (?, 'resource', ?, ?, ?)
        """, (
            tg_id,
            item[0],
            amount,
            item[1]
        ))

    conn.execute(
        "UPDATE mines SET last_mine=? WHERE id=?",
        (now, mine_data["id"])
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 75)

    return jsonify({
        "ok": True,
        "item": item[0],
        "amount": amount
    })


@app.route("/api/mine/upgrade", methods=["POST"])
def upgrade_mine():
    tg_id = auth()

    conn = db()

    mine_data = conn.execute(
        "SELECT * FROM mines WHERE telegram_id=? LIMIT 1",
        (tg_id,)
    ).fetchone()

    user = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    price = 2500 * mine_data["level"]

    if user["balance"] < price:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно 💎"
        })

    conn.execute(
        "UPDATE users SET balance=balance-? WHERE telegram_id=?",
        (price, tg_id)
    )

    conn.execute(
        "UPDATE mines SET level=level+1 WHERE id=?",
        (mine_data["id"],)
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 150)

    return jsonify({"ok": True})


# =========================================================
# FARM
# =========================================================

@app.route("/api/farm/harvest", methods=["POST"])
def harvest():
    tg_id = auth()

    conn = db()

    farm = conn.execute(
        "SELECT * FROM farms WHERE telegram_id=? LIMIT 1",
        (tg_id,)
    ).fetchone()

    if not farm:
        conn.close()
        return jsonify({"ok": False})

    now = int(time.time())

    if now - farm["last_harvest"] < 45:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Урожай ещё растёт"
        })

    amount = random.randint(
        100,
        180 + farm["level"] * 40
    )

    conn.execute(
        "UPDATE users SET balance=balance+? WHERE telegram_id=?",
        (amount, tg_id)
    )

    conn.execute(
        "UPDATE farms SET last_harvest=? WHERE id=?",
        (now, farm["id"])
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 60)

    return jsonify({
        "ok": True,
        "amount": amount
    })


@app.route("/api/farm/upgrade", methods=["POST"])
def upgrade_farm():
    tg_id = auth()

    conn = db()

    farm = conn.execute(
        "SELECT * FROM farms WHERE telegram_id=? LIMIT 1",
        (tg_id,)
    ).fetchone()

    user = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    price = 2000 * farm["level"]

    if user["balance"] < price:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно 💎"
        })

    conn.execute(
        "UPDATE users SET balance=balance-? WHERE telegram_id=?",
        (price, tg_id)
    )

    conn.execute(
        "UPDATE farms SET level=level+1 WHERE id=?",
        (farm["id"],)
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 100)

    return jsonify({"ok": True})


# =========================================================
# JOBS
# =========================================================

JOBS = {
    "Курьер": 250,
    "Шахтёр": 400,
    "Программист": 650,
    "Инженер": 900,
    "Директор": 1500
}


@app.route("/api/jobs")
def jobs():
    return jsonify(JOBS)


@app.route("/api/job/set", methods=["POST"])
def set_job():
    tg_id = auth()

    data = request.json or {}
    job = data.get("job")

    if job not in JOBS:
        return jsonify({
            "ok": False,
            "message": "Такой работы нет"
        })

    conn = db()

    conn.execute("""
        UPDATE jobs
        SET job=?, salary=?
        WHERE telegram_id=?
    """, (
        job,
        JOBS[job],
        tg_id
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/job/work", methods=["POST"])
def work():
    tg_id = auth()

    conn = db()

    job = conn.execute(
        "SELECT * FROM jobs WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    now = int(time.time())

    if now - job["last_work"] < 30:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Подожди немного перед следующей работой"
        })

    salary = job["salary"]

    conn.execute("""
        UPDATE users
        SET balance=balance+?
        WHERE telegram_id=?
    """, (
        salary,
        tg_id
    ))

    conn.execute(
        "UPDATE jobs SET last_work=? WHERE telegram_id=?",
        (now, tg_id)
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 80)

    return jsonify({
        "ok": True,
        "amount": salary
    })


# =========================================================
# FISHING
# =========================================================

@app.route("/api/fishing", methods=["POST"])
def fishing():
    tg_id = auth()

    conn = db()

    fish = conn.execute(
        "SELECT * FROM fishing WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    now = int(time.time())

    if now - fish["last_fish"] < 20:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Удочка отдыхает"
        })

    amount = random.randint(100, 350) * fish["level"]

    conn.execute(
        "UPDATE users SET balance=balance+? WHERE telegram_id=?",
        (amount, tg_id)
    )

    conn.execute("""
        UPDATE fishing
        SET fish=fish+1,last_fish=?
        WHERE telegram_id=?
    """, (
        now,
        tg_id
    ))

    conn.commit()
    conn.close()

    add_xp(tg_id, 70)

    return jsonify({
        "ok": True,
        "amount": amount
    })


# =========================================================
# BANK
# =========================================================

@app.route("/api/bank/deposit", methods=["POST"])
def bank_deposit():
    tg_id = auth()

    data = request.json or {}

    try:
        amount = int(data.get("amount", 0))
    except:
        amount = 0

    conn = db()

    user = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if amount <= 0 or user["balance"] < amount:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно средств"
        })

    conn.execute("""
        UPDATE users
        SET balance=balance-?,
            bank=bank+?
        WHERE telegram_id=?
    """, (
        amount,
        amount,
        tg_id
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/bank/withdraw", methods=["POST"])
def bank_withdraw():
    tg_id = auth()

    data = request.json or {}

    try:
        amount = int(data.get("amount", 0))
    except:
        amount = 0

    conn = db()

    user = conn.execute(
        "SELECT bank FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if amount <= 0 or user["bank"] < amount:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно средств в банке"
        })

    conn.execute("""
        UPDATE users
        SET bank=bank-?,
            balance=balance+?
        WHERE telegram_id=?
    """, (
        amount,
        amount,
        tg_id
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


# =========================================================
# PROPERTIES
# =========================================================

PROPERTY_LIST = [
    ("Квартира", 10000, 300),
    ("Дом", 30000, 900),
    ("Бизнес-центр", 100000, 3500),
    ("Небоскрёб", 500000, 20000)
]


@app.route("/api/properties")
def properties():
    return jsonify([
        {
            "name": x[0],
            "price": x[1],
            "income": x[2]
        }
        for x in PROPERTY_LIST
    ])


@app.route("/api/property/buy", methods=["POST"])
def buy_property():
    tg_id = auth()

    data = request.json or {}
    name = data.get("name")

    selected = None

    for x in PROPERTY_LIST:
        if x[0] == name:
            selected = x

    if not selected:
        return jsonify({"ok": False})

    conn = db()

    user = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if user["balance"] < selected[1]:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно 💎"
        })

    conn.execute(
        "UPDATE users SET balance=balance-? WHERE telegram_id=?",
        (selected[1], tg_id)
    )

    conn.execute("""
        INSERT INTO properties
        (telegram_id, property_name, level, income)
        VALUES (?, ?, 1, ?)
    """, (
        tg_id,
        selected[0],
        selected[2]
    ))

    conn.commit()
    conn.close()

    add_xp(tg_id, 500)

    return jsonify({"ok": True})


# =========================================================
# PETS
# =========================================================

PETS = [
    ("🐺 Волк", 5000),
    ("🐉 Дракон", 25000),
    ("🦊 Лиса", 8000),
    ("🦅 Феникс", 50000)
]


@app.route("/api/pets")
def pets():
    return jsonify([
        {
            "name": p[0],
            "price": p[1]
        }
        for p in PETS
    ])


@app.route("/api/pet/buy", methods=["POST"])
def buy_pet():
    tg_id = auth()

    data = request.json or {}
    name = data.get("name")

    selected = None

    for pet in PETS:
        if pet[0] == name:
            selected = pet

    if not selected:
        return jsonify({"ok": False})

    conn = db()

    user = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if user["balance"] < selected[1]:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно 💎"
        })

    conn.execute(
        "UPDATE users SET balance=balance-? WHERE telegram_id=?",
        (selected[1], tg_id)
    )

    conn.execute("""
        INSERT INTO pets
        (telegram_id,name,level,happiness)
        VALUES (?, ?, 1, 100)
    """, (
        tg_id,
        name
    ))

    conn.commit()
    conn.close()

    add_xp(tg_id, 300)

    return jsonify({"ok": True})


# =========================================================
# PLANETS
# =========================================================

PLANETS = [
    ("🌍 Земля", 0),
    ("🌙 Луна", 5000),
    ("🔴 Марс", 25000),
    ("🪐 Сатурн", 100000),
    ("🌌 Нексус", 500000)
]


@app.route("/api/planets")
def planets():
    return jsonify([
        {
            "name": p[0],
            "price": p[1]
        }
        for p in PLANETS
    ])


@app.route("/api/planet/travel", methods=["POST"])
def travel():
    tg_id = auth()

    data = request.json or {}
    name = data.get("name")

    selected = None

    for p in PLANETS:
        if p[0] == name:
            selected = p

    if not selected:
        return jsonify({"ok": False})

    conn = db()

    user = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if user["balance"] < selected[1]:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно 💎"
        })

    if selected[1] > 0:
        conn.execute(
            "UPDATE users SET balance=balance-? WHERE telegram_id=?",
            (selected[1], tg_id)
        )

    conn.commit()
    conn.close()

    add_xp(tg_id, 400)

    return jsonify({
        "ok": True,
        "planet": name
    })


# =========================================================
# INVENTORY
# =========================================================

@app.route("/api/inventory")
def inventory():
    tg_id = auth()

    conn = db()

    items = conn.execute("""
        SELECT * FROM inventory
        WHERE telegram_id=?
        AND item_type!='daily'
        ORDER BY id DESC
    """, (tg_id,)).fetchall()

    conn.close()

    return jsonify([
        dict(x)
        for x in items
    ])


# =========================================================
# MARKET
# =========================================================

@app.route("/api/market")
def market():
    conn = db()

    items = conn.execute("""
        SELECT * FROM market
        ORDER BY id DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    return jsonify([
        dict(x)
        for x in items
    ])


@app.route("/api/market/sell", methods=["POST"])
def market_sell():
    tg_id = auth()

    data = request.json or {}

    item_name = data.get("item_name")
    amount = int(data.get("amount", 1))
    price = int(data.get("price", 0))

    if amount <= 0 or price <= 0:
        return jsonify({
            "ok": False,
            "message": "Неверные данные"
        })

    conn = db()

    item = conn.execute("""
        SELECT * FROM inventory
        WHERE telegram_id=?
        AND item_name=?
        AND item_type='resource'
    """, (
        tg_id,
        item_name
    )).fetchone()

    if not item or item["amount"] < amount:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно предметов"
        })

    conn.execute(
        "UPDATE inventory SET amount=amount-? WHERE id=?",
        (amount, item["id"])
    )

    conn.execute("""
        INSERT INTO market
        (seller_id,item_type,item_name,amount,price,created_at)
        VALUES (?, 'resource', ?, ?, ?, ?)
    """, (
        tg_id,
        item_name,
        amount,
        price,
        int(time.time())
    ))

    conn.commit()
    conn.close()

    return jsonify({"ok": True})


@app.route("/api/market/buy", methods=["POST"])
def market_buy():
    tg_id = auth()

    data = request.json or {}

    try:
        listing_id = int(data.get("id"))
    except:
        return jsonify({"ok": False})

    conn = db()

    listing = conn.execute(
        "SELECT * FROM market WHERE id=?",
        (listing_id,)
    ).fetchone()

    if not listing:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Лот уже продан"
        })

    if listing["seller_id"] == tg_id:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Нельзя купить свой лот"
        })

    buyer = conn.execute(
        "SELECT balance FROM users WHERE telegram_id=?",
        (tg_id,)
    ).fetchone()

    if buyer["balance"] < listing["price"]:
        conn.close()
        return jsonify({
            "ok": False,
            "message": "Недостаточно 💎"
        })

    conn.execute(
        "UPDATE users SET balance=balance-? WHERE telegram_id=?",
        (listing["price"], tg_id)
    )

    conn.execute(
        "UPDATE users SET balance=balance+? WHERE telegram_id=?",
        (listing["price"], listing["seller_id"])
    )

    existing = conn.execute("""
        SELECT * FROM inventory
        WHERE telegram_id=?
        AND item_name=?
        AND item_type='resource'
    """, (
        tg_id,
        listing["item_name"]
    )).fetchone()

    if existing:
        conn.execute(
            "UPDATE inventory SET amount=amount+? WHERE id=?",
            (listing["amount"], existing["id"])
        )
    else:
        conn.execute("""
            INSERT INTO inventory
            (telegram_id,item_type,item_name,amount,value)
            VALUES (?, 'resource', ?, ?, 50)
        """, (
            tg_id,
            listing["item_name"],
            listing["amount"]
        ))

    conn.execute(
        "DELETE FROM market WHERE id=?",
        (listing_id,)
    )

    conn.commit()
    conn.close()

    add_xp(tg_id, 100)

    return jsonify({"ok": True})


# =========================================================
# LEADERBOARD
# =========================================================

@app.route("/api/leaderboard")
def leaderboard():
    conn = db()

    users = conn.execute("""
        SELECT first_name, username, level, balance, rating
        FROM users
        ORDER BY rating DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    return jsonify([
        dict(x)
        for x in users
    ])


# =========================================================
# CREATOR PREFIX
# =========================================================

@app.route("/api/prefix")
def prefix():
    tg_id = auth()

    return jsonify({
        "creator": is_creator(tg_id),
        "prefix": "👑 СОЗДАТЕЛЬ" if is_creator(tg_id) else ""
    })


# =========================================================
# CREATOR PANEL
# =========================================================

@app.route("/api/creator")
def creator():
    tg_id = auth()

    if not is_creator(tg_id):
        return jsonify({
            "ok": False
        })

    conn = db()

    users = conn.execute(
        "SELECT COUNT(*) AS c FROM users"
    ).fetchone()["c"]

    balance = conn.execute(
        "SELECT COALESCE(SUM(balance),0) AS c FROM users"
    ).fetchone()["c"]

    conn.close()

    return jsonify({
        "ok": True,
        "users": users,
        "economy": balance
    })


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
