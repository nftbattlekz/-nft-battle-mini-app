import os, json, time, hmac, hashlib, sqlite3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, parse_qsl

BASE=os.path.dirname(os.path.abspath(__file__)); WEB=os.path.join(BASE,'web'); INDEX=os.path.join(WEB,'index.html')
PORT=int(os.getenv('PORT','10000')); BOT_TOKEN=os.getenv('BOT_TOKEN','').strip(); DEMO=os.getenv('DEMO_MODE','1')=='1'
CHANNEL=os.getenv('DEV_CHANNEL_URL','https://t.me/').strip(); DB=os.getenv('DB_PATH',os.path.join(BASE,'delo17.db'))
VER='DELO17 COMPACT 2.0'
CH={1:'Последнее сообщение',2:'Квартира',3:'22:17',4:'Ложь',5:'ZERO',6:'Архив',7:'Предательство',8:'Точка невозврата',9:'Последняя ночь',10:'Правда'}
C={
'alina':('Алина','А','была недавно'),'kirill':('Кирилл','К','в сети'),'masha':('Маша','М','была недавно'),
'igor':('Игорь','И','в сети'),'zero':('ZERO','0','онлайн'),'orlov':('Орлов','О','был недавно'),'victor':('Виктор','В','в сети')}
E={
'photo':('Фото','Фото у кафе','Алина прислала снимок кафе «Луна». На заднем плане видна тёмная машина.'),
'plate':('Деталь','Номер машины','После увеличения читается номер KZ 777 FBA 01.'),
'key':('Предмет','Ключ Алины','Запасной ключ найден возле квартиры.'),
'receipt':('Документ','Чек 21:54','Чек из кафе «Луна» показывает время 21:54.'),
'camera':('Видео','Камера 22:17','Камера фиксирует тёмную машину у дома в 22:17.'),
'voice':('Аудио','Голосовое 00:43','На фоне слышно объявление и металлический звон двери.'),
'archive':('Архив','Файл Алины','В архиве отмечено имя Виктора.'),
'contract':('Документ','Черновик договора','Документ связывает Виктора с материалами Алины.'),
'zero_id':('Секрет','Кто такой ZERO','ZERO был источником Алины и скрывался из страха.'),
'final':('Доказательство','Последнее доказательство','Сообщения подтверждают интерес Виктора к материалам Алины.')}

def con():
    x=sqlite3.connect(DB,timeout=30,check_same_thread=False); x.row_factory=sqlite3.Row; x.execute('PRAGMA busy_timeout=30000'); return x

def init_db():
    x=con(); x.execute('CREATE TABLE IF NOT EXISTS players(user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT, state_json TEXT, updated_at INTEGER)'); x.commit(); x.close()

def fresh():
    return {'chapter':1,'chapter_title':CH[1],'step':'intro','unlocked':['alina'],'unread':{'alina':1},
    'messages':{'alina':[{'from':'them','text':'Привет...'},{'from':'them','text':'Если ты читаешь это — со мной что-то произошло.'},{'from':'them','text':'Посмотри фотографию. Там есть важная деталь.'},{'from':'them','text':'И пока никому не доверяй слишком быстро.'}]},
    'evidence':[],'tasks':[{'id':'inspect','title':'Изучить фотографию','done':False},{'id':'detail','title':'Найти важную деталь','done':False}],
    'trust':{'kirill':0,'masha':0,'igor':0,'zero':0,'orlov':0,'victor':0},'flags':{},'notes':[],'conclusions':[],
    'stats':{'correct':0,'secrets':0,'mistakes':0},'ending':None,'ending_title':None,'ending_text':None}

def norm(s):
    b=fresh()
    if not isinstance(s,dict): return b
    for k,v in b.items(): s.setdefault(k,v)
    for k in ('messages','unread','trust','flags','stats'):
        if not isinstance(s.get(k),dict): s[k]=dict(b[k])
    for k in ('unlocked','evidence','tasks','notes','conclusions'):
        if not isinstance(s.get(k),list): s[k]=list(b[k])
    for k,v in b['trust'].items(): s['trust'].setdefault(k,v)
    for k,v in b['stats'].items(): s['stats'].setdefault(k,v)
    s['chapter']=max(1,min(10,int(s.get('chapter',1) or 1))); s['chapter_title']=CH[s['chapter']]
    s['unlocked']=[i for i in s['unlocked'] if i in C] or ['alina']; return s

def verify(raw):
    if not raw or not BOT_TOKEN: return None
    try:
        d=dict(parse_qsl(raw,keep_blank_values=True)); got=d.pop('hash',''); check='\n'.join(f'{k}={v}' for k,v in sorted(d.items()))
        secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest(); calc=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc,got): return None
        u=json.loads(d.get('user','{}')); return {'id':int(u['id']),'first_name':str(u.get('first_name') or 'Игрок'),'username':str(u.get('username') or '')}
    except: return None

def user(headers,q):
    u=verify(headers.get('X-Telegram-Init-Data',''))
    if u: return u
    if DEMO: return {'id':int(q.get('demo_id',['170017'])[0]),'first_name':'Детектив','username':'demo'}
    return None

def load(u):
    x=con(); r=x.execute('SELECT state_json FROM players WHERE user_id=?',(u['id'],)).fetchone()
    if r:
        try:s=norm(json.loads(r['state_json']))
        except:s=fresh()
    else:s=fresh(); save(u,s); x.close(); return s
    x.close(); return s

def save(u,s):
    x=con(); raw=json.dumps(norm(s),ensure_ascii=False); now=int(time.time())
    x.execute('INSERT INTO players VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET first_name=excluded.first_name,username=excluded.username,state_json=excluded.state_json,updated_at=excluded.updated_at',(u['id'],u['first_name'],u['username'],raw,now)); x.commit(); x.close()

def msg(s,c,t,me=False,unread=False):
    s['messages'].setdefault(c,[]).append({'from':'me' if me else 'them','text':t})
    if unread:s['unread'][c]=s['unread'].get(c,0)+1

def unlock(s,c,t):
    if c not in s['unlocked']: s['unlocked'].append(c)
    msg(s,c,t,unread=True); return {'contact':c,'name':C[c][0],'preview':t}

def ev(s,e):
    if e in E and e not in s['evidence']: s['evidence'].append(e)

def tasks(s,*rows): s['tasks']=[{'id':a,'title':b,'done':False} for a,b in rows]
def done(s,i):
    for t in s['tasks']:
        if t['id']==i:t['done']=True

def chap(s,n,step,*rows): s.update(chapter=n,chapter_title=CH[n],step=step); tasks(s,*rows)
def A(i,t,c=None,style='normal'): return {'id':i,'title':t,'contact':c,'style':style}

def actions(s):
    m={
    'intro':[A('inspect_photo','Изучить фотографию','alina','primary')],
    'photo':[A('zoom_plate','Увеличить номер машины',None,'primary'),A('inspect_window','Рассмотреть отражение в окне')],
    'alina_last':[A('open_envelope','Открыть последнее вложение','alina','primary')],
    'kirill':[A('kirill_trust','Я тебе верю','kirill'),A('kirill_pressure','Ты что-то скрываешь','kirill','danger'),A('kirill_photo','Показать фотографию','kirill','primary')],
    'apartment':[A('search_apartment','Осмотреть квартиру',None,'primary'),A('call_orlov','Сообщить следователю')],
    'apartment_clues':[A('read_receipt','Проверить чек',None,'primary'),A('inspect_key','Осмотреть ключ')],
    'masha':[A('masha_soft','Спокойно расспросить','masha'),A('masha_pressure','Надавить','masha','danger'),A('masha_time','Спросить про 22:17','masha','primary')],
    'camera':[A('review_camera','Проверить запись камеры',None,'primary'),A('compare_time','Сверить чек и время')],
    'voice':[A('analyze_voice','Прослушать голосовое внимательно',None,'primary'),A('skip_voice','Отложить аудио')],
    'igor':[A('igor_work','Спросить про работу','igor'),A('igor_time','Спросить про 22:17','igor','primary'),A('igor_proof','Показать доказательство','igor','danger')],
    'igor_follow':[A('check_igor','Проверить его слова',None,'primary'),A('ask_victor','Спросить про Виктора','igor')],
    'zero':[A('zero_trust','Я доверяю тебе','zero','primary'),A('zero_distrust','Я тебе не верю','zero','danger'),A('zero_lie','Сказать, что расследование закончено','zero')],
    'code':[A('code_7317','7317',None,'primary'),A('code_2217','2217'),A('code_1809','1809'),A('code_7771','7771')],
    'archive':[A('archive_files','Изучить файлы',None,'primary'),A('archive_notes','Сверить заметки Алины')],
    'victor':[A('victor_direct','Показать записку Алины','victor','primary'),A('victor_bluff','Сделать вид, что всё известно','victor','danger'),A('victor_soft','Спросить спокойно','victor')],
    'victor_check':[A('check_contract','Сверить договор и записку',None,'primary'),A('check_old_messages','Проверить старые сообщения')],
    'betrayal':[A('ally_orlov','Передать материалы Орлову'),A('ally_kirill','Довериться Кириллу',None,'primary'),A('ally_hide','Скрыть материалы',None,'danger'),A('ally_solo','Действовать самостоятельно')],
    'archive_copy':[A('save_copy','Сохранить резервную копию',None,'primary'),A('no_copy','Не оставлять копию',None,'danger')],
    'critical':[A('critical_police','Передать телефон полиции'),A('critical_keep','Оставить телефон у себя',None,'danger'),A('critical_kirill','Попросить помощи Кирилла',None,'primary'),A('critical_zero','Попросить помощи ZERO')],
    'backup':[A('backup_orlov','Отправить копию Орлову'),A('backup_zero','Отправить копию ZERO'),A('backup_self','Оставить копию только у себя',None,'danger')],
    'timeline':[A('timeline_correct','21:54 → 22:17 → сообщение ZERO',None,'primary'),A('timeline_wrong','Другая последовательность')],
    'motive':[A('motive_materials','Получить материалы Алины',None,'primary'),A('motive_other','Личная месть')],
    'final':[A('accuse_victor','Виктор',None,'primary'),A('accuse_kirill','Кирилл'),A('accuse_zero','ZERO'),A('accuse_orlov','Орлов')]}
    return m.get(s['step'],[])

def process(s,a):
    p=s['step']; inc=rev=flash=None
    if p=='intro' and a=='inspect_photo': done(s,'inspect'); ev(s,'photo'); s['step']='photo'; rev='Найдена улика: фото у кафе «Луна»'
    elif p=='photo' and a=='inspect_window':
        if not s['flags'].get('window'): s['flags']['window']=1;s['stats']['secrets']+=1;s['notes'].append('В отражении окна видна часть машины.');rev='Скрытая деталь добавлена'
        else: rev='Ты уже изучил эту деталь'
    elif p=='photo' and a=='zoom_plate': done(s,'detail');ev(s,'plate');s['stats']['correct']+=1;s['step']='alina_last';msg(s,'alina','Открой последнее вложение. Там адрес человека, который может что-то знать.',unread=True);inc={'contact':'alina','name':'Алина','preview':'Открой последнее вложение.'}
    elif p=='alina_last' and a=='open_envelope': chap(s,2,'kirill',('talk','Поговорить с Кириллом'),('apt','Проверить квартиру Алины'));inc=unlock(s,'kirill','Зачем ты мне пишешь?');flash='Глава 2 — Квартира'
    elif p=='kirill' and a.startswith('kirill_'):
        done(s,'talk');s['trust']['kirill']+=2 if a=='kirill_trust' else (-2 if a=='kirill_pressure' else 1);s['stats']['mistakes']+=1 if a=='kirill_pressure' else 0;msg(s,'kirill','У Алины был запасной ключ. Проверь конверт возле квартиры.',unread=True);s['step']='apartment';inc={'contact':'kirill','name':'Кирилл','preview':'Проверь конверт возле квартиры.'}
    elif p=='apartment' and a in ('search_apartment','call_orlov'):
        if a=='call_orlov':s['trust']['orlov']+=1;inc=unlock(s,'orlov','Если найдёте что-то важное — сообщите.')
        ev(s,'key');ev(s,'receipt');done(s,'apt');s['step']='apartment_clues';rev='Найдены ключ и чек из кафе'
    elif p=='apartment_clues' and a in ('read_receipt','inspect_key'):
        s['stats']['correct']+=1 if a=='read_receipt' else 0;s['stats']['secrets']+=1 if a=='inspect_key' else 0;chap(s,3,'masha',('talk','Поговорить с соседкой'),('time','Проверить время 22:17'));inc=unlock(s,'masha','В тот вечер я слышала шум в коридоре.');flash='Глава 3 — 22:17'
    elif p=='masha' and a.startswith('masha_'): done(s,'talk');s['trust']['masha']+=2 if a=='masha_soft' else (-2 if a=='masha_pressure' else 1);msg(s,'masha','В 22:17 у дома остановилась тёмная машина.',unread=True);s['step']='camera';inc={'contact':'masha','name':'Маша','preview':'В 22:17 у дома была тёмная машина.'}
    elif p=='camera' and a in ('review_camera','compare_time'): done(s,'time');ev(s,'camera');s['stats']['correct']+=1;s['conclusions'].append('Кто-то был у дома Алины после 22:00.');s['step']='voice';rev='Открыта запись камеры 22:17'
    elif p=='voice' and a in ('analyze_voice','skip_voice'):
        if a=='analyze_voice':ev(s,'voice');s['stats']['secrets']+=1
        chap(s,4,'igor',('talk','Проверить показания Игоря'),('lie','Найти противоречие'));inc=unlock(s,'igor','У меня с Алиной был конфликт, но я не причастен.');flash='Глава 4 — Ложь'
    elif p=='igor' and a.startswith('igor_'): done(s,'talk');done(s,'lie');s['stats']['correct']+=1 if a=='igor_time' else 0;msg(s,'igor','Алина несколько раз говорила про человека по имени Виктор.',unread=True);s['step']='igor_follow';inc={'contact':'igor','name':'Игорь','preview':'Она говорила про Виктора.'}
    elif p=='igor_follow' and a in ('check_igor','ask_victor'): s['stats']['correct']+=1;chap(s,5,'zero',('zero','Выяснить, кто такой ZERO'),('code','Получить код архива'));inc=unlock(s,'zero','Ты задаёшь слишком много вопросов. Я могу помочь.');flash='Глава 5 — ZERO'
    elif p=='zero' and a.startswith('zero_'): done(s,'zero');s['trust']['zero']+=3 if a=='zero_trust' else -1;msg(s,'zero','Архив открывается четырьмя цифрами. Все подсказки уже у тебя.',unread=True);s['step']='code';inc={'contact':'zero','name':'ZERO','preview':'Все подсказки уже у тебя.'}
    elif p=='code' and a.startswith('code_'):
        if a=='code_7317': done(s,'code');s['stats']['correct']+=1;ev(s,'archive');chap(s,6,'archive',('archive','Изучить архив Алины'),('victor','Найти человека из архива'));rev='Архив разблокирован';flash='Глава 6 — Архив'
        else:s['stats']['mistakes']+=1;rev='Неверный код'
    elif p=='archive' and a in ('archive_files','archive_notes'): done(s,'archive');s['stats']['secrets']+=1 if a=='archive_notes' else 0;inc=unlock(s,'victor','Ты нашёл мой контакт у Алины, да?');s['step']='victor'
    elif p=='victor' and a.startswith('victor_'): done(s,'victor');ev(s,'contract');s['stats']['secrets']+=1 if a=='victor_bluff' else 0;msg(s,'victor','Ты видишь только часть истории.',unread=True);s['step']='victor_check';inc={'contact':'victor','name':'Виктор','preview':'Ты видишь только часть истории.'}
    elif p=='victor_check' and a in ('check_contract','check_old_messages'): s['stats']['correct']+=1;s['conclusions'].append('Виктор скрывает связь с материалами Алины.');chap(s,7,'betrayal',('ally','Решить, кому доверить материалы'),('copy','Сохранить копию архива'));flash='Глава 7 — Предательство'
    elif p=='betrayal' and a.startswith('ally_'): done(s,'ally');s['flags']['ally']=a;s['stats']['mistakes']+=1 if a=='ally_hide' else 0;s['step']='archive_copy'
    elif p=='archive_copy' and a in ('save_copy','no_copy'): done(s,'copy');s['flags']['archive_copy']=a=='save_copy';s['stats']['correct']+=1 if a=='save_copy' else 0;chap(s,8,'critical',('critical','Сделать необратимый выбор'),('backup','Решить, где оставить копию'));flash='Глава 8 — Точка невозврата'
    elif p=='critical' and a.startswith('critical_'): done(s,'critical');s['flags']['critical']=a;s['trust']['zero']+=2 if a=='critical_zero' else 0;s['trust']['kirill']+=2 if a=='critical_kirill' else 0;s['trust']['orlov']+=2 if a=='critical_police' else 0;ev(s,'zero_id') if a=='critical_zero' else None;s['stats']['secrets']+=1 if a in ('critical_zero','critical_keep') else 0;s['step']='backup'
    elif p=='backup' and a.startswith('backup_'): done(s,'backup');s['flags']['backup']=a;chap(s,9,'timeline',('timeline','Восстановить хронологию'),('motive','Определить мотив'));flash='Глава 9 — Последняя ночь'
    elif p=='timeline' and a.startswith('timeline_'): done(s,'timeline');s['stats']['correct']+=2 if a=='timeline_correct' else 0;s['stats']['mistakes']+=0 if a=='timeline_correct' else 2;s['step']='motive'
    elif p=='motive' and a.startswith('motive_'): done(s,'motive');s['stats']['correct']+=2 if a=='motive_materials' else 0;s['stats']['mistakes']+=0 if a=='motive_materials' else 1;ev(s,'final');chap(s,10,'final',('final','Сделать окончательный вывод'));flash='Глава 10 — Правда'
    elif p=='final' and a.startswith('accuse_'):
        done(s,'final');who=a[7:];score=s['stats']['correct']+s['stats']['secrets']-s['stats']['mistakes']
        if who=='victor' and score>=9 and s['flags'].get('archive_copy') and 'zero_id' in s['evidence']: s.update(ending='full',ending_title='ПОЛНАЯ ПРАВДА',ending_text='Ты восстановил всю цепочку. Виктор пытался получить материалы Алины, а ZERO оказался её источником. Алина в безопасности.')
        elif who=='victor': s.update(ending='truth',ending_title='ПРАВДА НАЙДЕНА',ending_text='Ты вышел на Виктора, но часть истории осталась скрытой.')
        elif who=='zero': s.update(ending='false',ending_title='ЛОЖНЫЙ СЛЕД',ending_text='ZERO пытался помочь Алине, а не навредить ей.')
        else:s.update(ending='wrong',ending_title='ДЕЛО ЗАКРЫТО С ОШИБКОЙ',ending_text='Ты связал улики не с тем человеком. Новое прохождение может открыть другой путь.')
        s['step']='finished'
    else:return False,'Этот выбор сейчас недоступен',None,None,None
    return True,None,inc,rev,flash

def public(u,s):
    contacts=[]
    for i in s['unlocked']:
        n,av,st=C[i]; ms=s['messages'].get(i,[]); contacts.append({'id':i,'name':n,'avatar':av,'status':st,'badge':s['unread'].get(i,0),'preview':ms[-1]['text'] if ms else ''})
    evidence=[{'id':i,'type':E[i][0],'title':E[i][1],'desc':E[i][2]} for i in s['evidence'] if i in E]
    return {'user':u,'chapter':s['chapter'],'chapter_title':s['chapter_title'],'step':s['step'],'contacts':contacts,'messages':{i:s['messages'].get(i,[]) for i in s['unlocked']},'evidence':evidence,'tasks':s['tasks'],'trust':s['trust'],'notes':s['notes'],'conclusions':s['conclusions'],'stats':s['stats'],'actions':actions(s),'ending':s['ending'],'ending_title':s['ending_title'],'ending_text':s['ending_text'],'chapters':[{'num':i,'title':CH[i],'unlocked':i<=s['chapter']} for i in range(1,11)],'dev_channel_url':CHANNEL,'version':VER}

class H(BaseHTTPRequestHandler):
    def log_message(self,f,*a): print('[HTTP]',f%a,flush=True)
    def out(self,o,code=200,ctype='application/json; charset=utf-8'):
        b=(json.dumps(o,ensure_ascii=False) if isinstance(o,(dict,list)) else o).encode(); self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
    def body(self):
        try:return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0') or 0)).decode() or '{}')
        except:return {}
    def usr(self,p):return user(self.headers,parse_qs(p.query))
    def index(self):
        if not os.path.isfile(INDEX):return self.out({'ok':False,'error':'web/index.html not found'},500)
        self.out(open(INDEX,'r',encoding='utf-8').read(),200,'text/html; charset=utf-8')
    def do_GET(self):
        p=urlparse(self.path)
        try:
            if p.path=='/health':return self.out({'ok':True,'app':'DELO17','version':VER})
            if p.path=='/api/state':
                u=self.usr(p)
                if not u:return self.out({'ok':False,'error':'Открой игру через Telegram или включи DEMO_MODE=1'},401)
                return self.out({'ok':True,'data':public(u,load(u))})
            if p.path.startswith('/api/'):return self.out({'ok':False,'error':'API route not found'},404)
            return self.index()
        except Exception as e: print('GET',repr(e),flush=True);return self.out({'ok':False,'error':str(e)},500)
    def do_POST(self):
        p=urlparse(self.path);u=self.usr(p)
        if not u:return self.out({'ok':False,'error':'Открой игру через Telegram или включи DEMO_MODE=1'},401)
        try:
            if p.path=='/api/action':
                s=load(u);aid=str(self.body().get('action') or '')
                if aid not in {x['id'] for x in actions(s)}:return self.out({'ok':False,'error':'Этот выбор сейчас недоступен'},400)
                ok,er,inc,rev,fl=process(s,aid)
                if not ok:return self.out({'ok':False,'error':er},400)
                save(u,s);return self.out({'ok':True,'data':public(u,s),'incoming':inc,'reveal':rev,'chapter_flash':fl})
            if p.path.startswith('/api/read/'):
                s=load(u);cid=p.path.rsplit('/',1)[-1]
                if cid not in s['unlocked']:return self.out({'ok':False,'error':'Чат ещё не открыт'},404)
                s['unread'][cid]=0;save(u,s);return self.out({'ok':True})
            if p.path=='/api/reset':s=fresh();save(u,s);return self.out({'ok':True,'data':public(u,s)})
            return self.out({'ok':False,'error':'API route not found'},404)
        except Exception as e: print('POST',repr(e),flush=True);return self.out({'ok':False,'error':str(e)},500)

def main():
    os.makedirs(WEB,exist_ok=True);init_db();srv=ThreadingHTTPServer(('0.0.0.0',PORT),H);print(f'{VER} running on 0.0.0.0:{PORT}',flush=True);srv.serve_forever()
if __name__=='__main__':main()
