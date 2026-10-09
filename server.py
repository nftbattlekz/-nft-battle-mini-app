import os, sqlite3, secrets, hmac, hashlib, json, time, random
from datetime import datetime, timezone
from urllib.parse import parse_qsl
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__, static_folder='web', static_url_path='')
DB_PATH = os.getenv('DB_PATH', 'nomer.db')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
DEMO_MODE = os.getenv('DEMO_MODE', '0') == '1'
LETTERS = 'ABEKMHOPCTYX'
DAILY_SPINS = 20
RARITIES = [('Обычный', 600), ('Необычный', 250), ('Редкий', 100), ('Эпический', 40), ('Легендарный', 9), ('Мифический', 1)]


def db():
    conn = sqlite3.connect(DB_PATH, timeout=20, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=20000')
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, username TEXT NOT NULL DEFAULT '', balance INTEGER NOT NULL DEFAULT 10000 CHECK(balance>=0), xp INTEGER NOT NULL DEFAULT 0, spins_day TEXT NOT NULL DEFAULT '', spins_used INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS plates (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, rarity TEXT NOT NULL, owner_id INTEGER NOT NULL REFERENCES users(id), created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS listings (id INTEGER PRIMARY KEY AUTOINCREMENT, plate_id INTEGER NOT NULL UNIQUE REFERENCES plates(id), seller_id INTEGER NOT NULL REFERENCES users(id), price INTEGER NOT NULL CHECK(price>0), created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, plate_id INTEGER NOT NULL, seller_id INTEGER NOT NULL, buyer_id INTEGER NOT NULL, price INTEGER NOT NULL, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_plates_owner ON plates(owner_id);
        CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
        ''')


def telegram_user(init_data):
    if DEMO_MODE and not init_data:
        return {'id': 10001, 'first_name': 'Demo Player', 'username': 'demo'}
    if not BOT_TOKEN or not init_data:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        provided = pairs.pop('hash', '')
        auth_date = int(pairs.get('auth_date', '0'))
        if abs(time.time() - auth_date) > 86400:
            return None
        data_check = '\n'.join(f'{k}={v}' for k,v in sorted(pairs.items()))
        secret = hmac.new(b'WebAppData', BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            return None
        user = json.loads(pairs['user'])
        return user if isinstance(user.get('id'), int) else None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def authenticated(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        tg = telegram_user(request.headers.get('X-Telegram-Init-Data', ''))
        if not tg:
            return jsonify(error='Открой игру через Telegram-бота. Для локального теста включи DEMO_MODE=1.'), 401
        uid = tg['id']
        with db() as c:
            c.execute('INSERT OR IGNORE INTO users(id,name,username,created_at) VALUES(?,?,?,?)', (uid, tg.get('first_name','Игрок')[:80], tg.get('username','')[:80], int(time.time())))
            c.execute('UPDATE users SET name=?,username=? WHERE id=?', (tg.get('first_name','Игрок')[:80], tg.get('username','')[:80], uid))
        return fn(uid, *args, **kwargs)
    return wrapper


def today():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def rarity_pick():
    return random.choices([r[0] for r in RARITIES], weights=[r[1] for r in RARITIES], k=1)[0]


def make_code(rarity):
    a,b,c = [secrets.choice(LETTERS) for _ in range(3)]
    if rarity == 'Обычный':
        digits = f'{secrets.randbelow(900)+100:03}'
    elif rarity == 'Необычный':
        x,y = secrets.choice('123456789'), secrets.choice('0123456789')
        digits = x+y+x
    elif rarity == 'Редкий':
        digits = secrets.choice('123456789')*3
    elif rarity == 'Эпический':
        b=c=a
        digits = '00'+secrets.choice('123456789')
    elif rarity == 'Легендарный':
        b=c=a
        digits = secrets.choice('123456789')*3
    else:
        b=c=a
        digits = '777'
    region = secrets.choice(['01','02','05','07','16','50','77','78','95','99','116','177','777'])
    return f'{a}{digits}{b}{c} {region}'


def plate_json(row):
    return {'id':row['id'], 'code':row['code'], 'rarity':row['rarity']}


@app.get('/')
def index():
    return send_from_directory('web','index.html')


@app.get('/api/me')
@authenticated
def me(uid):
    with db() as c:
        u = c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        count = c.execute('SELECT COUNT(*) FROM plates WHERE owner_id=?',(uid,)).fetchone()[0]
        active = u['spins_used'] if u['spins_day'] == today() else 0
        return jsonify(id=uid,name=u['name'],username=u['username'],balance=u['balance'],xp=u['xp'],level=min(100,1+u['xp']//250),spins_left=max(0,DAILY_SPINS-active),collection=count,demo=DEMO_MODE)


@app.post('/api/spin')
@authenticated
def spin(uid):
    with db() as c:
        try:
            c.execute('BEGIN IMMEDIATE')
            u = c.execute('SELECT spins_day,spins_used FROM users WHERE id=?',(uid,)).fetchone()
            used = u['spins_used'] if u['spins_day']==today() else 0
            if used >= DAILY_SPINS:
                c.rollback(); return jsonify(error='Попытки закончились. Возвращайся завтра (UTC).'), 400
            plate = None
            for _ in range(120):
                rarity = rarity_pick()
                code = make_code(rarity)
                try:
                    cur = c.execute('INSERT INTO plates(code,rarity,owner_id,created_at) VALUES(?,?,?,?)',(code,rarity,uid,int(time.time())))
                    plate = {'id':cur.lastrowid,'code':code,'rarity':rarity}
                    break
                except sqlite3.IntegrityError:
                    continue
            if not plate:
                c.rollback(); return jsonify(error='Не удалось подобрать свободный номер. Повтори позже.'), 503
            c.execute('UPDATE users SET spins_day=?,spins_used=?,xp=xp+10 WHERE id=?',(today(),used+1,uid))
            c.commit()
            return jsonify(plate=plate,spins_left=DAILY_SPINS-used-1)
        except Exception:
            c.rollback(); raise


@app.get('/api/collection')
@authenticated
def collection(uid):
    with db() as c:
        rows=c.execute('SELECT p.id,p.code,p.rarity,l.id AS listing_id FROM plates p LEFT JOIN listings l ON l.plate_id=p.id WHERE p.owner_id=? ORDER BY p.id DESC LIMIT 250',(uid,)).fetchall()
        return jsonify(plates=[dict(r) for r in rows])


@app.post('/api/sell-system')
@authenticated
def sell_system(uid):
    pid=request.get_json(silent=True) or {}
    try: pid=int(pid.get('plate_id'))
    except (ValueError,TypeError): return jsonify(error='Некорректный номер'),400
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT rarity FROM plates WHERE id=? AND owner_id=?',(pid,uid)).fetchone()
        if not p or p['rarity']!='Обычный' or c.execute('SELECT 1 FROM listings WHERE plate_id=?',(pid,)).fetchone():
            c.rollback(); return jsonify(error='Системе можно продать только свободный обычный номер'),400
        c.execute('DELETE FROM plates WHERE id=?',(pid,))
        c.execute('UPDATE users SET balance=balance+25 WHERE id=?',(uid,))
        c.execute('INSERT INTO ledger(user_id,amount,reason,created_at) VALUES(?,?,?,?)',(uid,25,'Продажа системе',int(time.time())))
        c.commit()
        return jsonify(ok=True)


@app.get('/api/market')
@authenticated
def market(uid):
    with db() as c:
        rows=c.execute('SELECT l.id,l.price,l.seller_id,p.code,p.rarity,u.name AS seller FROM listings l JOIN plates p ON p.id=l.plate_id JOIN users u ON u.id=l.seller_id ORDER BY l.id DESC LIMIT 100').fetchall()
        return jsonify(listings=[dict(r) for r in rows])


@app.post('/api/list')
@authenticated
def list_plate(uid):
    data=request.get_json(silent=True) or {}
    try: pid,price=int(data.get('plate_id')),int(data.get('price'))
    except (ValueError,TypeError): return jsonify(error='Укажи номер и цену'),400
    if not 100<=price<=100000000: return jsonify(error='Цена должна быть от 100 до 100 000 000 NC'),400
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT COUNT(*) FROM listings WHERE seller_id=?',(uid,)).fetchone()[0]>=3:
            c.rollback();return jsonify(error='Доступно не более трёх активных объявлений'),400
        p=c.execute('SELECT id FROM plates WHERE id=? AND owner_id=?',(pid,uid)).fetchone()
        if not p or c.execute('SELECT id FROM listings WHERE plate_id=?',(pid,)).fetchone():
            c.rollback();return jsonify(error='Номер недоступен для продажи'),400
        c.execute('INSERT INTO listings(plate_id,seller_id,price,created_at) VALUES(?,?,?,?)',(pid,uid,price,int(time.time())))
        c.commit();return jsonify(ok=True)


@app.post('/api/cancel')
@authenticated
def cancel(uid):
    data=request.get_json(silent=True) or {}
    try: lid=int(data.get('listing_id'))
    except (ValueError,TypeError): return jsonify(error='Неверное объявление'),400
    with db() as c:
        cur=c.execute('DELETE FROM listings WHERE id=? AND seller_id=?',(lid,uid))
        return jsonify(ok=cur.rowcount>0)


@app.post('/api/buy')
@authenticated
def buy(uid):
    data=request.get_json(silent=True) or {}
    try: lid=int(data.get('listing_id'))
    except (ValueError,TypeError): return jsonify(error='Неверное объявление'),400
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        item=c.execute('SELECT * FROM listings WHERE id=?',(lid,)).fetchone()
        if not item:
            c.rollback();return jsonify(error='Объявление уже закрыто'),404
        if item['seller_id']==uid:
            c.rollback();return jsonify(error='Нельзя купить свой номер'),400
        price=item['price']; fee=(price*5+99)//100
        cur=c.execute('UPDATE users SET balance=balance-? WHERE id=? AND balance>=?',(price,uid,price))
        if not cur.rowcount:
            c.rollback();return jsonify(error='Недостаточно NC'),400
        c.execute('UPDATE users SET balance=balance+? WHERE id=?',(price-fee,item['seller_id']))
        c.execute('UPDATE plates SET owner_id=? WHERE id=? AND owner_id=?',(uid,item['plate_id'],item['seller_id']))
        c.execute('DELETE FROM listings WHERE id=?',(lid,))
        now=int(time.time())
        c.execute('INSERT INTO trades(plate_id,seller_id,buyer_id,price,created_at) VALUES(?,?,?,?,?)',(item['plate_id'],item['seller_id'],uid,price,now))
        c.executemany('INSERT INTO ledger(user_id,amount,reason,created_at) VALUES(?,?,?,?)',[(uid,-price,'Покупка номера',now),(item['seller_id'],price-fee,'Продажа номера',now)])
        c.commit();return jsonify(ok=True)


@app.get('/api/top')
@authenticated
def top(uid):
    with db() as c:
        rows=c.execute('SELECT u.name,u.username,u.balance,COUNT(p.id) AS collection FROM users u LEFT JOIN plates p ON p.owner_id=u.id GROUP BY u.id ORDER BY collection DESC,balance DESC LIMIT 30').fetchall()
        return jsonify(players=[dict(r) for r in rows])


@app.get('/health')
def health(): return jsonify(status='ok')

init_db()
if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')),debug=False)
