import os
import sqlite3
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="web", static_url_path="/web")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "game.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT DEFAULT '',
            balance INTEGER DEFAULT 1000
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nft_name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            power INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()


@app.route("/")
def home():
    return send_from_directory(os.path.join(BASE_DIR, "web"), "index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/user/<int:user_id>")
def get_user(user_id):
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, balance FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if user is None:
        conn.execute(
            "INSERT INTO users (id, username, balance) VALUES (?, ?, ?)",
            (user_id, f"user_{user_id}", 1000)
        )
        conn.commit()
        user = conn.execute(
            "SELECT id, username, balance FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()

    inventory = conn.execute(
        "SELECT id, nft_name, rarity, power FROM inventory WHERE user_id = ?",
        (user_id,)
    ).fetchall()

    conn.close()

    return jsonify({
        "user": dict(user),
        "inventory": [dict(item) for item in inventory]
    })


@app.route("/api/balance/<int:user_id>", methods=["POST"])
def update_balance(user_id):
    data = request.get_json(silent=True) or {}
    amount = data.get("amount")

    if not isinstance(amount, int):
        return jsonify({"error": "amount must be an integer"}), 400

    conn = get_db()
    user = conn.execute(
        "SELECT balance FROM users WHERE id = ?", (user_id,)
    ).fetchone()

    if user is None:
        conn.close()
        return jsonify({"error": "user not found"}), 404

    new_balance = user["balance"] + amount

    if new_balance < 0:
        conn.close()
        return jsonify({"error": "insufficient balance"}), 400

    conn.execute(
        "UPDATE users SET balance = ? WHERE id = ?",
        (new_balance, user_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"balance": new_balance})


@app.route("/api/inventory/<int:user_id>", methods=["GET"])
def get_inventory(user_id):
    conn = get_db()
    items = conn.execute(
        "SELECT id, nft_name, rarity, power FROM inventory WHERE user_id = ?",
        (user_id,)
    ).fetchall()
    conn.close()

    return jsonify({"inventory": [dict(item) for item in items]})


@app.route("/api/inventory/<int:user_id>", methods=["POST"])
def add_nft(user_id):
    data = request.get_json(silent=True) or {}

    nft_name = str(data.get("nft_name", "NFT"))
    rarity = str(data.get("rarity", "Common"))
    power = int(data.get("power", 1))

    conn = get_db()

    user = conn.execute(
        "SELECT id FROM users WHERE id = ?", (user_id,)
    ).fetchone()

    if user is None:
        conn.close()
        return jsonify({"error": "user not found"}), 404

    cursor = conn.execute(
        """
        INSERT INTO inventory (user_id, nft_name, rarity, power)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, nft_name, rarity, power)
    )
    conn.commit()

    nft_id = cursor.lastrowid
    conn.close()

    return jsonify({
        "success": True,
        "id": nft_id,
        "nft_name": nft_name,
        "rarity": rarity,
        "power": power
    })


@app.route("/api/leaderboard")
def leaderboard():
    conn = get_db()
    users = conn.execute(
        """
        SELECT id, username, balance
        FROM users
        ORDER BY balance DESC
        LIMIT 50
        """
    ).fetchall()
    conn.close()

    return jsonify({"leaderboard": [dict(user) for user in users]})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
else:
    init_db()
