import os, sqlite3, hashlib, hmac, json, time, urllib.parse
from flask import Flask, jsonify, request, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DB_PATH = os.path.join(BASE_DIR, "game.db")
app = Flask(__name__)

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY, username TEXT DEFAULT 'Player',
      first_name TEXT DEFAULT '', photo_url TEXT DEFAULT '',
      balance INTEGER DEFAULT 1000, wins INTEGER DEFAULT 0,
      losses INTEGER DEFAULT 0, created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS nfts (
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      name TEXT NOT NULL, rarity TEXT NOT NULL, power INTEGER NOT NULL,
      level INTEGER DEFAULT 1, created_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS battles (
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
      opponent_id INTEGER, my_power INTEGER NOT NULL,
      opponent_power INTEGER NOT NULL, result TEXT NOT NULL,
      created_at INTEGER NOT NULL
    );
    """)
    c.commit(); c.close()

def validate_init_data(init_data):
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        return None, "BOT_TOKEN is not configured in Render"
    try:
        p = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received = p.pop("hash", None)
        if not received: return None, "Missing Telegram hash"
        auth_date = int(p.get("auth_date", "0"))
        if not auth_date or time.time() - auth_date > 86400:
            return None, "Telegram session expired"
        check = "\n".join(f"{k}={p[k]}" for k in sorted(p))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received):
            return None, "Invalid Telegram signature"
        return json.loads(p["user"]), None
    except Exception:
        return None, "Invalid Telegram initData"

def auth():
    raw = request.headers.get("X-Telegram-Init-Data", "")
    if not raw: return None, (jsonify(error="Open the app from Telegram"), 401)
    u, err = validate_init_data(raw)
    if err: return None, (jsonify(error=err), 401)
    return u, None

def upsert(u):
    uid = int(u["id"])
    c = db()
    c.execute("""INSERT INTO users(id,username,first_name,photo_url,created_at)
                 VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                 username=excluded.username, first_name=excluded.first_name,
                 photo_url=excluded.photo_url""",
              (uid, u.get("username") or u.get("first_name") or "Player",
               u.get("first_name",""), u.get("photo_url",""), int(time.time())))
    c.commit(); c.close()
    return uid

def state(uid):
    c = db()
    u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    n = c.execute("""SELECT id,name,rarity,power,level FROM nfts
                     WHERE user_id=? ORDER BY power DESC,id DESC""",(uid,)).fetchall()
    c.close()
    return {"user":dict(u), "nfts":[dict(x) for x in n],
            "total_power":sum(x["power"] for x in n)}

@app.route("/")
def home(): return send_from_directory(WEB_DIR, "index.html")

@app.route("/health")
def health(): return jsonify(status="ok")

@app.route("/api/me", methods=["POST"])
def me():
    u, err = auth()
    if err: return err
    uid = upsert(u)
    c = db()
    if c.execute("SELECT COUNT(*) n FROM nfts WHERE user_id=?",(uid,)).fetchone()["n"] == 0:
        c.executemany("""INSERT INTO nfts(user_id,name,rarity,power,level,created_at)
                         VALUES(?,?,?,?,?,?)""", [
            (uid,"Shadow Wolf","Rare",42,1,int(time.time())),
            (uid,"Neon Samurai","Common",25,1,int(time.time()))])
        c.commit()
    c.close()
    return jsonify(state(uid))

@app.route("/api/nft/reward", methods=["POST"])
def reward():
    u, err = auth()
    if err: return err
    uid = upsert(u)
    data = request.get_json(silent=True) or {}
    name = str(data.get("name","Cyber Knight"))[:40]
    rarity = str(data.get("rarity","Common"))[:20]
    power = max(1,min(int(data.get("power",30)),1000))
    c = db()
    cur = c.execute("""INSERT INTO nfts(user_id,name,rarity,power,level,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (uid,name,rarity,power,1,int(time.time())))
    c.commit(); nid=cur.lastrowid; c.close()
    return jsonify(success=True,nft_id=nid)

@app.route("/api/upgrade", methods=["POST"])
def upgrade():
    u, err = auth()
    if err: return err
    uid=upsert(u); data=request.get_json(silent=True) or {}
    nid=int(data.get("nft_id",0)); c=db()
    n=c.execute("SELECT * FROM nfts WHERE id=? AND user_id=?",(nid,uid)).fetchone()
    if not n: c.close(); return jsonify(error="NFT not found"),404
    cost=100*n["level"]
    bal=c.execute("SELECT balance FROM users WHERE id=?",(uid,)).fetchone()["balance"]
    if bal<cost: c.close(); return jsonify(error=f"Need {cost} coins"),400
    power=n["power"]+10*n["level"]; level=n["level"]+1
    c.execute("UPDATE users SET balance=balance-? WHERE id=?",(cost,uid))
    c.execute("UPDATE nfts SET power=?,level=? WHERE id=?",(power,level,nid))
    c.commit(); c.close()
    return jsonify(success=True,power=power,level=level,cost=cost)

@app.route("/api/battle", methods=["POST"])
def battle():
    u, err=auth()
    if err: return err
    uid=upsert(u); data=request.get_json(silent=True) or {}
    nid=int(data.get("nft_id",0)); c=db()
    mine=c.execute("SELECT power FROM nfts WHERE id=? AND user_id=?",(nid,uid)).fetchone()
    if not mine: c.close(); return jsonify(error="NFT not found"),404
    opp=c.execute("SELECT id,username FROM users WHERE id!=? ORDER BY RANDOM() LIMIT 1",(uid,)).fetchone()
    if opp:
        op=c.execute("SELECT COALESCE(SUM(power),0) p FROM nfts WHERE user_id=?",(opp["id"],)).fetchone()["p"]
        op=max(1,op); oid=opp["id"]; oname=opp["username"]
    else:
        op=50; oid=None; oname="Practice Bot"
    mp=mine["power"]; result="win" if mp>op else "loss" if mp<op else "draw"
    if result=="win": c.execute("UPDATE users SET wins=wins+1,balance=balance+50 WHERE id=?",(uid,))
    elif result=="loss": c.execute("UPDATE users SET losses=losses+1 WHERE id=?",(uid,))
    c.execute("""INSERT INTO battles(user_id,opponent_id,my_power,opponent_power,result,created_at)
                 VALUES(?,?,?,?,?,?)""",(uid,oid,mp,op,result,int(time.time())))
    c.commit(); c.close()
    return jsonify(result=result,my_power=mp,opponent_power=op,
                   opponent_name=oname,reward=50 if result=="win" else 0)

@app.route("/api/leaderboard")
def leaderboard():
    c=db()
    rows=c.execute("""SELECT id,username,balance,wins,losses,
                      COALESCE((SELECT SUM(power) FROM nfts WHERE user_id=users.id),0) total_power
                      FROM users ORDER BY total_power DESC,wins DESC LIMIT 50""").fetchall()
    c.close()
    return jsonify(leaderboard=[dict(x) for x in rows])

init_db()
if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
