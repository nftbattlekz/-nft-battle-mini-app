import os
import time
import hmac
import hashlib
import json
import random
import sqlite3
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="web")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CREATOR_TELEGRAM_ID = "8518976778"
DB_PATH = "nexora.db"


# =========================
# NFT
# =========================

RARITIES = [
    ("Common", 1, 12, 40, 90),
    ("Rare", 13, 24, 120, 250),
    ("Epic", 25, 36, 350, 700),
    ("Legendary", 37, 48, 1000, 2300),
    ("Mythic", 49, 60, 3000, 8500),
]

NFT_NAMES = [
    "Neon Core", "Red Pulse", "Dark Byte", "Cyber Eye",
    "Void Chip", "Nova Gear", "Chrome Soul", "Pixel Flame",
    "Shadow Key", "Digital Fang", "Quantum Coin", "Nexus Spark",

    "Blood Circuit", "Night Runner", "Cyber Wolf", "Neon Phantom",
    "Red Protocol", "Dark Matrix", "Ghost Drive", "Chrome Beast",
    "Zero Signal", "Black Nova", "Cyber Fang", "Pulse Hunter",

    "Omega Core", "Void Walker", "Neon Samurai", "Quantum Beast",
    "Dark Emperor", "Cyber Dragon", "Red Horizon", "Phantom X",
    "Night Protocol", "Digital Demon", "Nexus King", "Infinity Gear",

    "Galaxy Hunter", "Shadow Emperor", "Neon Titan", "Quantum Lord",
    "Cyber God", "Void Master", "Red Titan", "Dark Phoenix",
    "Chrome Legend", "Omega Dragon", "Night King", "Nexus Prime",

    "Mythic Core", "Absolute Zero", "Black Universe", "Neon Overlord",
    "Quantum Emperor", "Void King", "Cyber Overlord", "Infinity Soul",
    "Dark Universe", "NEXORA One", "Eternal Nexus", "Genesis"
]

NFTS = []

for rarity, start_id, end_id, minimum, maximum in RARITIES:
    for nft_id in range(start_id, end_id + 1):
        position = (nft_id - start_id) / max(1, end_id - start_id)

        NFTS.append({
            "id": nft_id,
            "name": NFT_NAMES[nft_id - 1],
            "rarity": rarity,
            "value": int(
                minimum + (maximum - minimum) * position
            )
        })

NFT_BY_ID = {nft["id"]: nft for nft in NFTS}


# =========================
# CASES
# =========================

CASES = [
    {
        "id": 1,
        "name": "STARTER",
        "subtitle": "Первый шаг",
        "accent": "blue",
        "pool": list(range(1, 13))
    },
    {
        "id": 2,
        "name": "NEON",
        "subtitle": "Неоновая серия",
        "accent": "pink",
        "pool": list(range(4, 25))
    },
    {
        "id": 3,
        "name": "SHADOW",
        "subtitle": "Тёмная коллекция",
        "accent": "purple",
        "pool": list(range(13, 37))
    },
    {
        "id": 4,
        "name": "CYBER",
        "subtitle": "Киберсерия",
        "accent": "red",
        "pool": list(range(13, 49))
    },
    {
        "id": 5,
        "name": "GALAXY",
        "subtitle": "Галактический дроп",
        "accent": "violet",
        "pool": list(range(25, 49))
    },
    {
        "id": 6,
        "name": "QUANTUM",
        "subtitle": "Квантовая серия",
        "accent": "cyan",
        "pool": list(range(29, 55))
    },
    {
        "id": 7,
        "name": "OMEGA",
        "subtitle": "Омега уровень",
        "accent": "orange",
        "pool": list(range(37, 61))
    },
    {
        "id": 8,
        "name": "LEGEND",
        "subtitle": "Легендарный дроп",
        "accent": "gold",
        "pool": list(range(37, 61))
    },
    {
        "id": 9,
        "name": "MYTHIC",
        "subtitle": "Мифическая серия",
        "accent": "mythic",
        "pool": list(range(49, 61))
    },
    {
        "id": 10,
        "name": "NEXORA",
        "subtitle": "Вся коллекция",
        "accent": "nexora",
        "pool": list(range(1, 61))
    }
]


# =========================
# PREFIXES
# =========================

PREFIXES = [
    (1, "Новичок", "⚡ Новичок", 1000),
    (2, "Охотник", "🎯 Охотник", 2500),
    (3, "Кибер", "🤖 Кибер", 5000),
    (4, "Неон", "💠 Неон", 7500),
    (5, "Призрак", "👻 Призрак", 10000),
    (6, "Ворон", "🐦‍⬛ Ворон", 15000),
    (7, "Самурай", "⚔️ Самурай", 22000),
    (8, "Титан", "🗿 Титан", 30000),
    (9, "Император", "👑 Император", 40000),
    (10, "Повелитель", "🔥 Повелитель", 55000),
    (11, "Владыка", "🌑 Владыка", 70000),
    (12, "Нексус", "🔮 Нексус", 90000),
    (13, "Омега", "Ω Омега", 115000),
    (14, "Легенда", "🏆 Легенда", 145000),
    (15, "Мифик", "💎 Мифик", 180000),
    (16, "Бессмертный", "♾️ Бессмертный", 220000),
    (17, "Архитектор", "🧬 Архитектор", 275000),
    (18, "Создатель", "🛠️ Создатель", 350000),
    (19, "Абсолют", "✦ Абсолют", 450000),
    (20, "NEXORA ELITE", "✧ NEXORA ELITE", 600000)
]

PREFIX_BY_ID = {
    p[0]: {
        "id": p[0],
        "name": p[1],
        "display": p[2],
        "price": p[3]
    }
    for p in PREFIXES
}


# =========================
# DATABASE
# =========================

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_prefixes (
            telegram_id TEXT NOT NULL,
            prefix_id INTEGER NOT NULL,
            PRIMARY KEY (telegram_id, prefix_id)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================
# TELEGRAM AUTH
# =========================

def get_telegram_user():

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    if init_data and BOT_TOKEN:

        try:

            params = dict(
                parse_qsl(
                    init_data,
                    keep_blank_values=True
                )
            )

            received_hash = params.pop("hash", None)

            if not received_hash:
                raise ValueError()

            auth_date = int(
                params.get("auth_date", "0")
            )

            if time.time() - auth_date > 86400:
                raise ValueError()

            data_check_string = "\n".join(
                f"{key}={params[key]}"
                for key in sorted(params)
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
                raise ValueError()

            user = json.loads(
                params.get("user", "{}")
            )

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

        except Exception:
            pass

    return {
        "id": "demo_user",
        "username": "demo",
        "first_name": "Demo"
    }


# =========================
# USERS
# =========================

def ensure_user(user):

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM users
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchone()

    if not row:

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


def get_collection_value(user_id):

    conn = get_db()

    rows = conn.execute("""
        SELECT nft_id
        FROM nfts
        WHERE telegram_id = ?
    """, (
        user_id,
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

    prefix = PREFIX_BY_ID.get(
        row["prefix_id"] or 0
    )

    return {
        "telegram_id": row["telegram_id"],
        "username": row["username"],
        "first_name": row["first_name"],
        "coins": row["coins"],
        "total_opened": row["total_opened"],
        "collection_value":
            get_collection_value(
                row["telegram_id"]
            ),
        "prefix_id":
            row["prefix_id"] or 0,
        "prefix":
            prefix["display"]
            if prefix
            else "",
        "creator":
            row["telegram_id"]
            == CREATOR_TELEGRAM_ID
    }


# =========================
# PROFILE
# =========================

@app.get("/api/me")
def me():

    user = get_telegram_user()

    row = ensure_user(user)

    return jsonify({
        "ok": True,
        "user": serialize_user(row)
    })


# =========================
# CASES
# =========================

@app.get("/api/cases")
def get_cases():

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


# =========================
# OPEN CASE
# =========================

@app.post("/api/cases/open")
def open_case():

    user = get_telegram_user()

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
        nft["id"],
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


# =========================
# INVENTORY
# =========================

@app.get("/api/inventory")
def inventory():

    user = get_telegram_user()

    ensure_user(user)

    conn = get_db()

    rows = conn.execute("""
        SELECT id, nft_id, created_at
        FROM nfts
        WHERE telegram_id = ?
        ORDER BY id DESC
    """, (
        user["id"],
    )).fetchall()

    conn.close()

    result = []

    for row in rows:

        nft = NFT_BY_ID.get(
            row["nft_id"]
        )

        if nft:

            result.append({
                "instance_id": row["id"],
                "id": nft["id"],
                "name": nft["name"],
                "rarity": nft["rarity"],
                "value": nft["value"],
                "created_at": row["created_at"]
            })

    return jsonify({
        "ok": True,
        "inventory": result
    })


# =========================
# SELL
# =========================

@app.post("/api/sell")
def sell_nft():

    user = get_telegram_user()

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

    row = conn.execute("""
        SELECT *
        FROM nfts
        WHERE id = ?
        AND telegram_id = ?
    """, (
        instance_id,
        user["id"]
    )).fetchone()

    if not row:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "NFT не найден"
        }), 404

    nft = NFT_BY_ID.get(
        row["nft_id"]
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
        "sold": nft,
        "user": serialize_user(updated)
    })


# =========================
# PREFIXES
# =========================

@app.get("/api/prefixes")
def get_prefixes():

    user = get_telegram_user()

    row = ensure_user(user)

    conn = get_db()

    owned_rows = conn.execute("""
        SELECT prefix_id
        FROM user_prefixes
        WHERE telegram_id = ?
    """, (
        user["id"],
    )).fetchall()

    conn.close()

    owned = {
        r["prefix_id"]
        for r in owned_rows
    }

    current = row["prefix_id"] or 0

    result = []

    for prefix in PREFIX_BY_ID.values():

        result.append({
            **prefix,
            "owned":
                prefix["id"] in owned,
            "equipped":
                prefix["id"] == current
        })

    return jsonify({
        "ok": True,
        "current_prefix_id": current,
        "prefixes": result
    })


# =========================
# BUY PREFIX
# =========================

@app.post("/api/prefixes/buy")
def buy_prefix():

    user = get_telegram_user()

    row = ensure_user(user)

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

    owned = conn.execute("""
        SELECT 1
        FROM user_prefixes
        WHERE telegram_id = ?
        AND prefix_id = ?
    """, (
        user["id"],
        prefix_id
    )).fetchone()

    if owned:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "Префикс уже куплен"
        })

    if row["coins"] < prefix["price"]:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "Недостаточно 💎"
        })

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

    conn.execute("""
        INSERT INTO user_prefixes (
            telegram_id,
            prefix_id
        )
        VALUES (?, ?)
    """, (
        user["id"],
        prefix_id
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
        "user": serialize_user(updated)
    })


# =========================
# EQUIP PREFIX
# =========================

@app.post("/api/prefixes/equip")
def equip_prefix():

    user = get_telegram_user()

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

    conn = get_db()

    if prefix_id != 0:

        owned = conn.execute("""
            SELECT 1
            FROM user_prefixes
            WHERE telegram_id = ?
            AND prefix_id = ?
        """, (
            user["id"],
            prefix_id
        )).fetchone()

        if not owned:

            conn.close()

            return jsonify({
                "ok": False,
                "error":
                    "Сначала купи этот префикс"
            })

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
        "user": serialize_user(row)
    })


# =========================
# LEADERBOARD
# =========================

@app.get("/api/leaderboard")
def leaderboard():

    conn = get_db()

    users = conn.execute("""
        SELECT *
        FROM users
    """).fetchall()

    nft_rows = conn.execute("""
        SELECT telegram_id, nft_id
        FROM nfts
    """).fetchall()

    conn.close()

    nft_values = {}

    for row in nft_rows:

        nft = NFT_BY_ID.get(
            row["nft_id"]
        )

        if not nft:
            continue

        uid = row["telegram_id"]

        nft_values[uid] = (
            nft_values.get(uid, 0)
            + nft["value"]
        )

    players = []

    for row in users:

        collection = nft_values.get(
            row["telegram_id"],
            0
        )

        prefix = PREFIX_BY_ID.get(
            row["prefix_id"] or 0
        )

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
                row["telegram_id"]
                == CREATOR_TELEGRAM_ID
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


# =========================
# FRONTEND
# =========================

@app.get("/")
def index():
    return send_from_directory(
        "web",
        "index.html"
    )


@app.get("/<path:path>")
def files(path):
    return send_from_directory(
        "web",
        path
    )


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
