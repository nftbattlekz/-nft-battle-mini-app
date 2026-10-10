import os
import json
import time
import hmac
import hashlib
import sqlite3

from functools import wraps
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException


# =========================================================
# ДЕЛО №17 — FIXED 2.1
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

DATA_DIR = os.getenv(
    "DATA_DIR",
    os.path.join(BASE_DIR, "data")
)

os.makedirs(DATA_DIR, exist_ok=True)

APP_VERSION = "DELO17 2.1 ROUTE FIX"
STATE_VERSION = 2

DB_PATH = os.getenv(
    "DB_PATH",
    os.path.join(DATA_DIR, "delo17.db")
)

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
).strip()

DEMO_MODE = (
    os.getenv(
        "DEMO_MODE",
        "0"
    ) == "1"
)

DEV_CHANNEL_URL = os.getenv(
    "DEV_CHANNEL_URL",
    "https://t.me/your_channel"
).strip()


app = Flask(
    __name__,
    static_folder=None
)

app.config.update(
    JSON_AS_ASCII=False,
    JSON_SORT_KEYS=False,
    MAX_CONTENT_LENGTH=256 * 1024
)


# =========================================================
# DATABASE
# =========================================================

def db():

    con = sqlite3.connect(
        DB_PATH,
        timeout=30,
        check_same_thread=False
    )

    con.row_factory = sqlite3.Row

    con.execute(
        "PRAGMA busy_timeout=30000"
    )

    con.execute(
        "PRAGMA foreign_keys=ON"
    )

    return con


def init_db():

    con = db()

    try:

        con.execute(
            "PRAGMA journal_mode=WAL"
        )

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
        """
        INSERT INTO app_meta(key,value)
        VALUES('version',?)

        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
        """,
        (
            APP_VERSION,
        )
    )

    con.commit()
    con.close()


# =========================================================
# CONTACTS
# =========================================================

CONTACTS = {

    "alina": {
        "name": "Алина",
        "role": "пропала",
        "avatar": "А",
        "online": "была недавно"
    },

    "kirill": {
        "name": "Кирилл",
        "role": "лучший друг Алины",
        "avatar": "К",
        "online": "в сети"
    },

    "masha": {
        "name": "Маша",
        "role": "соседка",
        "avatar": "М",
        "online": "была недавно"
    },

    "igor": {
        "name": "Игорь",
        "role": "коллега",
        "avatar": "И",
        "online": "в сети"
    },

    "zero": {
        "name": "ZERO",
        "role": "неизвестный контакт",
        "avatar": "0",
        "online": "онлайн"
    },

    "orlov": {
        "name": "Орлов",
        "role": "следователь",
        "avatar": "О",
        "online": "был недавно"
    },

    "victor": {
        "name": "Виктор",
        "role": "журналист",
        "avatar": "В",
        "online": "в сети"
    }

}


# =========================================================
# CHAPTERS
# =========================================================

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
    (10, "Правда")

]


# =========================================================
# EVIDENCE
# =========================================================

EVIDENCE_CATALOG = {

    "cafe_photo": {
        "title": "Фото у кафе",
        "type": "Фото",
        "desc": "На снимке видно кафе «Луна» и машину на заднем плане."
    },

    "plate": {
        "title": "Номер машины",
        "type": "Деталь",
        "desc": "На увеличенном фрагменте читается номер KZ 777 FBA 01."
    },

    "apartment_key": {
        "title": "Ключ от квартиры",
        "type": "Предмет",
        "desc": "Ключ лежал внутри конверта с подписью Алины."
    },

    "receipt": {
        "title": "Чек 18:09",
        "type": "Документ",
        "desc": "Чек из кафе «Луна». Время покупки — 21:54."
    },

    "cctv": {
        "title": "Камера 22:17",
        "type": "Видео",
        "desc": "Машина, похожая на машину Кирилла, появляется у кафе в 22:17."
    },

    "voice": {
        "title": "Голосовое 00:43",
        "type": "Аудио",
        "desc": "На фоне слышно объявление и металлический звон двери."
    },

    "archive_note": {
        "title": "Записка из архива",
        "type": "Документ",
        "desc": "Алина отмечала имя «Виктор» рядом со словом «источник»."
    },

    "contract": {
        "title": "Черновик договора",
        "type": "Документ",
        "desc": "Документ связывает Виктора с публикацией материалов Алины."
    },

    "zero_id": {
        "title": "Личность ZERO",
        "type": "Секрет",
        "desc": "ZERO — бывший источник Алины. Он скрывался из страха, а не из-за причастности."
    },

    "final_proof": {
        "title": "Последнее доказательство",
        "type": "Секрет",
        "desc": "Сообщения Виктора подтверждают, что он пытался забрать материалы Алины."
    }

}


# =========================================================
# NEW GAME
# =========================================================

def initial_state():

    return {

        "state_version": STATE_VERSION,

        "chapter": 1,

        "step": "alina_intro",

        "chapter_title":
            "Последнее сообщение",

        "unlocked_contacts": [
            "alina"
        ],

        "messages": {

            "alina": [

                {
                    "from": "them",
                    "text": "Привет...",
                    "kind": "text"
                },

                {
                    "from": "them",
                    "text": "Если ты это читаешь — значит, со мной что-то произошло.",
                    "kind": "text"
                },

                {
                    "from": "them",
                    "text": "Я не могу сейчас говорить. Посмотри фотографию. Там есть деталь, которая всё меняет.",
                    "kind": "text"
                },

                {
                    "from": "them",
                    "text": "И пожалуйста — не доверяй никому слишком быстро.",
                    "kind": "text"
                }

            ]

        },

        "evidence": [],

        "tasks": [

            {
                "id": "inspect_photo",
                "title": "Внимательно изучить фотографию",
                "done": False
            },

            {
                "id": "find_detail",
                "title": "Найти важную деталь",
                "done": False
            }

        ],

        "trust": {

            "kirill": 0,
            "masha": 0,
            "igor": 0,
            "zero": 0,
            "orlov": 0,
            "victor": 0

        },

        "flags": {},

        "notes": [],

        "conclusions": [],

        "ending": None,

        "ending_title": None,

        "ending_text": None,

        "stats": {

            "secrets": 0,
            "correct": 0,
            "mistakes": 0

        },

        "new_badges": {},

        "started_at":
            int(time.time())

    }


# =========================================================
# SAVE MIGRATION
# =========================================================

def migrate_state(raw_state):

    if not isinstance(
        raw_state,
        dict
    ):

        return initial_state()

    base = initial_state()

    state = dict(
        raw_state
    )

    simple_keys = [

        "chapter",
        "step",
        "chapter_title",
        "ending",
        "ending_title",
        "ending_text",
        "started_at"

    ]

    for key in simple_keys:

        if key not in state:

            state[key] = base[key]

    for key in [

        "unlocked_contacts",
        "messages",
        "evidence",
        "tasks",
        "flags",
        "notes",
        "conclusions",
        "new_badges"

    ]:

        expected = base[key]

        if not isinstance(
            state.get(key),
            type(expected)
        ):

            if isinstance(
                expected,
                dict
            ):

                state[key] = dict(
                    expected
                )

            else:

                state[key] = list(
                    expected
                )

    for key in [
        "trust",
        "stats"
    ]:

        merged = dict(
            base[key]
        )

        if isinstance(
            state.get(key),
            dict
        ):

            merged.update(
                state[key]
            )

        state[key] = merged

    state["unlocked_contacts"] = [

        x

        for x
        in state["unlocked_contacts"]

        if x in CONTACTS

    ]

    if not state[
        "unlocked_contacts"
    ]:

        state[
            "unlocked_contacts"
        ] = [
            "alina"
        ]

    try:

        chapter = int(
            state.get(
                "chapter",
                1
            )
        )

    except Exception:

        chapter = 1

    state["chapter"] = max(
        1,
        min(
            chapter,
            10
        )
    )

    state[
        "messages"
    ].setdefault(
        "alina",
        list(
            base[
                "messages"
            ][
                "alina"
            ]
        )
    )

    state[
        "state_version"
    ] = STATE_VERSION

    return state


# =========================================================
# TELEGRAM AUTH
# =========================================================

def verify_init_data(
    init_data
):

    if (
        not init_data
        or
        not BOT_TOKEN
    ):

        return None

    try:

        data = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = data.pop(
            "hash",
            ""
        )

        check_string = "\n".join(

            f"{k}={v}"

            for k, v
            in sorted(
                data.items()
            )

        )

        secret_key = hmac.new(

            b"WebAppData",

            BOT_TOKEN.encode(),

            hashlib.sha256

        ).digest()

        calculated = hmac.new(

            secret_key,

            check_string.encode(),

            hashlib.sha256

        ).hexdigest()

        if not hmac.compare_digest(
            calculated,
            received_hash
        ):

            return None

        auth_date = int(
            data.get(
                "auth_date",
                "0"
            )
            or 0
        )

        if (
            auth_date
            and
            abs(
                int(
                    time.time()
                )
                -
                auth_date
            )
            >
            172800
        ):

            return None

        user = json.loads(
            data.get(
                "user",
                "{}"
            )
        )

        if not user.get(
            "id"
        ):

            return None

        return user

    except Exception:

        return None


def current_user():

    init_data = request.headers.get(
        "X-Telegram-Init-Data",
        ""
    )

    user = verify_init_data(
        init_data
    )

    if user:

        return {

            "id":
                int(
                    user[
                        "id"
                    ]
                ),

            "first_name":
                str(
                    user.get(
                        "first_name"
                    )
                    or
                    "Игрок"
                ),

            "username":
                str(
                    user.get(
                        "username"
                    )
                    or
                    ""
                )

        }

    if DEMO_MODE:

        return {

            "id":
                170017,

            "first_name":
                "Детектив",

            "username":
                "demo_detective"

        }

    return None


def auth_required(
    fn
):

    @wraps(fn)

    def wrapper(
        *args,
        **kwargs
    ):

        user = current_user()

        if not user:

            return jsonify({
                "ok": False,
                "error":
                    "Telegram authorization failed"
            }), 401

        request.tg_user = user

        return fn(
            *args,
            **kwargs
        )

    return wrapper


# =========================================================
# PLAYER
# =========================================================

def load_player(
    user
):

    con = db()

    row = con.execute(

        """
        SELECT *
        FROM players
        WHERE telegram_id=?
        """,

        (
            user["id"],
        )

    ).fetchone()

    if row is None:

        state = initial_state()

        con.execute(

            """
            INSERT INTO players(
                telegram_id,
                first_name,
                username,
                state_json,
                updated_at
            )

            VALUES(?,?,?,?,?)
            """,

            (

                user["id"],

                user[
                    "first_name"
                ],

                user[
                    "username"
                ],

                json.dumps(
                    state,
                    ensure_ascii=False
                ),

                int(
                    time.time()
                )

            )

        )

        con.commit()

    else:

        try:

            raw = json.loads(
                row[
                    "state_json"
                ]
            )

        except Exception:

            raw = initial_state()

        state = migrate_state(
            raw
        )

    con.close()

    return state


def save_player(
    user,
    state
):

    state = migrate_state(
        state
    )

    con = db()

    con.execute(

        """
        INSERT INTO players(
            telegram_id,
            first_name,
            username,
            state_json,
            updated_at
        )

        VALUES(?,?,?,?,?)

        ON CONFLICT(telegram_id)

        DO UPDATE SET

            first_name=
                excluded.first_name,

            username=
                excluded.username,

            state_json=
                excluded.state_json,

            updated_at=
                excluded.updated_at
        """,

        (

            user["id"],

            user[
                "first_name"
            ],

            user[
                "username"
            ],

            json.dumps(
                state,
                ensure_ascii=False
            ),

            int(
                time.time()
            )

        )

    )

    con.commit()
    con.close()


# =========================================================
# HELPERS
# =========================================================

def add_msg(
    state,
    contact,
    text,
    sender="them"
):

    state[
        "messages"
    ].setdefault(
        contact,
        []
    ).append({

        "from":
            sender,

        "text":
            text,

        "kind":
            "text"

    })


def unlock_contact(
    state,
    contact
):

    if contact not in state[
        "unlocked_contacts"
    ]:

        state[
            "unlocked_contacts"
        ].append(
            contact
        )


def add_evidence(
    state,
    evidence_id
):

    if evidence_id not in state[
        "evidence"
    ]:

        state[
            "evidence"
        ].append(
            evidence_id
        )


def set_chapter(
    state,
    chapter
):

    state["chapter"] = chapter

    state[
        "chapter_title"
    ] = dict(
        CHAPTERS
    )[chapter]


def set_tasks(
    state,
    items
):

    state["tasks"] = [

        {

            "id":
                item[0],

            "title":
                item[1],

            "done":
                False

        }

        for item
        in items

    ]


def mark_task(
    state,
    task_id
):

    for task in state[
        "tasks"
    ]:

        if task[
            "id"
        ] == task_id:

            task[
                "done"
            ] = True


# =========================================================
# ACTIONS
# =========================================================

def available_actions(
    state
):

    step = state[
        "step"
    ]

    actions = []

    def add(
        action_id,
        title,
        style="normal",
        contact=None
    ):

        actions.append({

            "id":
                action_id,

            "title":
                title,

            "style":
                style,

            "contact":
                contact

        })

    if step == "alina_intro":

        add(
            "inspect_photo",
            "Изучить фотографию",
            "primary",
            "alina"
        )

    elif step == "photo_zoom":

        add(
            "find_plate",
            "Увеличить номер машины",
            "primary"
        )

        if not state[
            "flags"
        ].get(
            "window_detail"
        ):

            add(
                "look_window",
                "Рассмотреть окно кафе"
            )

    elif step == "alina_last_note":

        add(
            "open_envelope",
            "Открыть последнее вложение Алины",
            "primary",
            "alina"
        )

    elif step == "kirill_intro":

        add(
            "kirill_trust",
            "Я тебе верю",
            "normal",
            "kirill"
        )

        add(
            "kirill_pressure",
            "Ты что-то скрываешь",
            "danger",
            "kirill"
        )

        add(
            "kirill_show_photo",
            "Показать фотографию",
            "primary",
            "kirill"
        )

    elif step == "apartment":

        add(
            "search_apartment",
            "Осмотреть квартиру",
            "primary"
        )

        add(
            "ask_orlov",
            "Сообщить следователю"
        )

    elif step == "apartment_findings":

        add(
            "inspect_receipt",
            "Проверить чек из кафе",
            "primary"
        )

        add(
            "inspect_key",
            "Осмотреть ключ и конверт"
        )

    elif step == "masha_intro":

        add(
            "masha_soft",
            "Спокойно расспросить",
            "normal",
            "masha"
        )

        add(
            "masha_pressure",
            "Надавить на неё",
            "danger",
            "masha"
        )

        add(
            "masha_2217",
            "Спросить про 22:17",
            "primary",
            "masha"
        )

    elif step == "cctv_check":

        add(
            "review_cctv",
            "Проверить запись камеры",
            "primary"
        )

        add(
            "compare_receipt",
            "Сверить чек и время"
        )

    elif step == "voice_check":

        add(
            "analyze_voice",
            "Прослушать г
