
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
CREATOR_ID = int(os.getenv("CREATOR_TELEGRAM_ID", "0"))

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

SELL_PRICES = {
    "Обычный": 25,
    "Необычный": 75,
    "Редкий": 200,
    "Эпический": 500,
    "Легендарный": 1500,
    "Мифический": 5000
}

CARS = [
    ("Nissan Laurel C35", 180000),
    ("Nissan Skyline R34", 250000),
    ("Toyota Supra MK4", 320000),
    ("Toyota Mark II JZX100", 160000),
    ("Nissan Silvia S15", 210000),
    ("BMW M5 E39", 280000),
    ("Mercedes-Benz W124", 120000),
    ("Toyota Chaser JZX100", 190000)
]

TASKS = [
    ("first_plate", "Первый номер", "Получить 1 номер", 1, 300, 20, "plates"),
    ("collector_3", "Начинающий коллекционер", "Получить 3 номера", 3, 500, 30, "plates"),
    ("collector_10", "Коллекционер", "Получить 10 номеров", 10, 1500, 60, "plates"),
    ("collector_30", "Мастер номеров", "Получить 30 номеров", 30, 5000, 150, "plates"),
    ("first_car", "Первый автомобиль", "Купить автомобиль", 1, 2000, 100, "cars"),
    ("first_trade", "Первый покупатель", "Купить номер на маркете", 1, 500, 40, "buys"),
    ("seller", "Дилер", "Продать 3 номера игрокам", 3, 1500, 80, "sales")
]


def now():
    return int(time.time())


def day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
            balance INTEGER NOT NULL DEFAULT 10000 CHECK(balance>=0),
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
            plate_id INTEGER NOT NULL UNIQUE REFERENCES plates(id),
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

        CREATE TABLE IF NOT EXISTS cars(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            model TEXT NOT NULL,
            price INTEGER NOT NULL,
            plate_id INTEGER UNIQUE REFERENCES plates(id),
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS task_claims(
            user_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,
            claimed_at INTEGER NOT NULL,
            PRIMARY KEY(user_id,task_id)
        );

        CREATE TABLE IF NOT EXISTS user_stats(
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            plates_earned INTEGER NOT NULL DEFAULT 0,
            cars_bought INTEGER NOT NULL DEFAULT 0,
            buys INTEGER NOT NULL DEFAULT 0,
            sales INTEGER NOT NULL DEFAULT 0,
            last_bonus INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS clubs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS club_members(
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            club_id INTEGER NOT NULL REFERENCES clubs(id),
            joined_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS auctions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plate_id INTEGER NOT NULL UNIQUE REFERENCES plates(id),
            seller_id INTEGER NOT NULL REFERENCES users(id),
            start_price INTEGER NOT NULL,
            current_price INTEGER NOT NULL,
            bidder_id INTEGER REFERENCES users(id),
            ends_at INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS admin_logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            amount INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_plates_owner ON plates(owner_id);
        CREATE INDEX IF NOT EXISTS idx_listings_seller ON listings(seller_id);
        CREATE INDEX IF NOT EXISTS idx_cars_owner ON cars(owner_id);
        CREATE INDEX IF NOT EXISTS idx_auctions_status ON auctions(status,ends_at);
        """)

        # Добавляем только новые поля, не удаляя старые данные.
        columns = {
            r["name"] for r in c.execute("PRAGMA table_info(plates)")
        }
        if "favorite" not in columns:
            c.execute(
                "ALTER TABLE plates ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0"
            )

        # Статистика ранее созданных коллекций.
        c.execute("""
            INSERT OR IGNORE INTO user_stats(user_id,plates_earned)
            SELECT u.id,COUNT(p.id)
            FROM users u
            LEFT JOIN plates p ON p.owner_id=u.id
            GROUP BY u.id
        """)


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
                error="Нет авторизации Telegram. Открой игру через бота."
            ), 401

        uid = u["id"]
        name = str(u.get("first_name") or "Игрок")[:80]
        username = str(u.get("username") or "")[:80]

        with db() as c:
            c.execute("""
                INSERT OR IGNORE INTO users
                (id,name,username,created_at)
                VALUES(?,?,?,?)
            """, (uid, name, username, now()))

            c.execute(
                "UPDATE users SET name=?,username=? WHERE id=?",
                (name, username, uid)
            )

            c.execute(
                "INSERT OR IGNORE INTO user_stats(user_id) VALUES(?)",
                (uid,)
            )

        return fn(uid, *args, **kwargs)

    return wrapped


def payload():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def integer(obj, key):
    v = obj.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, str)):
        raise ValueError()
    return int(v)


def generate():
    rarity = secrets.SystemRandom().choices(
        [r[0] for r in RARITIES],
        weights=[r[1] for r in RARITIES]
    )[0]

    a, b, c = (secrets.choice(LETTERS) for _ in range(3))

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


def error(message, status=400):
    return jsonify(error=message), status


def stat(c, uid, field, amount=1):
    allowed = {
        "plates_earned", "cars_bought", "buys", "sales"
    }
    if field not in allowed:
        return

    c.execute(
        f"UPDATE user_stats SET {field}={field}+? WHERE user_id=?",
        (amount, uid)
    )


@app.get("/")
def home():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/health")
def health():
    return jsonify(status="ok", version="4.0")


@app.get("/api/me")
@auth
def me(uid):
    with db() as c:
        u = c.execute(
            "SELECT * FROM users WHERE id=?", (uid,)
        ).fetchone()

        n = c.execute(
            "SELECT COUNT(*) FROM plates WHERE owner_id=?", (uid,)
        ).fetchone()[0]

        cars = c.execute(
            "SELECT COUNT(*) FROM cars WHERE owner_id=?", (uid,)
        ).fetchone()[0]

        stats = c.execute(
            "SELECT * FROM user_stats WHERE user_id=?", (uid,)
        ).fetchone()

        club = c.execute("""
            SELECT cl.name FROM clubs cl
            JOIN club_members cm ON cm.club_id=cl.id
            WHERE cm.user_id=?
        """, (uid,)).fetchone()

    used = u["spins_used"] if u["spins_day"] == day() else 0

    return jsonify(
        id=uid,
        name=u["name"],
        username=u["username"],
        balance=u["balance"],
        xp=u["xp"],
        level=min(100, 1 + u["xp"] // 250),
        collection=n,
        cars=cars,
        spins_left=max(0, 20-used),
        club=club["name"] if club else None,
        bonus_ready=(
            u["balance"] < 500
            and now()-stats["last_bonus"] >= 86400
        ),
        is_admin=(uid == CREATOR_ID and CREATOR_ID != 0),
        demo=DEMO_MODE
    )


@app.post("/api/spin")
@auth
def spin(uid):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        u = c.execute(
            "SELECT spins_day,spins_used FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        used = u["spins_used"] if u["spins_day"] == day() else 0

        if used >= 20:
            return error("Сегодня попытки закончились")

        plate = None

        for _ in range(150):
            code, rarity = generate()

            try:
                cur = c.execute("""
                    INSERT INTO plates(code,rarity,owner_id,created_at)
                    VALUES(?,?,?,?)
                """, (code, rarity, uid, now()))

                plate = {
                    "id": cur.lastrowid,
                    "code": code,
                    "rarity": rarity,
                    "sell_price": SELL_PRICES[rarity]
                }
                break
            except sqlite3.IntegrityError:
                continue

        if plate is None:
            return error("Свободная комбинация не найдена", 503)

        c.execute("""
            UPDATE users
            SET spins_day=?,spins_used=?,xp=xp+10
            WHERE id=?
        """, (day(), used+1, uid))

        stat(c, uid, "plates_earned")

    return jsonify(
        plate=plate,
        spins_left=19-used
    )


@app.get("/api/collection")
@auth
def collection(uid):
    with db() as c:
        rows = c.execute("""
            SELECT p.id,p.code,p.rarity,p.created_at,p.favorite,
                   l.id AS listing_id,
                   a.id AS auction_id,
                   car.model AS installed_on
            FROM plates p
            LEFT JOIN listings l ON l.plate_id=p.id
            LEFT JOIN auctions a
              ON a.plate_id=p.id AND a.status='active'
            LEFT JOIN cars car ON car.plate_id=p.id
            WHERE p.owner_id=?
            ORDER BY p.favorite DESC,p.id DESC
            LIMIT 500
        """, (uid,)).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        item["sell_price"] = SELL_PRICES.get(item["rarity"], 25)
        result.append(item)

    return jsonify(plates=result)


@app.post("/api/favorite")
@auth
def favorite(uid):
    try:
        pid = integer(payload(), "plate_id")
    except ValueError:
        return error("Неверный ID")

    with db() as c:
        cur = c.execute("""
            UPDATE plates SET favorite=1-favorite
            WHERE id=? AND owner_id=?
        """, (pid, uid))

    return jsonify(ok=cur.rowcount == 1)


@app.get("/api/passport/<int:pid>")
@auth
def passport(uid, pid):
    with db() as c:
        plate = c.execute("""
            SELECT p.*,u.name AS owner
            FROM plates p
            JOIN users u ON u.id=p.owner_id
            WHERE p.id=?
        """, (pid,)).fetchone()

        if not plate:
            return error("Номер не найден", 404)

        history = c.execute("""
            SELECT t.price,t.created_at,
                   s.name AS seller,b.name AS buyer
            FROM trades t
            JOIN users s ON s.id=t.seller_id
            JOIN users b ON b.id=t.buyer_id
            WHERE t.plate_id=?
            ORDER BY t.id DESC LIMIT 30
        """, (pid,)).fetchall()

    return jsonify(
        plate=dict(plate),
        history=[dict(r) for r in history]
    )


@app.post("/api/sell-system")
@auth
def sell_system(uid):
    try:
        pid = integer(payload(), "plate_id")
    except ValueError:
        return error("Неверный ID")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        plate = c.execute("""
            SELECT rarity FROM plates
            WHERE id=? AND owner_id=?
        """, (pid, uid)).fetchone()

        if not plate:
            return error("Номер не найден")

        listed = c.execute(
            "SELECT 1 FROM listings WHERE plate_id=?", (pid,)
        ).fetchone()

        auction = c.execute("""
            SELECT 1 FROM auctions
            WHERE plate_id=? AND status='active'
        """, (pid,)).fetchone()

        installed = c.execute(
            "SELECT 1 FROM cars WHERE plate_id=?", (pid,)
        ).fetchone()

        if listed or auction or installed:
            return error("Сначала сними номер с продажи или автомобиля")

        price = SELL_PRICES.get(plate["rarity"], 25)

        c.execute("DELETE FROM plates WHERE id=?", (pid,))
        c.execute(
            "UPDATE users SET balance=balance+? WHERE id=?",
            (price, uid)
        )

    return jsonify(ok=True, earned=price)


@app.get("/api/cars/catalog")
@auth
def cars_catalog(uid):
    return jsonify(
        cars=[
            {"model": model, "price": price}
            for model, price in CARS
        ]
    )


@app.get("/api/cars")
@auth
def my_cars(uid):
    with db() as c:
        rows = c.execute("""
            SELECT car.*,p.code AS plate_code
            FROM cars car
            LEFT JOIN plates p ON p.id=car.plate_id
            WHERE car.owner_id=?
            ORDER BY car.id DESC
        """, (uid,)).fetchall()

    return jsonify(cars=[dict(r) for r in rows])


@app.post("/api/cars/buy")
@auth
def buy_car(uid):
    model = str(payload().get("model", ""))

    catalog = dict(CARS)
    if model not in catalog:
        return error("Автомобиль не найден")

    price = catalog[model]

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        paid = c.execute("""
            UPDATE users SET balance=balance-?
            WHERE id=? AND balance>=?
        """, (price, uid, price))

        if paid.rowcount != 1:
            return error("Недостаточно NC")

        c.execute("""
            INSERT INTO cars(owner_id,model,price,created_at)
            VALUES(?,?,?,?)
        """, (uid, model, price, now()))

        stat(c, uid, "cars_bought")

    return jsonify(ok=True)


@app.post("/api/cars/install")
@auth
def install_plate(uid):
    try:
        data = payload()
        car_id = integer(data, "car_id")
        plate_id = integer(data, "plate_id")
    except ValueError:
        return error("Некорректные данные")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        car = c.execute(
            "SELECT id FROM cars WHERE id=? AND owner_id=?",
            (car_id, uid)
        ).fetchone()

        plate = c.execute(
            "SELECT id FROM plates WHERE id=? AND owner_id=?",
            (plate_id, uid)
        ).fetchone()

        listed = c.execute(
            "SELECT 1 FROM listings WHERE plate_id=?",
            (plate_id,)
        ).fetchone()

        auction = c.execute("""
            SELECT 1 FROM auctions
            WHERE plate_id=? AND status='active'
        """, (plate_id,)).fetchone()

        if not car or not plate or listed or auction:
            return error("Номер или автомобиль недоступен")

        c.execute(
            "UPDATE cars SET plate_id=NULL WHERE plate_id=?",
            (plate_id,)
        )
        c.execute(
            "UPDATE cars SET plate_id=? WHERE id=?",
            (plate_id, car_id)
        )

    return jsonify(ok=True)


@app.get("/api/tasks")
@auth
def tasks(uid):
    with db() as c:
        stats = c.execute(
            "SELECT * FROM user_stats WHERE user_id=?",
            (uid,)
        ).fetchone()

        claimed = {
            r[0] for r in c.execute(
                "SELECT task_id FROM task_claims WHERE user_id=?",
                (uid,)
            ).fetchall()
        }

    result = []

    for task_id, title, desc, target, reward, xp, field in TASKS:
        progress = stats[field]

        result.append({
            "id": task_id,
            "title": title,
            "description": desc,
            "target": target,
            "progress": min(progress, target),
            "reward": reward,
            "xp": xp,
            "completed": progress >= target,
            "claimed": task_id in claimed
        })

    return jsonify(tasks=result)


@app.post("/api/tasks/claim")
@auth
def claim_task(uid):
    task_id = str(payload().get("task_id", ""))

    task = next((t for t in TASKS if t[0] == task_id), None)
    if not task:
        return error("Задание не найдено")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        stats = c.execute(
            "SELECT * FROM user_stats WHERE user_id=?",
            (uid,)
        ).fetchone()

        if stats[task[6]] < task[3]:
            return error("Задание ещё не выполнено")

        cur = c.execute("""
            INSERT OR IGNORE INTO task_claims
            (user_id,task_id,claimed_at)
            VALUES(?,?,?)
        """, (uid, task_id, now()))

        if cur.rowcount != 1:
            return error("Награда уже получена")

        c.execute("""
            UPDATE users SET balance=balance+?,xp=xp+?
            WHERE id=?
        """, (task[4], task[5], uid))

    return jsonify(ok=True, reward=task[4], xp=task[5])


@app.post("/api/bonus")
@auth
def bonus(uid):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        u = c.execute(
            "SELECT balance FROM users WHERE id=?",
            (uid,)
        ).fetchone()

        s = c.execute(
            "SELECT last_bonus FROM user_stats WHERE user_id=?",
            (uid,)
        ).fetchone()

        if u["balance"] >= 500:
            return error("Бонус доступен при балансе ниже 500 NC")

        if now()-s["last_bonus"] < 86400:
            return error("Бонус уже получен за последние 24 часа")

        c.execute(
            "UPDATE users SET balance=balance+1500 WHERE id=?",
            (uid,)
        )

        c.execute(
            "UPDATE user_stats SET last_bonus=? WHERE user_id=?",
            (now(), uid)
        )

    return jsonify(ok=True, earned=1500)


@app.post("/api/list")
@auth
def listing(uid):
    try:
        data = payload()
        pid = integer(data, "plate_id")
        price = integer(data, "price")
    except ValueError:
        return error("Некорректные данные")

    if not 100 <= price <= 100000000:
        return error("Цена от 100 до 100 000 000 NC")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        count = c.execute(
            "SELECT COUNT(*) FROM listings WHERE seller_id=?",
            (uid,)
        ).fetchone()[0]

        if count >= 3:
            return error("Можно выставить только 3 номера")

        owned = c.execute(
            "SELECT 1 FROM plates WHERE id=? AND owner_id=?",
            (pid, uid)
        ).fetchone()

        busy = c.execute("""
            SELECT 1 FROM auctions
            WHERE plate_id=? AND status='active'
        """, (pid,)).fetchone()

        installed = c.execute(
            "SELECT 1 FROM cars WHERE plate_id=?", (pid,)
        ).fetchone()

        listed = c.execute(
            "SELECT 1 FROM listings WHERE plate_id=?", (pid,)
        ).fetchone()

        if not owned or busy or installed or listed:
            return error("Номер недоступен для продажи")

        c.execute("""
            INSERT INTO listings(plate_id,seller_id,price,created_at)
            VALUES(?,?,?,?)
        """, (pid, uid, price, now()))

    return jsonify(ok=True)


@app.get("/api/market")
@auth
def market(uid):
    with db() as c:
        rows = c.execute("""
            SELECT l.id,l.price,l.seller_id,
                   p.code,p.rarity,u.name AS seller
            FROM listings l
            JOIN plates p ON p.id=l.plate_id
            JOIN users u ON u.id=l.seller_id
            ORDER BY l.id DESC LIMIT 100
        """).fetchall()

    return jsonify(listings=[dict(r) for r in rows])


@app.post("/api/cancel")
@auth
def cancel(uid):
    try:
        lid = integer(payload(), "listing_id")
    except ValueError:
        return error("Неверный ID")

    with db() as c:
        cur = c.execute(
            "DELETE FROM listings WHERE id=? AND seller_id=?",
            (lid, uid)
        )

    return jsonify(ok=cur.rowcount > 0)


@app.post("/api/buy")
@auth
def buy(uid):
    try:
        lid = integer(payload(), "listing_id")
    except ValueError:
        return error("Неверный ID")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        item = c.execute(
            "SELECT * FROM listings WHERE id=?", (lid,)
        ).fetchone()

        if not item:
            return error("Объявление закрыто", 404)

        if item["seller_id"] == uid:
            return error("Нельзя купить свой номер")

        price = item["price"]
        fee = (price*5+99)//100

        paid = c.execute("""
            UPDATE users SET balance=balance-?
            WHERE id=? AND balance>=?
        """, (price, uid, price))

        if paid.rowcount != 1:
            return error("Недостаточно NC")

        moved = c.execute("""
            UPDATE plates SET owner_id=?,favorite=0
            WHERE id=? AND owner_id=?
        """, (uid, item["plate_id"], item["seller_id"]))

        if moved.rowcount != 1:
            return error("Номер недоступен", 409)

        c.execute(
            "UPDATE users SET balance=balance+? WHERE id=?",
            (price-fee, item["seller_id"])
        )

        c.execute("DELETE FROM listings WHERE id=?", (lid,))

        c.execute("""
            INSERT INTO trades
            (plate_id,seller_id,buyer_id,price,created_at)
            VALUES(?,?,?,?,?)
        """, (
            item["plate_id"], item["seller_id"],
            uid, price, now()
        ))

        stat(c, uid, "buys")
        stat(c, item["seller_id"], "sales")

    return jsonify(ok=True)


@app.get("/api/auctions")
@auth
def auctions(uid):
    settle_auctions()

    with db() as c:
        rows = c.execute("""
            SELECT a.*,p.code,p.rarity,u.name AS seller
            FROM auctions a
            JOIN plates p ON p.id=a.plate_id
            JOIN users u ON u.id=a.seller_id
            WHERE a.status='active'
            ORDER BY a.ends_at ASC
            LIMIT 100
        """).fetchall()

    return jsonify(auctions=[dict(r) for r in rows])


@app.post("/api/auctions/create")
@auth
def create_auction(uid):
    try:
        data = payload()
        pid = integer(data, "plate_id")
        price = integer(data, "price")
    except ValueError:
        return error("Неверные данные")

    if not 100 <= price <= 100000000:
        return error("Некорректная цена")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        owned = c.execute(
            "SELECT 1 FROM plates WHERE id=? AND owner_id=?",
            (pid, uid)
        ).fetchone()

        listed = c.execute(
            "SELECT 1 FROM listings WHERE plate_id=?", (pid,)
        ).fetchone()

        installed = c.execute(
            "SELECT 1 FROM cars WHERE plate_id=?", (pid,)
        ).fetchone()

        active = c.execute("""
            SELECT 1 FROM auctions
            WHERE plate_id=? AND status='active'
        """, (pid,)).fetchone()

        if not owned or listed or installed or active:
            return error("Номер недоступен")

        # Один номер может иметь только один аукцион за всё время
        # в этой версии; повторный аукцион требует отдельной миграции.
        existing = c.execute(
            "SELECT 1 FROM auctions WHERE plate_id=?", (pid,)
        ).fetchone()

        if existing:
            return error("Этот номер уже участвовал в аукционе")

        c.execute("""
            INSERT INTO auctions
            (plate_id,seller_id,start_price,current_price,ends_at)
            VALUES(?,?,?,?,?)
        """, (pid, uid, price, price, now()+86400))

    return jsonify(ok=True)


@app.post("/api/auctions/bid")
@auth
def bid(uid):
    try:
        data = payload()
        aid = integer(data, "auction_id")
        amount = integer(data, "amount")
    except ValueError:
        return error("Неверные данные")

    if amount < 100 or amount > 100000000:
        return error("Некорректная ставка")

    settle_auctions()

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        a = c.execute("""
            SELECT * FROM auctions
            WHERE id=? AND status='active'
        """, (aid,)).fetchone()

        if not a or a["ends_at"] <= now():
            return error("Аукцион завершён")

        if a["seller_id"] == uid:
            return error("Нельзя делать ставку на свой номер")

        if a["bidder_id"] == uid:
            return error("Дождись другой ставки")

        minimum = (
            a["start_price"]
            if a["bidder_id"] is None
            else a["current_price"]+100
        )

        if amount < minimum:
            return error(f"Минимальная ставка: {minimum} NC")

        paid = c.execute("""
            UPDATE users SET balance=balance-?
            WHERE id=? AND balance>=?
        """, (amount, uid, amount))

        if paid.rowcount != 1:
            return error("Недостаточно NC")

        if a["bidder_id"] is not None:
            c.execute("""
                UPDATE users SET balance=balance+?
                WHERE id=?
            """, (a["current_price"], a["bidder_id"]))

        c.execute("""
            UPDATE auctions
            SET current_price=?,bidder_id=?
            WHERE id=?
        """, (amount, uid, aid))

    return jsonify(ok=True)


def settle_auctions():
    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        expired = c.execute("""
            SELECT * FROM auctions
            WHERE status='active' AND ends_at<=?
        """, (now(),)).fetchall()

        for a in expired:
            if a["bidder_id"] is not None:
                fee = (a["current_price"]*5+99)//100

                moved = c.execute("""
                    UPDATE plates SET owner_id=?,favorite=0
                    WHERE id=? AND owner_id=?
                """, (
                    a["bidder_id"], a["plate_id"], a["seller_id"]
                ))

                if moved.rowcount == 1:
                    c.execute("""
                        UPDATE users SET balance=balance+?
                        WHERE id=?
                    """, (a["current_price"]-fee, a["seller_id"]))

                    c.execute("""
                        INSERT INTO trades
                        (plate_id,seller_id,buyer_id,price,created_at)
                        VALUES(?,?,?,?,?)
                    """, (
                        a["plate_id"], a["seller_id"],
                        a["bidder_id"], a["current_price"], now()
                    ))

                    stat(c, a["bidder_id"], "buys")
                    stat(c, a["seller_id"], "sales")
                else:
                    c.execute("""
                        UPDATE users SET balance=balance+?
                        WHERE id=?
                    """, (a["current_price"], a["bidder_id"]))

            c.execute(
                "UPDATE auctions SET status='closed' WHERE id=?",
                (a["id"],)
            )


@app.get("/api/clubs")
@auth
def clubs(uid):
    with db() as c:
        rows = c.execute("""
            SELECT cl.id,cl.name,cl.owner_id,
                   COUNT(cm.user_id) AS members
            FROM clubs cl
            LEFT JOIN club_members cm ON cm.club_id=cl.id
            GROUP BY cl.id
            ORDER BY members DESC,cl.id ASC
            LIMIT 100
        """).fetchall()

    return jsonify(clubs=[dict(r) for r in rows])


@app.post("/api/clubs/create")
@auth
def create_club(uid):
    name = str(payload().get("name", "")).strip()

    if not 3 <= len(name) <= 30:
        return error("Название должно содержать 3–30 символов")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        existing = c.execute(
            "SELECT 1 FROM club_members WHERE user_id=?",
            (uid,)
        ).fetchone()

        if existing:
            return error("Ты уже состоишь в автоклубе")

        try:
            cur = c.execute("""
                INSERT INTO clubs(name,owner_id,created_at)
                VALUES(?,?,?)
            """, (name, uid, now()))
        except sqlite3.IntegrityError:
            return error("Такое название уже занято")

        c.execute("""
            INSERT INTO club_members(user_id,club_id,joined_at)
            VALUES(?,?,?)
        """, (uid, cur.lastrowid, now()))

    return jsonify(ok=True)


@app.post("/api/clubs/join")
@auth
def join_club(uid):
    try:
        club_id = integer(payload(), "club_id")
    except ValueError:
        return error("Неверный ID")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        club = c.execute(
            "SELECT 1 FROM clubs WHERE id=?", (club_id,)
        ).fetchone()

        member = c.execute(
            "SELECT 1 FROM club_members WHERE user_id=?",
            (uid,)
        ).fetchone()

        if not club or member:
            return error("Клуб не найден или ты уже состоишь в клубе")

        count = c.execute(
            "SELECT COUNT(*) FROM club_members WHERE club_id=?",
            (club_id,)
        ).fetchone()[0]

        if count >= 50:
            return error("В клубе нет свободных мест")

        c.execute("""
            INSERT INTO club_members(user_id,club_id,joined_at)
            VALUES(?,?,?)
        """, (uid, club_id, now()))

    return jsonify(ok=True)


@app.post("/api/clubs/leave")
@auth
def leave_club(uid):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        membership = c.execute("""
            SELECT cm.club_id,cl.owner_id
            FROM club_members cm
            JOIN clubs cl ON cl.id=cm.club_id
            WHERE cm.user_id=?
        """, (uid,)).fetchone()

        if not membership:
            return error("Ты не состоишь в клубе")

        if membership["owner_id"] == uid:
            return error("Владелец должен сначала распустить клуб")

        c.execute(
            "DELETE FROM club_members WHERE user_id=?",
            (uid,)
        )

    return jsonify(ok=True)


@app.post("/api/clubs/disband")
@auth
def disband_club(uid):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        club = c.execute(
            "SELECT id FROM clubs WHERE owner_id=?",
            (uid,)
        ).fetchone()

        if not club:
            return error("Ты не владелец клуба")

        c.execute(
            "DELETE FROM club_members WHERE club_id=?",
            (club["id"],)
        )
        c.execute(
            "DELETE FROM clubs WHERE id=?", (club["id"],)
        )

    return jsonify(ok=True)


@app.get("/api/top")
@auth
def top(uid):
    with db() as c:
        rows = c.execute("""
            SELECT u.id,u.name,u.balance,u.xp,
                   COUNT(p.id) AS collection
            FROM users u
            LEFT JOIN plates p ON p.owner_id=u.id
            GROUP BY u.id
            ORDER BY collection DESC,balance DESC
            LIMIT 30
        """).fetchall()

    return jsonify(players=[dict(r) for r in rows])


@app.get("/api/admin/players")
@auth
def admin_players(uid):
    if uid != CREATOR_ID or CREATOR_ID == 0:
        return error("Нет доступа", 403)

    with db() as c:
        rows = c.execute("""
            SELECT id,name,username,balance,xp
            FROM users ORDER BY created_at DESC LIMIT 100
        """).fetchall()

    return jsonify(players=[dict(r) for r in rows])


@app.post("/api/admin/grant")
@auth
def admin_grant(uid):
    if uid != CREATOR_ID or CREATOR_ID == 0:
        return error("Нет доступа", 403)

    try:
        data = payload()
        target = integer(data, "user_id")
        amount = integer(data, "amount")
        kind = str(data.get("kind", "balance"))
    except ValueError:
        return error("Неверные данные")

    if kind not in ("balance", "xp"):
        return error("Неверный тип начисления")

    if not -100000000 <= amount <= 100000000:
        return error("Слишком большое значение")

    with db() as c:
        c.execute("BEGIN IMMEDIATE")

        target_user = c.execute(
            "SELECT id FROM users WHERE id=?", (target,)
        ).fetchone()

        if not target_user:
            return error("Игрок не найден")

        c.execute(
            f"UPDATE users SET {kind}=MAX(0,{kind}+?) WHERE id=?",
            (amount, target)
        )

        c.execute("""
            INSERT INTO admin_logs
            (admin_id,target_id,action,amount,created_at)
            VALUES(?,?,?,?,?)
        """, (uid, target, kind, amount, now()))

    return jsonify(ok=True)


init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000"))
    )
