import os
import json
import time
import hmac
import hashlib
import sqlite3
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, parse_qsl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
INDEX_FILE = os.path.join(WEB_DIR, "index.html")
PORT = int(os.getenv("PORT", "10000"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"
DEV_CHANNEL_URL = os.getenv("DEV_CHANNEL_URL", "https://t.me/").strip()
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "delo17.db"))
APP_VERSION = "DELO17 TWO-FILE 1.0"

CHAPTERS = {
    1: "Последнее сообщение",
    2: "Квартира",
    3: "22:17",
    4: "Ложь",
    5: "ZERO",
    6: "Архив",
    7: "Предательство",
    8: "Точка невозврата",
    9: "Последняя ночь",
    10: "Правда",
}

CONTACTS = {
    "alina": {"name": "Алина", "avatar": "А", "status": "была недавно"},
    "kirill": {"name": "Кирилл", "avatar": "К", "status": "в сети"},
    "masha": {"name": "Маша", "avatar": "М", "status": "была недавно"},
    "igor": {"name": "Игорь", "avatar": "И", "status": "в сети"},
    "zero": {"name": "ZERO", "avatar": "0", "status": "онлайн"},
    "orlov": {"name": "Орлов", "avatar": "О", "status": "был недавно"},
    "victor": {"name": "Виктор", "avatar": "В", "status": "в сети"},
}

EVIDENCE = {
    "photo": {"type": "Фото", "title": "Фото у кафе", "desc": "Алина прислала снимок кафе «Луна». На заднем плане видна тёмная машина."},
    "plate": {"type": "Деталь", "title": "Номер машины", "desc": "После увеличения читается номер KZ 777 FBA 01."},
    "key": {"type": "Предмет", "title": "Ключ Алины", "desc": "Запасной ключ лежал в подписанном конверте возле квартиры."},
    "receipt": {"type": "Документ", "title": "Чек 21:54", "desc": "Чек из кафе «Луна» показывает время покупки 21:54."},
    "camera": {"type": "Видео", "title": "Камера 22:17", "desc": "Камера фиксирует похожую машину возле дома в 22:17."},
    "voice": {"type": "Аудио", "title": "Голосовое 00:43", "desc": "На фоне слышно объявление и металлический звон двери."},
    "archive": {"type": "Архив", "title": "Файл Алины", "desc": "Алина отмечала имя Виктора рядом со словом «источник»."},
    "contract": {"type": "Документ", "title": "Черновик договора", "desc": "Документ связывает Виктора с материалами Алины."},
    "zero_id": {"type": "Секрет", "title": "Кто такой ZERO", "desc": "ZERO был источником Алины и скрывался из страха."},
    "final": {"type": "Доказательство", "title": "Последнее доказательство", "desc": "Сообщения показывают, что Виктор пытался получить материалы Алины."},
}


def db():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    return con


def init_db():
    con = db()
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS players(
            user_id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            state_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    con.commit()
    con.close()


def new_state():
    return {
        "chapter": 1,
        "chapter_title": CHAPTERS[1],
        "step": "intro",
        "unlocked": ["alina"],
        "unread": {"alina": 1},
        "messages": {
            "alina": [
                {"from": "them", "text": "Привет..."},
                {"from": "them", "text": "Если ты читаешь это сообщение — значит, со мной что-то произошло."},
                {"from": "them", "text": "Посмотри фотографию, которую я отправила. Там есть важная деталь."},
                {"from": "them", "text": "И пока никому не доверяй слишком быстро."},
            ]
        },
        "evidence": [],
        "tasks": [
            {"id": "inspect_photo", "title": "Изучить фотографию", "done": False},
            {"id": "find_detail", "title": "Найти важную деталь", "done": False},
        ],
        "trust": {"kirill": 0, "masha": 0, "igor": 0, "zero": 0, "orlov": 0, "victor": 0},
        "flags": {},
        "notes": [],
        "conclusions": [],
        "stats": {"correct": 0, "secrets": 0, "mistakes": 0},
        "ending": None,
        "ending_title": None,
        "ending_text": None,
    }


def normalize_state(state):
    base = new_state()
    if not isinstance(state, dict):
        return base
    for k, v in base.items():
        if k not in state:
            state[k] = v
    if not isinstance(state.get("messages"), dict): state["messages"] = base["messages"]
    if not isinstance(state.get("unlocked"), list): state["unlocked"] = ["alina"]
    if not isinstance(state.get("unread"), dict): state["unread"] = {}
    if not isinstance(state.get("evidence"), list): state["evidence"] = []
    if not isinstance(state.get("tasks"), list): state["tasks"] = []
    if not isinstance(state.get("notes"), list): state["notes"] = []
    if not isinstance(state.get("conclusions"), list): state["conclusions"] = []
    for k in ("trust", "stats", "flags"):
        if not isinstance(state.get(k), dict): state[k] = dict(base[k])
    for k, v in base["trust"].items(): state["trust"].setdefault(k, v)
    for k, v in base["stats"].items(): state["stats"].setdefault(k, v)
    state["chapter"] = max(1, min(10, int(state.get("chapter", 1) or 1)))
    state["chapter_title"] = CHAPTERS[state["chapter"]]
    state["unlocked"] = [c for c in state["unlocked"] if c in CONTACTS] or ["alina"]
    state["messages"].setdefault("alina", base["messages"]["alina"])
    return state


def verify_telegram_init_data(init_data):
    if not init_data or not BOT_TOKEN:
        return None
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = data.pop("hash", "")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated, received_hash):
            return None
        auth_date = int(data.get("auth_date", "0") or 0)
        if auth_date and abs(int(time.time()) - auth_date) > 172800:
            return None
        user = json.loads(data.get("user", "{}"))
        if not user.get("id"):
            return None
        return {
            "id": int(user["id"]),
            "first_name": str(user.get("first_name") or "Игрок"),
            "username": str(user.get("username") or ""),
        }
    except Exception:
        return None


def get_user(headers, query):
    init_data = headers.get("X-Telegram-Init-Data", "")
    user = verify_telegram_init_data(init_data)
    if user:
        return user
    if DEMO_MODE:
        demo_id = 170017
        try:
            if query.get("demo_id"):
                demo_id = int(query["demo_id"][0])
        except Exception:
            pass
        return {"id": demo_id, "first_name": "Детектив", "username": "demo"}
    return None


def load_player(user):
    con = db()
    row = con.execute("SELECT * FROM players WHERE user_id=?", (user["id"],)).fetchone()
    if row is None:
        state = new_state()
        con.execute(
            "INSERT INTO players(user_id,first_name,username,state_json,updated_at) VALUES(?,?,?,?,?)",
            (user["id"], user["first_name"], user["username"], json.dumps(state, ensure_ascii=False), int(time.time()))
        )
        con.commit()
    else:
        try:
            state = normalize_state(json.loads(row["state_json"]))
        except Exception:
            state = new_state()
    con.close()
    return state


def save_player(user, state):
    state = normalize_state(state)
    con = db()
    con.execute(
        """
        INSERT INTO players(user_id,first_name,username,state_json,updated_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
            first_name=excluded.first_name,
            username=excluded.username,
            state_json=excluded.state_json,
            updated_at=excluded.updated_at
        """,
        (user["id"], user["first_name"], user["username"], json.dumps(state, ensure_ascii=False), int(time.time()))
    )
    con.commit()
    con.close()


def add_message(state, contact, text, sender="them", unread=False):
    state["messages"].setdefault(contact, []).append({"from": sender, "text": text})
    if unread:
        state["unread"][contact] = state["unread"].get(contact, 0) + 1


def unlock_contact(state, contact, first_message=None):
    first = contact not in state["unlocked"]
    if first:
        state["unlocked"].append(contact)
    if first_message:
        add_message(state, contact, first_message, "them", unread=True)
    return first


def add_evidence(state, eid):
    if eid in EVIDENCE and eid not in state["evidence"]:
        state["evidence"].append(eid)
        return True
    return False


def set_tasks(state, *items):
    state["tasks"] = [{"id": i, "title": t, "done": False} for i, t in items]


def done_task(state, tid):
    for task in state["tasks"]:
        if task.get("id") == tid:
            task["done"] = True


def set_chapter(state, chapter, step, *tasks):
    state["chapter"] = chapter
    state["chapter_title"] = CHAPTERS[chapter]
    state["step"] = step
    if tasks:
        set_tasks(state, *tasks)


def action(aid, title, contact=None, style="normal"):
    return {"id": aid, "title": title, "contact": contact, "style": style}


def available_actions(state):
    s = state["step"]
    A = []
    if s == "intro":
        A = [action("inspect_photo", "Изучить фотографию", "alina", "primary")]
    elif s == "photo":
        A = [action("zoom_plate", "Увеличить номер машины", None, "primary"), action("inspect_window", "Рассмотреть отражение в окне")]
    elif s == "alina_last":
        A = [action("open_envelope", "Открыть последнее вложение", "alina", "primary")]
    elif s == "kirill":
        A = [action("kirill_trust", "Я тебе верю", "kirill"), action("kirill_pressure", "Ты что-то скрываешь", "kirill", "danger"), action("kirill_photo", "Показать фотографию", "kirill", "primary")]
    elif s == "apartment":
        A = [action("search_apartment", "Осмотреть квартиру", None, "primary"), action("call_orlov", "Сообщить следователю")]
    elif s == "apartment_clues":
        A = [action("read_receipt", "Проверить чек", None, "primary"), action("inspect_key", "Осмотреть ключ")]
    elif s == "masha":
        A = [action("masha_soft", "Спокойно расспросить", "masha"), action("masha_pressure", "Надавить", "masha", "danger"), action("masha_time", "Спросить про 22:17", "masha", "primary")]
    elif s == "camera":
        A = [action("review_camera", "Проверить запись камеры", None, "primary"), action("compare_time", "Сверить чек и время")]
    elif s == "voice":
        A = [action("analyze_voice", "Прослушать голосовое внимательно", None, "primary"), action("skip_voice", "Отложить аудио")]
    elif s == "igor":
        A = [action("igor_work", "Спросить про работу", "igor"), action("igor_time", "Спросить про 22:17", "igor", "primary"), action("igor_proof", "Показать доказательство", "igor", "danger")]
    elif s == "igor_follow":
        A = [action("check_igor", "Проверить его слова", None, "primary"), action("ask_victor", "Спросить про Виктора", "igor")]
    elif s == "zero":
        A = [action("zero_trust", "Я доверяю тебе", "zero", "primary"), action("zero_distrust", "Я тебе не верю", "zero", "danger"), action("zero_lie", "Сказать, что расследование закончено", "zero")]
    elif s == "code":
        A = [action("code_7317", "7317", None, "primary"), action("code_2217", "2217"), action("code_1809", "1809"), action("code_7771", "7771")]
    elif s == "archive":
        A = [action("archive_files", "Изучить файлы", None, "primary"), action("archive_notes", "Сверить заметки Алины")]
    elif s == "victor":
        A = [action("victor_direct", "Показать записку Алины", "victor", "primary"), action("victor_bluff", "Сделать вид, что всё известно", "victor", "danger"), action("victor_soft", "Спросить спокойно", "victor")]
    elif s == "victor_check":
        A = [action("check_contract", "Сверить договор и записку", None, "primary"), action("check_old_messages", "Проверить старые сообщения")]
    elif s == "betrayal":
        A = [action("ally_orlov", "Передать материалы Орлову"), action("ally_kirill", "Довериться Кириллу", None, "primary"), action("ally_hide", "Скрыть материалы", None, "danger"), action("ally_solo", "Действовать самостоятельно")]
    elif s == "archive_copy":
        A = [action("save_copy", "Сохранить резервную копию", None, "primary"), action("no_copy", "Не оставлять копию", None, "danger")]
    elif s == "critical":
        A = [action("critical_police", "Передать телефон полиции"), action("critical_keep", "Оставить телефон у себя", None, "danger"), action("critical_kirill", "Попросить помощи Кирилла", None, "primary"), action("critical_zero", "Попросить помощи ZERO")]
    elif s == "backup":
        A = [action("backup_orlov", "Отправить копию Орлову"), action("backup_zero", "Отправить копию ZERO"), action("backup_self", "Оставить копию только у себя", None, "danger")]
    elif s == "timeline":
        A = [action("timeline_correct", "21:54 → 22:17 → сообщение ZERO", None, "primary"), action("timeline_wrong1", "22:17 → 21:54 → сообщение ZERO"), action("timeline_wrong2", "ZERO → 21:54 → 22:17")]
    elif s == "motive":
        A = [action("motive_materials", "Получить материалы Алины", None, "primary"), action("motive_revenge", "Личная месть"), action("motive_random", "Случайный конфликт")]
    elif s == "final":
        A = [action("accuse_victor", "Виктор", None, "primary"), action("accuse_kirill", "Кирилл"), action("accuse_zero", "ZERO"), action("accuse_orlov", "Орлов")]
    return A


def incoming_payload(contact, preview):
    return {"contact": contact, "name": CONTACTS[contact]["name"], "preview": preview}


def process_action(state, aid):
    s = state["step"]
    incoming = None
    reveal = None
    chapter_flash = None

    if s == "intro" and aid == "inspect_photo":
        done_task(state, "inspect_photo")
        add_evidence(state, "photo")
        state["step"] = "photo"
        reveal = "Найдена улика: фото у кафе «Луна»"

    elif s == "photo" and aid == "inspect_window":
        if not state["flags"].get("window_secret"):
            state["flags"]["window_secret"] = True
            state["stats"]["secrets"] += 1
            state["notes"].append("В отражении окна можно различить вывеску и часть машины.")
            reveal = "Скрытая деталь добавлена в заметки"
        else:
            reveal = "Ты уже изучил эту деталь"

    elif s == "photo" and aid == "zoom_plate":
        done_task(state, "find_detail")
        add_evidence(state, "plate")
        state["stats"]["correct"] += 1
        state["step"] = "alina_last"
        add_message(state, "alina", "Если ты разобрал номер, открой последнее вложение. Там адрес человека, который может что-то знать.", unread=True)
        incoming = incoming_payload("alina", "Открой последнее вложение.")

    elif s == "alina_last" and aid == "open_envelope":
        set_chapter(state, 2, "kirill", ("talk_kirill", "Поговорить с Кириллом"), ("visit_apartment", "Проверить квартиру Алины"))
        unlock_contact(state, "kirill", "Зачем ты мне пишешь?")
        add_message(state, "kirill", "Алина пропала, и ты решил написать именно мне.", unread=True)
        incoming = incoming_payload("kirill", "Зачем ты мне пишешь?")
        chapter_flash = "Глава 2 — Квартира"

    elif s == "kirill" and aid in {"kirill_trust", "kirill_pressure", "kirill_photo"}:
        done_task(state, "talk_kirill")
        if aid == "kirill_trust":
            state["trust"]["kirill"] += 2
            add_message(state, "kirill", "Ладно. Спасибо, что не начал сразу обвинять меня.", unread=True)
        elif aid == "kirill_pressure":
            state["trust"]["kirill"] -= 2
            state["stats"]["mistakes"] += 1
            add_message(state, "kirill", "Если ты уже всё решил, зачем вообще спрашиваешь?", unread=True)
        else:
            state["trust"]["kirill"] += 1
            add_message(state, "kirill", "Я знаю это место. Это кафе «Луна».", unread=True)
        add_message(state, "kirill", "У Алины был запасной ключ. Проверь конверт возле квартиры.", unread=True)
        state["step"] = "apartment"
        incoming = incoming_payload("kirill", "Проверь конверт возле квартиры.")

    elif s == "apartment" and aid in {"search_apartment", "call_orlov"}:
        if aid == "call_orlov":
            unlock_contact(state, "orlov", "Не трогайте ничего лишнего. Если найдёте важное — сообщите.")
            state["trust"]["orlov"] += 1
            incoming = incoming_payload("orlov", "Если найдёте важное — сообщите.")
        add_evidence(state, "key")
        add_evidence(state, "receipt")
        done_task(state, "visit_apartment")
        state["step"] = "apartment_clues"
        reveal = "Найдены ключ и чек из кафе"

    elif s == "apartment_clues" and aid in {"read_receipt", "inspect_key"}:
        if aid == "read_receipt":
            state["stats"]["correct"] += 1
        else:
            if not state["flags"].get("key_secret"):
                state["flags"]["key_secret"] = True
                state["stats"]["secrets"] += 1
                state["notes"].append("На конверте: «М. слышала больше, чем сказала». ")
        set_chapter(state, 3, "masha", ("talk_masha", "Поговорить с соседкой"), ("check_time", "Проверить время 22:17"))
        unlock_contact(state, "masha", "Привет. Ты ведь ищешь Алину?")
        add_message(state, "masha", "В тот вечер я слышала шум в коридоре.", unread=True)
        incoming = incoming_payload("masha", "Я слышала шум в коридоре.")
        chapter_flash = "Глава 3 — 22:17"

    elif s == "masha" and aid in {"masha_soft", "masha_pressure", "masha_time"}:
        done_task(state, "talk_masha")
        if aid == "masha_soft": state["trust"]["masha"] += 2
        elif aid == "masha_pressure": state["trust"]["masha"] -= 2
        else: state["trust"]["masha"] += 1
        add_message(state, "masha", "В 22:17 у дома остановилась тёмная машина. Водителя я не увидела.", unread=True)
        state["step"] = "camera"
        incoming = incoming_payload("masha", "В 22:17 у дома была тёмная машина.")

    elif s == "camera" and aid in {"review_camera", "compare_time"}:
        done_task(state, "check_time")
        add_evidence(state, "camera")
        state["stats"]["correct"] += 1
        state["conclusions"].append("Кто-то был рядом с домом Алины после 22:00.")
        state["step"] = "voice"
        reveal = "Открыта запись камеры 22:17"

    elif s == "voice" and aid in {"analyze_voice", "skip_voice"}:
        if aid == "analyze_voice":
            add_evidence(state, "voice")
            state["stats"]["secrets"] += 1
        set_chapter(state, 4, "igor", ("talk_igor", "Проверить показания Игоря"), ("find_lie", "Найти противоречие"))
        unlock_contact(state, "igor", "Я не понимаю, почему ты мне пишешь.")
        add_message(state, "igor", "У меня с Алиной был конфликт, но я не причастен.", unread=True)
        incoming = incoming_payload("igor", "Я не причастен.")
        chapter_flash = "Глава 4 — Ложь"

    elif s == "igor" and aid in {"igor_work", "igor_time", "igor_proof"}:
        done_task(state, "talk_igor")
        done_task(state, "find_lie")
        if aid == "igor_time":
            state["stats"]["correct"] += 1
            state["trust"]["igor"] += 2
        elif aid == "igor_proof":
            state["trust"]["igor"] -= 1
        else:
            state["trust"]["igor"] += 1
  
