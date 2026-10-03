import os
import json
import hmac
import hashlib
import sqlite3
import random
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nexora.db")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

app = Flask(__name__, static_folder="web")

CASES = [
    {"id": 1, "name": "Starter Case", "price": 100, "reward": ("Cyber Cat", "Common", 120, "🐱")},
    {"id": 2, "name": "Neon Case", "price": 250, "reward": ("Neon Samurai", "Common", 280, "⚔️")},
    {"id": 3, "name": "Shadow Case", "price": 500, "reward": ("Shadow Wolf", "Rare", 650, "🐺")},
    {"id": 4, "name": "Chrome Case", "price": 800, "reward": ("Chrome Rider", "Rare", 950, "🏍️")},
    {"id": 5, "name": "Cyber Case", "price": 1200, "reward": ("Cyber Knight", "Epic", 1500, "🛡️")},
    {"id": 6, "name": "Void Case", "price": 1800, "reward": ("Void Guardian", "Epic", 2300, "👾")},
    {"id": 7, "name": "Galaxy Case", "price": 2500, "reward": ("Galaxy Dragon", "Legendary", 3400, "🐉")},
    {"id": 8, "name": "Quantum Case", "price": 3500, "reward": ("Quantum Ghost", "Legendary", 4800, "👻")},
    {"id": 9, "name": "Omega Case", "price": 5000, "reward": ("Omega Titan", "Mythic", 7200, "🤖")},
    {"id": 10, "name": "NEXORA Case", "price": 8000, "reward": ("NEXORA Prime", "Mythic", 12000, "💠")},
]

UPGRADES = {
    "Common": ("Rare", 1.35),
    "Rare": ("Epic", 1.55),
    "Epic": ("Legendary", 1.75),
    "Legendary": ("Mythic", 2.0),
}

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        coins INTEGER NOT NULL DEFAULT 1000,
        wins INTEGER NOT NULL DEFAULT 0,
        total_received_value INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS nfts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        rarity TEXT NOT NULL,
        value INTEGER NOT NULL,
        icon TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        nft_name TEXT NOT NULL,
        value INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    con.commit()
    con.close()

def verify_init_data(raw):
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not configured in Render")
    if not raw:
        raise ValueError("Telegram initData is missing")
    data = dict(parse_qsl(raw, keep_blank_values=True))
    received = data.pop("hash", None)
    if not received:
        raise ValueError("Telegram hash is missing")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError("Invalid Telegram initData")
    if "auth_date" in data:
        import time
        if time.time() - int(data["auth_date"]) > 86400:
            raise ValueError("Telegram authorization expired")
    return json.loads(data["user"])

def current_user():
    raw = request.headers.get("X-Telegram-Init-Data", "")
    return verify_init_data(raw)

def ensure_user(tg):
    con = db()
    row = con.execute("SELECT * FROM users WHERE id=?", (tg["id"],)).fetchone()
    if not row:
        con.execute(
            "INSERT INTO users(id, username, first_name) VALUES(?,?,?)",
            (tg["id"], tg.get("username", ""), tg.get("first_name", "Игрок"))
        )
        # One deterministic starter NFT.
        con.execute(
            "INSERT INTO nfts(user_id,name,rarity,value,icon) VALUES(?,?,?,?,?)",
            (tg["id"], "Cyber Cat", "Common", 120, "🐱")
        )
        con.commit()
    else:
        con.execute(
            "UPDATE users SET username=?, first_name=? WHERE id=?",
            (tg.get("username", ""), tg.get("first_name", "Игрок"), tg["id"])
        )
        con.commit()
    row = con.execute("SELECT * FROM users WHERE id=?", (tg["id"],)).fetchone()
    con.close()
    return row

def serialize_user(tg_id):
    con = db()
    u = con.execute("SELECT * FROM users WHERE id=?", (tg_id,)).fetchone()
    nfts = con.execute(
        "SELECT id,name,rarity,value,icon FROM nfts WHERE user_id=? ORDER BY value DESC,id DESC",
        (tg_id,)
    ).fetchall()
    con.close()
    return {
        "id": u["id"],
        "username": u["username"],
        "first_name": u["first_name"],
        "coins": u["coins"],
        "wins": u["wins"],
        "total_received_value": u["total_received_value"],
        "nfts": [dict(x) for x in nfts]
    }

@app.route("/")
def home():
    return send_from_directory(os.path.join(BASE_DIR, "web"), "index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.post("/api/me")
def me():
    try:
        tg = current_user()
        ensure_user(tg)
        return jsonify(serialize_user(tg["id"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.get("/api/cases")
def cases():
    return jsonify([
        {"id": c["id"], "name": c["name"], "price": c["price"],
         "reward": {"name": c["reward"][0], "rarity": c["reward"][1],
                    "value": c["reward"][2], "icon": c["reward"][3]}}
        for c in CASES
    ])

@app.post("/api/cases/open")
def open_case():
    try:
        tg = current_user()
        ensure_user(tg)
        data = request.get_json(force=True) or {}
        case_id = int(data.get("case_id"))
        case = next((c for c in CASES if c["id"] == case_id), None)
        if not case:
            return jsonify({"error": "Кейс не найден"}), 404

        con = db()
        u = con.execute("SELECT coins FROM users WHERE id=?", (tg["id"],)).fetchone()
        if u["coins"] < case["price"]:
            con.close()
            return jsonify({"error": "Недостаточно монет"}), 400

        name, rarity, value, icon = case["reward"]
        con.execute("UPDATE users SET coins=coins-? WHERE id=?", (case["price"], tg["id"]))
        con.execute(
            "INSERT INTO nfts(user_id,name,rarity,value,icon) VALUES(?,?,?,?,?)",
            (tg["id"], name, rarity, value, icon)
        )
        con.execute(
            "UPDATE users SET total_received_value=total_received_value+? WHERE id=?",
            (value, tg["id"])
        )
        con.execute(
            "INSERT INTO history(user_id,nft_name,value) VALUES(?,?,?)",
            (tg["id"], name, value)
        )
        con.commit()
        con.close()
        return jsonify(serialize_user(tg["id"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.post("/api/sell")
def sell():
    try:
        tg = current_user()
        data = request.get_json(force=True) or {}
        nft_id = int(data.get("nft_id"))
        con = db()
        nft = con.execute(
            "SELECT * FROM nfts WHERE id=? AND user_id=?", (nft_id, tg["id"])
        ).fetchone()
        if not nft:
            con.close()
            return jsonify({"error": "NFT не найден"}), 404
        con.execute("DELETE FROM nfts WHERE id=?", (nft_id,))
        con.execute("UPDATE users SET coins=coins+? WHERE id=?", (nft["value"], tg["id"]))
        con.commit()
        con.close()
        return jsonify(serialize_user(tg["id"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.post("/api/upgrade")
def upgrade():
    try:
        tg = current_user()
        data = request.get_json(force=True) or {}
        nft_id = int(data.get("nft_id"))
        con = db()
        nft = con.execute(
            "SELECT * FROM nfts WHERE id=? AND user_id=?", (nft_id, tg["id"])
        ).fetchone()
        if not nft:
            con.close()
            return jsonify({"error": "NFT не найден"}), 404
        if nft["rarity"] not in UPGRADES:
            con.close()
            return jsonify({"error": "Этот NFT уже максимальной редкости"}), 400

        next_rarity, multiplier = UPGRADES[nft["rarity"]]
        cost = max(100, int(nft["value"] * 0.35))
        u = con.execute("SELECT coins FROM users WHERE id=?", (tg["id"],)).fetchone()
        if u["coins"] < cost:
            con.close()
            return jsonify({"error": f"Нужно {cost} монет"}), 400

        new_value = int(nft["value"] * multiplier)
        con.execute("UPDATE users SET coins=coins-? WHERE id=?", (cost, tg["id"]))
        con.execute(
            "UPDATE nfts SET rarity=?, value=?, name=? WHERE id=?",
            (next_rarity, new_value, f"{next_rarity} {nft['name']}", nft_id)
        )
        con.commit()
        con.close()
        return jsonify(serialize_user(tg["id"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.get("/api/leaderboard")
def leaderboard():
    con = db()
    rich = con.execute("""
        SELECT u.id,u.username,u.first_name,u.coins,
               COALESCE(SUM(n.value),0) AS collection_value
        FROM users u LEFT JOIN nfts n ON n.user_id=u.id
        GROUP BY u.id
        ORDER BY (u.coins + collection_value) DESC
        LIMIT 20
    """).fetchall()
    rare = con.execute("""
        SELECT n.name,n.rarity,n.value,u.username,u.first_name
        FROM nfts n JOIN users u ON u.id=n.user_id
        ORDER BY n.value DESC LIMIT 20
    """).fetchall()
    con.close()
    return jsonify({
        "richest": [dict(x) for x in rich],
        "expensive": [dict(x) for x in rare]
    })

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
