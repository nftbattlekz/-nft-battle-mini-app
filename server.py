import os
import time
import json
import hmac
import hashlib
import random
import sqlite3
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="web")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# ID СОЗДАТЕЛЯ NEXORA
CREATOR_TELEGRAM_ID = "8518976778"

DB_PATH = "nexora.db"


# =========================================================
# NFT
# =========================================================

NFTS = []

RARITIES = [
    ("Common", 1, 12, 40, 90),
    ("Rare", 13, 24, 120, 250),
    ("Epic", 25, 36, 350, 700),
    ("Legendary", 37, 48, 1000, 2300),
    ("Mythic", 49, 60, 3000, 8500),
]

NFT_NAMES = [
    "Neon Core",
    "Red Pulse",
    "Dark Byte",
    "Cyber Eye",
    "Void Chip",
    "Nova Gear",
    "Chrome Soul",
    "Pixel Flame",
    "Shadow Key",
    "Digital Fang",
    "Quantum Coin",
    "Nexus Spark",

    "Blood Circuit",
    "Night Runner",
    "Cyber Wolf",
    "Neon Phantom",
    "Red Protocol",
    "Dark Matrix",
    "Ghost Drive",
    "Chrome Beast",
    "Zero Signal",
    "Black Nova",
    "Cyber Fang",
    "Pulse Hunter",

    "Omega Core",
    "Void Walker",
    "Neon Samurai",
    "Quantum Beast",
    "Dark Emperor",
    "Cyber Dragon",
    "Red Horizon",
    "Phantom X",
    "Night Protocol",
    "Digital Demon",
    "Nexus King",
    "Infinity Gear",

    "Galaxy Hunter",
    "Shadow Emperor",
    "Neon Titan",
    "Quantum Lord",
    "Cyber God",
    "Void Master",
    "Red Titan",
    "Dark Phoenix",
    "Chrome Legend",
    "Omega Dragon",
    "Night King",
    "Nexus Prime",

    "Mythic Core",
    "Absolute Zero",
    "Black Universe",
    "Neon Overlord",
    "Quantum Emperor",
    "Void King",
    "Cyber Overlord",
    "Infinity Soul",
    "Dark Universe",
    "NEXORA One",
    "Eternal Nexus",
    "Genesis",
]

for rarity, start_id, end_id, min_value, max_value in RARITIES:
    for nft_id in range(start_id, end_id + 1):

        index = nft_id - start_id

        value = min_value + int(
            (max_value - min_value)
            * (index / max(1, end_id - start_id))
        )

        NFTS.append({
            "id": nft_id,
            "name": NFT_NAMES[nft_id - 1],
            "rarity": rarity,
            "value": value
        })

NFT_BY_ID = {
    nft["id"]: nft
    for nft in NFTS
}


# =========================================================
# CASES
# =========================================================

CASES = [
    {
        "id": 1,
        "name": "STARTER",
        "subtitle": "Первый шаг",
        "pool": list(range(1, 13)),
        "accent": "blue"
    },
    {
        "id": 2,
        "name": "NEON",
        "subtitle": "Неоновая серия",
        "pool": list(range(4, 25)),
        "accent": "pink"
    },
    {
        "id": 3,
        "name": "SHADOW",
        "subtitle": "Тёмная коллекция",
        "pool": list(range(13, 37)),
        "accent": "purple"
    },
    {
        "id": 4,
        "name": "CYBER",
        "subtitle": "Киберсерия",
        "pool": list(range(13, 49)),
        "accent": "red"
    },
    {
        "id": 5,
        "name": "GALAXY",
        "subtitle": "Галактический дроп",
        "pool": list(range(25, 49)),
        "accent": "violet"
    },
    {
        "id": 6,
        "name": "QUANTUM",
        "subtitle": "Квантовая серия",
        "pool": list(range(29, 55)),
        "accent": "cyan"
    },
    {
        "id": 7,
        "name": "OMEGA",
        "subtitle": "Омега уровень",
        "pool": list(range(37, 61)),
        "accent": "orange"
    },
    {
        "id": 8,
        "name": "LEGEND",
        "subtitle": "Легендарный дроп",
        "pool": list(range(37, 61)),
        "accent": "gold"
    },
    {
        "id": 9,
        "name": "MYTHIC",
        "subtitle": "Мифическая серия",
        "pool": list(range(49, 61)),
        "accent": "mythic"
    },
    {
        "id": 10,
        "name": "NEXORA",
        "subtitle": "Вся коллекция",
        "pool": list(range(1, 61)),
        "accent": "nexora"
    }
]


# =========================================================
# PREFIXES
# =========================================================

PREFIXES = [
    {"id": 1, "name": "Новичок", "display": "⚡ Новичок", "price": 1000},
    {"id": 2, "name": "Охотник", "display": "🎯 Охотник", "price": 2500},
    {"id": 3, "name": "Кибер", "display": "🤖 Кибер", "price": 5000},
    {"id": 4, "name": "Неон", "display": "💠 Неон", "price": 7500},
    {"id": 5, "name": "Призрак", "display": "👻 Призрак", "price": 10000},
    {"id": 6, "name": "Ворон", "display": "🐦‍⬛ Ворон", "price": 15000},
    {"id": 7, "name": "Самурай", "display": "⚔️ Самурай", "price": 22000},
    {"id": 8, "name": "Титан", "display": "🗿 Титан", "price": 30000},
    {"id": 9, "name": "Император", "display": "👑 Император", "price": 40000},
    {"id": 10, "name": "Повелитель", "display": "🔥 Повелитель", "price": 55000},
    {"id": 11, "name": "Владыка", "display": "🌑 Владыка", "price": 70000},
    {"id": 12, "name": "Нексус", "display": "🔮 Нексус", "price": 90000},
    {"id": 13, "name": "Омега", "display": "Ω Омега", "price": 115000},
    {"id": 14, "name": "Легенда", "display": "🏆 Легенда", "price": 145000},
    {"id": 15, "name": "Мифик", "display": "💎 Мифик", "price": 180000},
    {"id": 16, "name": "Бессмертный", "display": "♾️ Бессмертный", "price": 220000},
    {"id": 17, "name": "Архитектор", "display": "🧬 Архитектор", "price": 275000},
    {"id": 18, "name": "Создатель", "display": "🛠️ Создатель", "price": 350000},
    {"id": 19, "name": "Абсолют", "display": "✦ Абсолют", "price": 450000},
    {"id": 20, "name": "NEXORA ELITE", "display": "✧ NEXORA ELITE", "price": 600000},
]

PREFIX_BY_ID = {
    prefix["id"]: prefix
    for prefix in PREFIXES
}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id TEXT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            coins INTEGER DEFAULT 1000,
            total_opened INTEGER DEFAULT 0,
            total_received_value INTEGER DEFAULT 0,
            prefix_id INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS nfts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT NOT NULL,
            nft_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)

    columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
    ]

    if "prefix_id" not in columns:

        conn.execute("""
            ALTER TABLE users
            ADD COLUMN prefix_id INTEGER DEFAULT 0
        """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# TELEGRAM AUTH
# =========================================================

def validate_telegram_data(init_data):

    if not init_data or not BOT_TOKEN:
        return None

    try:

        pairs = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = pairs.pop("hash", None)

        if not received_hash:
            return None

        auth_date = int(
            pairs.get("auth_date", "0")
        )

        if time.time() - auth_date > 86400:
            return None

        data_check_string = "\n".join(
            f"{key}={pairs[key]}"
            for key in sorted(pairs)
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

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            return None

        user_data = json.loads(
            pairs.get("user", "{}")
        )

        if not user_data.get("id"):
            return None

        return user_data

    except Exception:
        return None


def get_current_user_data():

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    user = validate_telegram_data(init_data)

    if user:

        return {
            "id": str(user["id"]),
            "username": user.get(
                "username",
                ""
            ),
            "first_name": user.get(
                "first_name",
                "Player"
            )
        }

    return {
        "id": "demo_user",
        "username": "demo",
        "first_name": "Demo"
    }


def is_creator(telegram_id):

    return str(telegram_id) == CREATOR_TELEGRAM_ID


# =========================================================
# USER
# =========================================================

def ensure_user(user):

    conn = get_db()

    existing = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    if not existing:

        conn.execute("""
            INSERT INTO users (
                telegram_id,
                username,
                first_name,
                coins,
                total_opened,
                total_received_value,
                prefix_id
            )
            VALUES (?, ?, ?, 1000, 0, 0, 0)
        """, (
            user["id"],
            user["username"],
            user["first_name"]
        ))

    else:

        conn.execute("""
            UPDATE users
            SET username = ?,
                first_name = ?
            WHERE telegram_id = ?
        """, (
            user["username"],
            user["first_name"],
            user["id"]
        ))

    conn.commit()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    conn.close()

    return row


def collection_value(telegram_id):

    conn = get_db()

    rows = conn.execute("""
        SELECT nft_id
        FROM nfts
        WHERE telegram_id = ?
    """, (
        telegram_id,
    )).fetchall()

    conn.close()

    total = 0

    for row in rows:

        nft = NFT_BY_ID.get(
            row["nft_id"]
        )

        if nft:
            total += nft["value"]

    return total


def serialize_user(row):

    prefix_id = row["prefix_id"] or 0

    prefix = PREFIX_BY_ID.get(
        prefix_id
    )

    return {
        "telegram_id": row["telegram_id"],
        "username": row["username"],
        "first_name": row["first_name"],
        "coins": row["coins"],
        "total_opened": row["total_opened"],
        "total_received_value":
            row["total_received_value"],
        "collection_value":
            collection_value(
                row["telegram_id"]
            ),
        "prefix_id": prefix_id,
        "prefix":
            prefix["display"]
            if prefix
            else "",
        "creator":
            is_creator(
                row["telegram_id"]
            )
    }


# =========================================================
# ME
# =========================================================

@app.route("/api/me")
def api_me():

    user = get_current_user_data()

    row = ensure_user(user)

    return jsonify({
        "ok": True,
        "user": serialize_user(row)
    })


# =========================================================
# CASES
# =========================================================

@app.route("/api/cases")
def api_cases():

    result = []

    for case in CASES:

        result.append({
            "id": case["id"],
            "name": case["name"],
            "subtitle": case["subtitle"],
            "accent": case["accent"],
            "free": True
        })

    return jsonify({
        "ok": True,
        "cases": result
    })


# =========================================================
# OPEN CASE
# =========================================================

@app.route(
    "/api/cases/open",
    methods=["POST"]
)
def open_case():

    user = get_current_user_data()

    ensure_user(user)

    data = request.get_json(
        silent=True
    ) or {}

    try:
        case_id = int(
            data.get("case_id", 0)
        )
    except:
        case_id = 0

    case = next(
        (
            c for c in CASES
            if c["id"] == case_id
        ),
        None
    )

    if not case:

        return jsonify({
            "ok": False,
            "error": "Кейс не найден"
        }), 404

    nft_id = random.choice(
        case["pool"]
    )

    nft = NFT_BY_ID[nft_id]

    conn = get_db()

    conn.execute("""
        INSERT INTO nfts (
            telegram_id,
            nft_id,
            created_at
        )
        VALUES (?, ?, ?)
    """, (
        user["id"],
        nft_id,
        int(time.time())
    ))

    conn.execute("""
        UPDATE users
        SET total_opened =
                total_opened + 1,
            total_received_value =
                total_received_value + ?
        WHERE telegram_id = ?
    """, (
        nft["value"],
        user["id"]
    ))

    conn.commit()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "reward": nft,
        "user": serialize_user(row)
    })


# =========================================================
# INVENTORY
# =========================================================

@app.route("/api/inventory")
def api_inventory():

    user = get_current_user_data()

    ensure_user(user)

    conn = get_db()

    rows = conn.execute("""
        SELECT
            id,
            nft_id,
            created_at
        FROM nfts
        WHERE telegram_id = ?
        ORDER BY id DESC
    """, (
        user["id"],
    )).fetchall()

    conn.close()

    inventory = []

    for row in rows:

        nft = NFT_BY_ID.get(
            row["nft_id"]
        )

        if nft:

            inventory.append({
                "instance_id":
                    row["id"],
                "id":
                    nft["id"],
                "name":
                    nft["name"],
                "rarity":
                    nft["rarity"],
                "value":
                    nft["value"],
                "created_at":
                    row["created_at"]
            })

    return jsonify({
        "ok": True,
        "inventory": inventory
    })


# =========================================================
# SELL NFT
# =========================================================

@app.route(
    "/api/sell",
    methods=["POST"]
)
def sell_nft():

    user = get_current_user_data()

    ensure_user(user)

    data = request.get_json(
        silent=True
    ) or {}

    try:
        instance_id = int(
            data.get("instance_id", 0)
        )
    except:
        instance_id = 0

    conn = get_db()

    nft_row = conn.execute("""
        SELECT id, nft_id
        FROM nfts
        WHERE id = ?
        AND telegram_id = ?
    """, (
        instance_id,
        user["id"]
    )).fetchone()

    if not nft_row:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "NFT не найден"
        }), 404

    nft = NFT_BY_ID.get(
        nft_row["nft_id"]
    )

    if not nft:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "NFT не найден"
        }), 404

    conn.execute("""
        DELETE FROM nfts
        WHERE id = ?
    """, (
        instance_id,
    ))

    conn.execute("""
        UPDATE users
        SET coins = coins + ?
        WHERE telegram_id = ?
    """, (
        nft["value"],
        user["id"]
    ))

    conn.commit()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "sold": nft,
        "user": serialize_user(row)
    })


# =========================================================
# PREFIXES
# =========================================================

@app.route("/api/prefixes")
def api_prefixes():

    user = get_current_user_data()

    row = ensure_user(user)

    current_id = row["prefix_id"] or 0

    result = []

    for prefix in PREFIXES:

        result.append({
            **prefix,
            "owned":
                prefix["id"] == current_id,
            "equipped":
                prefix["id"] == current_id
        })

    return jsonify({
        "ok": True,
        "prefixes": result,
        "current_prefix_id":
            current_id
    })


# =========================================================
# BUY PREFIX
# =========================================================

@app.route(
    "/api/prefixes/buy",
    methods=["POST"]
)
def buy_prefix():

    user = get_current_user_data()

    ensure_user(user)

    data = request.get_json(
        silent=True
    ) or {}

    try:
        prefix_id = int(
            data.get("prefix_id", 0)
        )
    except:
        prefix_id = 0

    prefix = PREFIX_BY_ID.get(
        prefix_id
    )

    if not prefix:

        return jsonify({
            "ok": False,
            "error": "Префикс не найден"
        }), 404

    conn = get_db()

    current = conn.execute("""
        SELECT coins, prefix_id
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    if current["prefix_id"] == prefix_id:

        conn.close()

        return jsonify({
            "ok": False,
            "error":
                "Этот префикс уже установлен"
        }), 400

    if current["coins"] < prefix["price"]:

        conn.close()

        return jsonify({
            "ok": False,
            "error":
                "Недостаточно 💎"
        }), 400

    conn.execute("""
        UPDATE users
        SET coins = coins - ?,
            prefix_id = ?
        WHERE telegram_id = ?
    """, (
        prefix["price"],
        prefix_id,
        user["id"]
    ))

    conn.commit()

    updated = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "prefix": prefix,
        "user":
            serialize_user(updated)
    })


# =========================================================
# REMOVE PREFIX
# =========================================================

@app.route(
    "/api/prefixes/equip",
    methods=["POST"]
)
def equip_prefix():

    user = get_current_user_data()

    ensure_user(user)

    data = request.get_json(
        silent=True
    ) or {}

    try:
        prefix_id = int(
            data.get("prefix_id", 0)
        )
    except:
        prefix_id = 0

    if (
        prefix_id != 0
        and prefix_id not in PREFIX_BY_ID
    ):

        return jsonify({
            "ok": False,
            "error":
                "Префикс не найден"
        }), 404

    conn = get_db()

    conn.execute("""
        UPDATE users
        SET prefix_id = ?
        WHERE telegram_id = ?
    """, (
        prefix_id,
        user["id"]
    ))

    conn.commit()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "user":
            serialize_user(row)
    })


# =========================================================
# RATING
# =========================================================

@app.route("/api/leaderboard")
def leaderboard():

    conn = get_db()

    users = conn.execute("""
        SELECT
            telegram_id,
            username,
            first_name,
            coins,
            total_opened,
            prefix_id
        FROM users
    """).fetchall()

    nft_rows = conn.execute("""
        SELECT
            telegram_id,
            nft_id
        FROM nfts
    """).fetchall()

    conn.close()

    # =====================================================
    # СЧИТАЕМ СТОИМОСТЬ ВСЕХ NFT
    # =====================================================

    collection_by_user = {}

    for nft_row in nft_rows:

        nft = NFT_BY_ID.get(
            nft_row["nft_id"]
        )

        if not nft:
            continue

        telegram_id = nft_row["telegram_id"]

        collection_by_user[
            telegram_id
        ] = (
            collection_by_user.get(
                telegram_id,
                0
            )
            + nft["value"]
        )


    players = []

    for row in users:

        collection =
            collection_by_user.get(
                row["telegram_id"],
                0
            )

        prefix_id = row["prefix_id"] or 0

        prefix = PREFIX_BY_ID.get(
            prefix_id
        )

        # Рейтинг =
        # текущие 💎 + стоимость NFT
        score = (
            row["coins"]
            + collection
        )

        players.append({
            "telegram_id":
                row["telegram_id"],

            "username":
                row["username"],

            "first_name":
                row["first_name"],

            "coins":
                row["coins"],

            "total_opened":
                row["total_opened"],

            "collection_value":
                collection,

            "score":
                score,

            "prefix":
                prefix["display"]
                if prefix
                else "",

            "creator":
                is_creator(
                    row["telegram_id"]
                )
        })


    players.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    for index, player in enumerate(
        players,
        start=1
    ):
        player["rank"] = index


    return jsonify({
        "ok": True,
        "players": players[:50]
    })


# =========================================================
# FRONTEND
# =========================================================

@app.route("/")
def index():

    return send_from_directory(
        "web",
        "index.html"
    )


@app.route("/<path:path>")
def static_files(path):

    return send_from_directory(
        "web",
        path
    )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
