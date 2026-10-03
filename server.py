import os
import sqlite3
import json
import hmac
import hashlib
import urllib.parse
import random

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DB_PATH = os.path.join(BASE_DIR, "nexora.db")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")


# =========================================================
# NFT DATABASE
# =========================================================

NFTS = [
    # COMMON
    {"id": 1, "name": "Cyber Cat", "rarity": "Common", "value": 100, "icon": "🐱"},
    {"id": 2, "name": "Pixel Dog", "rarity": "Common", "value": 110, "icon": "🐶"},
    {"id": 3, "name": "Neon Duck", "rarity": "Common", "value": 120, "icon": "🦆"},
    {"id": 4, "name": "Blue Cube", "rarity": "Common", "value": 130, "icon": "🔷"},
    {"id": 5, "name": "Red Cube", "rarity": "Common", "value": 140, "icon": "🔴"},
    {"id": 6, "name": "Pixel Ghost", "rarity": "Common", "value": 150, "icon": "👻"},
    {"id": 7, "name": "Mini Robot", "rarity": "Common", "value": 160, "icon": "🤖"},
    {"id": 8, "name": "Digital Skull", "rarity": "Common", "value": 170, "icon": "💀"},
    {"id": 9, "name": "Neon Smile", "rarity": "Common", "value": 180, "icon": "😎"},
    {"id": 10, "name": "Cyber Ball", "rarity": "Common", "value": 190, "icon": "🔮"},
    {"id": 11, "name": "Pink Pixel", "rarity": "Common", "value": 200, "icon": "🩷"},
    {"id": 12, "name": "Green Pixel", "rarity": "Common", "value": 210, "icon": "🟢"},

    # RARE
    {"id": 13, "name": "Neon Samurai", "rarity": "Rare", "value": 300, "icon": "⚔️"},
    {"id": 14, "name": "Shadow Wolf", "rarity": "Rare", "value": 340, "icon": "🐺"},
    {"id": 15, "name": "Chrome Rider", "rarity": "Rare", "value": 380, "icon": "🏍️"},
    {"id": 16, "name": "Cyber Fox", "rarity": "Rare", "value": 420, "icon": "🦊"},
    {"id": 17, "name": "Neon Tiger", "rarity": "Rare", "value": 450, "icon": "🐯"},
    {"id": 18, "name": "Dark Eagle", "rarity": "Rare", "value": 480, "icon": "🦅"},
    {"id": 19, "name": "Cyber Panda", "rarity": "Rare", "value": 520, "icon": "🐼"},
    {"id": 20, "name": "Laser Snake", "rarity": "Rare", "value": 550, "icon": "🐍"},
    {"id": 21, "name": "Neon Dragon", "rarity": "Rare", "value": 580, "icon": "🐲"},
    {"id": 22, "name": "Chrome Skull", "rarity": "Rare", "value": 620, "icon": "💀"},
    {"id": 23, "name": "Digital Shark", "rarity": "Rare", "value": 650, "icon": "🦈"},
    {"id": 24, "name": "Cyber Crow", "rarity": "Rare", "value": 680, "icon": "🐦‍⬛"},

    # EPIC
    {"id": 25, "name": "Cyber Knight", "rarity": "Epic", "value": 800, "icon": "🛡️"},
    {"id": 26, "name": "Void Guardian", "rarity": "Epic", "value": 900, "icon": "👾"},
    {"id": 27, "name": "Galaxy Wolf", "rarity": "Epic", "value": 1000, "icon": "🐺"},
    {"id": 28, "name": "Neon Demon", "rarity": "Epic", "value": 1100, "icon": "😈"},
    {"id": 29, "name": "Quantum Fox", "rarity": "Epic", "value": 1200, "icon": "🦊"},
    {"id": 30, "name": "Cyber Reaper", "rarity": "Epic", "value": 1300, "icon": "☠️"},
    {"id": 31, "name": "Digital Dragon", "rarity": "Epic", "value": 1400, "icon": "🐉"},
    {"id": 32, "name": "Chrome Samurai", "rarity": "Epic", "value": 1500, "icon": "🥷"},
    {"id": 33, "name": "Neon Mecha", "rarity": "Epic", "value": 1600, "icon": "🤖"},
    {"id": 34, "name": "Void Beast", "rarity": "Epic", "value": 1700, "icon": "👹"},
    {"id": 35, "name": "Cyber Phoenix", "rarity": "Epic", "value": 1800, "icon": "🔥"},
    {"id": 36, "name": "Galaxy Rider", "rarity": "Epic", "value": 1900, "icon": "🏎️"},

    # LEGENDARY
    {"id": 37, "name": "Galaxy Dragon", "rarity": "Legendary", "value": 2500, "icon": "🐉"},
    {"id": 38, "name": "Quantum Ghost", "rarity": "Legendary", "value": 2800, "icon": "👻"},
    {"id": 39, "name": "Cyber Emperor", "rarity": "Legendary", "value": 3100, "icon": "👑"},
    {"id": 40, "name": "Void Dragon", "rarity": "Legendary", "value": 3400, "icon": "🐲"},
    {"id": 41, "name": "Neon Phoenix", "rarity": "Legendary", "value": 3700, "icon": "🔥"},
    {"id": 42, "name": "Omega Samurai", "rarity": "Legendary", "value": 4000, "icon": "⚔️"},
    {"id": 43, "name": "Galaxy Titan", "rarity": "Legendary", "value": 4300, "icon": "🤖"},
    {"id": 44, "name": "Quantum Knight", "rarity": "Legendary", "value": 4600, "icon": "🛡️"},
    {"id": 45, "name": "Cyber Leviathan", "rarity": "Legendary", "value": 4900, "icon": "🐋"},
    {"id": 46, "name": "Void King", "rarity": "Legendary", "value": 5200, "icon": "👑"},
    {"id": 47, "name": "Neon Beast", "rarity": "Legendary", "value": 5500, "icon": "👹"},
    {"id": 48, "name": "Digital Phoenix", "rarity": "Legendary", "value": 5800, "icon": "🪽"},

    # MYTHIC
    {"id": 49, "name": "Omega Titan", "rarity": "Mythic", "value": 7000, "icon": "🤖"},
    {"id": 50, "name": "NEXORA Prime", "rarity": "Mythic", "value": 8000, "icon": "💠"},
    {"id": 51, "name": "Galaxy Emperor", "rarity": "Mythic", "value": 9000, "icon": "👑"},
    {"id": 52, "name": "Void Overlord", "rarity": "Mythic", "value": 10000, "icon": "🌑"},
    {"id": 53, "name": "Quantum Dragon", "rarity": "Mythic", "value": 11000, "icon": "🐉"},
    {"id": 54, "name": "Cyber God", "rarity": "Mythic", "value": 12000, "icon": "⚡"},
    {"id": 55, "name": "Neon Destroyer", "rarity": "Mythic", "value": 13000, "icon": "☄️"},
    {"id": 56, "name": "Omega Phoenix", "rarity": "Mythic", "value": 14000, "icon": "🔥"},
    {"id": 57, "name": "NEXORA Dragon", "rarity": "Mythic", "value": 15000, "icon": "🐲"},
    {"id": 58, "name": "Infinite Knight", "rarity": "Mythic", "value": 16000, "icon": "🛡️"},
    {"id": 59, "name": "Digital God", "rarity": "Mythic", "value": 18000, "icon": "✨"},
    {"id": 60, "name": "NEXORA Genesis", "rarity": "Mythic", "value": 20000, "icon": "💎"},
]


NFT_BY_ID = {x["id"]: x for x in NFTS}


# =========================================================
# 10 CASES
# =========================================================

CASE_DEFINITIONS = [
    {
        "id": 1,
        "name": "STARTER",
        "subtitle": "Первый шаг",
        "icon": "📦",
        "pool": list(range(1, 13))
    },
    {
        "id": 2,
        "name": "NEON",
        "subtitle": "Неоновая серия",
        "icon": "🌈",
        "pool": list(range(4, 25))
    },
    {
        "id": 3,
        "name": "SHADOW",
        "subtitle": "Тёмная коллекция",
        "icon": "🌑",
        "pool": list(range(13, 37))
    },
    {
        "id": 4,
        "name": "CYBER",
        "subtitle": "Кибер-серия",
        "icon": "🤖",
        "pool": list(range(13, 49))
    },
    {
        "id": 5,
        "name": "GALAXY",
        "subtitle": "Космическая серия",
        "icon": "🌌",
        "pool": list(range(25, 49))
    },
    {
        "id": 6,
        "name": "QUANTUM",
        "subtitle": "Квантовая коллекция",
        "icon": "⚛️",
        "pool": list(range(29, 55))
    },
    {
        "id": 7,
        "name": "OMEGA",
        "subtitle": "Omega collection",
        "icon": "⚡",
        "pool": list(range(37, 61))
    },
    {
        "id": 8,
        "name": "LEGEND",
        "subtitle": "Легендарные NFT",
        "icon": "👑",
        "pool": list(range(37, 61))
    },
    {
        "id": 9,
        "name": "MYTHIC",
        "subtitle": "Mythic collection",
        "icon": "💎",
        "pool": list(range(49, 61))
    },
    {
        "id": 10,
        "name": "NEXORA",
        "subtitle": "Главная коллекция",
        "icon": "💠",
        "pool": list(range(1, 61))
    },
]


# =========================================================
# DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            first_name TEXT DEFAULT '',
            username TEXT DEFAULT '',
            coins INTEGER DEFAULT 1000,
            total_received_value INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS nfts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nft_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# TELEGRAM AUTH
# =========================================================

def validate_telegram_data(init_data):
    if not BOT_TOKEN:
        return None

    if not init_data:
        return None

    try:
        parsed = urllib.parse.parse_qs(
            init_data,
            keep_blank_values=True
        )

        received_hash = parsed.pop(
            "hash",
            [None]
        )[0]

        if not received_hash:
            return None

        data_check = []

        for key in sorted(parsed.keys()):
            value = parsed[key][0]
            data_check.append(
                f"{key}={value}"
            )

        data_check_string = "\n".join(
            data_check
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
            parsed["user"][0]
        )

        return user_data

    except Exception:
        return None


def current_user():
    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    telegram_user = validate_telegram_data(
        init_data
    )

    if telegram_user:
        return telegram_user

    # Для локального тестирования
    return {
        "id": 999999999,
        "first_name": "Demo",
        "username": "demo"
    }


# =========================================================
# SERIALIZATION
# =========================================================

def nft_json(nft_row):
    nft = NFT_BY_ID.get(
        nft_row["nft_id"]
    )

    if not nft:
        return None

    return {
        "id": nft_row["id"],
        "nft_id": nft["id"],
        "name": nft["name"],
        "rarity": nft["rarity"],
        "value": nft["value"],
        "icon": nft["icon"]
    }


def user_json(user_id):
    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        return None

    rows = conn.execute(
        """
        SELECT *
        FROM nfts
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,)
    ).fetchall()

    collection = []

    for row in rows:
        item = nft_json(row)
        if item:
            collection.append(item)

    conn.close()

    return {
        "id": user["id"],
        "first_name": user["first_name"],
        "username": user["username"],
        "coins": user["coins"],
        "total_received_value": user["total_received_value"],
        "nfts": collection
    }


# =========================================================
# CREATE / UPDATE USER
# =========================================================

def ensure_user(telegram_user):
    user_id = int(
        telegram_user["id"]
    )

    first_name = telegram_user.get(
        "first_name",
        "Player"
    )

    username = telegram_user.get(
        "username",
        ""
    )

    conn = db()

    existing = conn.execute(
        "SELECT id FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not existing:

        conn.execute(
            """
            INSERT INTO users
            (id, first_name, username, coins)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                first_name,
                username,
                1000
            )
        )

        # Стартовый NFT
        conn.execute(
            """
            INSERT INTO nfts
            (user_id, nft_id)
            VALUES (?, ?)
            """,
            (
                user_id,
                1
            )
        )

        conn.execute(
            """
            UPDATE users
            SET total_received_value = ?
            WHERE id = ?
            """,
            (
                NFT_BY_ID[1]["value"],
                user_id
            )
        )

    else:

        conn.execute(
            """
            UPDATE users
            SET first_name = ?,
                username = ?
            WHERE id = ?
            """,
            (
                first_name,
                username,
                user_id
            )
        )

    conn.commit()
    conn.close()

    return user_id


# =========================================================
# API
# =========================================================

@app.route("/")
def index():
    return send_from_directory(
        WEB_DIR,
        "index.html"
    )


@app.route("/health")
def health():
    return jsonify({
        "status": "ok"
    })


@app.route("/api/me", methods=["POST", "GET"])
def me():

    telegram_user = current_user()

    user_id = ensure_user(
        telegram_user
    )

    return jsonify(
        user_json(user_id)
    )


@app.route("/api/cases", methods=["GET"])
def cases():

    result = []

    for case in CASE_DEFINITIONS:

        nft_pool = [
            NFT_BY_ID[n]
            for n in case["pool"]
            if n in NFT_BY_ID
        ]

        result.append({
            "id": case["id"],
            "name": case["name"],
            "subtitle": case["subtitle"],
            "icon": case["icon"],
            "count": len(nft_pool),
            "pool": nft_pool
        })

    return jsonify(result)


@app.route("/api/cases/open", methods=["POST"])
def open_case():

    telegram_user = current_user()

    user_id = ensure_user(
        telegram_user
    )

    data = request.get_json(
        silent=True
    ) or {}

    case_id = int(
        data.get("case_id", 0)
    )

    selected_case = next(
        (
            x for x in CASE_DEFINITIONS
            if x["id"] == case_id
        ),
        None
    )

    if not selected_case:
        return jsonify({
            "error": "Кейс не найден"
        }), 404

    pool = [
        NFT_BY_ID[n]
        for n in selected_case["pool"]
        if n in NFT_BY_ID
    ]

    if not pool:
        return jsonify({
            "error": "В кейсе нет NFT"
        }), 400

    # Случайный NFT
    reward = random.choice(pool)

    conn = db()

    conn.execute(
        """
        INSERT INTO nfts
        (user_id, nft_id)
        VALUES (?, ?)
        """,
        (
            user_id,
            reward["id"]
        )
    )

    conn.execute(
        """
        UPDATE users
        SET total_received_value =
            total_received_value + ?
        WHERE id = ?
        """,
        (
            reward["value"],
            user_id
        )
    )

    conn.commit()
    conn.close()

    return jsonify(
        user_json(user_id)
    )


@app.route("/api/sell", methods=["POST"])
def sell():

    telegram_user = current_user()

    user_id = ensure_user(
        telegram_user
    )

    data = request.get_json(
        silent=True
    ) or {}

    inventory_id = int(
        data.get("nft_id", 0)
    )

    conn = db()

    nft_row = conn.execute(
        """
        SELECT *
        FROM nfts
        WHERE id = ?
        AND user_id = ?
        """,
        (
            inventory_id,
            user_id
        )
    ).fetchone()

    if not nft_row:

        conn.close()

        return jsonify({
            "error": "NFT не найден"
        }), 404

    nft = NFT_BY_ID.get(
        nft_row["nft_id"]
    )

    if not nft:

        conn.close()

        return jsonify({
            "error": "NFT повреждён"
        }), 400

    conn.execute(
        "DELETE FROM nfts WHERE id = ?",
        (inventory_id,)
    )

    conn.execute(
        """
        UPDATE users
        SET coins = coins + ?
        WHERE id = ?
        """,
        (
            nft["value"],
            user_id
        )
    )

    conn.commit()
    conn.close()

    return jsonify(
        user_json(user_id)
    )


@app.route("/api/leaderboard", methods=["GET"])
def leaderboard():

    conn = db()

    users = conn.execute(
        "SELECT * FROM users"
    ).fetchall()

    richest = []

    for user in users:

        rows = conn.execute(
            """
            SELECT nft_id
            FROM nfts
            WHERE user_id = ?
            """,
            (user["id"],)
        ).fetchall()

        collection_value = sum(
            NFT_BY_ID[r["nft_id"]]["value"]
            for r in rows
            if r["nft_id"] in NFT_BY_ID
        )

        richest.append({
            "id": user["id"],
            "first_name": user["first_name"],
            "username": user["username"],
            "coins": user["coins"],
            "collection_value": collection_value
        })

    richest.sort(
        key=lambda x:
            x["coins"] +
            x["collection_value"],
        reverse=True
    )

    expensive = conn.execute(
        """
        SELECT
            n.id,
            n.user_id,
            n.nft_id,
            u.first_name,
            u.username
        FROM nfts n
        JOIN users u
        ON u.id = n.user_id
        """
    ).fetchall()

    expensive_list = []

    for row in expensive:

        nft = NFT_BY_ID.get(
            row["nft_id"]
        )

        if not nft:
            continue

        expensive_list.append({
            "id": row["id"],
            "name": nft["name"],
            "rarity": nft["rarity"],
            "value": nft["value"],
            "icon": nft["icon"],
            "first_name": row["first_name"],
            "username": row["username"]
        })

    expensive_list.sort(
        key=lambda x: x["value"],
        reverse=True
    )

    conn.close()

    return jsonify({
        "richest": richest[:20],
        "expensive": expensive_list[:20]
    })


if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
