import os
import json
import time
import hmac
import hashlib
import sqlite3
from urllib.parse import parse_qsl
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

APP_VERSION = "DELO17 2.0 FIXED"
STATE_VERSION = 2
DB_PATH = os.getenv("DB_PATH", os.path.join(DATA_DIR, "delo17.db"))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"
DEV_CHANNEL_URL = os.getenv("DEV_CHANNEL_URL", "https://t.me/your_channel").strip()

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")
app.config.update(
    JSON_AS_ASCII=False,
    JSON_SORT_KEYS=False,
    MAX_CONTENT_LENGTH=256 * 1024,
)


def db():
    # timeout/busy_timeout make SQLite much more stable under Gunicorn threads.
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    con = db()
    # WAL improves read/write concurrency for this small game database.
    try:
        con.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS players (
            telegram_id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            state_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    con.execute(
        "INSERT INTO app_meta(key,value) VALUES('version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (APP_VERSION,),
    )
    con.commit()
    con.close()


def initial_state():
    return {
        "state_version": STATE_VERSION,
        "chapter": 1,
        "step": "alina_intro",
        "chapter_title": "Последнее сообщение",
        "unlocked_contacts": ["alina"],
        "messages": {
            "alina": [
                {"from": "them", "text": "Привет...", "kind": "text"},
                {"from": "them", "text": "Если ты это читаешь — значит, со мной что-то произошло.", "kind": "text"},
                {"from": "them", "text": "Я не могу сейчас говорить. Посмотри фотографию. Там есть деталь, которая всё меняет.", "kind": "text"},
                {"from": "them", "text": "И пожалуйста — не доверяй никому слишком быстро.", "kind": "text"},
            ]
        },
        "evidence": [],
        "tasks": [
            {"id": "inspect_photo", "title": "Внимательно изучить фотографию", "done": False},
            {"id": "find_detail", "title": "Найти важную деталь", "done": False},
        ],
        "trust": {"kirill": 0, "masha": 0, "igor": 0, "zero": 0, "orlov": 0, "victor": 0},
        "flags": {},
        "notes": [],
        "conclusions": [],
        "ending": None,
        "ending_title": None,
        "ending_text": None,
        "stats": {"secrets": 0, "correct": 0, "mistakes": 0},
        "new_badges": {},
        "started_at": int(time.time()),
    }


CONTACTS = {
    "alina": {"name": "Алина", "role": "пропала", "avatar": "А", "online": "была недавно"},
    "kirill": {"name": "Кирилл", "role": "лучший друг Алины", "avatar": "К", "online": "в сети"},
    "masha": {"name": "Маша", "role": "соседка", "avatar": "М", "online": "была недавно"},
    "igor": {"name": "Игорь", "role": "коллега", "avatar": "И", "online": "в сети"},
    "zero": {"name": "ZERO", "role": "неизвестный контакт", "avatar": "0", "online": "онлайн"},
    "orlov": {"name": "Орлов", "role": "следователь", "avatar": "О", "online": "был недавно"},
    "victor": {"name": "Виктор", "role": "журналист", "avatar": "В", "online": "в сети"},
}

CHAPTERS = [
    (1, "Последнее сообщение"),
    (2, "Квартира"),
    (3, "22:17"),
    (4, "Ложь"),
    (5, "ZERO"),
    (6, "Архив"),
    (7, "Предательство"),
    (8, "Точка невозврата"),
    (9, "Последняя ночь"),
    (10, "Правда"),
]

EVIDENCE_CATALOG = {
    "cafe_photo": {"title": "Фото у кафе", "type": "Фото", "desc": "На снимке видно кафе «Луна» и машину на заднем плане."},
    "plate": {"title": "Номер машины", "type": "Деталь", "desc": "На увеличенном фрагменте читается номер KZ 777 FBA 01."},
    "apartment_key": {"title": "Ключ от квартиры", "type": "Предмет", "desc": "Ключ лежал внутри конверта с подписью Алины."},
    "receipt": {"title": "Чек 18:09", "type": "Документ", "desc": "Чек из кафе «Луна». Время покупки — 21:54."},
    "cctv": {"title": "Камера 22:17", "type": "Видео", "desc": "Машина, похожая на машину Кирилла, появляется у кафе в 22:17."},
    "voice": {"title": "Голосовое 00:43", "type": "Аудио", "desc": "На фоне слышно объявление и металлический звон двери."},
    "archive_note": {"title": "Записка из архива", "type": "Документ", "desc": "Алина отмечала имя «Виктор» рядом со словом «источник»."},
    "contract": {"title": "Черновик договора", "type": "Документ", "desc": "Документ связывает Виктора с публикацией материалов Алины."},
    "zero_id": {"title": "Личность ZERO", "type": "Секрет", "desc": "ZERO — бывший источник Алины. Он скрывался из страха, а не из-за причастности."},
    "final_proof": {"title": "Последнее доказательство", "type": "Секрет", "desc": "В сообщениях Виктора есть признание, что он пытался заставить Алину замолчать и забрать материалы."},
}


def migrate_state(raw_state):
    """Bring old saves forward instead of crashing with KeyError after deploys."""
    if not isinstance(raw_state, dict):
        return initial_state()

    base = initial_state()
    state = dict(raw_state)

    # Required simple keys.
    for key in (
        "chapter", "step", "chapter_title", "ending",
        "ending_title", "ending_text", "started_at"
    ):
        if key not in state:
            state[key] = base[key]

    # Required list/dict containers.
    for key in ("unlocked_contacts", "messages", "evidence", "tasks",
                "flags", "notes", "conclusions", "new_badges"):
        expected = base[key]
        if not isinstance(state.get(key), type(expected)):
            state[key] = expected.copy() if isinstance(expected, (dict, list)) else expected

    # Merge nested dictionaries so new fields do not break old saves.
    for key in ("trust", "stats"):
        merged = dict(base[key])
        if isinstance(state.get(key), dict):
            merged.update(state[key])
        state[key] = merged

    # Sanitize values that are used as lookup keys.
    state["unlocked_contacts"] = [
        x for x in state["unlocked_contacts"]
        if x in CONTACTS
    ] if "CONTACTS" in globals() else state["unlocked_contacts"]

    if not state["unlocked_contacts"]:
        state["unlocked_contacts"] = ["alina"]

    try:
        chapter = int(state.get("chapter", 1))
    except (TypeError, ValueError):
        chapter = 1
    state["chapter"] = min(10, max(1, chapter))

    if not isinstance(state.get("messages"), dict):
        state["messages"] = base["messages"]
    state["messages"].setdefault("alina", list(base["messages"]["alina"]))

    state["state_version"] = STATE_VERSION
    return state


def verify_init_data(init_data: str):
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
        return user
    except Exception:
        return None


def current_user():
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    user = verify_init_data(init_data)
    if user:
        return {
            "id": int(user["id"]),
            "first_name": str(user.get("first_name") or "Игрок"),
            "username": str(user.get("username") or ""),
        }
    if DEMO_MODE:
        return {"id": 170017, "first_name": "Детектив", "username": "demo_detective"}
    return None


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"ok": False, "error": "Telegram authorization failed"}), 401
        request.tg_user = user
        return fn(*args, **kwargs)
    return wrapper


def load_player(user):
    con = db()
    row = con.execute("SELECT * FROM players WHERE telegram_id=?", (user["id"],)).fetchone()
    changed = False
    if row is None:
        state = initial_state()
        con.execute(
            "INSERT INTO players(telegram_id, first_name, username, state_json, updated_at) VALUES(?,?,?,?,?)",
            (user["id"], user["first_name"], user["username"], json.dumps(state, ensure_ascii=False), int(time.time())),
        )
        con.commit()
    else:
        try:
            raw = json.loads(row["state_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            raw = initial_state()
            changed = True
        state = migrate_state(raw)
        if state.get("state_version") != raw.get("state_version"):
            changed = True
        if changed:
            con.execute(
                "UPDATE players SET state_json=?, updated_at=? WHERE telegram_id=?",
                (json.dumps(state, ensure_ascii=False), int(time.time()), user["id"]),
            )
            con.commit()
    con.close()
    return state


def save_player(user, state):
    state = migrate_state(state)
    con = db()
    con.execute(
        "INSERT INTO players(telegram_id, first_name, username, state_json, updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET first_name=excluded.first_name, username=excluded.username, "
        "state_json=excluded.state_json, updated_at=excluded.updated_at",
        (user["id"], user["first_name"], user["username"], json.dumps(state, ensure_ascii=False), int(time.time())),
    )
    con.commit()
    con.close()


def add_msg(state, contact, text, sender="them", kind="text"):
    state["messages"].setdefault(contact, []).append({"from": sender, "text": text, "kind": kind})


def unlock_contact(state, contact):
    if contact not in state["unlocked_contacts"]:
        state["unlocked_contacts"].append(contact)


def add_evidence(state, evidence_id):
    if evidence_id not in state["evidence"]:
        state["evidence"].append(evidence_id)


def set_chapter(state, chapter):
    state["chapter"] = chapter
    state["chapter_title"] = dict(CHAPTERS)[chapter]


def set_tasks(state, items):
    state["tasks"] = [{"id": i[0], "title": i[1], "done": False} for i in items]


def mark_task(state, task_id):
    for t in state["tasks"]:
        if t["id"] == task_id:
            t["done"] = True


def available_actions(state):
    step = state["step"]
    A = []
    def a(id_, title, style="normal", contact=None):
        A.append({"id": id_, "title": title, "style": style, "contact": contact})

    if step == "alina_intro":
        a("inspect_photo", "Изучить фотографию", "primary", "alina")
    elif step == "photo_zoom":
        a("find_plate", "Увеличить номер машины", "primary")
        if not state.get("flags", {}).get("window_detail"):
            a("look_window", "Рассмотреть окно кафе")
    elif step == "alina_last_note":
        a("open_envelope", "Открыть последнее вложение Алины", "primary", "alina")
    elif step == "kirill_intro":
        a("kirill_trust", "Я тебе верю", "normal", "kirill")
        a("kirill_pressure", "Ты что-то скрываешь", "danger", "kirill")
        a("kirill_show_photo", "Показать фотографию", "primary", "kirill")
    elif step == "apartment":
        a("search_apartment", "Осмотреть квартиру", "primary")
        a("ask_orlov", "Сообщить следователю")
    elif step == "apartment_findings":
        a("inspect_receipt", "Проверить чек из кафе", "primary")
        a("inspect_key", "Осмотреть ключ и конверт")
    elif step == "masha_intro":
        a("masha_soft", "Спокойно расспросить", "normal", "masha")
        a("masha_pressure", "Надавить на неё", "danger", "masha")
        a("masha_2217", "Спросить про 22:17", "primary", "masha")
    elif step == "cctv_check":
        a("review_cctv", "Проверить запись камеры", "primary")
        a("compare_receipt", "Сверить чек и время")
    elif step == "voice_check":
        a("analyze_voice", "Прослушать голосовое внимательно", "primary")
        a("skip_voice", "Отложить аудио на потом")
    elif step == "igor_intro":
        a("igor_work", "Спросить про работу", "normal", "igor")
        a("igor_2217", "Спросить про 22:17", "primary", "igor")
        a("igor_proof", "Показать доказательство", "danger", "igor")
    elif step == "igor_followup":
        a("check_igor_claim", "Проверить слова Игоря", "primary", "igor")
        a("ask_about_victor", "Спросить, кто такой Виктор", "normal", "igor")
    elif step == "zero_intro":
        a("zero_trust", "Я доверяю тебе", "primary", "zero")
        a("zero_distrust", "Я тебе не верю", "danger", "zero")
        a("zero_lie", "Сказать, что расследование закончено", "normal", "zero")
    elif step == "archive_code":
        a("code_7317", "7317", "primary")
        a("code_2217", "2217")
        a("code_1809", "1809")
        a("code_7771", "7771")
    elif step == "archive_review":
        a("read_archive_files", "Изучить файлы из архива", "primary")
        a("read_archive_notes", "Сверить заметки Алины")
    elif step == "victor_intro":
        a("victor_direct", "Показать записку Алины", "primary", "victor")
        a("victor_bluff", "Сделать вид, что всё известно", "danger", "victor")
        a("victor_soft", "Спросить спокойно", "normal", "victor")
    elif step == "victor_crosscheck":
        a("crosscheck_contract", "Сверить договор и записку", "primary")
        a("crosscheck_messages", "Проверить старые сообщения")
    elif step == "betrayal":
        a("betray_orlov", "Передать материалы Орлову", "normal")
        a("betray_kirill", "Довериться Кириллу", "primary")
        a("betray_hide", "Скрыть материалы", "danger")
        a("betray_solo", "Действовать самостоятельно", "normal")
    elif step == "chapter7_after":
        a("save_archive_copy", "Сохранить резервную копию архива", "primary")
        a("leave_no_copy", "Не оставлять копию", "danger")
    elif step == "point_no_return":
        a("critical_police", "Передать телефон полиции", "normal")
        a("critical_keep", "Оставить телефон у себя", "danger")
        a("critical_kirill", "Попросить помощи Кирилла", "primary")
        a("critical_zero", "Попросить помощи ZERO", "normal")
    elif step == "critical_followup":
        a("backup_orlov", "Отправить копию Орлову", "normal")
        a("backup_zero", "Отправить копию ZERO", "normal")
        a("backup_self", "Оставить копию только у себя", "danger")
    elif step == "timeline":
        a("timeline_correct", "21:54 → 22:17 → сообщение ZERO", "primary")
        a("timeline_wrong1", "22:17 → 21:54 → сообщение ZERO")
        a("timeline_wrong2", "Сообщение ZERO → 21:54 → 22:17")
    elif step == "motive":
        a("motive_materials", "Забрать материалы Алины", "primary")
        a("motive_revenge", "Личная месть")
        a("motive_random", "Случайный конфликт")
    elif step == "final_accusation":
        a("accuse_victor", "Виктор", "primary")
        a("accuse_kirill", "Кирилл")
        a("accuse_orlov", "Орлов")
        a("accuse_zero", "ZERO")
    return A


def public_state(user, state):
    visible_contacts = []
    for cid in state["unlocked_contacts"]:
        c = dict(CONTACTS[cid])
        c["id"] = cid
        c["badge"] = state["new_badges"].get(cid, 0)
        msgs = state["messages"].get(cid, [])
        c["preview"] = msgs[-1]["text"] if msgs else ""
        visible_contacts.append(c)

    ev = [{"id": x, **EVIDENCE_CATALOG[x]} for x in state["evidence"] if x in EVIDENCE_CATALOG]
    return {
        "user": {"id": user["id"], "first_name": user["first_name"], "username": user["username"]},
        "chapter": state["chapter"],
        "chapter_title": state["chapter_title"],
        "step": state["step"],
        "contacts": visible_contacts,
        "messages": {cid: state["messages"].get(cid, []) for cid in state["unlocked_contacts"]},
        "evidence": ev,
        "tasks": state["tasks"],
        "trust": state["trust"],
        "conclusions": state["conclusions"],
        "notes": state["notes"],
        "ending": state["ending"],
        "ending_title": state["ending_title"],
        "ending_text": state["ending_text"],
        "stats": state["stats"],
        "actions": available_actions(state),
        "chapters": [{"num": n, "title": t, "unlocked": n <= state["chapter"]} for n, t in CHAPTERS],
        "dev_channel_url": DEV_CHANNEL_URL,
    }


def process_action(state, action):
    incoming = None
    reveal = None
    chapter_flash = None

    def notify(contact, preview):
        nonlocal incoming
        state["new_badges"][contact] = state["new_badges"].get(contact, 0) + 1
        incoming = {"contact": contact, "name": CONTACTS[contact]["name"], "preview": preview}

    if action == "inspect_photo" and state["step"] == "alina_intro":
        mark_task(state, "inspect_photo")
        add_evidence(state, "cafe_photo")
        state["step"] = "photo_zoom"
        reveal = "Новая улика: фото у кафе «Луна»"

    elif action == "find_plate" and state["step"] == "photo_zoom":
        mark_task(state, "find_detail")
        add_evidence(state, "plate")
        state["stats"]["correct"] += 1
        state["step"] = "alina_last_note"
        add_msg(state, "alina", "Если ты смог разобрать номер — открой последнее вложение. Там адрес и имя человека, которому я когда-то доверяла.")
        notify("alina", "Открой последнее вложение. Там адрес и имя.")

    elif action == "open_envelope" and state["step"] == "alina_last_note":
        set_chapter(state, 2)
        state["step"] = "kirill_intro"
        set_tasks(state, [("talk_kirill", "Поговорить с Кириллом"), ("visit_apartment", "Проверить квартиру Алины")])
        unlock_contact(state, "kirill")
        add_msg(state, "kirill", "Зачем ты мне пишешь?")
        add_msg(state, "kirill", "Алина пропала, и ты мне пишешь именно сейчас...")
        notify("kirill", "Зачем ты мне пишешь?")
        chapter_flash = "Глава 2 — Квартира"

    elif action == "look_window" and state["step"] == "photo_zoom" and not state.get("flags", {}).get("window_detail"):
        state["flags"]["window_detail"] = True
        state["notes"].append("На окне кафе отражается яркая вывеска. Возможно, время снимка можно проверить по камерам.")
        state["stats"]["secrets"] += 1
        reveal = "Секретная деталь добавлена в заметки"

    elif action in {"kirill_trust", "kirill_pressure", "kirill_show_photo"} and state["step"] == "kirill_intro":
        mark_task(state, "talk_kirill")
        if action == "kirill_trust":
            state["trust"]["kirill"] += 2
            add_msg(state, "kirill", "Ладно. Спасибо, что не начал сразу обвинять меня.")
        elif action == "kirill_pressure":
            state["trust"]["kirill"] -= 2
            state["stats"]["mistakes"] 
