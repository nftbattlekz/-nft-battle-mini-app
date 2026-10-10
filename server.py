import os
import time
import json
import hmac
import hashlib
import secrets
import sqlite3
from functools import wraps
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

# =========================================================
# NOMER CLUB 6.4 UNLIMITED
# =========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

os.makedirs(WEB_DIR, exist_ok=True)

APP_VERSION = "NOMER CLUB 6.4 UNLIMITED"

app = Flask(
    __name__,
    static_folder=WEB_DIR,
    static_url_path=""
)

app.config["JSON_AS_ASCII"] = False


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

PRIMARY_CREATOR_ID = 8518976778

_extra_admins = set()

for raw in os.getenv(
    "ADMIN_TELEGRAM_IDS",
    ""
).split(","):

    raw = raw.strip()

    if raw.isdigit():
        _extra_admins.add(
            int(raw)
        )


ADMIN_TELEGRAM_IDS = {
    PRIMARY_CREATOR_ID,
    *_extra_admins
}


SPIN_COST = 100

START_BALANCE = 10000

RESCUE_BONUS = 1500

MARKET_FEE_PERCENT = 5

MAX_ACTIVE_LISTINGS = 3


_db_env = os.getenv(
    "DB_PATH",
    ""
).strip()


DB_PATH = (
    _db_env
    if _db_env
    else os.path.join(
        BASE_DIR,
        "nomer_fixed.db"
    )
)


if not os.path.isabs(
    DB_PATH
):
    DB_PATH = os.path.join(
        BASE_DIR,
        DB_PATH
    )


DB_PATH = os.path.abspath(
    DB_PATH
)


os.makedirs(
    os.path.dirname(
        DB_PATH
    ) or BASE_DIR,
    exist_ok=True
)


LETTERS = "ABEKMHOPCTYX"


REGIONS = [
    "01",
    "02",
    "05",
    "07",
    "16",
    "50",
    "77",
    "78",
    "95",
    "99",
    "116",
    "177",
    "777"
]


RARITIES = [

    (
        "Обычный",
        600
    ),

    (
        "Необычный",
        250
    ),

    (
        "Редкий",
        100
    ),

    (
        "Эпический",
        40
    ),

    (
        "Легендарный",
        9
    ),

    (
        "Мифический",
        1
    )
]


RARITY_ORDER = {

    "Обычный": 0,

    "Необычный": 1,

    "Редкий": 2,

    "Эпический": 3,

    "Легендарный": 4,

    "Мифический": 5
}


SYSTEM_SELL_PRICES = {

    "Обычный": 35,

    "Необычный": 75,

    "Редкий": 220,

    "Эпический": 800,

    "Легендарный": 3500,

    "Мифический": 15000
}


TASKS = [

    {
        "key": "spin_3",
        "title": "Сгенерируй 3 номера",
        "stat": "spins",
        "target": 3,
        "reward_nc": 350,
        "reward_xp": 30
    },

    {
        "key": "spin_10",
        "title": "Сгенерируй 10 номеров",
        "stat": "spins",
        "target": 10,
        "reward_nc": 800,
        "reward_xp": 80
    },

    {
        "key": "list_1",
        "title": "Выставь номер на маркет",
        "stat": "listings",
        "target": 1,
        "reward_nc": 300,
        "reward_xp": 35
    },

    {
        "key": "buy_1",
        "title": "Купи номер на маркете",
        "stat": "buys",
        "target": 1,
        "reward_nc": 500,
        "reward_xp": 50
    },

    {
        "key": "rare_1",
        "title": "Найди редкий номер или лучше",
        "stat": "rare_found",
        "target": 1,
        "reward_nc": 700,
        "reward_xp": 70
    }
]


TASK_BY_KEY = {
    x["key"]: x
    for x in TASKS
}


ACHIEVEMENTS = [

    {
        "key": "first_plate",
        "title": "Первый номер",
        "target": 1,
        "field": "collection"
    },

    {
        "key": "collector_10",
        "title": "Коллекционер",
        "target": 10,
        "field": "collection"
    },

    {
        "key": "collector_50",
        "title": "Большой гараж",
        "target": 50,
        "field": "collection"
    },

    {
        "key": "level_10",
        "title": "Уровень 10",
        "target": 10,
        "field": "level"
    },

    {
        "key": "level_25",
        "title": "Уровень 25",
        "target": 25,
        "field": "level"
    }
]


@app.after_request
def no_cache(response):

    response.headers[
        "Cache-Control"
    ] = (
        "no-store, no-cache, "
        "must-revalidate, max-age=0"
    )

    response.headers[
        "Pragma"
    ] = "no-cache"

    response.headers[
        "Expires"
    ] = "0"

    response.headers[
        "X-Nomer-Club-Version"
    ] = APP_VERSION

    return response


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

    try:

        con.execute(
            "PRAGMA journal_mode=WAL"
        )

    except sqlite3.Error:

        pass

    return con


def table_columns(
    con,
    table
):

    return {
        row["name"]

        for row in con.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    }


def ensure_column(
    con,
    table,
    name,
    ddl
):

    if name not in table_columns(
        con,
        table
    ):

        con.execute(
            f"""
            ALTER TABLE {table}
            ADD COLUMN {name} {ddl}
            """
        )


def init_db():

    with db() as con:

        con.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY,

                name TEXT NOT NULL,

                username TEXT
                NOT NULL
                DEFAULT '',

                balance INTEGER
                NOT NULL
                DEFAULT {START_BALANCE},

                xp INTEGER
                NOT NULL
                DEFAULT 0,

                spins_day TEXT
                NOT NULL
                DEFAULT '',

                spins_used INTEGER
                NOT NULL
                DEFAULT 0,

                created_at INTEGER
                NOT NULL,

                rescue_claimed INTEGER
                NOT NULL
                DEFAULT 0,

                mythic_mode INTEGER
                NOT NULL
                DEFAULT 0,

                mythic_queue INTEGER
                NOT NULL
                DEFAULT 0,

                pending_plate_id INTEGER
            );


            CREATE TABLE IF NOT EXISTS plates(

                id INTEGER
                PRIMARY KEY AUTOINCREMENT,

                code TEXT
                NOT NULL
                UNIQUE,

                rarity TEXT
                NOT NULL,

                owner_id INTEGER
                NOT NULL,

                created_at INTEGER
                NOT NULL
            );


            CREATE TABLE IF NOT EXISTS listings(

                id INTEGER
                PRIMARY KEY AUTOINCREMENT,

                plate_id INTEGER
                NOT NULL
                UNIQUE,

                seller_id INTEGER
                NOT NULL,

                price INTEGER
                NOT NULL
                CHECK(price > 0),

                created_at INTEGER
                NOT NULL
            );


            CREATE TABLE IF NOT EXISTS daily_stats(

                user_id INTEGER
                NOT NULL,

                day TEXT
                NOT NULL,

                spins INTEGER
                NOT NULL
                DEFAULT 0,

                listings INTEGER
                NOT NULL
                DEFAULT 0,

                buys INTEGER
                NOT NULL
                DEFAULT 0,

                sales INTEGER
                NOT NULL
                DEFAULT 0,

                rare_found INTEGER
                NOT NULL
                DEFAULT 0,

                PRIMARY KEY(
                    user_id,
                    day
                )
            );


            CREATE TABLE IF NOT EXISTS task_claims(

                user_id INTEGER
                NOT NULL,

                day TEXT
                NOT NULL,

                task_key TEXT
                NOT NULL,

                claimed_at INTEGER
                NOT NULL,

                PRIMARY KEY(
                    user_id,
                    day,
                    task_key
                )
            );


            CREATE TABLE IF NOT EXISTS spin_requests(

                request_id TEXT
                NOT NULL,

                user_id INTEGER
                NOT NULL,

                plate_id INTEGER
                NOT NULL,

                created_at INTEGER
                NOT NULL,

                PRIMARY KEY(
                    request_id,
                    user_id
                )
            );


            CREATE TABLE IF NOT EXISTS admin_logs(

                id INTEGER
                PRIMARY KEY AUTOINCREMENT,

                admin_id INTEGER
                NOT NULL,

                target_id INTEGER
                NOT NULL,

                action TEXT
                NOT NULL,

                amount INTEGER
                NOT NULL
                DEFAULT 0,

                reason TEXT
                NOT NULL
                DEFAULT '',

                created_at INTEGER
                NOT NULL
            );
            """
        )


        ensure_column(
            con,
            "users",
            "mythic_mode",
            "INTEGER NOT NULL DEFAULT 0"
        )


        ensure_column(
            con,
            "users",
            "mythic_queue",
            "INTEGER NOT NULL DEFAULT 0"
        )


        ensure_column(
            con,
            "users",
            "pending_plate_id",
            "INTEGER"
        )


        ensure_column(
            con,
            "users",
            "rescue_claimed",
            "INTEGER NOT NULL DEFAULT 0"
        )


        for col in (

            "spins",

            "listings",

            "buys",

            "sales",

            "rare_found"

        ):

            ensure_column(
                con,
                "daily_stats",
                col,
                "INTEGER NOT NULL DEFAULT 0"
            )


        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_plates_owner
            ON plates(owner_id)
            """
        )


        con.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_listings_seller
            ON listings(seller_id)
            """
        )


def utc_day():

    return time.strftime(
        "%Y-%m-%d",
        time.gmtime()
    )


def level_for_xp(
    xp
):

    xp = max(
        0,
        int(xp)
    )

    return (
        1 +
        xp // 250
    )


def tg_user(
    init_data
):

    if DEMO_MODE:

        return {

            "id":
                PRIMARY_CREATOR_ID,

            "first_name":
                "Creator",

            "username":
                "demo_creator"
        }


    if (
        not BOT_TOKEN
        or
        not init_data
    ):

        return None


    try:

        pairs = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )


        received_hash = pairs.pop(
            "hash",
            ""
        )


        if not received_hash:

            return None


        data_check_string = (
            "\n".join(

                f"{key}={pairs[key]}"

                for key
                in sorted(
                    pairs
                )
            )
        )


        secret_key = hmac.new(

            b"WebAppData",

            BOT_TOKEN.encode(),

            hashlib.sha256

        ).digest()


        calculated_hash = hmac.new(

            secret_key,

            data_check_string.encode(),

            hashlib.sha256

        ).hexdigest()


        if not hmac.compare_digest(

            calculated_hash,

            received_hash

        ):

            return None


        auth_date = int(
            pairs.get(
                "auth_date",
                "0"
            )
            or
            0
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
            ) > 86400
        ):

            return None


        user = json.loads(
            pairs.get(
                "user",
                "{}"
            )
        )


        if (
            type(
                user.get(
                    "id"
                )
            )
            is not int
        ):

            return None


        return user


    except (

        ValueError,

        TypeError,

        json.JSONDecodeError

    ):

        return None


def auth(
    fn
):

    @wraps(fn)
    def wrapped(
        *args,
        **kwargs
    ):

        user = tg_user(

            request.headers.get(

                "X-Telegram-Init-Data",

                ""
            )
        )


        if not user:

            return jsonify(

                error=(
                    "Нет авторизации Telegram. "
                    "Открой Mini App через бота "
                    "и проверь BOT_TOKEN в Render."
                )

            ), 401


        uid = int(
            user["id"]
        )


        name = str(

            user.get(
                "first_name"
            )
            or
            "Игрок"

        )[:80]


        username = str(

            user.get(
                "username"
            )
            or
            ""

        )[:80]


        now = int(
            time.time()
        )


        with db() as con:

            con.execute(
                """
                INSERT OR IGNORE
                INTO users(
                    id,
                    name,
                    username,
                    created_at
                )
                VALUES(?,?,?,?)
                """,

                (
                    uid,
                    name,
                    username,
                    now
                )
            )


            con.execute(
                """
                UPDATE users

                SET
                    name=?,
                    username=?

                WHERE id=?
                """,

                (
                    name,
                    username,
                    uid
                )
            )


        return fn(
            uid,
            *args,
            **kwargs
        )


    return wrapped


def creator_only(
    fn
):

    @wraps(fn)
    def wrapped(
        uid,
        *args,
        **kwargs
    ):

        if int(uid) not in ADMIN_TELEGRAM_IDS:

            return jsonify(
                error="Нет доступа к админ-панели"
            ), 403


        return fn(
            uid,
            *args,
            **kwargs
        )


    return wrapped


def payload():

    obj = request.get_json(
        silent=True
    )

    return (
        obj
        if isinstance(
            obj,
            dict
        )
        else
        {}
    )


def as_int(
    obj,
    *keys,
    default=None
):

    for key in keys:

        if key in obj:

            value = obj.get(
                key
            )


            if isinstance(
                value,
                bool
            ):

                raise ValueError()


            return int(
                value
            )


    if default is not None:

        return int(
            default
        )


    raise ValueError()


def touch_daily_stats(
    con,
    uid
):

    day = utc_day()


    con.execute(
        """
        INSERT OR IGNORE
        INTO daily_stats(
            user_id,
            day
        )
        VALUES(?,?)
        """,

        (
            uid,
            day
        )
    )


    return day


def add_stat(
    con,
    uid,
    field,
    amount=1
):

    if field not in {

        "spins",

        "listings",

        "buys",

        "sales",

        "rare_found"

    }:

        return


    day = touch_daily_stats(
        con,
        uid
    )


    con.execute(

        f"""
        UPDATE daily_stats

        SET {field}={field}+?

        WHERE
            user_id=?
            AND
            day=?
        """,

        (
            amount,
            uid,
            day
        )
    )


def maybe_rescue_bonus(
    con,
    uid
):

    row = con.execute(
        """
        SELECT
            balance,
            rescue_claimed

        FROM users

        WHERE id=?
        """,

        (
            uid,
        )
    ).fetchone()


    if (
        not row
        or
        int(
            row["rescue_claimed"]
        )
        or
        int(
            row["balance"]
        ) >= SPIN_COST
    ):

        return 0


    con.execute(
        """
        UPDATE users

        SET
            balance=balance+?,
            rescue_claimed=1

        WHERE id=?
        """,

        (
            RESCUE_BONUS,
            uid
        )
    )


    return RESCUE_BONUS


def pending_plate_json(
    con,
    uid,
    pending_id
):

    if not pending_id:

        return None


    row = con.execute(
        """
        SELECT
            id,
            code,
            rarity

        FROM plates

        WHERE
            id=?
            AND
            owner_id=?
        """,

        (
            pending_id,
            uid
        )
    ).fetchone()


    if not row:

        con.execute(
            """
            UPDATE users

            SET pending_plate_id=NULL

            WHERE id=?
            """,

            (
                uid,
            )
        )

        return None


    item = dict(
        row
    )


    item[
        "sell_price"
    ] = int(
        SYSTEM_SELL_PRICES.get(
            item["rarity"],
            0
        )
    )


    return item


def user_json(
    con,
    uid
):

    rescue = maybe_rescue_bonus(
        con,
        uid
    )


    user = con.execute(
        """
        SELECT *

        FROM users

        WHERE id=?
        """,

        (
            uid,
        )
    ).fetchone()


    collection = con.execute(
        """
        SELECT COUNT(*)

        FROM plates

        WHERE owner_id=?
        """,

        (
            uid,
        )
    ).fetchone()[0]


    xp = int(
        user["xp"]
    )


    return {

        "id":
            uid,

        "name":
            user["name"],

        "username":
            user["username"],

        "balance":
            int(
                user["balance"]
            ),

        "xp":
            xp,

        "level":
            level_for_xp(
                xp
            ),

        "collection":
            int(
                collection
            ),

        "unlimited_spins":
            True,

        "spin_cost":
            SPIN_COST,

        "rescue_bonus":
            rescue,

        "creator":
            uid in ADMIN_TELEGRAM_IDS,

        "mythic_mode":
            bool(
                user["mythic_mode"]
            ),

        "mythic_queue":
            int(
                user["mythic_queue"]
            ),

        "pending_plate":
            pending_plate_json(

                con,

                uid,

                user[
                    "pending_plate_id"
                ]
            ),

        "demo":
            DEMO_MODE
    }


def generate_plate(
    forced_rarity=None
):

    rng = secrets.SystemRandom()


    rarity = (
        forced_rarity

        or

        rng.choices(

            [
                x[0]
                for x
                in RARITIES
            ],

            weights=[
                x[1]
                for x
                in RARITIES
            ],

            k=1

        )[0]
    )


    a = secrets.choice(
        LETTERS
    )


    b = secrets.choice(
        LETTERS
    )


    c = secrets.choice(
        LETTERS
    )


    if rarity == "Обычный":

        digits = (
            f"{secrets.randbelow(900) + 100:03}"
        )


    elif rarity == "Необычный":

        x = secrets.choice(
            "123456789"
        )

        digits = (
            x
            +
            secrets.choice(
                "0123456789"
            )
            +
            x
        )


    elif rarity == "Редкий":

        digits = (
            secrets.choice(
                "123456789"
            )
            *
            3
        )


    elif rarity == "Эпический":

        b = c = a

        digits = (
            "00"
            +
            secrets.choice(
                "123456789"
            )
        )


    elif rarity == "Легендарный":

        b = c = a

        digits = (
            secrets.choice(
                "123456789"
            )
            *
            3
        )


    else:

        b = c = a

        digits = "777"


    return (

        f"{a}{digits}{b}{c} "
        f"{secrets.choice(REGIONS)}",

        rarity
    )


def sell_plate_system_tx(
    con,
    uid,
    plate_id,
    missing_ok=False
):

    plate = con.execute(
        """
        SELECT rarity

        FROM plates

        WHERE
            id=?
            AND
            owner_id=?
        """,

        (
            plate_id,
            uid
        )
    ).fetchone()


    if not plate:

        if missing_ok:

            return None


        raise ValueError(
            "Номер не найден"
        )


    if con.execute(
        """
        SELECT 1

        FROM listings

        WHERE plate_id=?
        """,

        (
            plate_id,
        )
    ).fetchone():

        raise ValueError(
            "Сначала сними номер с маркета"
        )


    reward = int(
        SYSTEM_SELL_PRICES.get(
            plate["rarity"],
            0
        )
    )


    if reward <= 0:

        raise ValueError(
            "Для этой редкости не настроена цена продажи"
        )


    con.execute(
        """
        DELETE FROM plates

        WHERE id=?
        """,

        (
            plate_id,
        )
    )


    con.execute(
        """
        UPDATE users

        SET balance=balance+?

        WHERE id=?
        """,

        (
            reward,
            uid
        )
    )


    con.execute(
        """
        UPDATE users

        SET pending_plate_id=NULL

        WHERE
            id=?
            AND
            pending_plate_id=?
        """,

        (
            uid,
            plate_id
        )
    )


    add_stat(
        con,
        uid,
        "sales",
        1
    )


    return {

        "plate_id":
            int(
                plate_id
            ),

        "rarity":
            plate["rarity"],

        "reward":
            reward
    }


# =========================================================
# STATIC
# =========================================================


@app.get("/")
def home():

    return send_from_directory(
        WEB_DIR,
        "index.html"
    )


@app.get("/index.html")
def index_file():

    return send_from_directory(
        WEB_DIR,
        "index.html"
    )


@app.get("/health")
def health():

    db_ok = False


    try:

        with db() as con:

            con.execute(
                "SELECT 1"
            ).fetchone()


        db_ok = True


    except sqlite3.Error:

        pass


    return jsonify(

        status="ok",

        version=APP_VERSION,

        db_ok=db_ok,

        web_index=os.path.isfile(
            os.path.join(
                WEB_DIR,
                "index.html"
            )
        ),

        bot_token_configured=bool(
            BOT_TOKEN
        ),

        spin_cost=SPIN_COST,

        unlimited_spins=True
    )


# =========================================================
# USER
# =========================================================


@app.get("/api/me")
@auth
def me(
    uid
):

    with db() as con:

        return jsonify(
            **user_json(
                con,
                uid
            )
        )


@app.get("/api/bootstrap")
@auth
def bootstrap(
    uid
):

    with db() as con:

        return jsonify(

            user=user_json(
                con,
                uid
            ),

            spin_cost=SPIN_COST,

            unlimited_spins=True,

            creator=(
                uid
                in
                ADMIN_TELEGRAM_IDS
            )
        )


@app.post("/api/keep")
@auth
def keep_plate(
    uid
):

    data = payload()


    try:

        plate_id = as_int(
            data,
            "plate_id",
            "id"
        )


    except (
        ValueError,
        TypeError
    ):

        return jsonify(
            error="Неверный ID номера"
        ), 400


    with db() as con:

        row = con.execute(
            """
            SELECT id

            FROM plates

            WHERE
                id=?
                AND
                owner_id=?
            """,

            (
                plate_id,
                uid
            )
        ).fetchone()


        if not row:

            return jsonify(
                error="Номер не найден"
            ), 404


        con.execute(
            """
            UPDATE users

            SET pending_plate_id=NULL

            WHERE
                id=?
                AND
                pending_plate_id=?
            """,

            (
                uid,
                plate_id
            )
        )


        return jsonify(

            ok=True,

            user=user_json(
                con,
                uid
            )
        )


@app.post("/api/spin")
@auth
def spin(
    uid
):

    data = payload()


    request_id = str(
        data.get(
            "request_id"
        )
        or
        ""
    ).strip()[:80]


    with db() as con:

        con.execute(
            "BEGIN IMMEDIATE"
        )


        if request_id:

            previous = con.execute(
                """
                SELECT plate_id

                FROM spin_requests

                WHERE
                    request_id=?
                    AND
                    user_id=?
                """,

                (
                    request_id,
                    uid
                )
            ).fetchone()


            if previous:

                row = con.execute(
                    """
                    SELECT
                        id,
                        code,
                        rarity

                    FROM plates

                    WHERE
                        id=?
                        AND
                        owner_id=?
                    """,

                    (
                        previous[
                            "plate_id"
                        ],

                        uid
                    )
                ).fetchone()


                if row:

                    plate = dict(
                        row
                    )


                    plate[
                        "sell_price"
                    ] = int(
                        SYSTEM_SELL_PRICES.get(
                            plate["rarity"],
                            0
                        )
                    )


                    return jsonify(

                        ok=True,

                        repeated=True,

                        plate=plate,

                        auto_sold=None,

                        spin_cost=SPIN_COST,

                        user=user_json(
                            con,
                            uid
                        )
                    )


        user = con.execute(
            """
            SELECT
                balance,
                mythic_mode,
                mythic_queue,
                pending_plate_id

            FROM users

            WHERE id=?
            """,

            (
                uid,
            )
        ).fetchone()


        if not user:

            return jsonify(
                error="Игрок не найден"
            ), 404


        auto_sold = None


        if user[
            "pending_plate_id"
        ]:

            try:

                auto_sold = (
                    sell_plate_system_tx(

                        con,

                        uid,

                        int(
                            user[
                                "pending_plate_id"
                            ]
                        ),

                        missing_ok=True
                    )
                )


            except ValueError as exc:

                return jsonify(
                    error=str(exc)
                ), 400


        maybe_rescue_bonus(
            con,
            uid
        )


        user = con.execute(
            """
            SELECT
                balance,
                mythic_mode,
                mythic_queue

            FROM users

            WHERE id=?
            """,

            (
                uid,
            )
        ).fetchone()


        if int(
            user["balance"]
        ) < SPIN_COST:

            return jsonify(

                error=(
                    f"Недостаточно NC. "
                    f"Одна прокрутка стоит "
                    f"{SPIN_COST} NC"
                )

            ), 400


        force_mythic = (

            bool(
                user[
                    "mythic_mode"
                ]
            )

            or

            int(
                user[
                    "mythic_queue"
                ]
            ) > 0
        )


        forced_rarity = (

            "Мифический"

            if force_mythic

            else None
        )


        plate = None


        for _ in range(
            400
        ):

            code, rarity = generate_plate(
                forced_rarity
            )


            try:

                cur = con.execute(
                    """
                    INSERT INTO plates(
                        code,
                        rarity,
                        owner_id,
                        created_at
                    )
                    VALUES(?,?,?,?)
                    """,

                    (
                        code,
                        rarity,
                        uid,
                        int(
                            time.time()
                        )
                    )
                )


                plate = {

                    "id":
                        cur.lastrowid,

                    "code":
                        code,

                    "rarity":
                        rarity,

                    "sell_price":
                        int(
                            SYSTEM_SELL_PRICES.get(
                                rarity,
                                0
                            )
                        )
                }


                break


            except sqlite3.IntegrityError:

                continue


        if plate is None:

            return jsonify(
                error=(
                    "Не удалось создать свободный номер. "
                    "Попробуй ещё раз."
                )
            ), 503


        con.execute(
            """
            UPDATE users

            SET
                balance=balance-?,
                xp=xp+10,
                pending_plate_id=?

            WHERE id=?
            """,

            (
                SPIN_COST,
                plate["id"],
                uid
            )
        )


        if (
            not bool(
                user["mythic_mode"]
            )
            and
            int(
                user["mythic_queue"]
            ) > 0
        ):

            con.execute(
                """
                UPDATE users

                SET
                    mythic_queue=
                    mythic_queue-1

                WHERE id=?
                """,

                (
                    uid,
                )
            )


        if request_id:

            con.execute(
                """
                INSERT OR IGNORE
                INTO spin_requests(
                    request_id,
                    user_id,
                    plate_id,
                    created_at
                )
                VALUES(?,?,?,?)
                """,

                (
                    request_id,
                    uid,
                    plate["id"],
                    int(
                        time.time()
                    )
                )
            )


        con.execute(
            """
            DELETE FROM spin_requests

            WHERE created_at<?
            """,

            (
                int(
                    time.time()
                )
                -
                86400 * 7,
            )
        )


        add_stat(
            con,
            uid,
            "spins",
            1
        )


        if (
            RARITY_ORDER.get(
                plate["rarity"],
                0
            )
            >=
            RARITY_ORDER[
                "Редкий"
            ]
        ):

            add_stat(
                con,
                uid,
                "rare_found",
                1
            )


        return jsonify(

            ok=True,

            plate=plate,

            auto_sold=auto_sold,

            spin_cost=SPIN_COST,

            unlimited_spins=True,

            user=user_json(
                con,
                uid
            )
        )


@app.post("/api/sell-system")
@auth
def sell_system(
    uid
):

    try:

        plate_id = as_int(
            payload(),
            "plate_id",
            "id"
        )


    except (
        ValueError,
        TypeError
    ):

        return jsonify(
            error="Неверный ID номера"
        ), 400


    with db() as con:

        con.execute(
            "BEGIN IMMEDIATE"
        )


        try:

            sold = sell_plate_system_tx(
                con,
                uid,
                plate_id
            )


        except ValueError as exc:

            return jsonify(
                error=str(exc)
            ), 400


        return jsonify(

            ok=True,

            reward=sold[
                "reward"
            ],

            sold=sold,

            user=user_json(
                con,
                uid
            )
        )


# =========================================================
# COLLECTION
# =========================================================


@app.get("/api/collection")
@auth
def collection(
    uid
):

    with db() as con:

        rows = con.execute(
            """
            SELECT
                p.id,
                p.code,
                p.rarity,
                p.created_at,
                l.id AS listing_id

            FROM plates p

            LEFT JOIN listings l
            ON l.plate_id=p.id

            WHERE p.owner_id=?

            ORDER BY p.id DESC

            LIMIT 1000
            """,

            (
                uid,
            )
        ).fetchall()


        plates = []


        for row in rows:

            item = dict(
                row
            )


            item[
                "sell_price"
            ] = int(
                SYSTEM_SELL_PRICES.get(
                    item["rarity"],
                    0
                )
            )


            plates.append(
                item
            )


        return jsonify(
            plates=plates
        )


# =========================================================
# MARKET
# =========================================================


@app.get("/api/market")
@auth
def market(
    uid
):

    with db() as con:

        rows = con.execute(
            """
            SELECT
                l.id,
                l.plate_id,
                l.seller_id,
                l.price,
                l.created_at,

                p.code,
                p.rarity,

                u.name AS seller,
                u.username AS seller_username

            FROM listings l

            JOIN plates p
            ON p.id=l.plate_id

            JOIN users u
            ON u.id=l.seller_id

            ORDER BY l.id DESC

            LIMIT 250
            """
        ).fetchall()


        return jsonify(
            listings=[
                dict(x)
                for x
                in rows
            ]
        )


@app.post("/api/list")
@auth
def create_listing(
    uid
):

    data = payload()


    try:

        plate_id = as_int(
            data,
            "plate_id",
            "id"
        )


        price = as_int(
            data,
            "price"
        )


    except (
        ValueError,
        TypeError
    ):

        return jsonify(
            error="Некорректные данные"
        ), 400


    if not (
        100
        <=
        price
        <=
        100_000_000
    ):

        return jsonify(
            error=(
                "Цена должна быть "
                "от 100 до 100000000 NC"
            )
        ), 400


    with db() as con:

        con.execute(
            "BEGIN IMMEDIATE"
        )


        plate = con.execute(
            """
            SELECT id

            FROM plates

            WHERE
                id=?
                AND
                owner_id=?
            """,

            (
                plate_id,
                uid
            )
        ).fetchone()


        if not plate:

            return jsonify(
                error="Номер не найден"
            ), 404


        if con.execute(
            """
            SELECT 1

            FROM listings

            WHERE plate_id=?
            """,

            (
                plate_id,
            )
        ).fetchone():

            return jsonify(
                error="Номер уже выставлен"
            ), 400


        active = con.execute(
            """
            SELECT COUNT(*)

            FROM listings

            WHERE seller_id=?
            """,

            (
                uid,
            )
        ).fetchone()[0]


        if int(
            active
        ) >= MAX_ACTIVE_LISTINGS:

            return jsonify(

                error=(
                    f"Можно иметь максимум "
                    f"{MAX_ACTIVE_LISTINGS} "
                    f"активных объявления"
                )

            ), 400


        con.execute(
            """
            INSERT INTO listings(
                plate_id,
                seller_id,
                price,
                created_at
            )
            VALUES(?,?,?,?)
            """,

            (
                plate_id,
                uid,
                price,
                int(
                    time.time()
                )
            )
        )


        con.execute(
            """
            UPDATE users

            SET pending_plate_id=NULL

            WHERE
                id=?
                AND
                pending_plate_id=?
            """,

            (
                uid,
                plate_id
            )
        )


        add_stat(
            con,
            uid,
            "listings",
            1
        )


        return jsonify(
            ok=True
        )


@app.post("/api/cancel")
@auth
def cancel_listing(
    uid
):

    try:

        listing_id = as_int(
            payload(),
            "listing_id",
            "id"
        )


    except (
        ValueError,
        TypeError
    ):

        return jsonify(
            error="Неверный ID объявления"
        ), 400


    with db() as con:

        cur = con.execute(
            """
            DELETE FROM listings

            WHERE
                id=?
                AND
                seller_id=?
            """,

            (
                listing_id,
                uid
            )
        )


        if cur.rowcount != 1:

            return jsonify(
                error="Объявление не найдено"
            ), 404


        return jsonify(
            ok=True
        )


@app.post("/api/buy")
@auth
def buy_listing(
    uid
):

    try:

        listing_id = as_int(
            payload(),
            "listing_id",
            "id"
        )


    except (
        ValueError,
        TypeError
    ):

        return jsonify(
            error="Неверный ID объявления"
        ), 400


    with db() as con:

        con.execute(
            "BEGIN IMMEDIATE"
        )


        listing = con.execute(
            """
            SELECT *

            FROM listings

            WHERE id=?
            """,

            (
                listing_id,
            )
        ).fetchone()


        if not listing:

            return jsonify(
                error="Объявление уже недоступно"
            ), 404


        if int(
            listing["seller_id"]
        ) == uid:

            return jsonify(
                error="Нельзя купить свой номер"
            ), 400


        buyer = con.execute(
            """
            SELECT balance

            FROM users

            WHERE id=?
            """,

            (
                uid,
            )
        ).fetchone()


        price = int(
            listing["price"]
        )


        if int(
            buyer["balance"]
        ) < price:

            return jsonify(
                error="Недостаточно NC"
            ), 400


        plate = con.execute(
            """
            SELECT owner_id

            FROM plates

            WHERE id=?
            """,

            (
                listing[
                    "plate_id"
                ],
            )
        ).fetchone()


        if (
            not plate
            or
            int(
                plate["owner_id"]
            )
            !=
            int(
                listing[
                    "seller_id"
                ]
            )
        ):

            con.execute(
                """
                DELETE FROM listings

                WHERE id=?
                """,

                (
                    listing_id,
                )
            )


            return jsonify(
                error="Номер уже недоступен"
            ), 409


        fee = (

            price
            *
            MARKET_FEE_PERCENT
            +
            99

        ) // 100


        seller_gets = (
            price
            -
            fee
        )


        con.execute(
            """
            UPDATE users

            SET balance=balance-?

            WHERE id=?
            """,

            (
                price,
                uid
            )
        )


        con.execute(
            """
            UPDATE users

            SET balance=balance+?

            WHERE id=?
            """,

            (
                seller_gets,
                listing[
                    "seller_id"
                ]
            )
        )


        con.execute(
            """
            UPDATE plates

            SET owner_id=?

            WHERE id=?
            """,

            (
                uid,
                listing[
                    "plate_id"
                ]
            )
        )


        con.execute(
            """
            DELETE FROM listings

            WHERE id=?
            """,

            (
                listing_id,
            )
        )


        add_stat(
            con,
            uid,
            "buys",
            1
        )


        return jsonify(

            ok=True,

            user=user_json(
                con,
                uid
            )
        )


# =========================================================
# TASKS
# =========================================================


@app.get("/api/tasks")
@auth
def tasks(
    uid
):

    with db() as con:

        day = touch_daily_stats(
            con,
            uid
        )


        stats = con.execute(
            """
            SELECT *

            FROM daily_stats

            WHERE
                user_id=?
                AND
                day=?
            """,

            (
                uid,
                day
            )
        ).fetchone()


        claimed = {

            row["task_key"]

            for row
            in con.execute(
                """
                SELECT task_key

                FROM task_claims

                WHERE
                    user_id=?
                    AND
                    day=?
                """,

                (
                    uid,
                    day
                )
            ).fetchall()
        }


        result = []


        for task in TASKS:

            progress = (

                int(
                    stats[
                        task[
                            "stat"
                        ]
                    ]
                )

                if stats

                else 0
            )


            result.append({

                **task,

                "progress":
                    progress,

                "completed":
                    (
                        progress
                        >=
                        int(
                            task[
                                "target"
                            ]
                        )
                    ),

                "claimed":
                    (
                        task["key"]
                        in
                        claimed
                    )
            })


        return jsonify(

            day=day,

            tasks=result
        )


@app.post("/api/tasks/claim")
@auth
def claim_task(
    uid
):

    data = payload()


    key = str(
        data.get(
            "task_key"
        )
        or
        data.get(
            "key"
        )
        or
        ""
    )


    task = TASK_BY_KEY.get(
        key
    )


    if not task:

        return jsonify(
            error="Задание не найдено"
        ), 404


    with db() as con:

        con.execute(
            "BEGIN IMMEDIATE"
        )


        day = touch_daily_stats(
            con,
            uid
        )


        stats = con.execute(
            """
            SELECT *

            FROM daily_stats

            WHERE
                user_id=?
                AND
                day=?
            """,

            (
                uid,
                day
            )
        ).fetchone()


        progress = (

            int(
                stats[
                    task["stat"]
                ]
            )

            if stats

            else 0
        )


        if progress < int(
            task["target"]
        ):

            return jsonify(
                error="Задание ещё не выполнено"
            ), 400


        if con.execute(
            """
            SELECT 1

            FROM task_claims

            WHERE
                user_id=?
                AND
                day=?
                AND
                task_key=?
            """,

            (
                uid,
                day,
                key
            )
        ).fetchone():

            return jsonify(
                error="Награда уже получена"
            ), 400


        con.execute(
            """
            INSERT INTO task_claims(
                user_id,
                day,
                task_key,
                claimed_at
            )
            VALUES(?,?,?,?)
            """,

            (
                uid,
                day,
                key,
                int(
                    time.time()
                )
            )
        )


        con.execute(
            """
            UPDATE users

            SET
                balance=balance+?,
                xp=xp+?

            WHERE id=?
            """,

            (
                task[
                    "reward_nc"
                ],

                task[
                    "reward_xp"
                ],

                uid
            )
        )


        return jsonify(

            ok=True,

            reward_nc=task[
                "reward_nc"
            ],

            reward_xp=task[
                "reward_xp"
            ],

            user=user_json(
                con,
                uid
            )
        )


@app.get("/api/achievements")
@auth
def achievements(
    uid
):

    with db() as con:

        user = user_json(
            con,
            uid
        )


        result = []


        for item in ACHIEVEMENTS:

            progress = int(
                user[
                    item[
                        "field"
                    ]
                ]
            )


            result.append({

                **item,

                "progress":
                    progress,

                "completed":
                    (
                        progress
                        >=
                        int(
                            item[
                                "target"
                            ]
                        )
                    )
            })


        return jsonify(
            achievements=result
        )


@app.get("/api/top")
@auth
def top(
    uid
):

    with db() as con:

        rows = con.execute(
            """
            SELECT
                u.id,
                u.name,
                u.username,
                u.balance,
                u.xp,
                COUNT(p.id)
                AS collection

            FROM users u

            LEFT JOIN plates p
            ON p.owner_id=u.id

            GROUP BY u.id

            ORDER BY
                u.balance DESC,
                collection DESC,
                u.xp DESC

            LIMIT 50
            """
        ).fetchall()


        players = []


        for row in rows:

            item = dict(
                row
            )


            item[
                "level"
            ] = level_for_xp(
                item["xp"]
            )


            item[
                "creator"
            ] = (
                int(
                    item["id"]
                )
                in
                ADMIN_TELEGRAM_IDS
            )


            players.append(
                item
            )


        return jsonify(
            players=players
        )


# =========================================================
# ADMIN
# =========================================================


@app.get("/api/admin/stats")
@auth
@creator_only
def admin_stats(
    uid
):

    with db() as con:

        return jsonify(

            users=con.execute(
                """
                SELECT COUNT(*)
                FROM users
                """
            ).fetchone()[0],

            plates=con.execute(
                """
                SELECT COUNT(*)
                FROM plates
                """
            ).fetchone()[0],

            listings=con.execute(
                """
                SELECT COUNT(*)
                FROM listings
                """
            ).fetchone()[0],

            mythic=con.execute(
                """
                SELECT COUNT(*)

                FROM plates

                WHERE rarity='Мифический'
                """
            ).fetchone()[0]
        )


@app.get("/api/admin/players")
@auth
@creator_only
def admin_players(
    uid
):

    query = str(
        request.args.get(
            "q"
        )
        or
        ""
    ).strip().lower()


    params = []

    where = ""


    if query:

        where = (
            "WHERE "
            "CAST(u.id AS TEXT) LIKE ? "
            "OR LOWER(u.name) LIKE ? "
            "OR LOWER(u.username) LIKE ?"
        )


        like = (
            f"%{query}%"
        )


        params = [
            like,
            like,
            like
        ]


    with db() as con:

        rows = con.execute(
            f"""
            SELECT
                u.id,
                u.name,
                u.username,
                u.balance,
                u.xp,
                u.mythic_mode,
                u.mythic_queue,

                COUNT(p.id)
                AS collection

            FROM users u

            LEFT JOIN plates p
            ON p.owner_id=u.id

            {where}

            GROUP BY u.id

            ORDER BY u.id DESC

            LIMIT 200
            """,

            params
        ).fetchall()


        players = []


        for row in rows:

            item = dict(
                row
            )


            item[
                "level"
            ] = level_for_xp(
                item["xp"]
            )


            item[
                "creator"
            ] = (
                int(
                    item["id"]
                )
                in
                ADMIN_TELEGRAM_IDS
            )


            item[
                "mythic_mode"
            ] = bool(
                item[
                    "mythic_mode"
                ]
            )


            players.append(
                item
            )


        return jsonify(
            players=players
        )


@app.post("/api/admin/grant")
@auth
@creator_only
def admin_grant(
    uid
):

    data = payload()


    try:

        target_id = as_int(
            data,
            "user_id",
            "target_id",
            "id"
        )


        nc = int(
            data.get(
                "nc",
                0
            )
            or
            0
        )


        xp = int(
            data.get(
                "xp",
                0
            )
            or
            0
        )


    except (
        ValueError,
        TypeError
    ):

        return jsonify(
            error="Некорректные данные"
        ), 400


    if (
        nc == 0
        and
        xp == 0
    ):

        return jsonify(
            error="Укажи NC или XP"
        ), 400


    if (
        abs(nc)
        >
        100_000_000

        or

        abs(xp)
        >
        10_000_000
    ):

        return jsonify(
            error="Слишком большое значение"
        ), 400


    reason = str(
        data.get(
            "reason"
        )
        or
        "Админ-панель"
    )[:200]


    with db() as con:

        con.execute(
            "BEGIN IMMEDIATE"
        )


        target = con.execute(
            """
            SELECT
                balance,
                xp

            FROM users

            WHERE id=?
            """,

            (
                target_id,
            )
        ).fetchone()


        if not target:

            return jsonify(
                error="Игрок не найден"
            ), 404


        if (
            int(
                target["balance"]
            )
            +
            nc
            <
            0

            or

            int(
                target["xp"]
            )
            +
            xp
            <
            0
        ):

            return jsonify(
                error=(
                    "Баланс или XP "
                    "не могут стать отрицательными"
                )
            ), 400


        con.execute(
            """
            UPDATE users

            SET
                balance=balance+?,
                xp=xp+?

            WHERE id=?
            """,

            (
                nc,
                xp,
                target_id
            )
        )


        if nc:

            con.execute(
                """
                INSERT INTO admin_logs(
                    admin_id,
                    target_id,
                    action,
                    amount,
                    reason,
                    created_at
                )
                VALUES(?,?,?,?,?,?)
                """,

                (
                    uid,
                    target_id,
                    "nc",
                    nc,
                    reason,
                    int(
                        time.time()
                    )
                )
            )


        if xp:

            con.execute(
                """
                INSERT INTO admin_logs(
                    admin_id,
                    target_id,
                    action,
                    amount,
                    reason,
                    created_at
                )
                VALUES(?,?,?,?,?,?)
                """,

                (
                    uid,
                    target_id,
                    "xp",
                    xp,
                    reason,
                    int(
                        time.time()
                    )
                )
            )


        return jsonify(

            ok=True,

            target=user_json(
                con,
                target_id
            )
        )


@app.post("/api/admin/mythic")
@auth
@creator_only
def admin_mythic(
    uid
):

    data = payload()


    try:

        target_id = as_int(
            data,
            "user_id",
            "target_id",
            "id"
        )


    except (
        ValueError,
        TypeError
    ):

        return jsonify(
            error="Не выбран игрок"
        ), 400


    mode = str(
        data.get(
            "mode"
        )
        or
        "queue"
    ).lower()


    with db() as con:

        con.execute(
            "BEGIN IMMEDIATE"
        )


        if not con.execute(
            """
            SELECT 1

            FROM users

            WHERE id=?
            """,

            (
                target_id,
            )
        ).fetchone():

            return jsonify(
                error="Игрок не найден"
            ), 404


        if mode in (
            "on",
            "enable",
            "always"
        ):

            con.execute(
                """
                UPDATE users

                SET mythic_mode=1

                WHERE id=?
                """,

                (
                    target_id,
                )
            )


            action = (
                "mythic_mode_on"
            )

            amount = 1


        elif mode in (
            "off",
            "disable"
        ):

            con.execute(
                """
                UPDATE users

                SET mythic_mode=0

                WHERE id=?
                """,

                (
                    target_id,
                )
            )


            action = (
                "mythic_mode_off"
            )

            amount = 0


        elif mode in (
            "clear",
            "reset",
            "clear_queue",
            "queue_off"
        ):

            con.execute(
                """
                UPDATE users

                SET mythic_queue=0

                WHERE id=?
                """,

                (
                    target_id,
                )
            )


            action = (
                "mythic_queue_clear"
            )

            amount = 0


        elif mode in (
            "all_off",
            "disable_all"
        ):

            con.execute(
                """
                UPDATE users

                SET
                    mythic_mode=0,
                    mythic_queue=0

                WHERE id=?
                """,

                (
                    target_id,
                )
            )


            action = (
                "mythic_all_off"
            )

            amount = 0


        else:

            try:

                count = int(
                    data.get(
                        "count",
                        1
                    )
                )


            except (
                ValueError,
                TypeError
            ):

                return jsonify(
                    error="Некорректное количество"
                ), 400


            if not (
                1
                <=
                count
                <=
                100
            ):

                return jsonify(
                    error=(
                        "Можно добавить "
                        "от 1 до 100 "
                        "гарантированных мификов"
                    )
                ), 400


            con.execute(
                """
                UPDATE users

                SET
                    mythic_queue=
                    mythic_queue+?

                WHERE id=?
                """,

                (
                    count,
                    target_id
                )
            )


            action = (
                "mythic_queue"
            )

            amount = count


        con.execute(
            """
            INSERT INTO admin_logs(
                admin_id,
                target_id,
                action,
                amount,
                reason,
                created_at
            )
            VALUES(?,?,?,?,?,?)
            """,

            (
                uid,
                target_id,
                action,
                amount,
                "Управление мифическим дропом",
                int(
                    time.time()
                )
            )
        )


        return jsonify(

            ok=True,

            target=user_json(
                con,
                target_id
            )
        )


@app.errorhandler(
    sqlite3.Error
)
def sqlite_error(
    error
):

    app.logger.exception(
        "SQLite error: %s",
        error
    )


    return jsonify(
        error=(
            "Ошибка базы данных. "
            "Попробуй ещё раз."
        )
    ), 500


@app.errorhandler(
    Exception
)
def unhandled_error(
    error
):

    if isinstance(
        error,
        HTTPException
    ):

        return jsonify(
            error=error.description
        ), error.code


    app.logger.exception(
        "Unhandled error: %s",
        error
    )


    return jsonify(
        error="Внутренняя ошибка сервера"
    ), 500


init_db()


if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        )
    )
