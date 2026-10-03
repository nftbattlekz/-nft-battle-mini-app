import os, random, sqlite3, secrets
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

app=Flask(__name__, static_folder="web")
DB=os.getenv("DB_PATH","game.db")
BOT_TOKEN=os.getenv("BOT_TOKEN","")

RARITIES=[
 {"id":"common","name":"Common","chance":60,"power":10,"emoji":"🐱"},
 {"id":"rare","name":"Rare","chance":25,"power":25,"emoji":"🥷"},
 {"id":"epic","name":"Epic","chance":10,"power":55,"emoji":"🐉"},
 {"id":"legendary","name":"Legendary","chance":4,"power":100,"emoji":"🤖"},
 {"id":"mythic","name":"Mythic","chance":1,"power":180,"emoji":"👑"}]
NAMES={
"common":["Cyber Cat","Pixel Bot","Neon Dog"],
"rare":["Shadow Ninja","Neon Samurai","Chrome Fox"],
"epic":["Void Dragon","Cyber Phoenix","Mecha Wolf"],
"legendary":["Titan X","Golden Mecha","Neon God"],
"mythic":["Cosmic King","Genesis Dragon","Omega Prime"]}
CASES={"starter":("Starter Case",100),"neon":("Neon Case",250),"elite":("Elite Case",500)}

def db():
 c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
 c=db()
 c.executescript("""CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, balance INTEGER NOT NULL DEFAULT 1000,
 created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS nfts(
 id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT,rarity TEXT,power INTEGER,emoji TEXT,created TEXT);
 CREATE TABLE IF NOT EXISTS battles(
 id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER, nft_id INTEGER, enemy_name TEXT, enemy_power INTEGER, won INTEGER, created TEXT);
 CREATE TABLE IF NOT EXISTS transactions(
 id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,kind TEXT,amount INTEGER,balance_after INTEGER,created TEXT);
"""); c.commit(); c.close()
init()

def user_id():
 # Demo fallback. Production must validate Telegram WebApp initData with BOT_TOKEN.
 x=request.headers.get("X-Telegram-User-Id") or request.args.get("user_id")
 return int(x) if x and x.isdigit() else None

def require_user():
 uid=user_id()
 if not uid: return None,("Telegram user is required",401)
 c=db(); u=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
 if not u:
  c.execute("INSERT INTO users(id,username,first_name,created) VALUES(?,?,?,?,?)",
            (uid,"demo","Player",datetime.utcnow().isoformat()))
  c.commit(); u=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
 c.close(); return u,None

def pick_rarity():
 r=random.random()*100; s=0
 for x in RARITIES:
  s+=x["chance"]
  if r<s:return x
 return RARITIES[-1]

def make_nft(r):
 return random.choice(NAMES[r["id"]]),r

@app.get("/")
def index(): return send_from_directory("web","index.html")

@app.get("/api/me")
def me():
 u,e=require_user()
 if e:return jsonify({"error":e[0]}),e[1]
 c=db(); items=[dict(x) for x in c.execute("SELECT id,name,rarity,power,emoji FROM nfts WHERE user_id=? ORDER BY id DESC",(u["id"],))]
 c.close(); return jsonify({"id":u["id"],"username":u["username"],"balance":u["balance"],"inventory":items})

@app.post("/api/open")
def open_case():
 u,e=require_user()
 if e:return jsonify({"error":e[0]}),e[1]
 data=request.get_json(silent=True) or {}; case=data.get("case")
 if case not in CASES:return jsonify({"error":"Unknown case"}),400
 title,price=CASES[case]
 c=db(); u=c.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
 if u["balance"]<price:c.close();return jsonify({"error":"Not enough Credits"}),400
 r=pick_rarity(); name,r=make_nft(r)
 now=datetime.utcnow().isoformat()
 c.execute("UPDATE users SET balance=balance-? WHERE id=?",(price,u["id"]))
 c.execute("INSERT INTO nfts(user_id,name,rarity,power,emoji,created) VALUES(?,?,?,?,?,?)",(u["id"],name,r["id"],r["power"],r["emoji"],now))
 nftid=c.lastrowid
 bal=c.execute("SELECT balance FROM users WHERE id=?",(u["id"],)).fetchone()["balance"]
 c.execute("INSERT INTO transactions(user_id,kind,amount,balance_after,created) VALUES(?,?,?,?,?)",(u["id"],"case",-price,bal,now))
 c.commit();c.close()
 return jsonify({"nft":{"id":nftid,"name":name,"rarity":r["id"],"power":r["power"],"emoji":r["emoji"],"chance":r["chance"]},"balance":bal})

@app.post("/api/battle")
def battle():
 u,e=require_user()
 if e:return jsonify({"error":e[0]}),e[1]
 data=request.get_json(silent=True) or {}; nid=int(data.get("nft_id",0))
 c=db(); nft=c.execute("SELECT * FROM nfts WHERE id=? AND user_id=?",(nid,u["id"])).fetchone()
 if not nft:c.close();return jsonify({"error":"NFT not found"}),404
 er=random.choice(RARITIES); enemy=random.choice(NAMES[er["id"]]); ep=max(1,er["power"]+random.randint(-max(1,er["power"]//4),max(1,er["power"]//4)))
 won=1 if nft["power"]>=ep else 0; reward=75 if won else 0
 if reward:c.execute("UPDATE users SET balance=balance+? WHERE id=?",(reward,u["id"]))
 bal=c.execute("SELECT balance FROM users WHERE id=?",(u["id"],)).fetchone()["balance"]
 c.execute("INSERT INTO battles(user_id,nft_id,enemy_name,enemy_power,won,created) VALUES(?,?,?,?,?,?)",(u["id"],nid,enemy,ep,won,datetime.utcnow().isoformat()))
 c.commit();c.close()
 return jsonify({"won":bool(won),"reward":reward,"balance":bal,"enemy":{"name":enemy,"power":ep}})

@app.post("/api/upgrade")
def upgrade():
 u,e=require_user()
 if e:return jsonify({"error":e[0]}),e[1]
 c=db()
 for i,r in enumerate(RARITIES[:-1]):
  rows=c.execute("SELECT id FROM nfts WHERE user_id=? AND rarity=? ORDER BY id LIMIT 3",(u["id"],r["id"])).fetchall()
  if len(rows)==3:
   ids=[x["id"] for x in rows]; nr=RARITIES[i+1]; name=random.choice(NAMES[nr["id"]])
   c.executemany("DELETE FROM nfts WHERE id=? AND user_id=?",[(x,u["id"]) for x in ids])
   c.execute("INSERT INTO nfts(user_id,name,rarity,power,emoji,created) VALUES(?,?,?,?,?,?)",(u["id"],name,nr["id"],nr["power"],nr["emoji"],datetime.utcnow().isoformat()))
   out={"name":name,"rarity":nr["id"],"power":nr["power"],"emoji":nr["emoji"]}
   c.commit();c.close();return jsonify({"nft":out})
 c.close();return jsonify({"error":"Need 3 NFTs of the same rarity"}),400

@app.get("/api/leaderboard")
def leaderboard():
 c=db(); rows=[dict(x) for x in c.execute("""SELECT u.id,u.username,u.first_name,COUNT(n.id) nft_count
 FROM users u LEFT JOIN nfts n ON n.user_id=u.id GROUP BY u.id ORDER BY nft_count DESC,u.id LIMIT 20""")]
 c.close();return jsonify(rows)

@app.get("/health")
def health():return jsonify({"ok":True})

if __name__=="__main__":
 app.run(host="0.0.0.0",port=int(os.getenv("PORT","8080")))
