# NEXORA server.py — updated business empire version
import os, json, time, random, sqlite3, hashlib, hmac, uuid
from functools import wraps
from urllib.parse import parse_qsl
from flask import Flask, request, jsonify, send_from_directory

app=Flask(__name__,static_folder='web',static_url_path='')
DB_PATH=os.getenv('DB_PATH','nexora.db'); BOT_TOKEN=os.getenv('BOT_TOKEN','')
CREATOR_TELEGRAM_ID=os.getenv('CREATOR_TELEGRAM_ID','8518976778')
app.config['JSON_AS_ASCII']=False

def db():
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; return con

def init_db():
    con=db()
    con.execute('PRAGMA busy_timeout=5000')
    schema=[
        "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id TEXT UNIQUE NOT NULL,username TEXT DEFAULT '',first_name TEXT DEFAULT '',last_name TEXT DEFAULT '',photo_url TEXT DEFAULT '',coins INTEGER DEFAULT 1000,xp INTEGER DEFAULT 0,level INTEGER DEFAULT 1,rating INTEGER DEFAULT 0,bank INTEGER DEFAULT 0,created_at INTEGER DEFAULT 0,last_daily INTEGER DEFAULT 0,role TEXT DEFAULT 'player',world INTEGER DEFAULT 1);",
        'CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,item_key TEXT NOT NULL,quantity INTEGER DEFAULT 0,UNIQUE(user_id,item_key));',
        'CREATE TABLE IF NOT EXISTS cooldowns(user_id INTEGER NOT NULL,action TEXT NOT NULL,last_used INTEGER DEFAULT 0,PRIMARY KEY(user_id,action));',
        'CREATE TABLE IF NOT EXISTS businesses(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,business_key TEXT NOT NULL,level INTEGER DEFAULT 1,last_collect INTEGER DEFAULT 0,UNIQUE(user_id,business_key));',
        'CREATE TABLE IF NOT EXISTS properties(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,property_key TEXT NOT NULL,UNIQUE(user_id,property_key));',
        'CREATE TABLE IF NOT EXISTS skills(user_id INTEGER PRIMARY KEY,mining INTEGER DEFAULT 1,farming INTEGER DEFAULT 1,fishing INTEGER DEFAULT 1,business INTEGER DEFAULT 1,work INTEGER DEFAULT 1);',
        "CREATE TABLE IF NOT EXISTS market(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,item_key TEXT NOT NULL,quantity INTEGER NOT NULL,price_each INTEGER NOT NULL,created_at INTEGER DEFAULT 0,status TEXT DEFAULT 'active');",
        "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,creator_id TEXT NOT NULL,event_type TEXT NOT NULL,multiplier REAL DEFAULT 1,ends_at INTEGER NOT NULL,title TEXT DEFAULT '',description TEXT DEFAULT '',active INTEGER DEFAULT 1,created_at INTEGER DEFAULT 0);",
        "CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,amount INTEGER NOT NULL,reason TEXT DEFAULT '',created_at INTEGER DEFAULT 0);",
        'CREATE TABLE IF NOT EXISTS quests(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,quest_key TEXT NOT NULL,progress INTEGER DEFAULT 0,completed INTEGER DEFAULT 0,claimed INTEGER DEFAULT 0,UNIQUE(user_id,quest_key));',
        'CREATE TABLE IF NOT EXISTS achievements(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,achievement_key TEXT NOT NULL,UNIQUE(user_id,achievement_key));',
        'CREATE TABLE IF NOT EXISTS prefixes(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,prefix_key TEXT NOT NULL,UNIQUE(user_id,prefix_key));',
        'CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);',
        'CREATE TABLE IF NOT EXISTS promo_codes(code TEXT PRIMARY KEY,coins INTEGER NOT NULL DEFAULT 0,xp INTEGER NOT NULL DEFAULT 0,active INTEGER DEFAULT 1);',
        'CREATE TABLE IF NOT EXISTS promo_redemptions(user_id INTEGER NOT NULL,code TEXT NOT NULL,redeemed_at INTEGER DEFAULT 0,PRIMARY KEY(user_id,code));',
        "CREATE TABLE IF NOT EXISTS business_market(id INTEGER PRIMARY KEY AUTOINCREMENT,seller_id INTEGER NOT NULL,business_id INTEGER NOT NULL,business_key TEXT NOT NULL,title TEXT NOT NULL,level INTEGER DEFAULT 1,price INTEGER NOT NULL,created_at INTEGER DEFAULT 0,status TEXT DEFAULT 'active');",
        'CREATE TABLE IF NOT EXISTS wipe_history(id INTEGER PRIMARY KEY AUTOINCREMENT,creator_id TEXT NOT NULL,created_at INTEGER DEFAULT 0,affected_users INTEGER DEFAULT 0);',
        "CREATE TABLE IF NOT EXISTS admin_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,creator_id TEXT NOT NULL,action TEXT NOT NULL,target_telegram_id TEXT DEFAULT '',details TEXT DEFAULT '',created_at INTEGER DEFAULT 0);",
        "CREATE TABLE IF NOT EXISTS item_catalog(item_key TEXT PRIMARY KEY,name TEXT NOT NULL,icon TEXT DEFAULT '',base_price INTEGER DEFAULT 0);",
        "CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,message TEXT NOT NULL,type TEXT DEFAULT 'info',is_read INTEGER DEFAULT 0,created_at INTEGER DEFAULT 0);",
        'CREATE TABLE IF NOT EXISTS work_sessions(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,job_key TEXT NOT NULL,taps_required INTEGER NOT NULL,taps INTEGER DEFAULT 0,started_at INTEGER DEFAULT 0,expires_at INTEGER NOT NULL,completed INTEGER DEFAULT 0);',
    ]
    try:
        for index, statement in enumerate(schema, 1):
            try:
                con.execute(statement)
            except sqlite3.Error as exc:
                print(f'NEXORA SQL ERROR #{index}: {exc} | {statement}', flush=True)
                con.rollback()
                raise
        con.commit()
    finally:
        con.close()
try:
    init_db()
except Exception as exc:
    print('NEXORA DATABASE INIT ERROR:', repr(exc), flush=True)
    raise

def migrate_database():
    con=db(); cols={r['name'] for r in con.execute('PRAGMA table_info(users)').fetchall()}
    if 'role' not in cols: con.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'player'")
    if 'world' not in cols: con.execute("ALTER TABLE users ADD COLUMN world INTEGER DEFAULT 1")
    con.execute("UPDATE users SET world=1 WHERE world IS NULL OR world<1")
    con.execute("UPDATE users SET role='creator' WHERE telegram_id=?",(str(CREATOR_TELEGRAM_ID),))
    con.execute("UPDATE users SET role='player' WHERE role IS NULL OR role='' ")
    con.commit(); con.close()
try:
    migrate_database()
except Exception as exc:
    print('NEXORA DATABASE MIGRATION ERROR:', repr(exc), flush=True)
    raise

def seed_promo_codes():
    con=db(); con.executemany('INSERT OR IGNORE INTO promo_codes(code,coins,xp,active) VALUES(?,?,?,1)',[("START",1500,20),("BETA TEST",1500,20),("GO",1500,20)]); con.commit(); con.close()
try:
    seed_promo_codes()
except Exception as exc:
    print('NEXORA PROMO SEED ERROR:', repr(exc), flush=True)
    raise

WORLDS={1:{'name':'Мир бизнеса','level':1,'description':'Стартовый мир NEXORA'},2:{'name':'Мир корпораций','level':100,'description':'Новый мир открывается на 100 уровне'},3:{'name':'Мир мегакорпораций','level':200,'description':'Третий мир открывается на 200 уровне'}}
JOBS={
'courier':{'name':'Курьер','level':1,'reward':80,'xp':10,'cooldown':45,'world':1,'taps':12},
'loader':{'name':'Грузчик','level':2,'reward':140,'xp':15,'cooldown':60,'world':1,'taps':15},
'fisher':{'name':'Рыбак','level':4,'reward':230,'xp':22,'cooldown':90,'world':1,'taps':18},
'miner':{'name':'Шахтёр','level':6,'reward':360,'xp':32,'cooldown':110,'world':1,'taps':20},
'driver':{'name':'Водитель','level':9,'reward':520,'xp':42,'cooldown':130,'world':1,'taps':22},
'programmer':{'name':'Программист','level':13,'reward':750,'xp':55,'cooldown':160,'world':1,'taps':25},
'trader':{'name':'Трейдер','level':18,'reward':1050,'xp':72,'cooldown':190,'world':1,'taps':28},
'engineer':{'name':'Инженер','level':24,'reward':1450,'xp':92,'cooldown':220,'world':1,'taps':30},
'director':{'name':'Директор','level':32,'reward':2100,'xp':120,'cooldown':260,'world':1,'taps':34},
'magnate':{'name':'Магнат','level':45,'reward':3200,'xp':160,'cooldown':320,'world':1,'taps':38},
'corporate_manager':{'name':'Корпоративный менеджер','level':100,'reward':7000,'xp':250,'cooldown':360,'world':2,'taps':45},
'investment_banker':{'name':'Инвестиционный банкир','level':110,'reward':11000,'xp':160,'cooldown':400,'world':2,'taps':50},
'tech_ceo':{'name':'CEO технологической компании','level':125,'reward':17000,'xp':420,'cooldown':450,'world':2,'taps':55},
'global_trader':{'name':'Глобальный трейдер','level':145,'reward':26000,'xp':550,'cooldown':500,'world':2,'taps':60},
'corporation_owner':{'name':'Владелец корпорации','level':170,'reward':40000,'xp':700,'cooldown':560,'world':2,'taps':65},
'ceo_empire':{'name':'CEO империи','level':200,'reward':65000,'xp':900,'cooldown':620,'world':3,'taps':75},
'industrial_tycoon':{'name':'Промышленный магнат','level':225,'reward':95000,'xp':1100,'cooldown':680,'world':3,'taps':82},
'global_empire':{'name':'Глобальный император','level':250,'reward':140000,'xp':1400,'cooldown':750,'world':3,'taps':90}}
ITEMS={'iron':{'name':'Железо','icon':'⛓️','base_price':35},'coal':{'name':'Уголь','icon':'⬛','base_price':25},'gold':{'name':'Золото','icon':'🪙','base_price':120},'wood':{'name':'Древесина','icon':'🪵','base_price':30},'wheat':{'name':'Пшеница','icon':'🌾','base_price':20},'apple':{'name':'Яблоко','icon':'🍎','base_price':25},'fish':{'name':'Рыба','icon':'🐟','base_price':70},'rare_fish':{'name':'Редкая рыба','icon':'🐠','base_price':250},'steel':{'name':'Сталь','icon':'🔩','base_price':180},'energy_core':{'name':'Энергокристалл','icon':'🔷','base_price':500},'microchip':{'name':'Микрочип','icon':'💾','base_price':750},'quantum':{'name':'Квантовый модуль','icon':'🧬','base_price':1800}}
BUSINESS_LIMITS={'farm':100,'mine':75,'factory':50,'tech':25,'space':10}; PROPERTY_LIMITS={'room':500,'apartment':250,'penthouse':50,'mansion':10}; BUSINESS_UPGRADE_MULTIPLIER=1.55
BUSINESSES={'farm':{'name':'Ферма','price':5000,'income':300,'interval':3600},'mine':{'name':'Шахта','price':15000,'income':900,'interval':3600},'factory':{'name':'Завод','price':50000,'income':3200,'interval':3600},'tech':{'name':'IT-компания','price':150000,'income':10000,'interval':3600},'space':{'name':'Космическая корпорация','price':500000,'income':38000,'interval':3600}}
PROPERTIES={'room':{'name':'Комната','price':2500,'rating':5},'apartment':{'name':'Квартира','price':25000,'rating':30},'penthouse':{'name':'Пентхаус','price':150000,'rating':100},'mansion':{'name':'Особняк','price':750000,'rating':300}}
QUESTS={'work3':{'name':'Рабочая смена','description':'Выполнить 3 работы','target':3,'reward':500},'mine10':{'name':'Шахтёр','description':'Добыть 10 ресурсов','target':10,'reward':1000},'market1':{'name':'Торговец','description':'Продать предмет на рынке','target':1,'reward':1500}}
ROLE_LABELS={'creator':'Создатель','assistant':'Помощник создателя','player':'Игрок'}

def now(): return int(time.time())
def is_creator(u): return str(u['telegram_id'])==str(CREATOR_TELEGRAM_ID)
def is_assistant(u): return not is_creator(u) and str(u['role'] or 'player')=='assistant'
def role_name(u): return 'creator' if is_creator(u) else ('assistant' if is_assistant(u) else 'player')
def role_display(u): return ROLE_LABELS.get(role_name(u),'Игрок')
def world_for_level(level):
    current=1
    for wid,w in WORLDS.items():
        if level>=w['level']: current=wid
    return current
def world_unlocked(level,wid): return level>=WORLDS.get(wid,{'level':10**9})['level']
def current_world(u):
    try: wid=int(u['world'] or 1)
    except: wid=1
    if wid not in WORLDS: wid=1
    return wid

def level_from_xp(xp):
    level=1; need=100
    # Level is no longer capped at 100: level 100 opens world 2 and later worlds continue.
    while xp>=need and level<300:
        xp-=need; level+=1; need=int(100*(1.18**(level-1)))
    return level

def xp_for_level(level):
    xp=0
    for lv in range(1,max(1,min(level,300))): xp+=int(100*(1.18**(lv-1)))
    return xp

def add_notification(con,user_id,title,message,kind='info'):
    con.execute('INSERT INTO notifications(user_id,title,message,type,is_read,created_at) VALUES(?,?,?,?,0,?)',(user_id,title,message,kind,now()))

def add_xp(con,user_id,amount):
    u=con.execute('SELECT xp,level,rating FROM users WHERE id=?',(user_id,)).fetchone()
    if not u:return
    old=u['level']; new_xp=u['xp']+amount; new_level=level_from_xp(new_xp); rating_add=max(1,amount//5)
    con.execute('UPDATE users SET xp=?,level=?,rating=rating+? WHERE id=?',(new_xp,new_level,rating_add,user_id))
    if new_level>old:
        row=con.execute('SELECT world FROM users WHERE id=?',(user_id,)).fetchone()
        current=int(row['world'] or 1) if row else 1
        unlocked=[wid for wid,w in WORLDS.items() if wid>current and new_level>=w['level']]
        if unlocked:
            wid=min(unlocked); add_notification(con,user_id,f'🌎 Доступен {WORLDS[wid]["name"]}',f'Ты достиг {new_level} уровня. Теперь в разделе «Мир» можно перейти в новый мир и начать его экономику заново.','world')
        else:
            add_notification(con,user_id,'📈 Новый уровень',f'Ты достиг уровня {new_level}.','level')

def add_coins(con,user_id,amount,reason=''):
    con.execute('UPDATE users SET coins=coins+? WHERE id=?',(amount,user_id)); con.execute('INSERT INTO transactions(user_id,amount,reason,created_at) VALUES(?,?,?,?)',(user_id,amount,reason,now()))

def cleanup_events(con): con.execute('UPDATE events SET active=0 WHERE active=1 AND ends_at<=?',(now(),))
def get_multiplier(con,event_type):
    cleanup_events(con); rows=con.execute("SELECT multiplier FROM events WHERE active=1 AND ends_at>? AND (event_type=? OR event_type='all')",(now(),event_type)).fetchall(); r=1.0
    for x in rows:r*=max(1,float(x['multiplier']))
    return min(10,r)
def get_discount(con,event_type):
    cleanup_events(con); rows=con.execute("SELECT multiplier FROM events WHERE active=1 AND ends_at>? AND event_type=?",(now(),event_type)).fetchall(); rem=1
    for x in rows: rem*=1-max(0,min(.9,float(x['multiplier'])/100))
    return min(.9,1-rem)
def discounted_price(con,event_type,p): return max(1,int(round(p*(1-get_discount(con,event_type)))))
def log_admin(con,actor,action,target='',details=''): con.execute('INSERT INTO admin_logs(creator_id,action,target_telegram_id,details,created_at) VALUES(?,?,?,?,?)',(str(actor),action,str(target),details,now()))


def cooldown_remaining(con,uid,action,cooldown):
    r=con.execute('SELECT last_used FROM cooldowns WHERE user_id=? AND action=?',(uid,action)).fetchone(); return 0 if not r else max(0,cooldown-(now()-r['last_used']))
def set_cooldown(con,uid,action): con.execute('INSERT INTO cooldowns(user_id,action,last_used) VALUES(?,?,?) ON CONFLICT(user_id,action) DO UPDATE SET last_used=excluded.last_used',(uid,action,now()))
def add_item(con,uid,key,q=1):
    if key in ITEMS: con.execute('INSERT INTO inventory(user_id,item_key,quantity) VALUES(?,?,?) ON CONFLICT(user_id,item_key) DO UPDATE SET quantity=quantity+excluded.quantity',(uid,key,q))
def remove_item(con,uid,key,q):
    r=con.execute('SELECT quantity FROM inventory WHERE user_id=? AND item_key=?',(uid,key)).fetchone()
    if not r or r['quantity']<q:return False
    con.execute('UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND item_key=?',(q,uid,key));return True

def ensure_user(tg):
    con=db(); tid=str(tg['id']); u=con.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
    if not u:
        con.execute('INSERT INTO users(telegram_id,username,first_name,last_name,photo_url,coins,xp,level,created_at,role) VALUES(?,?,?,?,?,1000,0,1,?,?)',(tid,tg.get('username',''),tg.get('first_name',''),tg.get('last_name',''),tg.get('photo_url',''),now(),'creator' if tid==str(CREATOR_TELEGRAM_ID) else 'player'));con.commit();u=con.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
    else:
        con.execute('UPDATE users SET username=?,first_name=?,last_name=?,photo_url=? WHERE telegram_id=?',(tg.get('username',''),tg.get('first_name',''),tg.get('last_name',''),tg.get('photo_url',''),tid));con.commit()
    if tid==str(CREATOR_TELEGRAM_ID):con.execute("UPDATE users SET role='creator' WHERE telegram_id=?",(tid,))
    con.execute('INSERT OR IGNORE INTO skills(user_id) VALUES(?)',(u['id'],))
    for k in QUESTS:con.execute('INSERT OR IGNORE INTO quests(user_id,quest_key) VALUES(?,?)',(u['id'],k))
    if tid==str(CREATOR_TELEGRAM_ID):con.execute("INSERT OR IGNORE INTO prefixes(user_id,prefix_key) VALUES(?, 'creator')",(u['id'],))
    if str(u['role'] or '')=='assistant':con.execute("INSERT OR IGNORE INTO prefixes(user_id,prefix_key) VALUES(?, 'assistant')",(u['id'],))
    else:con.execute("DELETE FROM prefixes WHERE user_id=? AND prefix_key='assistant'",(u['id'],))
    con.commit();con.close();return get_user_by_tg(tid)
def get_user_by_tg(tid):
    con=db();u=con.execute('SELECT * FROM users WHERE telegram_id=?',(str(tid),)).fetchone();con.close();return u

def telegram_auth():
    header=request.headers.get('X-Telegram-Init-Data','')
    if not BOT_TOKEN:return {'id':'8518976778','username':'creator','first_name':'Creator','last_name':'NEXORA','photo_url':''}
    if not header:return None
    try:
        data=dict(parse_qsl(header,keep_blank_values=True)); received=data.pop('hash',None); auth_date=int(data.get('auth_date','0'))
        if not received or now()-auth_date>86400:return None
        check='\n'.join(f'{k}={data[k]}' for k in sorted(data)); secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest(); calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc,received):return None
        return json.loads(data.get('user','{}'))
    except:return None
def current_user():
    tg=telegram_auth()
    if not tg:return None
    ensure_user(tg);return get_user_by_tg(str(tg['id']))
def require_user(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        u=current_user()
        if not u:return jsonify({'ok':False,'error':'Telegram авторизация не прошла'}),401
        return fn(u,*a,**kw)
    return wrapper
def require_admin(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        u=current_user()
        if not u:return jsonify({'ok':False,'error':'Авторизация не прошла'}),401
        if not(is_creator(u) or is_assistant(u)):return jsonify({'ok':False,'error':'Доступ только для администрации'}),403
        return fn(u,*a,**kw)
    return wrapper
def require_creator(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        u=current_user()
        if not u:return jsonify({'ok':False,'error':'Авторизация не прошла'}),401
        if not is_creator(u):return jsonify({'ok':False,'error':'Доступ только для создателя'}),403
        return fn(u,*a,**kw)
    return wrapper

def user_json(u,con):
    inv=con.execute('SELECT item_key,quantity FROM inventory WHERE user_id=? AND quantity>0 ORDER BY quantity DESC',(u['id'],)).fetchall(); inventory=[]
    for r in inv:
        if r['item_key'] in ITEMS: inventory.append({'key':r['item_key'],'name':ITEMS[r['item_key']]['name'],'icon':ITEMS[r['item_key']]['icon'],'quantity':r['quantity'],'price':ITEMS[r['item_key']]['base_price']})
    unread=con.execute('SELECT COUNT(*) c FROM notifications WHERE user_id=? AND is_read=0',(u['id'],)).fetchone()['c']
    return {'id':u['id'],'telegram_id':u['telegram_id'],'username':u['username'],'first_name':u['first_name'],'last_name':u['last_name'],'photo_url':u['photo_url'],'coins':u['coins'],'bank':u['bank'],'xp':u['xp'],'level':u['level'],'rating':u['rating'],'prefix':role_display(u),'role':role_name(u),'role_display':role_display(u),'creator':is_creator(u),'assistant':is_assistant(u),'world':current_world(u),'world_name':WORLDS[current_world(u)]['name'],'inventory':inventory,'unread_notifications':unread}

@app.get('/health')
def health():
    try:
        con=db(); con.execute('SELECT 1').fetchone(); con.close()
        return jsonify({'ok':True,'service':'NEXORA'})
    except Exception as exc:
        return jsonify({'ok':False,'error':str(exc)}),500

@app.get('/')
def index():return send_from_directory('web','index.html')

@app.get('/api/bootstrap')
@require_user
def bootstrap(u):
    con=db();cleanup_events(con);data=user_json(u,con)
    events=[dict(x) for x in con.execute('SELECT id,event_type,multiplier,ends_at,title,description FROM events WHERE active=1 AND ends_at>? ORDER BY id DESC',(now(),)).fetchall()]
    market=[]
    for r in con.execute('SELECT m.*,u.username,u.first_name FROM market m JOIN users u ON u.id=m.seller_id WHERE m.status="active" ORDER BY m.id DESC LIMIT 50').fetchall():
        if r['item_key'] in ITEMS:market.append({'id':r['id'],'item_key':r['item_key'],'name':ITEMS[r['item_key']]['name'],'icon':ITEMS[r['item_key']]['icon'],'quantity':r['quantity'],'price_each':r['price_each'],'total':r['quantity']*r['price_each'],'seller':r['username'] or r['first_name'] or 'Игрок','mine':r['seller_id']==u['id']})
    bm=[{'id':r['id'],'business_key':r['business_key'],'name':r['title'],'level':r['level'],'price':r['price'],'seller':r['username'] or r['first_name'] or 'Игрок','mine':r['seller_id']==u['id']} for r in con.execute('SELECT bm.*,u.username,u.first_name FROM business_market bm JOIN users u ON u.id=bm.seller_id WHERE bm.status="active" ORDER BY bm.id DESC LIMIT 50').fetchall()]
    businesses=[]; owned={r['business_key']:dict(r) for r in con.execute('SELECT business_key,level,last_collect FROM businesses WHERE user_id=?',(u['id'],)).fetchall()}
    for k,v in BUSINESSES.items():
        own=owned.get(k); cnt=con.execute('SELECT COUNT(*) c FROM businesses WHERE business_key=?',(k,)).fetchone()['c']; sr=con.execute('SELECT value FROM settings WHERE key=?',(f'business_name:{u["id"]}:{k}',)).fetchone();name=sr['value'] if sr else v['name'];businesses.append({'key':k,**v,'name':name,'price':discounted_price(con,'business_discount',v['price']),'base_price':v['price'],'discount':int(get_discount(con,'business_discount')*100),'limit':BUSINESS_LIMITS.get(k,0),'owned_count':cnt,'available':cnt<BUSINESS_LIMITS.get(k,10**9),'owned':bool(own),'level_owned':own['level'] if own else 0,'last_collect':own['last_collect'] if own else 0})
    properties=[]; ownedp={r['property_key'] for r in con.execute('SELECT property_key FROM properties WHERE user_id=?',(u['id'],)).fetchall()}
    for k,v in PROPERTIES.items():
        cnt=con.execute('SELECT COUNT(*) c FROM properties WHERE property_key=?',(k,)).fetchone()['c'];properties.append({'key':k,**v,'price':discounted_price(con,'property_discount',v['price']),'base_price':v['price'],'discount':int(get_discount(con,'property_discount')*100),'limit':PROPERTY_LIMITS.get(k,0),'owned_count':cnt,'available':cnt<PROPERTY_LIMITS.get(k,10**9),'owned':k in ownedp})
    quests=[]
    for r in con.execute('SELECT quest_key,progress,completed,claimed FROM quests WHERE user_id=?',(u['id'],)).fetchall():
        if r['quest_key'] in QUESTS:quests.append({'key':r['quest_key'],**QUESTS[r['quest_key']],'progress':r['progress'],'completed':bool(r['completed']),'claimed':bool(r['claimed'])})
    sr=con.execute('SELECT * FROM skills WHERE user_id=?',(u['id'],)).fetchone();skills=dict(sr) if sr else {}
    con.commit();con.close()
    return jsonify({'ok':True,'user':data,'jobs':[{'key':k,**v,'world_name':WORLDS[v['world']]['name'],'world_unlocked':world_unlocked(u['level'],v['world'])} for k,v in JOBS.items()],'worlds':[{'key':k,**v,'unlocked':world_unlocked(u['level'],k)} for k,v in WORLDS.items()],'items':ITEMS,'businesses':businesses,'properties':properties,'quests':quests,'skills':skills,'market':market,'business_market':bm,'events':events,'promo_codes':['START','BETA TEST','GO'],'creator':is_creator(u),'assistant':is_assistant(u),'admin':is_creator(u) or is_assistant(u)})

# WORLD SWITCH
@app.post('/api/world/switch')
@require_user
def world_switch(u):
    data=request.get_json(silent=True) or {}
    try: wid=int(data.get('world',0))
    except: wid=0
    if wid not in WORLDS:
        return jsonify({'ok':False,'error':'Мир не найден'}),400
    if wid<=current_world(u):
        return jsonify({'ok':False,'error':'Можно перейти только в следующий мир'}),400
    if u['level']<WORLDS[wid]['level']:
        return jsonify({'ok':False,'error':f'Нужен уровень {WORLDS[wid]["level"]}'}),400
    con=db()
    # Новый мир получает отдельную экономику. Уровень/XP и общий рейтинг сохраняются.
    uid=u['id']
    # Отменяем старые торговые объявления, чтобы после сброса экономики не возникало дубликатов.
    for r in con.execute("SELECT item_key,quantity FROM market WHERE seller_id=? AND status='active'",(uid,)).fetchall():
        add_item(con,uid,r['item_key'],r['quantity'])
    con.execute("UPDATE market SET status='cancelled' WHERE seller_id=? AND status='active'",(uid,))
    con.execute("UPDATE business_market SET status='cancelled' WHERE seller_id=? AND status='active'",(uid,))
    for table in ('inventory','businesses','properties','cooldowns'):
        con.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
    con.execute('DELETE FROM work_sessions WHERE user_id=?',(uid,))
    con.execute('UPDATE users SET world=?,coins=1000,bank=0 WHERE id=?',(wid,uid))
    con.execute('INSERT INTO transactions(user_id,amount,reason,created_at) VALUES(?,?,?,?)',(uid,1000,f'Стартовая экономика: {WORLDS[wid]["name"]}',now()))
    add_notification(con,uid,'🌍 Новый мир',f'Ты перешёл в {WORLDS[wid]["name"]}. Экономика нового мира начата с 1000 💎.','world')
    con.commit(); fresh=con.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone(); con.close()
    return jsonify({'ok':True,'world':wid,'world_name':WORLDS[wid]['name'],'user':{'coins':fresh['coins'],'bank':fresh['bank'],'world':wid,'world_name':WORLDS[wid]['name']}})

# WORK TAP SYSTEM
@app.post('/api/work/start')
@require_user
def work_start(u):
    data=request.get_json(silent=True) or {};key=data.get('job');job=JOBS.get(key)
    if not job:return jsonify({'ok':False,'error':'Работа не найдена'}),400
    if job['world'] != current_world(u):
        return jsonify({'ok':False,'error':f'Работа доступна только в {WORLDS[job["world"]]["name"]}'}),400
    if not world_unlocked(u['level'],job['world']):return jsonify({'ok':False,'error':f'Открой {WORLDS[job["world"]]["name"]} на {WORLDS[job["world"]]["level"]} уровне'}),400
    if u['level']<job['level']:return jsonify({'ok':False,'error':f'Нужен уровень {job["level"]}'}),400
    con=db();rem=cooldown_remaining(con,u['id'],'job_'+key,job['cooldown'])
    if rem:con.close();return jsonify({'ok':False,'error':f'Подожди {rem} сек.'}),400
    sid=uuid.uuid4().hex;required=job.get('taps',20);expires=now()+120
    con.execute('DELETE FROM work_sessions WHERE user_id=? AND completed=0',(u['id'],));con.execute('INSERT INTO work_sessions(id,user_id,job_key,taps_required,taps,started_at,expires_at,completed) VALUES(?,?,?,?,?,?,?,0)',(sid,u['id'],key,required,0,now(),expires));con.commit();con.close()
    return jsonify({'ok':True,'session_id':sid,'job':key,'taps':0,'taps_required':required,'progress':0,'expires_at':expires})

@app.post('/api/work/tap')
@require_user
def work_tap(u):
    data=request.get_json(silent=True) or {};sid=str(data.get('session_id',''));con=db();s=con.execute('SELECT * FROM work_sessions WHERE id=? AND user_id=? AND completed=0',(sid,u['id'])).fetchone()
    if not s:con.close();return jsonify({'ok':False,'error':'Рабочая сессия не найдена'}),400
    if s['expires_at']<now():con.execute('DELETE FROM work_sessions WHERE id=?',(sid,));con.commit();con.close();return jsonify({'ok':False,'error':'Время работы истекло'}),400
    taps=min(s['taps']+1,s['taps_required']);con.execute('UPDATE work_sessions SET taps=? WHERE id=?',(taps,sid));con.commit();con.close()
    return jsonify({'ok':True,'taps':taps,'taps_required':s['taps_required'],'progress':min(100,int(taps*100/s['taps_required'])),'complete':taps>=s['taps_required']})

@app.post('/api/work/complete')
@require_user
def work_complete(u):
    data=request.get_json(silent=True) or {};sid=str(data.get('session_id',''));con=db();s=con.execute('SELECT * FROM work_sessions WHERE id=? AND user_id=? AND completed=0',(sid,u['id'])).fetchone()
    if not s:con.close();return jsonify({'ok':False,'error':'Рабочая сессия не найдена'}),400
    if s['expires_at']<now():con.execute('DELETE FROM work_sessions WHERE id=?',(sid,));con.commit();con.close();return jsonify({'ok':False,'error':'Время работы истекло'}),400
    if s['taps']<s['taps_required']:con.close();return jsonify({'ok':False,'error':f'Заполни круг до 100% ({s["taps"]}/{s["taps_required"]})'}),400
    job=JOBS[s['job_key']];mult=get_multiplier(con,'jobs');reward=int(job['reward']*mult);add_coins(con,u['id'],reward,f'Работа: {job["name"]}');add_xp(con,u['id'],job['xp']);set_cooldown(con,u['id'],'job_'+s['job_key']);con.execute('UPDATE work_sessions SET completed=1 WHERE id=?',(sid,));q=con.execute("SELECT progress FROM quests WHERE user_id=? AND quest_key='work3'",(u['id'],)).fetchone()
    if q and q['progress']<3:
        p=q['progress']+1;con.execute('UPDATE quests SET progress=?,completed=? WHERE user_id=? AND quest_key=\'work3\'',(p,1 if p>=3 else 0,u['id']))
    con.commit();fresh=con.execute('SELECT coins,xp,level FROM users WHERE id=?',(u['id'],)).fetchone();con.close();return jsonify({'ok':True,'reward':reward,'multiplier':mult,'user':dict(fresh)})

# Compatibility endpoint: frontend will be switched to start/tap/complete.
@app.post('/api/work')
@require_user
def work_compat(u):
    return jsonify({'ok':False,'error':'Теперь работа выполняется тапами: используй /api/work/start, /api/work/tap и /api/work/complete.'}),400

# MINING/FARM/FISHING
@app.post('/api/mining')
@require_user
def mining(u):
    con=db();rem=cooldown_remaining(con,u['id'],'mining',30)
    if rem:con.close();return jsonify({'ok':False,'error':f'Шахта перезаряжается: {rem} сек.'}),400
    r=con.execute('SELECT mining FROM skills WHERE user_id=?',(u['id'],)).fetchone();lvl=r['mining'] if r else 1;possible=['iron','coal','wood']
    if lvl>=3:possible.append('gold')
    if lvl>=6:possible.append('steel')
    key=random.choice(possible);q=1+min(3,lvl//3);add_item(con,u['id'],key,q);add_xp(con,u['id'],35+lvl*2);set_cooldown(con,u['id'],'mining');con.execute('UPDATE skills SET mining=mining+1 WHERE user_id=? AND mining<20',(u['id'],));con.commit();con.close();return jsonify({'ok':True,'item':ITEMS[key]['name'],'icon':ITEMS[key]['icon'],'quantity':q})
@app.post('/api/farm')
@require_user
def farm(u):
    con=db();rem=cooldown_remaining(con,u['id'],'farm',40)
    if rem:con.close();return jsonify({'ok':False,'error':f'Ферма готовится: {rem} сек.'}),400
    r=con.execute('SELECT farming FROM skills WHERE user_id=?',(u['id'],)).fetchone();lvl=r['farming'] if r else 1;add_item(con,u['id'],'wheat',2+lvl//3);add_item(con,u['id'],'apple',1+lvl//5);add_xp(con,u['id'],30);con.execute('UPDATE skills SET farming=farming+1 WHERE user_id=? AND farming<20',(u['id'],));set_cooldown(con,u['id'],'farm');con.commit();con.close();return jsonify({'ok':True,'message':'Урожай собран'})
@app.post('/api/fishing')
@require_user
def fishing(u):
    con=db();rem=cooldown_remaining(con,u['id'],'fishing',35)
    if rem:con.close();return jsonify({'ok':False,'error':f'Рыбалка недоступна ещё {rem} сек.'}),400
    r=con.execute('SELECT fishing FROM skills WHERE user_id=?',(u['id'],)).fetchone();lvl=r['fishing'] if r else 1;key='rare_fish' if lvl>=7 and random.random()<.2 else 'fish';q=1+lvl//5;add_item(con,u['id'],key,q);add_xp(con,u['id'],40);con.execute('UPDATE skills SET fishing=fishing+1 WHERE user_id=? AND fishing<20',(u['id'],));set_cooldown(con,u['id'],'fishing');con.commit();con.close();return jsonify({'ok':True,'item':ITEMS[key]['name'],'icon':ITEMS[key]['icon'],'quantity':q})

# BUSINESSES
@app.post('/api/businesses/buy')
@require_user
def buy_business(u):
    data=request.get_json(silent=True) or {};k=data.get('key');b=BUSINESSES.get(k)
    if not b:return jsonify({'ok':False,'error':'Предприятие не найдено'}),400
    con=db()
    if con.execute('SELECT id FROM businesses WHERE user_id=? AND business_key=?',(u['id'],k)).fetchone():con.close();return jsonify({'ok':False,'error':'Предприятие уже куплено'}),400
    cnt=con.execute('SELECT COUNT(*) c FROM businesses WHERE business_key=?',(k,)).fetchone()['c'];limit=BUSINESS_LIMITS.get(k,10**9)
    if cnt>=limit:con.close();return jsonify({'ok':False,'error':f'Лимит предприятия достигнут: {limit} шт.'}),400
    price=discounted_price(con,'business_discount',b['price'])
    if u['coins']<price:con.close();return jsonify({'ok':False,'error':'Недостаточно 💎'}),400
    add_coins(con,u['id'],-price,f'Покупка предприятия: {b["name"]}');con.execute('INSERT INTO businesses(user_id,business_key,level,last_collect) VALUES(?,?,1,?)',(u['id'],k,now()));add_xp(con,u['id'],150);con.commit();con.close();return jsonify({'ok':True,'message':'Предприятие приобретено'})
@app.post('/api/businesses/collect')
@require_user
def collect_business(u):
    data=request.get_json(silent=True) or {};k=data.get('key');b=BUSINESSES.get(k)
    if not b:return jsonify({'ok':False,'error':'Предприятие не найдено'}),400
    con=db();own=con.execute('SELECT level,last_collect FROM businesses WHERE user_id=? AND business_key=?',(u['id'],k)).fetchone()
    if not own:con.close();return jsonify({'ok':False,'error':'Сначала купи предприятие'}),400
    elapsed=now()-own['last_collect']
    if elapsed<b['interval']:con.close();return jsonify({'ok':False,'error':f'Доход будет готов через {(b["interval"]-elapsed)//60} мин.'}),400
    cycles=min(24,elapsed//b['interval']);mult=get_multiplier(con,'businesses');income=int(b['income']*own['level']*cycles*mult);add_coins(con,u['id'],income,f'Доход: {b["name"]}');con.execute('UPDATE businesses SET last_collect=? WHERE user_id=? AND business_key=?',(now(),u['id'],k));add_xp(con,u['id'],100*cycles);con.commit();con.close();return jsonify({'ok':True,'income':income,'multiplier':mult})
@app.post('/api/businesses/upgrade')
@require_user
def upgrade_business(u):
    data=request.get_json(silent=True) or {};k=data.get('key');b=BUSINESSES.get(k)
    if not b:return jsonify({'ok':False,'error':'Предприятие не найдено'}),400
    con=db();o=con.execute('SELECT id,level FROM businesses WHERE user_id=? AND business_key=?',(u['id'],k)).fetchone()
    if not o:con.close();return jsonify({'ok':False,'error':'Предприятие не куплено'}),400
    cost=int(b['price']*(BUSINESS_UPGRADE_MULTIPLIER**o['level']))
    if u['coins']<cost:con.close();return jsonify({'ok':False,'error':f'Нужно {cost:,} 💎'.replace(',',' ')}),400
    nl=o['level']+1;add_coins(con,u['id'],-cost,f'Улучшение предприятия: {b["name"]} Lv.{nl}');con.execute('UPDATE businesses SET level=? WHERE id=?',(nl,o['id']));add_xp(con,u['id'],200+nl*25);con.commit();con.close();return jsonify({'ok':True,'level':nl,'cost':cost})
@app.post('/api/businesses/rename')
@require_user
def rename_business(u):
    d=request.get_json(silent=True) or {};k=d.get('key');title=str(d.get('title','')).strip()
    if k not in BUSINESSES or not title:return jsonify({'ok':False,'error':'Введите корректное название'}),400
    if len(title)>32:return jsonify({'ok':False,'error':'Название максимум 32 символа'}),400
    con=db();con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(f'business_name:{u["id"]}:{k}',title));con.commit();con.close();return jsonify({'ok':True,'name':title})
@app.post('/api/businesses/list')
@require_user
def list_business_for_sale(u):
    d=request.get_json(silent=True) or {};k=d.get('key');price=int(d.get('price',0));title=str(d.get('title','')).strip()
    if k not in BUSINESSES or price<=0:return jsonify({'ok':False,'error':'Неверные данные'}),400
    con=db();o=con.execute('SELECT id,level FROM businesses WHERE user_id=? AND business_key=?',(u['id'],k)).fetchone()
    if not o:con.close();return jsonify({'ok':False,'error':'Предприятие не найдено'}),400
    if con.execute("SELECT id FROM business_market WHERE business_id=? AND status='active'",(o['id'],)).fetchone():con.close();return jsonify({'ok':False,'error':'Предприятие уже выставлено'}),400
    if not title:
        s=con.execute('SELECT value FROM settings WHERE key=?',(f'business_name:{u["id"]}:{k}',)).fetchone();title=s['value'] if s else BUSINESSES[k]['name']
    con.execute('INSERT INTO business_market(seller_id,business_id,business_key,title,level,price,created_at) VALUES(?,?,?,?,?,?,?)',(u['id'],o['id'],k,title,o['level'],price,now()));con.commit();con.close();return jsonify({'ok':True})
@app.post('/api/businesses/market/buy')
@require_user
def buy_business_market(u):
    d=request.get_json(silent=True) or {};lid=int(d.get('id',0));con=db();l=con.execute("SELECT * FROM business_market WHERE id=? AND status='active'",(lid,)).fetchone()
    if not l:con.close();return jsonify({'ok':False,'error':'Предприятие уже продано'}),404
    if l['seller_id']==u['id']:con.close();return jsonify({'ok':False,'error':'Нельзя купить своё предприятие'}),400
    if u['coins']<l['price']:con.close();return jsonify({'ok':False,'error':'Недостаточно 💎'}),400
    if con.execute('SELECT id FROM businesses WHERE user_id=? AND business_key=?',(u['id'],l['business_key'])).fetchone():con.close();return jsonify({'ok':False,'error':'У тебя уже есть это предприятие'}),400
    add_coins(con,u['id'],-l['price'],'Покупка предприятия на рынке');add_coins(con,l['seller_id'],l['price'],'Продажа предприятия на рынке');con.execute('UPDATE businesses SET user_id=? WHERE id=?',(u['id'],l['business_id']));con.execute("UPDATE business_market SET status='sold' WHERE id=?",(lid,));add_xp(con,u['id'],300);add_xp(con,l['seller_id'],300);add_notification(con,l['seller_id'],'🏢 Предприятие продано',f'Игрок {u["username"] or u["first_name"] or "Игрок"} купил твой бизнес «{l["title"]}» за 💎 {l["price"]:,}.'.replace(',',' '),'market');con.commit();con.close();return jsonify({'ok':True,'price':l['price']})
@app.post('/api/businesses/market/cancel')
@require_user
def cancel_business_listing(u):
    d=request.get_json(silent=True) or {};lid=int(d.get('id',0));con=db();r=con.execute("SELECT id FROM business_market WHERE id=? AND seller_id=? AND status='active'",(lid,u['id'])).fetchone()
    if not r:con.close();return jsonify({'ok':False,'error':'Лот не найден'}),404
    con.execute("UPDATE business_market SET status='cancelled' WHERE id=?",(lid,));con.commit();con.close();return jsonify({'ok':True})

# PROPERTIES/PETS/PLANETS
@app.post('/api/properties/buy')
@require_user
def buy_property(u):
    d=request.get_json(silent=True) or {};k=d.get('key');p=PROPERTIES.get(k)
    if not p:return jsonify({'ok':False,'error':'Недвижимость не найдена'}),400
    con=db()
    if con.execute('SELECT id FROM properties WHERE user_id=? AND property_key=?',(u['id'],k)).fetchone():con.close();return jsonify({'ok':False,'error':'У тебя уже есть эта недвижимость'}),400
    cnt=con.execute('SELECT COUNT(*) c FROM properties WHERE property_key=?',(k,)).fetchone()['c'];lim=PROPERTY_LIMITS.get(k,10**9)
    if cnt>=lim:con.close();return jsonify({'ok':False,'error':f'Лимит достигнут: {lim} шт.'}),400
    price=discounted_price(con,'property_discount',p['price'])
    if u['coins']<price:con.close();return jsonify({'ok':False,'error':'Недостаточно 💎'}),400
    add_coins(con,u['id'],-price,f'Покупка недвижимости: {p["name"]}');con.execute('INSERT INTO properties(user_id,property_key) VALUES(?,?)',(u['id'],k));con.execute('UPDATE users SET rating=rating+? WHERE id=?',(p['rating'],u['id']));con.commit();con.close();return jsonify({'ok':True})
# INVENTORY / MARKET
@app.get('/api/inventory')
@require_user
def inventory(u):
    con=db();rows=con.execute('SELECT item_key,quantity FROM inventory WHERE user_id=? AND quantity>0 ORDER BY item_key',(u['id'],)).fetchall();res=[{'key':r['item_key'],'name':ITEMS[r['item_key']]['name'],'icon':ITEMS[r['item_key']]['icon'],'quantity':r['quantity'],'price':ITEMS[r['item_key']]['base_price']} for r in rows if r['item_key'] in ITEMS];con.close();return jsonify({'ok':True,'inventory':res})
@app.post('/api/market/create')
@require_user
def market_create(u):
    d=request.get_json(silent=True) or {};k=d.get('item_key');q=int(d.get('quantity',0));price=int(d.get('price_each',0))
    if k not in ITEMS:return jsonify({'ok':False,'error':'Предмет не найден'}),400
    if q<=0 or price<=0:return jsonify({'ok':False,'error':'Неверное количество или цена'}),400
    if price>100000000:return jsonify({'ok':False,'error':'Слишком высокая цена'}),400
    con=db()
    if not remove_item(con,u['id'],k,q):con.close();return jsonify({'ok':False,'error':'У тебя нет такого количества предмета'}),400
    con.execute('INSERT INTO market(seller_id,item_key,quantity,price_each,created_at) VALUES(?,?,?,?,?)',(u['id'],k,q,price,now()));qr=con.execute("SELECT progress FROM quests WHERE user_id=? AND quest_key='market1'",(u['id'],)).fetchone()
    if qr and qr['progress']<1:con.execute("UPDATE quests SET progress=1,completed=1 WHERE user_id=? AND quest_key='market1'",(u['id'],))
    con.commit();con.close();return jsonify({'ok':True,'message':'Лот выставлен'})
@app.post('/api/market/buy')
@require_user
def market_buy(u):
    d=request.get_json(silent=True) or {};lid=int(d.get('id',0));con=db();l=con.execute("SELECT * FROM market WHERE id=? AND status='active'",(lid,)).fetchone()
    if not l:con.close();return jsonify({'ok':False,'error':'Лот уже продан или удалён'}),404
    if l['seller_id']==u['id']:con.close();return jsonify({'ok':False,'error':'Нельзя купить собственный лот'}),400
    total=l['quantity']*l['price_each']
    if u['coins']<total:con.close();return jsonify({'ok':False,'error':'Недостаточно 💎'}),400
    seller=con.execute('SELECT id,username,first_name FROM users WHERE id=?',(l['seller_id'],)).fetchone()
    if not seller:con.close();return jsonify({'ok':False,'error':'Продавец не найден'}),400
    item=ITEMS[l['item_key']];buyer_name=u['username'] or u['first_name'] or 'Игрок';add_coins(con,u['id'],-total,'Покупка на рынке');add_coins(con,l['seller_id'],total,'Продажа на рынке');add_item(con,u['id'],l['item_key'],l['quantity']);con.execute("UPDATE market SET status='sold' WHERE id=?",(lid,));add_xp(con,u['id'],50);add_xp(con,l['seller_id'],50)
    add_notification(con,l['seller_id'],'🛒 Лот куплен!',f'Игрок {buyer_name} купил {item["icon"]} {item["name"]} ×{l["quantity"]} за 💎 {total:,}.'.replace(',',' '),'market');con.commit();con.close();return jsonify({'ok':True,'total':total})
@app.post('/api/market/cancel')
@require_user
def market_cancel(u):
    d=request.get_json(silent=True) or {};lid=int(d.get('id',0));con=db();l=con.execute("SELECT * FROM market WHERE id=? AND status='active' AND seller_id=?",(lid,u['id'])).fetchone()
    if not l:con.close();return jsonify({'ok':False,'error':'Лот не найден'}),404
    add_item(con,u['id'],l['item_key'],l['quantity']);con.execute("UPDATE market SET status='cancelled' WHERE id=?",(lid,));con.commit();con.close();return jsonify({'ok':True})

# QUESTS / PROMO / BANK
@app.post('/api/quests/claim')
@require_user
def quest_claim(u):
    d=request.get_json(silent=True) or {};k=d.get('key');q=QUESTS.get(k)
    if not q:return jsonify({'ok':False,'error':'Задание не найдено'}),400
    con=db();r=con.execute('SELECT * FROM quests WHERE user_id=? AND quest_key=?',(u['id'],k)).fetchone()
    if not r or not r['completed']:con.close();return jsonify({'ok':False,'error':'Задание ещё не выполнено'}),400
    if r['claimed']:con.close();return jsonify({'ok':False,'error':'Награда уже получена'}),400
    add_coins(con,u['id'],q['reward'],f'Награда: {q["name"]}');con.execute('UPDATE quests SET claimed=1 WHERE user_id=? AND quest_key=?',(u['id'],k));con.commit();con.close();return jsonify({'ok':True,'reward':q['reward']})
@app.post('/api/promo/redeem')
@require_user
def redeem_promo(u):
    d=request.get_json(silent=True) or {};code=' '.join(str(d.get('code','')).strip().upper().split());con=db();p=con.execute('SELECT * FROM promo_codes WHERE code=? AND active=1',(code,)).fetchone()
    if not p:con.close();return jsonify({'ok':False,'error':'Промокод не найден'}),400
    if con.execute('SELECT 1 FROM promo_redemptions WHERE user_id=? AND code=?',(u['id'],code)).fetchone():con.close();return jsonify({'ok':False,'error':'Ты уже использовал этот промокод'}),400
    add_coins(con,u['id'],p['coins'],f'Промокод {code}');add_xp(con,u['id'],p['xp']);con.execute('INSERT INTO promo_redemptions(user_id,code,redeemed_at) VALUES(?,?,?)',(u['id'],code,now()));con.commit();con.close();return jsonify({'ok':True,'coins':p['coins'],'xp':p['xp'],'code':code})
@app.post('/api/bank')
@require_user
def bank(u):
    d=request.get_json(silent=True) or {};action=d.get('action');amount=int(d.get('amount',0))
    if amount<=0:return jsonify({'ok':False,'error':'Введите сумму'}),400
    con=db();fresh=con.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone()
    if action=='deposit':
        if fresh['coins']<amount:con.close();return jsonify({'ok':False,'error':'Недостаточно 💎'}),400
        con.execute('UPDATE users SET coins=coins-?,bank=bank+? WHERE id=?',(amount,amount,u['id']))
    elif action=='withdraw':
        if fresh['bank']<amount:con.close();return jsonify({'ok':False,'error':'Недостаточно средств в банке'}),400
        con.execute('UPDATE users SET bank=bank-?,coins=coins+? WHERE id=?',(amount,amount,u['id']))
    else:con.close();return jsonify({'ok':False,'error':'Неизвестное действие'}),400
    con.commit();con.close();return jsonify({'ok':True})

# NOTIFICATIONS
@app.get('/api/notifications')
@require_user
def notifications(u):
    con=db();rows=con.execute('SELECT id,title,message,type,is_read,created_at FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],)).fetchall();unread=sum(1 for r in rows if not r['is_read']);con.close();return jsonify({'ok':True,'notifications':[dict(r) for r in rows],'unread':unread})
@app.post('/api/notifications/read')
@require_user
def notifications_read(u):
    d=request.get_json(silent=True) or {};nid=int(d.get('id',0));con=db()
    if nid:con.execute('UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?',(nid,u['id']))
    else:con.execute('UPDATE notifications SET is_read=1 WHERE user_id=?',(u['id'],))
    con.commit();con.close();return jsonify({'ok':True})

# LEADERBOARDS
@app.get('/api/leaderboard')
@require_user
def leaderboard(u):
    con=db();rows=con.execute('SELECT telegram_id,username,first_name,photo_url,level,rating,coins,xp,role FROM users ORDER BY rating DESC,level DESC,xp DESC,id ASC').fetchall();res=[];mine=None
    for i,r in enumerate(rows,1):
        role='creator' if str(r['telegram_id'])==str(CREATOR_TELEGRAM_ID) else (r['role'] or 'player');role=role if role in ROLE_LABELS else 'player';res.append({'place':i,'telegram_id':r['telegram_id'],'username':r['username'],'name':r['first_name'] or r['username'] or 'Игрок','photo_url':r['photo_url'],'level':r['level'],'rating':r['rating'],'coins':r['coins'],'role':role,'role_display':ROLE_LABELS[role],'prefix':ROLE_LABELS[role],'creator':role=='creator','assistant':role=='assistant'});mine=i if str(r['telegram_id'])==str(u['telegram_id']) else mine
    con.close();return jsonify({'ok':True,'players':res[:100],'my_place':mine})
@app.get('/api/richest')
@require_user
def richest(u):
    con=db();rows=con.execute('SELECT telegram_id,username,first_name,photo_url,coins,bank,level,role FROM users ORDER BY (coins+bank) DESC,level DESC LIMIT 50').fetchall();res=[]
    for i,r in enumerate(rows,1):
        role='creator' if str(r['telegram_id'])==str(CREATOR_TELEGRAM_ID) else (r['role'] or 'player');res.append({'place':i,'telegram_id':r['telegram_id'],'username':r['username'],'name':r['first_name'] or r['username'] or 'Игрок','photo_url':r['photo_url'],'coins':r['coins'],'bank':r['bank'],'total':r['coins']+r['bank'],'level':r['level'],'role':role,'role_display':ROLE_LABELS.get(role,'Игрок'),'prefix':ROLE_LABELS.get(role,'Игрок'),'creator':role=='creator','assistant':role=='assistant'})
    con.close();return jsonify({'ok':True,'players':res})

# ADMIN
@app.post('/api/admin/xp')
@require_admin
def admin_xp(actor):
    d=request.get_json(silent=True) or {};tid=str(d.get('telegram_id','')).strip();amount=int(d.get('amount',0));action=str(d.get('action','give')).lower();reason=str(d.get('reason','Административное изменение XP')).strip()[:200]
    if not tid or amount<=0:return jsonify({'ok':False,'error':'Неверные данные'}),400
    con=db();t=con.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
    if not t:con.close();return jsonify({'ok':False,'error':'Игрок не найден'}),404
    if action=='take':
        new=max(0,t['xp']-amount);lvl=level_from_xp(new);con.execute('UPDATE users SET xp=?,level=? WHERE id=?',(new,lvl,t['id']));actual=t['xp']-new;title='⚠️ XP изъяты';msg=f'У тебя изъято {actual} XP. Причина: {reason}'
    else:
        add_xp(con,t['id'],amount);actual=amount;title='📈 XP выданы';msg=f'Тебе выдано +{amount} XP. Причина: {reason}'
    add_notification(con,t['id'],title,msg,'admin');log_admin(con,actor['telegram_id'],f'xp_{action}',tid,f'amount={actual}; reason={reason}');con.commit();fresh=con.execute('SELECT xp,level FROM users WHERE id=?',(t['id'],)).fetchone();con.close();return jsonify({'ok':True,'xp':fresh['xp'],'level':fresh['level'],'amount':actual})
@app.post('/api/admin/level')
@require_admin
def admin_level(actor):
    d=request.get_json(silent=True) or {};tid=str(d.get('telegram_id','')).strip();action=str(d.get('action','set')).lower();reason=str(d.get('reason','Административное изменение уровня')).strip()[:200]
    if not tid:return jsonify({'ok':False,'error':'Неверные данные'}),400
    con=db();t=con.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
    if not t:con.close();return jsonify({'ok':False,'error':'Игрок не найден'}),404
    if action in ('give','take'):
        amount=int(d.get('amount',d.get('level',0))); 
        if amount<=0:con.close();return jsonify({'ok':False,'error':'Укажи количество уровней'}),400
        new=max(1,min(300,t['level']+(amount if action=='give' else -amount)));title='📈 Уровень выдан' if action=='give' else '⚠️ Уровень изъят';verb='выдано' if action=='give' else 'изъято';msg=f'Тебе {verb} {abs(new-t["level"])} ур. Причина: {reason}'
    else:
        new=int(d.get('level',0));
        if new<1 or new>300:con.close();return jsonify({'ok':False,'error':'Уровень должен быть 1-300'}),400
        title='📈 Уровень изменён';msg=f'Твой уровень установлен на {new}. Причина: {reason}'
    con.execute('UPDATE users SET level=?,xp=? WHERE id=?',(new,xp_for_level(new),t['id']));add_notification(con,t['id'],title,msg,'admin');log_admin(con,actor['telegram_id'],f'level_{action}',tid,f'level={new}; reason={reason}');con.commit();con.close();return jsonify({'ok':True,'level':new})
@app.post('/api/admin/money')
@require_admin
def admin_money(actor):
    d=request.get_json(silent=True) or {};tid=str(d.get('telegram_id','')).strip();amount=int(d.get('amount',0));action=str(d.get('action','give')).lower();reason=str(d.get('reason','Администрация NEXORA')).strip()[:200]
    if not tid or amount<=0:return jsonify({'ok':False,'error':'Неверные данные'}),400
    con=db();t=con.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
    if not t:con.close();return jsonify({'ok':False,'error':'Игрок не найден'}),404
    if action=='give':actual=amount;add_coins(con,t['id'],actual,reason);title='💎 Деньги выданы';msg=f'Тебе выдано +💎 {actual:,}. Причина: {reason}'.replace(',',' ')
    elif action=='take':actual=min(amount,t['coins']);add_coins(con,t['id'],-actual,reason);title='⚠️ Деньги изъяты';msg=f'У тебя изъято 💎 {actual:,}. Причина: {reason}'.replace(',',' ')
    else:con.close();return jsonify({'ok':False,'error':'Неизвестное действие'}),400
    add_notification(con,t['id'],title,msg,'admin');log_admin(con,actor['telegram_id'],f'money_{action}',tid,f'amount={actual}; reason={reason}');con.commit();new=t=con.execute('SELECT coins FROM users WHERE id=?',(t['id'],)).fetchone();con.close();return jsonify({'ok':True,'coins':new['coins'],'amount':actual})
@app.post('/api/admin/item')
@require_admin
def admin_item(actor):
    d=request.get_json(silent=True) or {};tid=str(d.get('telegram_id','')).strip();k=str(d.get('item_key','')).strip();q=int(d.get('quantity',0))
    if not tid or k not in ITEMS or q<=0 or q>100000:return jsonify({'ok':False,'error':'Неверные данные'}),400
    con=db();t=con.execute('SELECT * FROM users WHERE telegram_id=?',(tid,)).fetchone()
    if not t:con.close();return jsonify({'ok':False,'error':'Игрок не найден'}),404
    add_item(con,t['id'],k,q);reason=str(d.get('reason','Административная награда')).strip()[:200];add_notification(con,t['id'],'🎁 Предмет выдан',f'Тебе выдано {ITEMS[k]["icon"]} {ITEMS[k]["name"]} ×{q}. Причина: {reason}','admin');log_admin(con,actor['telegram_id'],'give_item',tid,f'{k} x{q}; reason={reason}');con.commit();con.close();return jsonify({'ok':True,'item_key':k,'quantity':q})
@app.get('/api/admin/items')
@require_admin
def admin_items(actor):return jsonify({'ok':True,'items':[{'key':k,**v} for k,v in ITEMS.items()]})
@app.get('/api/admin/logs')
@require_admin
def admin_logs(actor):
    con=db();r=[dict(x) for x in con.execute('SELECT * FROM admin_logs ORDER BY id DESC LIMIT 100').fetchall()];con.close();return jsonify({'ok':True,'logs':r})
@app.get('/api/admin/players')
@require_admin
def admin_players(actor):
    con=db();q=str(request.args.get('q','')).strip();like=f'%{q}%'
    rows=con.execute('SELECT id,telegram_id,username,first_name,last_name,coins,bank,level,xp,rating,role FROM users WHERE telegram_id LIKE ? OR username LIKE ? OR first_name LIKE ? ORDER BY id DESC LIMIT 200',(like,like,like)).fetchall() if q else con.execute('SELECT id,telegram_id,username,first_name,last_name,coins,bank,level,xp,rating,role FROM users ORDER BY id DESC LIMIT 200').fetchall();players=[]
    for r in rows:
        x=dict(r);x['role']='creator' if str(x['telegram_id'])==str(CREATOR_TELEGRAM_ID) else (x['role'] or 'player');x['role_display']=ROLE_LABELS.get(x['role'],'Игрок');x['prefix']=x['role_display'];players.append(x)
    con.close();return jsonify({'ok':True,'players':players})
@app.post('/api/admin/role')
@require_creator
def admin_role(actor):
    d=request.get_json(silent=True) or {};tid=str(d.get('telegram_id','')).strip();role=str(d.get('role','player')).strip().lower()
    if role not in ('assistant','player') or not tid:return jsonify({'ok':False,'error':'Неверные данные'}),400
    if tid==str(CREATOR_TELEGRAM_ID):return jsonify({'ok':False,'error':'Нельзя изменить роль создателя'}),400
    con=db();t=con.execute('SELECT id FROM users WHERE telegram_id=?',(tid,)).fetchone()
    if not t:con.close();return jsonify({'ok':False,'error':'Игрок не найден'}),404
    con.execute('UPDATE users SET role=? WHERE id=?',(role,t['id']))
    if role=='assistant':con.execute("INSERT OR IGNORE INTO prefixes(user_id,prefix_key) VALUES(?, 'assistant')",(t['id'],))
    else:con.execute("DELETE FROM prefixes WHERE user_id=? AND prefix_key='assistant'",(t['id'],))
    add_notification(con,t['id'],'🛡️ Роль изменена',f'Тебе назначена роль: {ROLE_LABELS[role]}.','admin');log_admin(con,actor['telegram_id'],'set_role',tid,f'role={role}');con.commit();con.close();return jsonify({'ok':True,'telegram_id':tid,'role':role,'role_display':ROLE_LABELS[role]})
@app.post('/api/admin/event')
@require_admin
def admin_event(actor):
    d=request.get_json(silent=True) or {};et=d.get('event_type','all');mult=float(d.get('multiplier',2));mins=int(d.get('duration_minutes',60));title=str(d.get('title','Событие NEXORA')).strip()[:80];desc=str(d.get('description','Временный бонус для экономики NEXORA')).strip()[:200]
    allowed=['jobs','businesses','all','business_discount','property_discount']
    if et not in allowed:return jsonify({'ok':False,'error':'Неизвестный тип события'}),400
    if et.endswith('_discount') and not(0<mult<=90):return jsonify({'ok':False,'error':'Скидка 1-90%'}),400
    if not et.endswith('_discount') and not(1<=mult<=10):return jsonify({'ok':False,'error':'Множитель x1-x10'}),400
    if not(1<=mins<=10080):return jsonify({'ok':False,'error':'Неверная длительность'}),400
    con=db();cleanup_events(con);con.execute('UPDATE events SET active=0 WHERE active=1 AND event_type=?',(et,));end=now()+mins*60;con.execute('INSERT INTO events(creator_id,event_type,multiplier,ends_at,title,description,active,created_at) VALUES(?,?,?,?,?,?,1,?)',(actor['telegram_id'],et,mult,end,title,desc,now()));log_admin(con,actor['telegram_id'],'event_create','',f'type={et}; value={mult}; duration={mins}m');con.commit();con.close();return jsonify({'ok':True,'ends_at':end,'multiplier':mult})
@app.get('/api/admin/events')
@require_admin
def admin_events(actor):
    con=db();cleanup_events(con);con.commit();r=[dict(x) for x in con.execute('SELECT * FROM events ORDER BY id DESC LIMIT 50').fetchall()];con.close();return jsonify({'ok':True,'events':r})
@app.post('/api/admin/event/stop')
@require_admin
def admin_event_stop(actor):
    d=request.get_json(silent=True) or {};eid=int(d.get('id',0));con=db();con.execute('UPDATE events SET active=0 WHERE id=?',(eid,));log_admin(con,actor['telegram_id'],'event_stop','',f'id={eid}');con.commit();con.close();return jsonify({'ok':True})
@app.post('/api/admin/wipe')
@require_creator
def admin_wipe(actor):
    d=request.get_json(silent=True) or {}
    if str(d.get('confirm','')).upper()!='WIPE':return jsonify({'ok':False,'error':'Для вайпа отправь confirm=WIPE'}),400
    con=db();users=con.execute('SELECT id,telegram_id FROM users').fetchall()
    for r in users:
        uid=r['id'];con.execute('UPDATE users SET coins=1000,xp=0,level=1,rating=0,bank=0,last_daily=0,world=1 WHERE id=?',(uid,))
        for table in ('inventory','cooldowns','businesses','properties','achievements','notifications'):con.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
        con.execute('UPDATE skills SET mining=1,farming=1,fishing=1,business=1,work=1 WHERE user_id=?',(uid,));con.execute('DELETE FROM quests WHERE user_id=?',(uid,))
        for k in QUESTS:con.execute('INSERT OR IGNORE INTO quests(user_id,quest_key) VALUES(?,?)',(uid,k))
        con.execute('DELETE FROM prefixes WHERE user_id=?',(uid,))
        if str(r['telegram_id'])==str(CREATOR_TELEGRAM_ID):con.execute("INSERT OR IGNORE INTO prefixes(user_id,prefix_key) VALUES(?, 'creator')",(uid,))
        elif con.execute('SELECT role FROM users WHERE id=?',(uid,)).fetchone()['role']=='assistant':con.execute("INSERT OR IGNORE INTO prefixes(user_id,prefix_key) VALUES(?, 'assistant')",(uid,))
    for r in con.execute("SELECT seller_id,item_key,quantity FROM market WHERE status='active'").fetchall():add_item(con,r['seller_id'],r['item_key'],r['quantity'])
    con.execute("UPDATE market SET status='wiped' WHERE status='active'");con.execute("UPDATE business_market SET status='wiped' WHERE status='active'");con.execute("UPDATE events SET active=0 WHERE active=1");con.execute('INSERT INTO wipe_history(creator_id,created_at,affected_users) VALUES(?,?,?)',(actor['telegram_id'],now(),len(users)));log_admin(con,actor['telegram_id'],'WIPE','',f'{len(users)} players reset; each received 1000 coins');con.commit();con.close();return jsonify({'ok':True,'affected_users':len(users),'start_balance':1000})

@app.get('/api/history')
@require_user
def history(u):
    con=db();r=[dict(x) for x in con.execute('SELECT amount,reason,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 50',(u['id'],)).fetchall()];con.close();return jsonify({'ok':True,'history':r})

@app.errorhandler(404)
def not_found(e):return jsonify({'ok':False,'error':'Маршрут не найден'}),404
@app.errorhandler(500)
def server_error(e):return jsonify({'ok':False,'error':'Внутренняя ошибка сервера'}),500

if __name__=='__main__':app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=False)
