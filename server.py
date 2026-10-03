import os
import json
import hmac
import hashlib
import sqlite3
import random
import time

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DB_PATH = os.path.join(BASE_DIR, "nexora.db")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


# =========================
# NFT COLLECTION
# =========================

NFTS = []

RARITIES = [
    ("Common", 1, 12),
    ("Rare", 13, 24),
    ("Epic", 25, 36),
    ("Legendary", 37, 48),
    ("Mythic", 49, 60),
]

COMMON_NAMES = [
    "Cyber Cat", "Pixel Ghost", "Neon Cube", "Chrome Bot",
    "Dark Fox", "Byte Wolf", "Glitch Eye", "Nano Skull",
    "Cyber Duck", "Red Core", "Night Byte", "Zero Mask"
]

RARE_NAMES = [
    "Neon Samurai", "Shadow Rider", "Cyber Ninja", "Digital Ronin",
    "Chrome Dragon", "Red Phantom", "Night Hunter", "Pixel Samurai",
    "Cyber Oni", "Neon Beast", "Dark Racer", "Quantum Fox"
]

EPIC_NAMES = [
    "Void Warrior", "Cyber Emperor", "Neon Demon", "Shadow Dragon",
    "Quantum Knight", "Digital Titan", "Chrome Phantom", "Dark Samurai",
    "Cyber Reaper", "Neon Assassin", "Void Hunter", "Omega Beast"
]

LEGENDARY_NAMES = [
    "Galaxy King", "Cyber God", "Neon Overlord", "Quantum Dragon",
    "Shadow Emperor", "Digital Legend", "Chrome King", "Void Lord",
    "Omega Samurai", "Cyber Titan", "Neon Destroyer", "Dark Emperor"
]

MYTHIC_NAMES = [
    "NEXORA Prime", "Eternal Dragon", "Galaxy Emperor", "Void Genesis",
    "Cyber Infinity", "Omega Prime", "Digital God", "Neon Genesis",
    "Shadow Infinity", "Quantum Prime", "NEXORA Origin", "Absolute Zero"
]

ICONS = ["◆", "◇", "✦", "✧", "⬢", "⬡", "✺", "✹", "◈", "❖", "✪", "⟡"]

name_groups = [
    COMMON_NAMES,
    RARE_NAMES,
    EPIC_NAMES,
    LEGENDARY_NAMES,
    MYTHIC_NAMES
]

values = [
    list(range(100, 221, 10)),
    list(range(300, 651, 30)),
    list(range(800, 1901, 100)),
    list(range(2500, 5801, 300)),
    list(range(7000, 20001, 1000))
]

for rarity_index, (rarity, start, end) in enumerate(RARITIES):
    names = name_groups[rarity_index]

    for i, nft_id in enumerate(range(start, end + 1)):
        NFTS.append({
            "id": nft_id,
            "name": names[i],
            "rarity": rarity,
            "value": values[rarity_index][i],
            "icon": ICONS[i % len(ICONS)]
        })


NFT_BY_ID = {n["id"]: n for n in NFTS}


# =========================
# CASES
# =========================

CASE_DEFINITIONS = [
    {
        "id": 1,
        "name": "STARTER",
        "subtitle": "FIRST CONTACT",
        "icon": "✦",
        "color": "cyan",
        "pool": list(range(1, 13))
    },
    {
        "id": 2,
        "name": "NEON",
        "subtitle": "CITY LIGHTS",
        "icon": "◇",
        "color": "blue",
        "pool": list(range(4, 25))
    },
    {
        "id": 3,
        "name": "SHADOW",
        "subtitle": "DARK SIGNAL",
        "icon": "◈",
        "color": "purple",
        "pool": list(range(13, 37))
    },
    {
        "id": 4,
        "name": "CYBER",
        "subtitle": "DIGITAL CORE",
        "icon": "⬢",
        "color": "pink",
        "pool": list(range(13, 49))
    },
    {
        "id": 5,
        "name": "GALAXY",
        "subtitle": "DEEP SPACE",
        "icon": "✺",
        "color": "violet",
        "pool": list(range(25, 49))
    },
    {
        "id": 6,
        "name": "QUANTUM",
        "subtitle": "UNKNOWN DATA",
        "icon": "✧",
        "color": "gold",
        "pool": list(range(29, 55))
    },
    {
        "id": 7,
        "name": "OMEGA",
        "subtitle": "FINAL PROTOCOL",
        "icon": "◆",
        "color": "red",
        "pool": list(range(37, 61))
    },
    {
        "id": 8,
        "name": "LEGEND",
        "subtitle": "LEGACY",
        "icon": "❖",
        "color": "orange",
        "pool": list(range(37, 61))
    },
    {
        "id": 9,
        "name": "MYTHIC",
        "subtitle": "BEYOND LIMITS",
        "icon": "✪",
        "color": "mythic",
        "pool": list(range(49, 61))
    },
    {
        "id": 10,
        "name": "NEXORA",
        "subtitle": "ULTIMATE CASE",
        "icon": "⟡",
        "color": "nexora",
        "pool": list(range(1, 61))
    }
]


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
            total_received_value INTEGER DEFAULT 0
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

    conn.commit()
    conn.close()


init_db()


# =========================
# TELEGRAM AUTH
# =========================

def validate_telegram_data(init_data):
    if not init_data:
        return None

    if not BOT_TOKEN:
        return None

    try:
        from urllib.parse import parse_qsl

        data = dict(parse_qsl(init_data, keep_blank_values=True))

        received_hash = data.pop("hash", None)

        if not received_hash:
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

        auth_date = int(data.get("auth_date", 0))

        if time.time() - auth_date > 86400:
            return None

        user_data = json.loads(data.get("user", "{}"))

        return user_data

    except Exception:
        return None


def get_current_user():
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    user = validate_telegram_data(init_data)

    if user:
        return user

    # Demo fallback
    return {
        "id": "demo_user",
        "username": "demo",
        "first_name": "NEXORA"
    }


# =========================
# USER
# =========================

def ensure_user(user):
    telegram_id = str(user["id"])

    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?",
        (telegram_id,)
    ).fetchone()

    if not existing:
        conn.execute("""
            INSERT INTO users
            (telegram_id, username, first_name, coins, total_opened, total_received_value)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            telegram_id,
            user.get("username", ""),
            user.get("first_name", "Player"),
            1000,
            0,
            0
        ))

        conn.commit()

    else:
        conn.execute("""
            UPDATE users
            SET username = ?, first_name = ?
            WHERE telegram_id = ?
        """, (
            user.get("username", ""),
            user.get("first_name", "Player"),
            telegram_id
        ))

        conn.commit()

    result = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?",
        (telegram_id,)
    ).fetchone()

    conn.close()

    return result


def get_user_nfts(telegram_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT id, nft_id, created_at
        FROM nfts
        WHERE telegram_id = ?
        ORDER BY id DESC
    """, (telegram_id,)).fetchall()

    conn.close()

    result = []

    for row in rows:
        nft = NFT_BY_ID.get(row["nft_id"])

        if nft:
            item = dict(nft)
            item["inventory_id"] = row["id"]
            item["created_at"] = row["created_at"]
            result.append(item)

    return result


def serialize_user(user_row):
    telegram_id = user_row["telegram_id"]

    return {
        "telegram_id": telegram_id,
        "username": user_row["username"],
        "first_name": user_row["first_name"],
        "coins": user_row["coins"],
        "total_opened": user_row["total_opened"],
        "total_received_value": user_row["total_received_value"],
        "nfts": get_user_nfts(telegram_id)
    }


# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(WEB_DIR, path)


@app.route("/api/me")
def api_me():
    user = get_current_user()
    db_user = ensure_user(user)

    return jsonify({
        "ok": True,
        "user": serialize_user(db_user)
    })


@app.route("/api/cases")
def api_cases():
    result = []

    for case in CASE_DEFINITIONS:
        result.append({
            "id": case["id"],
            "name": case["name"],
            "subtitle": case["subtitle"],
            "icon": case["icon"],
            "color": case["color"],
            "free": True
        })

    return jsonify({
        "ok": True,
        "cases": result
    })


# =========================
# FREE RANDOM CASE
# =========================

@app.route("/api/cases/open", methods=["POST"])
def open_case():
    user = get_current_user()
    db_user = ensure_user(user)

    data = request.get_json(silent=True) or {}

    try:
        case_id = int(data.get("case_id"))
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Invalid case"
        }), 400

    case = next(
        (c for c in CASE_DEFINITIONS if c["id"] == case_id),
        None
    )

    if not case:
        return jsonify({
            "ok": False,
            "error": "Case not found"
        }), 404

    # Бесплатный случайный выбор NFT
    nft_id = random.choice(case["pool"])
    nft = NFT_BY_ID[nft_id]

    telegram_id = str(user["id"])

    conn = get_db()

    conn.execute("""
        INSERT INTO nfts
        (telegram_id, nft_id, created_at)
        VALUES (?, ?, ?)
    """, (
        telegram_id,
        nft_id,
        int(time.time())
    ))

    conn.execute("""
        UPDATE users
        SET total_opened = total_opened + 1,
            total_received_value = total_received_value + ?
        WHERE telegram_id = ?
    """, (
        nft["value"],
        telegram_id
    ))

    conn.commit()

    updated = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?",
        (telegram_id,)
    ).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "case": case,
        "reward": nft,
        "user": serialize_user(updated)
    })


# =========================
# SELL NFT
# =========================

@app.route("/api/sell", methods=["POST"])
def sell_nft():
    user = get_current_user()
    db_user = ensure_user(user)

    data = request.get_json(silent=True) or {}

    try:
        inventory_id = int(data.get("inventory_id"))
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Invalid NFT"
        }), 400

    telegram_id = str(user["id"])

    conn = get_db()

    row = conn.execute("""
        SELECT id, nft_id
        FROM nfts
        WHERE id = ? AND telegram_id = ?
    """, (
        inventory_id,
        telegram_id
    )).fetchone()

    if not row:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "NFT not found"
        }), 404

    nft = NFT_BY_ID.get(row["nft_id"])

    if not nft:
        conn.close()

        return jsonify({
            "ok": False,
            "error": "NFT data not found"
        }), 404

    conn.execute(
        "DELETE FROM nfts WHERE id = ?",
        (inventory_id,)
    )

    conn.execute("""
        UPDATE users
        SET coins = coins + ?
        WHERE telegram_id = ?
    """, (
        nft["value"],
        telegram_id
    ))

    conn.commit()

    updated = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?",
        (telegram_id,)
    ).fetchone()

    conn.close()

    return jsonify({
        "ok": True,
        "sold": nft,
        "user": serialize_user(updated)
    })


# =========================
# LEADERBOARD
# =========================

@app.route("/api/leaderboard")
def leaderboard():
    conn = get_db()

    users = conn.execute("""
        SELECT
            u.telegram_id,
            u.username,
            u.first_name,
            u.coins,
            u.total_opened,
            COALESCE(SUM(n.value), 0) AS collection_value
        FROM users u
        LEFT JOIN (
            SELECT
                nfts.telegram_id,
                NFT_VALUES.value
            FROM nfts
            JOIN (
                SELECT 1 AS id, 100 AS value
                UNION ALL SELECT 2, 110
                UNION ALL SELECT 3, 120
                UNION ALL SELECT 4, 130
                UNION ALL SELECT 5, 140
                UNION ALL SELECT 6, 150
                UNION ALL SELECT 7, 160
                UNION ALL SELECT 8, 170
                UNION ALL SELECT 9, 180
                UNION ALL SELECT 10, 190
                UNION ALL SELECT 11, 200
                UNION ALL SELECT 12, 210
            ) NFT_VALUES
            ON nfts.nft_id = NFT_VALUES.id
        ) n
        ON u.telegram_id = n.telegram_id
        GROUP BY u.telegram_id
        ORDER BY (u.coins + COALESCE(SUM(n.value), 0)) DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    result = []

    for index, row in enumerate(users, start=1):
        result.append({
            "rank": index,
            "username": row["username"],
            "first_name": row["first_name"],
            "coins": row["coins"],
            "opened": row["total_opened"],
            "collection_value": row["collection_value"]
        })

    return jsonify({
        "ok": True,
        "players": result
    })


# =========================
# START
# =========================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
