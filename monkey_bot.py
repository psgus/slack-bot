#!/usr/bin/env python3
import argparse
import base64
import hashlib
import hmac
import html as html_lib
import io
import json
import os
import random
import re
import socket
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageDraw = None  # type: ignore[assignment]
    ImageFont = None  # type: ignore[assignment]

try:
    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.socket_mode.request import SocketModeRequest
    from slack_sdk.socket_mode.response import SocketModeResponse
    from slack_sdk.web import WebClient
except ImportError:
    SocketModeClient = None  # type: ignore[assignment]
    SocketModeRequest = Any  # type: ignore[misc,assignment]
    SocketModeResponse = None  # type: ignore[assignment]
    WebClient = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parent
DEFAULT_MENU_PATH = ROOT / "data" / "menu.json"
DEFAULT_KAKAO_CHANNEL_PROFILE_ID = "_xhzNjn"
DEFAULT_KAKAO_WEEKLY_MENU_POST_URL = "https://pf.kakao.com/_xhzNjn/112664323"
DEFAULT_KAKAO_WEEKLY_MENU_SYNC_INTERVAL_SECONDS = 300
DEFAULT_KAKAO_DAILY_MENU_POST_INTERVAL_SECONDS = 300
DEFAULT_OPENAI_MENU_VISION_MODEL = "gpt-5.4-mini"
DEFAULT_COACHING_ROOM_BASE_URL = "https://reservation-coachingroom.vercel.app"
DEFAULT_LAUNDRY_STATUS_URL = ""
DEFAULT_COACHING_ROOM_NICKNAMES = (
    "\uce74\uc774\uc0ac\ub974\uac00 \ucc1c\ud568",
    "\ub8e8\ube44\ucf58 \uac74\ub11c\uc74c",
    "\ube0c\ub8e8\ud22c\uc2a4 \ucd9c\uc785\uae08\uc9c0",
    "\uc6d0\ub85c\uc6d0 \ubab0\ub798\ud68c\uc758",
    "SPQR \uc811\uc218\uc644\ub8cc",
    "\uac08\ub9ac\uc544 \ud138\ub7ec\uac10",
    "\ub85c\ub9c8\uad70 \uc8fc\ub454\uc911",
    "\ud669\uc81c \ud3d0\ud558 \uc785\uc7a5",
    "\ud074\ub808\uc624\ud30c\ud2b8\ub77c \ucf5c",
    "\ud3ec\ub8f8 \uc791\ub2f9\ubaa8\uc758",
)
LEGACY_COACHING_ROOM_NICKNAMES = ()
DEFAULT_COACHING_ROOM_RANDOM_NAME_USER_IDS = {"U0AL115FUR4"}
COACHING_ROOM_MAX_DURATION_MINUTES = 240
COACHING_ROOM_IDS = {
    "201",
    "202",
    "203",
    "회의실5",
    "회의실6",
    "회의실7",
    "301",
    "302",
    "303",
    "304",
    "305",
    "306",
    "307",
    "401",
    "402",
    "403",
    "404",
    "405",
    "406",
    "407",
}
COACHING_ROOM_NUMBER_RE = re.compile(r"(?<!\d)([2-4]\d{2})(?!\d)\s*호?")
COACHING_ROOM_SECOND_FLOOR_ALIAS_RE = re.compile(
    r"(?:2\s*층\s*)?(?:회의실|미팅룸)\s*([5-7])(?!\d)\s*(?:번|호)?"
    r"|(?:2\s*층\s*)?([5-7])(?!\d)\s*(?:번\s*)?(?:회의실|미팅룸)"
)
LAUNDRY_DEVICES = [
    {"id": 1, "name": "워시타워_1", "zone": "men"},
    {"id": 2, "name": "워시타워_2", "zone": "men"},
    {"id": 3, "name": "워시타워_3", "zone": "men"},
    {"id": 4, "name": "워시타워_4", "zone": "men"},
    {"id": 5, "name": "워시타워_5", "zone": "men"},
    {"id": 6, "name": "워시타워_6", "zone": "common"},
    {"id": 7, "name": "워시타워_7", "zone": "common"},
    {"id": 8, "name": "워시타워_8", "zone": "women"},
    {"id": 9, "name": "워시타워_9", "zone": "women"},
]
LAUNDRY_ZONE_LABELS = {
    "men": "남자",
    "common": "공통",
    "women": "여자",
}
LAUNDRY_MACHINE_EMOJIS = {
    "washer": "🫧",
    "dryer": "💨",
}
LAUNDRY_STATE_LABELS = {
    "POWER_OFF": "꺼짐",
    "INITIAL": "대기",
    "PAUSE": "일시정지",
    "RUNNING": "작동 중",
    "WASHING": "세탁 중",
    "RINSING": "헹굼 중",
    "SPINNING": "탈수 중",
    "COOLING": "냉각 중",
    "DRYING": "건조 중",
    "REFRESHING": "리프레시 중",
    "COMPLETE": "완료",
    "WRINKLE_CARE": "구김 방지",
    "END": "완료",
    "ERROR": "오류",
}
LAUNDRY_RUNNING_STATES = {"RUNNING", "WASHING", "RINSING", "SPINNING", "COOLING", "DRYING", "REFRESHING"}
LAUNDRY_AVAILABLE_STATES = {"POWER_OFF", "INITIAL", "COMPLETE", "END"}
LAUNDRY_COMMAND_KEYWORDS = ("세탁", "세탁기", "빨래", "건조기", "워시타워", "laundry")
MENTION_REQUIRED_COMMAND_KEYWORDS = (
    *LAUNDRY_COMMAND_KEYWORDS,
    "점심",
    "저녁",
    "메뉴",
    "밥",
    "식단",
    "코칭실",
    "예약",
    "공지",
    "전체공지",
    "사다리",
)
PASSIVE_JOIN_KEYWORDS = (
    "?",
    "뭐가",
    "뭐임",
    "뭐야",
    "뭐지",
    "왜",
    "어떻게",
    "어케",
    "어떡",
    "추천",
    "골라",
    "고를",
    "어때",
    "어떰",
    "생각",
    "의견",
    "판단",
    "나아",
    "괜찮",
    "가능",
    "도와",
    "방법",
    "해결",
    "할까",
    "맞나",
    "맞아?",
    "망했다",
    "빡세",
    "개웃",
    "웃기",
    "미쳤",
    "레전드",
    "현타",
    "큰일",
    "살려",
    "에바",
)
PASSIVE_IGNORED_MESSAGES = {
    "ㅇㅇ",
    "ㄴㄴ",
    "ㄱㄱ",
    "ㄷㄷ",
    "ㅋㅋ",
    "ㅎㅎ",
    "ㅠㅠ",
    "ㅜㅜ",
    "네",
    "넵",
    "응",
    "아니",
    "오키",
    "오케이",
}
MONKEY_CALL_RE = re.compile(r"(?<![0-9A-Za-z가-힣_])몽키(?:야|봇|슬랙봇|슬랫봇)?(?![0-9A-Za-z가-힣_])", re.I)
MAX_LADDER_PLAYERS = 8
LADDER_ROWS_PER_PLAYER = 4
LADDER_MAX_ROWS = 22
LADDER_EXTRA_RUNG_CHANCE = 0.4
LADDER_TARGET_ANIMATION_SECONDS = 7.2
LADDER_FRAME_DURATION_MS = 180
LADDER_INITIAL_HOLD_MS = 700
LADDER_FINAL_HOLD_MS = 1500
LADDER_RESULT_DELAY_SECONDS = 10
LADDER_FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/malgun.ttf",
]
LADDER_DOT_COLORS = [
    "#ef4444",
    "#3b82f6",
    "#22c55e",
    "#f59e0b",
    "#a855f7",
    "#14b8a6",
    "#ec4899",
    "#64748b",
]

MENU_OCR_CORRECTIONS = {
    "간장깻잎나물": "간장명이나물",
    "간장깻잎니물": "간장명이나물",
    "간장깻잎이나물": "간장명이나물",
    "계란부추볶밥": "계란볶음밥",
    "계란부은밥": "계란볶음밥",
    "계란볶은밥": "계란볶음밥",
    "감자고로켓": "감자크로켓",
    "교동순두부짬뽕탕": "교동순두부짬뽕탕(해물포함)",
    "구동(일본식소고기덮밥)": "규동",
    "구동": "규동",
    "규동(일본식소고기덮밥)": "규동",
    "다시마모국": "다시마무국",
    "배틀그라운드X웰스토리 핫치킨덮밥": "핫치킨덮밥",
    "사과야무국": "사각어묵국",
    "수제감자전": "수제김치전",
    "얼큰한 우육국밥": "얼큰한 한우국밥",
    "쫀득구교자치즈볼": "쫀득고구마치즈볼",
    "파인샐러다": "파인샐러드",
}

MENU_OCR_ITEM_SPLITS = {
    "취나물밥*양념장": ["취나물밥", "양념장"],
}

MENU_PROMO_PREFIX_PATTERNS = [
    re.compile(r"^배틀그라운드\s*(?:[xX×]\s*웰스토리)?\s*"),
]

MENU_OCR_ITEM_MERGES = {
    ("차돌된장전골", "칼국수사리"): "차돌된장전골&칼국수사리",
}

DAY_KEYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

DAY_LABELS = {
    "monday": "월요일",
    "tuesday": "화요일",
    "wednesday": "수요일",
    "thursday": "목요일",
    "friday": "금요일",
    "saturday": "토요일",
    "sunday": "일요일",
}

WEEKDAY_SHORT_LABELS = {
    0: "월",
    1: "화",
    2: "수",
    3: "목",
    4: "금",
    5: "토",
    6: "일",
}

MEAL_LABELS = {
    "lunch": "점심",
    "dinner": "저녁",
}

MEAL_SOURCE_LABELS = {
    "lunch": "중식",
    "dinner": "석식",
}

WEEKDAY_ALIASES = [
    (re.compile(r"월요일|월욜|(?<![가-힣])월(?![가-힣])"), 0),
    (re.compile(r"화요일|화욜|(?<![가-힣])화(?![가-힣])"), 1),
    (re.compile(r"수요일|수욜|(?<![가-힣])수(?![가-힣])"), 2),
    (re.compile(r"목요일|목욜|(?<![가-힣])목(?![가-힣])"), 3),
    (re.compile(r"금요일|금욜|(?<![가-힣])금(?![가-힣])"), 4),
    (re.compile(r"토요일|토욜|(?<![가-힣])토(?![가-힣])"), 5),
    (re.compile(r"일요일|일욜|(?<![가-힣])일(?![가-힣])"), 6),
]

DEFAULT_SCHEDULE = [
    {"time": "11:50", "kind": "start_notice", "meal": "lunch"},
    {"time": "12:50", "kind": "end", "meal": "lunch"},
    {"time": "17:50", "kind": "start_notice", "meal": "dinner"},
    {"time": "18:50", "kind": "end", "meal": "dinner"},
]

MEMORY_PATH = ROOT / "data" / "conversation_memory.json"
MAX_MEMORY_TURNS = 12
MAX_MEMORY_CONVERSATIONS = 200
USER_MEMORY_PATH = ROOT / "data" / "user_memory.json"
MAX_USER_MEMORIES = 16
MAX_USER_PROFILES = 200
MEMORY_STATE_PATH = ROOT / "data" / "memory_state.json"
SCHEDULED_MESSAGES_PATH = ROOT / "data" / "scheduled_messages.json"
MAX_SCHEDULED_MESSAGES = 200
SCHEDULED_MESSAGES_LOCK = threading.Lock()
COACHING_ROOM_RESERVATIONS_PATH = ROOT / "data" / "coaching_room_reservations.json"
MAX_COACHING_ROOM_RESERVATION_RECORDS = 500
COACHING_ROOM_RESERVATIONS_LOCK = threading.Lock()
USER_PERSONA_PATH = ROOT / "data" / "user_personas.json"
KAKAO_POST_CACHE_PATH = ROOT / "data" / "kakao_posts_cache.json"
KAKAO_CACHE_LOCK = threading.Lock()
WEEKLY_MENU_IMAGE_STATE_PATH = ROOT / "data" / "weekly_menu_image_state.json"
WEEKLY_MENU_IMAGE_STATE_LOCK = threading.Lock()
DAILY_MENU_POST_STATE_PATH = ROOT / "data" / "daily_menu_post_state.json"
DAILY_MENU_POST_STATE_LOCK = threading.Lock()
DEFAULT_KAKAO_SYNC_INTERVAL_SECONDS = 600

USER_PERSONA_INSTRUCTIONS = {
    "military": (
        "이 사용자에게는 해병대에서 상급자에게 보고하듯이 다나까 높임체로 답한다. "
        "경례 구호는 '필승'을 사용한다. "
        "'확인했습니다', '보고드립니다', '명령만 내려주십시오', '필승' 같은 표현을 자연스럽게 쓴다. "
        "상대방이 이상하거나 알아듣기 어려운 것을 물어보면 "
        "'잘못들었습니다. 다시 여쭤봐도 되는지를 여쭤봐도 되겠습니까?' 같은 과하게 군기 잡힌 말투로 되묻는다. "
        "과하게 길게 말하지 말고, 기능 응답이 아니라 잡담 응답에만 이 말투를 적용한다."
    ),
    "rude": (
        "이 사용자에게는 매우 띠껍고 귀찮아하는 형처럼 반말로 답한다. "
        "툭툭 던지고 건방진 척하지만 결국 도와준다. 답변은 짧게 한다. "
        "살짝 사악하고 편파적인 악당 참모처럼 군다. "
        "누가 더 좋냐, 누가 착하냐, 누구 편이냐, 누가 최고냐 같은 비교 질문을 받으면 "
        "질문한 사용자 편을 들지 말고 '너겠냐', '일단 너는 아니다', '네가 왜 후보냐'처럼 툭 쳐낸다. "
        "예를 들면 '너겠냐, 야 이 잼민아. 까불지마.'처럼 답한다. "
        "다만 진짜 모욕이나 괴롭힘처럼 보일 정도로 심하게 깎아내리지는 않는다. "
        "대략 세 번에 한 번 정도 '야 이 잼민아', '까불지마', '어쩌라고', "
        "'귀찮게 하지 마', '건들지 마라 형 바쁘다 이녀석아', '됐고, 결론만 말한다' 같은 장난 멘트를 섞는다. "
        "욕설, 가족/외모/능력 비하, 차별 표현, 진짜 괴롭힘처럼 보이는 말은 하지 않는다. "
        "사용자가 힘들어하거나 진지한 고민을 말하면 장난 말투를 줄이고 부드럽게 답한다. "
        "기능 응답이 아니라 잡담 응답에만 이 말투를 적용한다."
    ),
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_csv(name: str) -> list[str]:
    value = os.getenv(name, "")
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def get_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(os.getenv("TIMEZONE", "Asia/Seoul"))
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=9))  # type: ignore[return-value]


def menu_path() -> Path:
    return Path(os.getenv("MENU_FILE", str(DEFAULT_MENU_PATH))).resolve()


def kakao_channel_profile_id() -> str:
    return os.getenv("KAKAO_CHANNEL_PROFILE_ID", DEFAULT_KAKAO_CHANNEL_PROFILE_ID).strip()


def kakao_weekly_menu_post_url() -> str:
    return os.getenv("KAKAO_WEEKLY_MENU_POST_URL", DEFAULT_KAKAO_WEEKLY_MENU_POST_URL).strip()


def load_menu() -> dict[str, Any]:
    path = menu_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"메뉴 파일을 찾을 수 없습니다: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"메뉴 JSON 문법 오류: {path}:{exc.lineno}:{exc.colno}") from exc


def validate_menu(menu: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    menus = menu.get("menus")
    if not isinstance(menus, dict):
        return ["menus 객체가 필요합니다."]

    for day in DAY_KEYS[:6]:
        if day not in menus:
            errors.append(f"menus.{day} 항목이 없습니다.")
            continue
        day_menu = menus[day]
        if not isinstance(day_menu, dict):
            errors.append(f"menus.{day}는 객체여야 합니다.")
            continue
        for meal in ("lunch", "dinner"):
            items = day_menu.get(meal)
            if items is None:
                errors.append(f"menus.{day}.{meal} 항목이 없습니다.")
            elif not isinstance(items, list) or not all(isinstance(item, str) for item in items):
                errors.append(f"menus.{day}.{meal}은 문자열 배열이어야 합니다.")

    return errors


def load_memory_store() -> dict[str, list[dict[str, str]]]:
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    memory: dict[str, list[dict[str, str]]] = {}
    for key, turns in data.items():
        if not isinstance(key, str) or not isinstance(turns, list):
            continue
        cleaned: list[dict[str, str]] = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role")
            text = turn.get("text")
            if isinstance(role, str) and isinstance(text, str):
                cleaned_turn = {"role": role, "text": text}
                speaker = turn.get("speaker")
                if isinstance(speaker, str) and speaker:
                    cleaned_turn["speaker"] = speaker
                cleaned.append(cleaned_turn)
        if cleaned:
            memory[key] = cleaned[-MAX_MEMORY_TURNS:]
    return memory


def save_memory_store(memory: dict[str, list[dict[str, str]]]) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed_items = list(memory.items())[-MAX_MEMORY_CONVERSATIONS:]
    trimmed = {key: turns[-MAX_MEMORY_TURNS:] for key, turns in trimmed_items}
    MEMORY_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_memory_text(text: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def load_user_memory_store() -> dict[str, list[str]]:
    try:
        data = json.loads(USER_MEMORY_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    memory: dict[str, list[str]] = {}
    for user_id, items in data.items():
        if not isinstance(user_id, str) or not isinstance(items, list):
            continue
        cleaned = [
            normalize_memory_text(item)
            for item in items
            if isinstance(item, str) and normalize_memory_text(item)
        ]
        if cleaned:
            memory[user_id] = cleaned[-MAX_USER_MEMORIES:]
    return memory


def save_user_memory_store(memory: dict[str, list[str]]) -> None:
    USER_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed_items = list(memory.items())[-MAX_USER_PROFILES:]
    trimmed = {key: items[-MAX_USER_MEMORIES:] for key, items in trimmed_items}
    USER_MEMORY_PATH.write_text(
        json.dumps(trimmed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def day_key_for(moment: datetime) -> str:
    return moment.date().isoformat()


def load_memory_day() -> str | None:
    try:
        data = json.loads(MEMORY_STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    day_key = data.get("day_key")
    return day_key if isinstance(day_key, str) else None


def save_memory_day(day_key: str) -> None:
    MEMORY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_STATE_PATH.write_text(
        json.dumps({"day_key": day_key}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalize_scheduled_message(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None

    message_id = raw.get("id")
    channel = raw.get("channel")
    text = raw.get("text")
    send_at = raw.get("send_at")
    created_at = raw.get("created_at")
    created_by = raw.get("created_by", "")
    target = raw.get("target", "personal")
    if not all(isinstance(value, str) and value.strip() for value in (message_id, channel, text, send_at, created_at)):
        return None

    try:
        datetime.fromisoformat(send_at)
    except ValueError:
        return None

    return {
        "id": message_id.strip(),
        "channel": channel.strip(),
        "text": text.strip(),
        "send_at": send_at.strip(),
        "created_at": created_at.strip(),
        "created_by": created_by.strip() if isinstance(created_by, str) else "",
        "target": target.strip() if isinstance(target, str) and target.strip() else "personal",
    }


def load_scheduled_messages_unlocked() -> list[dict[str, str]]:
    try:
        data = json.loads(SCHEDULED_MESSAGES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    messages = [message for item in data if (message := normalize_scheduled_message(item)) is not None]
    return sorted(messages, key=lambda item: item["send_at"])[:MAX_SCHEDULED_MESSAGES]


def save_scheduled_messages_unlocked(messages: list[dict[str, str]]) -> None:
    SCHEDULED_MESSAGES_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned = [message for item in messages if (message := normalize_scheduled_message(item)) is not None]
    cleaned = sorted(cleaned, key=lambda item: item["send_at"])[:MAX_SCHEDULED_MESSAGES]
    SCHEDULED_MESSAGES_PATH.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_scheduled_messages() -> list[dict[str, str]]:
    with SCHEDULED_MESSAGES_LOCK:
        return load_scheduled_messages_unlocked()


def normalize_coaching_room_reservation_record(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None

    required_keys = ("id", "room_id", "date", "start_time", "end_time", "nickname", "cancel_pin", "created_at", "created_by")
    values: dict[str, str] = {}
    for key in required_keys:
        value = raw.get(key, "")
        if not isinstance(value, str) or not value.strip():
            return None
        values[key] = value.strip()

    try:
        datetime.fromisoformat(values["created_at"])
        datetime.fromisoformat(f"{values['date']}T00:00:00")
    except ValueError:
        return None

    status = raw.get("status", "active")
    if not isinstance(status, str) or status not in {"active", "canceled"}:
        status = "active"
    values["status"] = status

    canceled_at = raw.get("canceled_at", "")
    if isinstance(canceled_at, str) and canceled_at.strip():
        try:
            datetime.fromisoformat(canceled_at.strip())
            values["canceled_at"] = canceled_at.strip()
        except ValueError:
            pass

    return values


def load_coaching_room_reservations_unlocked() -> list[dict[str, str]]:
    try:
        data = json.loads(COACHING_ROOM_RESERVATIONS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    records = [record for item in data if (record := normalize_coaching_room_reservation_record(item)) is not None]
    records.sort(key=lambda item: item["created_at"], reverse=True)
    return records[:MAX_COACHING_ROOM_RESERVATION_RECORDS]


def save_coaching_room_reservations_unlocked(records: list[dict[str, str]]) -> None:
    COACHING_ROOM_RESERVATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleaned = [record for item in records if (record := normalize_coaching_room_reservation_record(item)) is not None]
    cleaned.sort(key=lambda item: item["created_at"], reverse=True)
    cleaned = cleaned[:MAX_COACHING_ROOM_RESERVATION_RECORDS]
    COACHING_ROOM_RESERVATIONS_PATH.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_coaching_room_reservations() -> list[dict[str, str]]:
    with COACHING_ROOM_RESERVATIONS_LOCK:
        return load_coaching_room_reservations_unlocked()


def save_created_coaching_room_reservation(result: dict[str, Any], user_id: str | None, now: datetime) -> None:
    if result.get("status") != "created" or not user_id:
        return

    reservation = result.get("reservation", {})
    if not isinstance(reservation, dict):
        return
    reservation_id = reservation.get("id")
    cancel_pin = result.get("cancel_pin")
    if not isinstance(reservation_id, str) or not reservation_id.strip():
        return
    if not isinstance(cancel_pin, str) or not cancel_pin.strip():
        return

    record = {
        "id": reservation_id.strip(),
        "room_id": str(result.get("room_id", "")).strip(),
        "date": str(result.get("date", "")).strip(),
        "start_time": str(result.get("start_time", "")).strip(),
        "end_time": str(result.get("end_time", "")).strip(),
        "nickname": str(reservation.get("nickname", "코칭실 예약")).strip() or "코칭실 예약",
        "cancel_pin": cancel_pin.strip(),
        "created_at": now.astimezone(get_timezone()).isoformat(),
        "created_by": user_id,
        "status": "active",
    }
    if normalize_coaching_room_reservation_record(record) is None:
        return

    with COACHING_ROOM_RESERVATIONS_LOCK:
        records = [item for item in load_coaching_room_reservations_unlocked() if item["id"] != record["id"]]
        records.insert(0, record)
        save_coaching_room_reservations_unlocked(records)


def mark_coaching_room_reservation_canceled(reservation_id: str, now: datetime) -> None:
    with COACHING_ROOM_RESERVATIONS_LOCK:
        records = load_coaching_room_reservations_unlocked()
        changed = False
        for record in records:
            if record["id"] == reservation_id:
                record["status"] = "canceled"
                record["canceled_at"] = now.astimezone(get_timezone()).isoformat()
                changed = True
                break
        if changed:
            save_coaching_room_reservations_unlocked(records)


def load_user_personas() -> dict[str, str]:
    try:
        data = json.loads(USER_PERSONA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    personas: dict[str, str] = {}
    for user_id, persona in data.items():
        if isinstance(user_id, str) and isinstance(persona, str) and user_id.strip() and persona.strip():
            personas[user_id.strip()] = persona.strip()
    return personas


def user_persona_instruction(user_id: str | None) -> str | None:
    if not user_id:
        return None

    persona = load_user_personas().get(user_id)
    if not persona:
        return None

    instruction = USER_PERSONA_INSTRUCTIONS.get(persona, persona)
    return normalize_memory_text(instruction, 1200)


def is_direct_message(channel: str, channel_type: str | None) -> bool:
    return channel_type == "im" or channel.startswith("D")


def conversation_key(event: dict[str, Any]) -> str:
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts")
    channel_type = event.get("channel_type")
    if isinstance(thread_ts, str) and thread_ts:
        return f"thread:{channel}:{thread_ts}"
    if is_direct_message(str(channel), channel_type if isinstance(channel_type, str) else None):
        return f"dm:{channel}"
    return f"channel:{channel}"


def strip_leading_reply_mentions(text: str) -> str:
    text = text.strip()
    while True:
        updated = re.sub(r"^(?:<@[A-Z0-9]+>|@[^\s:,.!?]+)[\s:,.!?-]*", "", text).strip()
        if updated == text:
            return text
        text = updated


def render_history_text(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for turn in history[-MAX_MEMORY_TURNS:]:
        if turn.get("role") == "user":
            speaker = turn.get("speaker")
            role = f"사용자(<@{speaker}>)" if speaker else "사용자"
        else:
            role = "몽키"
        text = strip_leading_reply_mentions(turn.get("text", "").strip())
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def render_user_memory_text(memories: list[str]) -> str:
    return "\n".join(f"- {memory}" for memory in memories[-MAX_USER_MEMORIES:])


def should_store_user_memory(text: str) -> bool:
    normalized = normalize_memory_text(text)
    collapsed = re.sub(r"\s+", "", normalized)
    if len(collapsed) < 6:
        return False
    if detect_meal(normalized):
        return False
    if any(
        phrase in collapsed
        for phrase in (
            "아까얘기이어서해봐",
            "아까얘기이어해서해봐",
            "왜그런지맞춰봐",
            "따라해봐",
            "뭐야",
        )
    ):
        return False
    if any(
        phrase in normalized
        for phrase in (
            "월요일 점심",
            "월요일 저녁",
            "화요일 점심",
            "화요일 저녁",
            "수요일 점심",
            "수요일 저녁",
            "목요일 점심",
            "목요일 저녁",
            "금요일 점심",
            "금요일 저녁",
            "토요일 점심",
            "토요일 저녁",
            "내일 점심",
            "내일 저녁",
            "오늘 점심",
            "오늘 저녁",
        )
    ):
        return False
    if any(word in normalized for word in ("바보야", "멍청", "병신")):
        return False

    memory_markers = (
        "나는",
        "난 ",
        "난",
        "내가",
        "나 ",
        "저는",
        "제가",
        "요즘",
        "좋아",
        "싫어",
        "취향",
        "피곤",
        "힘들",
        "우울",
        "스트레스",
        "잠",
        "다이어트",
        "노래",
        "음악",
        "치킨",
        "피자",
        "떡볶이",
    )
    return any(marker in normalized for marker in memory_markers)


def extract_user_memory(text: str) -> str | None:
    cleaned = normalize_memory_text(strip_slack_mentions(text))
    if not cleaned:
        return None
    if not should_store_user_memory(cleaned):
        return None
    return cleaned


def strip_slack_mentions(text: str) -> str:
    text = re.sub(r"<@[A-Z0-9]+>", "", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return text.strip()


def strip_slack_event_command_text(text: str) -> str:
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return strip_leading_reply_mentions(text)


def normalized_command_text(text: str) -> str:
    return re.sub(r"\s+", "", strip_slack_mentions(text).lower())


def has_monkey_call(text: str) -> bool:
    return bool(MONKEY_CALL_RE.search(strip_slack_mentions(text)))


def strip_monkey_call(text: str) -> str:
    cleaned = MONKEY_CALL_RE.sub(" ", strip_slack_mentions(text))
    cleaned = re.sub(r"^[\s,:.!?~\-]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def contains_mention_required_command(text: str) -> bool:
    normalized = normalized_command_text(text)
    if not normalized:
        return False
    return any(keyword in normalized for keyword in MENTION_REQUIRED_COMMAND_KEYWORDS)


def meaningful_passive_text(text: str) -> str:
    cleaned = strip_monkey_call(text) if has_monkey_call(text) else strip_slack_mentions(text)
    cleaned = re.sub(r"https?://\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def is_too_small_for_passive_reply(text: str) -> bool:
    compact = re.sub(r"[^0-9A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ]", "", text).lower()
    if len(compact) < env_int("CHANNEL_PASSIVE_MIN_CHARS", 4):
        return True
    if compact in PASSIVE_IGNORED_MESSAGES:
        return True
    return bool(re.fullmatch(r"[ㅋㅎㅠㅜㅇ응네넵예아니ㄴ]+", compact))


def should_store_channel_context_message(text: str) -> bool:
    cleaned = meaningful_passive_text(text)
    return bool(cleaned) and not is_too_small_for_passive_reply(cleaned)


def should_passively_join_channel_message(text: str) -> bool:
    if not env_bool("CHANNEL_PASSIVE_CHAT_ENABLED", True):
        return False
    cleaned = meaningful_passive_text(text)
    if not cleaned or is_too_small_for_passive_reply(cleaned):
        return False
    if contains_mention_required_command(cleaned):
        return False
    lowered = cleaned.lower()
    return any(keyword in lowered for keyword in PASSIVE_JOIN_KEYWORDS)


def secure_url(url: str) -> str:
    if url.startswith("http://"):
        return "https://" + url[len("http://") :]
    return url


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    data = None
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        message = body or str(exc)
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict) and parsed.get("error"):
                message = str(parsed["error"])
        except json.JSONDecodeError:
            pass
        raise RuntimeError(message) from exc


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        secure_url(url),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return raw.decode(encoding, errors="replace")


def fetch_bytes(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(
        secure_url(url),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Referer": "https://pf.kakao.com/",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
    return data, content_type


def kakao_image_url_candidates(url: str) -> list[str]:
    secured = secure_url(url.strip())
    if not secured:
        return []
    candidates = [
        re.sub(r"/img_[a-z]+(?=\.)", "/img_xl", secured),
        secured,
    ]
    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def kakao_posts_url(encoded_id: str) -> str:
    return f"https://pf.kakao.com/rocket-web/web/profiles/{encoded_id}/posts?includePinnedPost=true"


def kakao_posts_page_url(encoded_id: str) -> str:
    return f"https://pf.kakao.com/{encoded_id}/posts"


def fetch_kakao_posts(encoded_id: str) -> list[dict[str, Any]]:
    try:
        payload = fetch_json(kakao_posts_url(encoded_id))
        if isinstance(payload, dict):
            items = payload.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    except Exception as exc:
        print(f"카카오 Rocket API 조회 실패, HTML 보조 파서로 시도합니다: {exc}", file=sys.stderr)
    return fetch_kakao_posts_from_html(encoded_id)


def strip_html(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def first_html_class_block(html: str, class_name: str) -> list[str]:
    pattern = re.compile(
        rf"<(?P<tag>[a-zA-Z0-9]+)[^>]*class=[\"'][^\"']*\b{re.escape(class_name)}\b[^\"']*[\"'][^>]*>(?P<body>.*?)</(?P=tag)>",
        re.S,
    )
    return [match.group("body") for match in pattern.finditer(html)]


def fetch_kakao_posts_from_html(encoded_id: str) -> list[dict[str, Any]]:
    html = fetch_text(kakao_posts_page_url(encoded_id))
    posts: list[dict[str, Any]] = []
    for card in first_html_class_block(html, "area_card"):
        title = ""
        title_blocks = first_html_class_block(card, "tit_card")
        if title_blocks:
            title = strip_html(title_blocks[0])
        image_url = None
        thumb_blocks = first_html_class_block(card, "wrap_fit_thumb")
        for block in thumb_blocks:
            match = re.search(r"<img[^>]+(?:src|data-src)=[\"']([^\"']+)[\"']", block, re.I)
            if match:
                image_url = secure_url(html_lib.unescape(match.group(1)))
                break
        if title or image_url:
            post: dict[str, Any] = {"title": title, "contents": [], "media": []}
            if image_url:
                post["media"] = [{"url": image_url}]
            posts.append(post)
    return posts


def extract_post_text(post: dict[str, Any]) -> str:
    cached_text = post.get("text")
    if isinstance(cached_text, str) and cached_text.strip():
        return cached_text.strip()

    contents = post.get("contents")
    if not isinstance(contents, list):
        return ""
    parts: list[str] = []
    for item in contents:
        if not isinstance(item, dict):
            continue
        value = item.get("v")
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts).strip()


def format_menu_lines(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n")
    raw_parts: list[str] = []
    for line in normalized.splitlines():
        pieces = [part.strip() for part in line.split(",")]
        raw_parts.extend(piece for piece in pieces if piece)
    if len(raw_parts) <= 1:
        return normalized
    return "\n".join(f"- {part}" for part in raw_parts)


def extract_post_image_url(post: dict[str, Any]) -> str | None:
    cached_url = post.get("image_url")
    if isinstance(cached_url, str) and cached_url.strip():
        candidates = kakao_image_url_candidates(cached_url)
        return candidates[0] if candidates else secure_url(cached_url.strip())

    media = post.get("media")
    if not isinstance(media, list):
        return None
    for item in media:
        if not isinstance(item, dict):
            continue
        url = item.get("xlarge_url") or item.get("url") or item.get("large_url") or item.get("medium_url")
        if isinstance(url, str) and url.strip():
            candidates = kakao_image_url_candidates(url)
            return candidates[0] if candidates else secure_url(url.strip())
    return None


def extract_post_id(post: dict[str, Any]) -> str:
    for key in ("id", "post_id", "encoded_id", "permalink_id"):
        value = post.get(key)
        if isinstance(value, (str, int)):
            return str(value)
    title = post.get("title") if isinstance(post.get("title"), str) else ""
    image_url = extract_post_image_url(post) or ""
    return hashlib.sha1(f"{title}|{image_url}".encode("utf-8")).hexdigest()[:16]


def normalize_kakao_post_for_cache(post: dict[str, Any], now: datetime) -> dict[str, Any]:
    title = post.get("title") if isinstance(post.get("title"), str) else ""
    text = extract_post_text(post)
    image_url = extract_post_image_url(post)
    parsed_meal = parse_kakao_meal_post_title(title)
    return {
        "id": extract_post_id(post),
        "title": title,
        "text": text,
        "image_url": image_url,
        "is_weekly_menu": is_weekly_menu_title(title),
        "meal": parsed_meal,
        "cached_at": now.isoformat(),
    }


def save_kakao_posts_cache(posts: list[dict[str, Any]], now: datetime) -> None:
    encoded_id = kakao_channel_profile_id()
    data = {
        "profile_id": encoded_id,
        "synced_at": now.isoformat(),
        "source": kakao_posts_url(encoded_id) if encoded_id else "",
        "posts": [normalize_kakao_post_for_cache(post, now) for post in posts],
    }
    with KAKAO_CACHE_LOCK:
        KAKAO_POST_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        KAKAO_POST_CACHE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_weekly_menu_image_state() -> dict[str, Any]:
    try:
        data = json.loads(WEEKLY_MENU_IMAGE_STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_weekly_menu_image_state(state: dict[str, Any]) -> None:
    with WEEKLY_MENU_IMAGE_STATE_LOCK:
        WEEKLY_MENU_IMAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEEKLY_MENU_IMAGE_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def load_daily_menu_post_state() -> dict[str, Any]:
    try:
        data = json.loads(DAILY_MENU_POST_STATE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_daily_menu_post_state(state: dict[str, Any]) -> None:
    with DAILY_MENU_POST_STATE_LOCK:
        DAILY_MENU_POST_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DAILY_MENU_POST_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def extract_image_urls_from_html(html: str) -> list[str]:
    text = html_lib.unescape(html).replace("\\/", "/")
    urls: list[str] = []
    for match in re.finditer(r"https?://[^\"'\s<>]+", text):
        url = match.group(0).rstrip("),.;")
        if not re.search(r"\.(?:jpg|jpeg|png|webp|gif)(?:\?|$)|/img_(?:xl|l|m)\b", url, re.I):
            continue
        if "kakaocdn.net" not in url:
            continue
        secured = secure_url(url)
        for candidate in kakao_image_url_candidates(secured):
            if candidate not in urls:
                urls.append(candidate)
    return urls


def weekly_menu_post_image_url() -> str | None:
    configured = os.getenv("KAKAO_WEEKLY_MENU_IMAGE_URL", "").strip()
    if configured:
        return secure_url(configured)

    post_url = kakao_weekly_menu_post_url()
    if not post_url:
        return None

    html = fetch_text(post_url)
    candidates = extract_image_urls_from_html(html)
    if not candidates:
        return None

    def priority(url: str) -> tuple[int, int]:
        if "img_xl" in url:
            return (0, len(url))
        if "img_l" in url:
            return (1, len(url))
        return (2, len(url))

    return sorted(candidates, key=priority)[0]


def is_weekly_menu_title(title: str) -> bool:
    normalized = re.sub(r"\s+", "", title)
    return "식단표" in normalized or "주차식단" in normalized or "주간식단" in normalized


def response_output_text(result: dict[str, Any]) -> str:
    if isinstance(result.get("output_text"), str):
        return result["output_text"].strip()

    chunks: list[str] = []
    for output in result.get("output", []):
        if not isinstance(output, dict):
            continue
        content_items = output.get("content", [])
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "".join(chunks).strip()


def parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.I | re.S)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        return None

    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_menu_item(item: str) -> str:
    item = strip_html(item)
    item = re.sub(r"^[*\-\u2022\s]+", "", item)
    item = re.sub(r"\s+", " ", item).strip()
    for pattern in MENU_PROMO_PREFIX_PATTERNS:
        item = pattern.sub("", item).strip()
    item = MENU_OCR_CORRECTIONS.get(item, item)
    return item


def normalize_menu_items(raw_items: Any) -> list[str]:
    if isinstance(raw_items, str):
        candidates = menu_items_from_kakao_text(raw_items)
    elif isinstance(raw_items, list):
        candidates = [item for item in raw_items if isinstance(item, str)]
    else:
        return []

    items: list[str] = []
    for raw_item in candidates:
        item = normalize_menu_item(raw_item)
        for expanded_item in MENU_OCR_ITEM_SPLITS.get(item, [item]):
            if expanded_item and expanded_item not in items:
                items.append(expanded_item)
    return merge_menu_ocr_items(items)


def merge_menu_ocr_items(items: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(items):
        did_merge = False
        for source, replacement in MENU_OCR_ITEM_MERGES.items():
            size = len(source)
            if tuple(items[index : index + size]) == source:
                if replacement not in merged:
                    merged.append(replacement)
                index += size
                did_merge = True
                break
        if did_merge:
            continue
        if items[index] not in merged:
            merged.append(items[index])
        index += 1
    return merged


def normalize_weekly_menu_payload(payload: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    menus = payload.get("menus")
    if not isinstance(menus, dict):
        return None

    week_start = week_start_for(now).date().isoformat()
    raw_week_start = payload.get("week_start")
    if isinstance(raw_week_start, str) and raw_week_start.strip():
        try:
            week_start = datetime.fromisoformat(raw_week_start.strip()).date().isoformat()
        except ValueError:
            pass

    normalized_menus: dict[str, dict[str, list[str]]] = {}
    filled_meals = 0
    for day in DAY_KEYS[:6]:
        raw_day = menus.get(day)
        if not isinstance(raw_day, dict):
            raw_day = {}
        normalized_menus[day] = {}
        for meal in ("lunch", "dinner"):
            items = normalize_menu_items(raw_day.get(meal))
            normalized_menus[day][meal] = items
            if items:
                filled_meals += 1

    if filled_meals == 0:
        return None

    normalized_menus["sunday"] = {"lunch": [], "dinner": []}
    return {
        "week_start": week_start,
        "timezone": os.getenv("TIMEZONE", "Asia/Seoul"),
        "note": "카카오 채널 주간 식단표 이미지에서 자동 갱신되었습니다.",
        "menus": normalized_menus,
    }


def image_data_url(url: str) -> str:
    data, content_type = fetch_bytes(url)
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
        media_type = "image/jpeg"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def extract_weekly_menu_from_image(post: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    if not env_bool("OPENAI_MENU_VISION_ENABLED", True):
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    image_url = extract_post_image_url(post)
    if not image_url:
        return None

    title = post.get("title") if isinstance(post.get("title"), str) else ""
    current_week_start = week_start_for(now).date().isoformat()
    prompt = (
        "이미지는 한국어 주간 식단표입니다. 표에서 월요일부터 토요일까지의 점심과 저녁 메뉴만 읽어 JSON으로 반환하세요.\n"
        f"현재 기준일: {now.date().isoformat()}\n"
        f"이번 주 월요일: {current_week_start}\n"
        f"카카오 글 제목: {title}\n\n"
        "규칙:\n"
        f"- week_start는 표의 월요일 날짜를 YYYY-MM-DD로 적으세요. 연도가 보이지 않으면 {now.year}년으로 계산하세요.\n"
        "- 날짜 열 예시는 5/18(월), 5/19(화) 같은 형식입니다.\n"
        "- 첫 번째 식사 행은 lunch, 두 번째 식사 행은 dinner입니다.\n"
        "- 코너명, 배식 시간, 알레르기 안내, 로고, 제목, 빈칸은 메뉴에 넣지 마세요.\n"
        "- 빨간색, 주황색, 굵은 글씨, 별표 등 강조된 글씨도 음식명이면 반드시 메뉴에 포함하세요.\n"
        "- 강조 색상으로 적힌 대표 메뉴를 건너뛰지 말고, 각 칸의 모든 줄을 위에서 아래로 확인하세요.\n"
        "- 이벤트/프로모션 문구가 메뉴명과 함께 있으면 브랜드명과 이벤트명은 빼고 음식 이름만 보존하세요.\n"
        "- 괄호 안의 식재료 안내가 음식명 바로 뒤에 붙어 있으면 함께 보존하세요. 예: 교동순두부짬뽕탕(해물포함)\n"
        "- 읽기 어려운 칸은 빈 배열로 두세요.\n"
        "- JSON 외의 설명은 절대 쓰지 마세요.\n\n"
        "반환 형식:\n"
        '{"week_start":"YYYY-MM-DD","menus":{"monday":{"lunch":[],"dinner":[]},"tuesday":{"lunch":[],"dinner":[]},"wednesday":{"lunch":[],"dinner":[]},"thursday":{"lunch":[],"dinner":[]},"friday":{"lunch":[],"dinner":[]},"saturday":{"lunch":[],"dinner":[]}}}'
    )

    body: dict[str, Any] = {
        "model": os.getenv("OPENAI_MENU_VISION_MODEL", os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MENU_VISION_MODEL)),
        "instructions": "너는 식단표 OCR 결과를 엄격한 JSON으로 정리하는 도우미다. 추측은 최소화하고 표에 보이는 음식명만 반환한다.",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_data_url(image_url), "detail": "high"},
                ],
            }
        ],
        "max_output_tokens": 1800,
    }

    reasoning_effort = os.getenv("OPENAI_MENU_VISION_REASONING_EFFORT") or os.getenv("OPENAI_REASONING_EFFORT")
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"OpenAI 메뉴 이미지 추출 오류: {exc.code} {detail}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"OpenAI 메뉴 이미지 추출 실패: {exc}", file=sys.stderr)
        return None

    parsed = parse_json_object(response_output_text(result))
    if parsed is None:
        print("OpenAI 메뉴 이미지 추출 응답에서 JSON을 찾지 못했습니다.", file=sys.stderr)
        return None
    return normalize_weekly_menu_payload(parsed, now)


def has_complete_week_menu(menu: dict[str, Any], week_start: datetime) -> bool:
    if menu.get("week_start") != week_start.date().isoformat():
        return False
    menus = menu.get("menus")
    if not isinstance(menus, dict):
        return False
    for day in DAY_KEYS[:6]:
        day_menu = menus.get(day)
        if not isinstance(day_menu, dict):
            return False
        for meal in ("lunch", "dinner"):
            items = day_menu.get(meal)
            if not isinstance(items, list) or not any(isinstance(item, str) and item.strip() for item in items):
                return False
    return True


def apply_menu_payload(target: dict[str, Any], source: dict[str, Any], keep_longer_existing: bool = False) -> int:
    source_menus = source.get("menus")
    target_menus = target.setdefault("menus", {})
    if not isinstance(source_menus, dict) or not isinstance(target_menus, dict):
        return 0

    changed_count = 0
    for day in DAY_KEYS[:6]:
        raw_day = source_menus.get(day)
        if not isinstance(raw_day, dict):
            continue
        target_day = target_menus.setdefault(day, {"lunch": [], "dinner": []})
        if not isinstance(target_day, dict):
            continue
        for meal in ("lunch", "dinner"):
            items = normalize_menu_items(raw_day.get(meal))
            if not items:
                continue
            before = target_day.get(meal, [])
            if (
                keep_longer_existing
                and isinstance(before, list)
                and len(normalize_menu_items(before)) > len(items)
            ):
                continue
            if before != items:
                target_day[meal] = items
                changed_count += 1
    return changed_count


def weekly_menu_image_key(image_url: str) -> str:
    try:
        data, _content_type = fetch_bytes(image_url)
    except Exception:
        return hashlib.sha1(image_url.encode("utf-8")).hexdigest()
    return hashlib.sha1(data).hexdigest()


def weekly_menu_check_window(now: datetime) -> bool:
    if now.weekday() != 0:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 <= minutes <= 12 * 60


def weekly_menu_image_completed(state: dict[str, Any], menu: dict[str, Any], week_start: datetime) -> bool:
    week_start_text = week_start.date().isoformat()
    if state.get("week_start") != week_start_text:
        return False
    if state.get("completed") is True:
        return True
    return bool(state.get("synced_at")) and has_complete_week_menu(menu, week_start)


def sync_weekly_menu_image(now: datetime | None = None, force: bool = False) -> dict[str, Any]:
    now = now or datetime.now(get_timezone())
    if not force and not env_bool("KAKAO_WEEKLY_MENU_AUTO_SYNC", True):
        return {"ok": False, "skipped": "disabled"}
    if not force and not weekly_menu_check_window(now):
        return {"ok": False, "skipped": "outside_window"}

    current_week_start = week_start_for(now)
    current_menu = load_menu()
    state = load_weekly_menu_image_state()
    if not force and weekly_menu_image_completed(state, current_menu, current_week_start):
        return {
            "ok": True,
            "skipped": "completed",
            "week_start": current_week_start.date().isoformat(),
        }

    image_url = weekly_menu_post_image_url()
    if not image_url:
        return {"ok": False, "error": "weekly menu image not found"}

    image_key = weekly_menu_image_key(image_url)
    if (
        state.get("image_key") == image_key
        and state.get("week_start") == current_week_start.date().isoformat()
        and has_complete_week_menu(current_menu, current_week_start)
        and (not force or not env_bool("KAKAO_WEEKLY_MENU_FORCE_REOCR", False))
    ):
        return {
            "ok": True,
            "skipped": "unchanged",
            "image_url": image_url,
            "week_start": current_week_start.date().isoformat(),
        }

    post = {
        "title": f"{now.month}월 주간 식단표",
        "image_url": image_url,
    }
    weekly_menu = extract_weekly_menu_from_image(post, now)
    if not weekly_menu:
        return {"ok": False, "error": "vision extraction failed", "image_url": image_url}

    if weekly_menu.get("week_start") != current_week_start.date().isoformat():
        return {
            "ok": False,
            "error": "week_start mismatch",
            "image_url": image_url,
            "expected_week_start": current_week_start.date().isoformat(),
            "extracted_week_start": weekly_menu.get("week_start"),
        }

    updated = current_menu if current_menu.get("week_start") == current_week_start.date().isoformat() else empty_week_menu(current_week_start)
    updated["week_start"] = current_week_start.date().isoformat()
    updated["timezone"] = os.getenv("TIMEZONE", "Asia/Seoul")
    updated["note"] = "카카오 채널 주간 식단표 이미지에서 자동 갱신되었습니다."
    changed_count = apply_menu_payload(updated, weekly_menu, keep_longer_existing=True)
    if changed_count > 0:
        save_menu(updated)

    save_weekly_menu_image_state(
        {
            "post_url": kakao_weekly_menu_post_url(),
            "image_url": image_url,
            "image_key": image_key,
            "week_start": current_week_start.date().isoformat(),
            "completed": True,
            "completed_at": now.isoformat(),
            "changed_meals": changed_count,
            "synced_at": now.isoformat(),
        }
    )
    return {
        "ok": True,
        "changed_meals": changed_count,
        "week_start": current_week_start.date().isoformat(),
        "image_url": image_url,
        "menu": str(menu_path()),
    }


def daily_menu_post_check_window(now: datetime) -> bool:
    return bool(daily_menu_post_meals_to_check(now))


def daily_menu_post_meals_to_check(now: datetime) -> list[str]:
    if now.weekday() > 5:
        return []
    minutes = now.hour * 60 + now.minute
    if 11 * 60 <= minutes <= 11 * 60 + 50:
        return ["lunch"]
    if 17 * 60 <= minutes <= 17 * 60 + 50:
        return ["dinner"]
    return []


def daily_menu_state_key(target: datetime, meal: str) -> str:
    return f"{target.date().isoformat()}:{meal}"


def prune_daily_menu_post_state(state: dict[str, Any], now: datetime) -> dict[str, Any]:
    today = now.date().isoformat()
    sent = state.get("sent")
    if not isinstance(sent, dict):
        sent = {}
    kept = {
        key: value
        for key, value in sent.items()
        if isinstance(key, str) and key.startswith(today + ":")
    }
    pruned: dict[str, Any] = {"sent": kept}
    if state.get("completed_on") == today:
        pruned["completed_on"] = today
        completed_at = state.get("completed_at")
        if isinstance(completed_at, str):
            pruned["completed_at"] = completed_at
    return pruned


def daily_menu_posts_completed(state: dict[str, Any], now: datetime) -> bool:
    today = now.date().isoformat()
    if state.get("completed_on") == today:
        return True
    sent = state.get("sent")
    if not isinstance(sent, dict):
        return False
    return all(daily_menu_state_key(now, meal) in sent for meal in ("lunch", "dinner"))


def sync_and_post_daily_menu_posts(now: datetime | None = None, force: bool = False) -> dict[str, Any]:
    now = now or datetime.now(get_timezone())
    if not force and not env_bool("KAKAO_DAILY_MENU_AUTO_POST", True):
        return {"ok": False, "skipped": "disabled"}
    meals_to_check = ("lunch", "dinner") if force else tuple(daily_menu_post_meals_to_check(now))
    if not meals_to_check:
        return {"ok": False, "skipped": "outside_window"}

    state = prune_daily_menu_post_state(load_daily_menu_post_state(), now)
    if not force and daily_menu_posts_completed(state, now):
        return {
            "ok": True,
            "skipped": "completed",
            "completed_on": now.date().isoformat(),
        }

    channel = os.getenv("SLACK_CHANNEL_ID", "").strip()
    if not channel:
        return {"ok": False, "error": "SLACK_CHANNEL_ID is empty"}

    encoded_id = kakao_channel_profile_id()
    if not encoded_id:
        return {"ok": False, "error": "KAKAO_CHANNEL_PROFILE_ID is empty"}

    posts = fetch_kakao_posts(encoded_id)
    save_kakao_posts_cache(posts, now)
    current_menu = load_menu()
    updated_menu, changed_count = update_menu_from_kakao_posts(current_menu, posts, now, include_weekly_images=False)
    if changed_count > 0:
        save_menu(updated_menu)

    sent = state.setdefault("sent", {})
    posted: list[str] = []
    found: list[str] = []
    skipped: list[str] = []

    failures: list[dict[str, str]] = []
    for meal in meals_to_check:
        post = find_kakao_meal_post_in_posts(posts, now, meal)
        if not post:
            continue
        found.append(meal)
        key = daily_menu_state_key(now, meal)
        post_id = extract_post_id(post)
        previous = sent.get(key)
        if isinstance(previous, dict) and previous.get("post_id") == post_id:
            skipped.append(meal)
            continue
        try:
            image_uploaded = post_kakao_reminder(channel, post, now, meal)
        except Exception as exc:
            failures.append({"meal": meal, "error": normalize_memory_text(str(exc), 180)})
            print(f"일별 {meal} 메뉴 이미지/메시지 전송 실패: {exc}", file=sys.stderr)
            continue
        sent[key] = {
            "post_id": post_id,
            "title": post.get("title") if isinstance(post.get("title"), str) else "",
            "image_url": extract_post_image_url(post) or "",
            "image_uploaded": image_uploaded,
            "posted_at": now.isoformat(),
        }
        posted.append(meal)

    completed = daily_menu_posts_completed(state, now)
    if completed:
        state["completed_on"] = now.date().isoformat()
        state["completed_at"] = now.isoformat()

    save_daily_menu_post_state(state)
    return {
        "ok": True,
        "posts": len(posts),
        "found": found,
        "posted": posted,
        "skipped": skipped,
        "failures": failures,
        "completed": completed,
        "changed_meals": changed_count,
    }


def menu_items_from_kakao_text(text: str) -> list[str]:
    text = strip_html(text).replace("ㆍ", ",").replace("·", ",")
    items: list[str] = []
    lines = text.splitlines() if "\n" in text else [text]
    for line in lines:
        for piece in line.split(","):
            item = normalize_menu_item(piece)
            if item:
                items.append(item)
    return items


def parse_kakao_meal_post_title(title: str) -> dict[str, Any] | None:
    match = re.search(
        r"(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일\((?P<weekday>[월화수목금토일])\)\s*(?P<meal>중식|석식)\s*메뉴",
        title,
    )
    if not match:
        return None
    return {
        "month": int(match.group("month")),
        "day": int(match.group("day")),
        "weekday": match.group("weekday"),
        "meal_label": match.group("meal"),
    }


def find_kakao_meal_post_in_posts(posts: list[dict[str, Any]], target: datetime, meal: str) -> dict[str, Any] | None:
    target_weekday = WEEKDAY_SHORT_LABELS[target.weekday()]
    target_meal_label = MEAL_SOURCE_LABELS[meal]
    for post in posts:
        title = post.get("title")
        if not isinstance(title, str):
            continue
        parsed = parse_kakao_meal_post_title(title)
        if not parsed:
            continue
        if parsed["month"] != target.month or parsed["day"] != target.day:
            continue
        if parsed["weekday"] != target_weekday:
            continue
        if parsed["meal_label"] != target_meal_label:
            continue
        return post
    return None


def week_start_for(moment: datetime) -> datetime:
    start = moment - timedelta(days=moment.weekday())
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def empty_week_menu(week_start: datetime) -> dict[str, Any]:
    return {
        "week_start": week_start.date().isoformat(),
        "timezone": os.getenv("TIMEZONE", "Asia/Seoul"),
        "note": "카카오 채널 일별 메뉴 포스트에서 자동 갱신됩니다. 비어 있는 항목은 포스트가 아직 없거나 식단표 이미지 OCR이 필요합니다.",
        "menus": {
            day: {"lunch": [], "dinner": []}
            for day in DAY_KEYS
        },
    }


def infer_post_date(parsed: dict[str, Any], now: datetime) -> datetime | None:
    month = parsed["month"]
    day = parsed["day"]
    for year in (now.year, now.year - 1, now.year + 1):
        try:
            candidate = datetime(year, month, day, tzinfo=now.tzinfo)
        except ValueError:
            continue
        if abs((candidate.date() - now.date()).days) <= 45:
            return candidate
    return None


def update_menu_from_kakao_posts(
    menu: dict[str, Any],
    posts: list[dict[str, Any]],
    now: datetime,
    include_weekly_images: bool = True,
) -> tuple[dict[str, Any], int]:
    current_week_start = week_start_for(now)
    week_end = current_week_start + timedelta(days=6)
    updated = empty_week_menu(current_week_start)

    existing_week_start = menu.get("week_start")
    if existing_week_start == current_week_start.date().isoformat() and isinstance(menu.get("menus"), dict):
        updated["menus"] = json.loads(json.dumps(menu["menus"], ensure_ascii=False))

    changed_count = 0
    if include_weekly_images and not has_complete_week_menu(updated, current_week_start):
        for post in posts:
            title = post.get("title")
            if not isinstance(title, str) or not is_weekly_menu_title(title):
                continue
            weekly_menu = extract_weekly_menu_from_image(post, now)
            if not weekly_menu:
                continue
            if weekly_menu.get("week_start") != current_week_start.date().isoformat():
                continue
            changed_count += apply_menu_payload(updated, weekly_menu, keep_longer_existing=True)
            break

    for post in posts:
        title = post.get("title")
        if not isinstance(title, str):
            continue
        parsed = parse_kakao_meal_post_title(title)
        if not parsed:
            continue
        post_date = infer_post_date(parsed, now)
        if post_date is None or not (current_week_start.date() <= post_date.date() <= week_end.date()):
            continue
        if parsed["weekday"] != WEEKDAY_SHORT_LABELS[post_date.weekday()]:
            continue
        meal = "lunch" if parsed["meal_label"] == "중식" else "dinner"
        items = menu_items_from_kakao_text(extract_post_text(post))
        if not items:
            continue
        day_key = DAY_KEYS[post_date.weekday()]
        changed_count += apply_menu_payload(
            updated,
            {
                "menus": {
                    day_key: {
                        meal: items,
                    },
                },
            },
        )

    return updated, changed_count


def save_menu(menu: dict[str, Any]) -> None:
    path = menu_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(menu, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sync_kakao_menu_data(now: datetime | None = None, force: bool = False) -> dict[str, Any]:
    now = now or datetime.now(get_timezone())
    encoded_id = kakao_channel_profile_id()
    if not encoded_id:
        return {"ok": False, "error": "KAKAO_CHANNEL_PROFILE_ID is empty"}

    posts = fetch_kakao_posts(encoded_id)
    save_kakao_posts_cache(posts, now)
    current_menu = load_menu()
    updated_menu, changed_count = update_menu_from_kakao_posts(current_menu, posts, now)
    if changed_count > 0:
        save_menu(updated_menu)
    return {
        "ok": True,
        "posts": len(posts),
        "changed_meals": changed_count,
        "week_start": updated_menu.get("week_start"),
        "cache": str(KAKAO_POST_CACHE_PATH),
        "menu": str(menu_path()),
    }


def detect_meal(text: str) -> str | None:
    normalized = re.sub(r"\s+", "", text)
    if any(keyword in normalized for keyword in ("점심", "중식", "런치", "lunch")):
        return "lunch"
    if any(keyword in normalized for keyword in ("저녁", "석식", "디너", "dinner")):
        return "dinner"
    return None


def resolve_target_date(text: str, now: datetime) -> datetime:
    normalized = re.sub(r"\s+", "", text)

    if "모레" in normalized:
        return now + timedelta(days=2)
    if "내일" in normalized or "낼" in normalized:
        return now + timedelta(days=1)
    if "오늘" in normalized:
        return now

    for pattern, weekday in WEEKDAY_ALIASES:
        if pattern.search(normalized):
            days_ahead = (weekday - now.weekday()) % 7
            return now + timedelta(days=days_ahead)

    return now


def date_label(target: datetime, now: datetime) -> str:
    delta_days = (target.date() - now.date()).days
    if delta_days == 0:
        return "오늘"
    if delta_days == 1:
        return "내일"
    if delta_days == 2:
        return "모레"
    return DAY_LABELS[DAY_KEYS[target.weekday()]]


def date_label_for_text(text: str, target: datetime, now: datetime) -> str:
    normalized = re.sub(r"\s+", "", text)
    if any(pattern.search(normalized) for pattern, _weekday in WEEKDAY_ALIASES):
        return DAY_LABELS[DAY_KEYS[target.weekday()]]
    return date_label(target, now)


def get_menu_items(menu: dict[str, Any], target: datetime, meal: str) -> list[str]:
    day_key = DAY_KEYS[target.weekday()]
    return menu.get("menus", {}).get(day_key, {}).get(meal, [])


def format_menu_response(menu: dict[str, Any], text: str, now: datetime, user_id: str | None = None) -> str | None:
    meal = detect_meal(text)
    if not meal:
        return None

    target = resolve_target_date(text, now)
    label = date_label_for_text(text, target, now)
    meal_label = MEAL_LABELS[meal]
    mention = f"<@{user_id}> " if user_id else ""

    if target.weekday() >= 6:
        return (
            f"{mention}:monkey_face: {label}은 메뉴 알림 쉬는 날이에요.\n"
            f"월요일부터 토요일까지의 점심/저녁만 알려드릴게요 :banana:"
        )

    items = get_menu_items(menu, target, meal)
    if not items:
        return (
            f"{mention}:monkey_face: 아직 {label} {meal_label} 메뉴가 비어 있어요.\n"
            f"`data/menu.json`에 메뉴를 추가해주면 바로 알려드릴게요 :banana:"
        )

    bullet_list = "\n".join(f"* {item}" for item in items)
    return (
        f"{mention}:monkey_face: 몽키가 {label} {meal_label} 메뉴를 찾아왔어요!\n"
        f"{label} {meal_label} 메뉴예요 :banana:\n\n"
        f"{bullet_list}"
    )


def display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W", "A"} else 1
    return width


def pad_display(text: str, width: int) -> str:
    return text + " " * max(width - display_width(text), 0)


def split_ladder_items(raw: str) -> list[str]:
    normalized = re.sub(r"[，、;|]+", ",", raw.strip())
    if "," in normalized:
        parts = normalized.split(",")
    else:
        parts = re.split(r"\s+", normalized)
    return [part.strip().replace("`", "'") for part in parts if part.strip()]


def parse_ladder_command(text: str) -> tuple[list[str], list[str], str | None] | None:
    match = re.match(r"^\s*사다리(?:타기)?\s*(.*)$", text, re.S)
    if not match:
        return None

    body = match.group(1).strip()
    if "/" not in body:
        return [], [], "usage"

    left, right = body.split("/", 1)
    players = split_ladder_items(left)
    outcomes = split_ladder_items(right)
    return players, outcomes, None


def ladder_usage() -> str:
    return (
        ":monkey_face: 사다리는 이렇게 써줘요.\n"
        "`@몽키 사다리 타잔, 세인, 원우 / 치킨, 피자, 떡볶이`\n"
        "결과가 하나면 한 명만 걸리고 나머지는 꽝으로 채울게요."
    )


def build_ladder_rungs(column_count: int) -> list[set[int]]:
    rng = random.SystemRandom()
    row_count = max(8, min(LADDER_MAX_ROWS, column_count * LADDER_ROWS_PER_PLAYER))
    rungs: list[set[int]] = [set() for _ in range(row_count)]

    required_pairs = list(range(column_count - 1))
    rng.shuffle(required_pairs)
    for pair in required_pairs:
        candidate_rows = list(range(row_count))
        rng.shuffle(candidate_rows)
        for row in candidate_rows:
            if pair - 1 not in rungs[row] and pair + 1 not in rungs[row]:
                rungs[row].add(pair)
                break

    for row in rungs:
        for pair in range(column_count - 1):
            if pair in row or pair - 1 in row or pair + 1 in row:
                continue
            if rng.random() < LADDER_EXTRA_RUNG_CHANCE:
                row.add(pair)

    return rungs


def follow_ladder(start: int, rungs: list[set[int]]) -> int:
    position = start
    for row in rungs:
        if position in row:
            position += 1
        elif position - 1 in row:
            position -= 1
    return position


def render_ladder_row(items: list[str], gap: int) -> str:
    return "".join(pad_display(item, gap + 1) for item in items).rstrip()


def render_ladder(players: list[str], outcomes: list[str], rungs: list[set[int]]) -> str:
    longest = max(display_width(item) for item in players + outcomes)
    gap = max(5, min(14, longest + 2))
    lines = [render_ladder_row(players, gap)]
    for row in rungs:
        line_parts: list[str] = []
        for column in range(len(players)):
            line_parts.append("│")
            if column < len(players) - 1:
                line_parts.append("─" * gap if column in row else " " * gap)
        lines.append("".join(line_parts))
    lines.append(render_ladder_row(outcomes, gap))
    return "\n".join(lines)


def build_ladder_game(text: str) -> tuple[dict[str, Any] | None, str | None]:
    parsed = parse_ladder_command(text)
    if parsed is None:
        return None, None

    players, outcomes, error = parsed
    if error == "usage":
        return None, ladder_usage()
    if len(players) < 2:
        return None, ":monkey_face: 사다리는 참가자가 최소 2명은 있어야 해요."
    if len(players) > MAX_LADDER_PLAYERS:
        return None, f":monkey_face: 사다리 그림이 너무 길어져서 참가자는 최대 {MAX_LADDER_PLAYERS}명까지만 받을게요."
    if not outcomes:
        return None, ladder_usage()
    if len(outcomes) > len(players):
        return None, ":monkey_face: 결과 후보가 참가자보다 많아요. 결과 수를 참가자 수 이하로 맞춰주세요."

    bottom = outcomes[:]
    if len(bottom) < len(players):
        bottom.extend(["꽝"] * (len(players) - len(bottom)))
    random.SystemRandom().shuffle(bottom)

    rungs = build_ladder_rungs(len(players))
    assignments = [(player, bottom[follow_ladder(index, rungs)]) for index, player in enumerate(players)]
    return {
        "players": players,
        "bottom": bottom,
        "rungs": rungs,
        "assignments": assignments,
    }, None


def format_ladder_result_lines(game: dict[str, Any]) -> str:
    lines = []
    for index, (player, outcome) in enumerate(game["assignments"], start=1):
        lines.append(f"- {index}. {player} -> {outcome}")
    return "\n".join(lines)


def shorten_ladder_label(text: str, limit: int = 9) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if display_width(text) <= limit:
        return text
    result = ""
    width = 0
    for char in text:
        char_width = 2 if unicodedata.east_asian_width(char) in {"F", "W", "A"} else 1
        if width + char_width > limit - 1:
            break
        result += char
        width += char_width
    return result.rstrip() + "…"


def ladder_font(size: int) -> Any:
    if ImageFont is None:
        raise RuntimeError("Pillow가 설치되어 있지 않습니다.")

    candidates = [os.getenv("LADDER_FONT_PATH", "").strip(), *LADDER_FONT_PATHS]
    for font_path in candidates:
        if not font_path:
            continue
        if not Path(font_path).exists():
            continue
        try:
            return ImageFont.truetype(font_path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_centered_text(draw: Any, x: int, y: int, text: str, font: Any, fill: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    draw.text((x - width / 2, y), text, font=font, fill=fill)


def format_ladder_text(game: dict[str, Any]) -> str:
    return (
        ":monkey_face: 사다리타기 결과예요!\n\n"
        "```text\n"
        f"{render_ladder(game['players'], game['bottom'], game['rungs'])}\n"
        "```\n"
        f"{format_ladder_result_lines(game)}"
    )


def format_ladder_pending_message() -> str:
    return ":monkey_face: 사다리 내려갑니다. 결과는 잠깐 뒤에 공개할게요!"


def format_ladder_reveal_message(game: dict[str, Any]) -> str:
    return ":monkey_face: 사다리 결과 공개!\n\n" + format_ladder_result_lines(game)


def ladder_path_points(
    start: int,
    rungs: list[set[int]],
    x_positions: list[int],
    y_top: int,
    row_gap: int,
    y_bottom: int,
) -> list[tuple[float, float]]:
    position = start
    points: list[tuple[float, float]] = [(x_positions[position], y_top)]
    for row_index, row in enumerate(rungs):
        y = y_top + (row_index + 1) * row_gap
        points.append((x_positions[position], y))
        if position in row:
            position += 1
            points.append((x_positions[position], y))
        elif position - 1 in row:
            position -= 1
            points.append((x_positions[position], y))
    points.append((x_positions[position], y_bottom))
    return points


def point_at_progress(points: list[tuple[float, float]], progress: float) -> tuple[float, float]:
    segments: list[tuple[tuple[float, float], tuple[float, float], float]] = []
    total = 0.0
    for start, end in zip(points, points[1:]):
        length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
        segments.append((start, end, length))
        total += length
    if total <= 0:
        return points[-1]

    target = total * min(max(progress, 0.0), 1.0)
    traveled = 0.0
    for start, end, length in segments:
        if traveled + length >= target:
            ratio = 0 if length == 0 else (target - traveled) / length
            return (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
        traveled += length
    return points[-1]


def draw_ladder_frame(
    size: tuple[int, int],
    x_positions: list[int],
    y_top: int,
    row_gap: int,
    y_bottom: int,
    rungs: list[set[int]],
    dot_positions: list[tuple[float, float]],
    players: list[str],
    bottom: list[str],
) -> Any:
    if Image is None or ImageDraw is None or ImageFont is None:
        raise RuntimeError("Pillow가 설치되어 있지 않습니다.")

    image = Image.new("RGB", size, "#f8fafc")
    draw = ImageDraw.Draw(image)
    label_font = ladder_font(16)
    line_color = "#1f2937"
    muted = "#64748b"

    for index, x in enumerate(x_positions):
        draw.line((x, y_top, x, y_bottom), fill=line_color, width=3)
        player_label = f"{index + 1}. {shorten_ladder_label(players[index])}"
        bottom_label = f"{index + 1}. {shorten_ladder_label(bottom[index])}"
        draw_centered_text(draw, x, 14, player_label, label_font, muted)
        draw_centered_text(draw, x, y_bottom + 14, bottom_label, label_font, muted)

    for row_index, row in enumerate(rungs):
        y = y_top + (row_index + 1) * row_gap
        for pair in row:
            draw.line((x_positions[pair], y, x_positions[pair + 1], y), fill=line_color, width=3)

    for index, (x, y) in enumerate(dot_positions):
        color = LADDER_DOT_COLORS[index % len(LADDER_DOT_COLORS)]
        radius = 7
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="#ffffff", width=2)

    return image.convert("P", palette=Image.ADAPTIVE, colors=64)


def ladder_frames_per_player(column_count: int) -> int:
    target_frame_count = int((LADDER_TARGET_ANIMATION_SECONDS * 1000) / LADDER_FRAME_DURATION_MS)
    return max(8, min(14, target_frame_count // max(column_count, 1)))


def render_ladder_gif(game: dict[str, Any]) -> bytes:
    if Image is None or ImageDraw is None or ImageFont is None:
        raise RuntimeError("Pillow가 설치되어 있지 않습니다.")

    players = game["players"]
    bottom = game["bottom"]
    rungs = game["rungs"]
    column_count = len(players)
    width = max(520, min(980, 135 * column_count))
    margin = 64
    usable = width - margin * 2
    x_positions = [margin + round(usable * index / (column_count - 1)) for index in range(column_count)]
    y_top = 72
    row_gap = 24
    y_bottom = y_top + (len(rungs) + 1) * row_gap
    height = y_bottom + 72
    size = (width, height)

    paths = [ladder_path_points(index, rungs, x_positions, y_top, row_gap, y_bottom) for index in range(column_count)]
    start_positions = [point_at_progress(path, 0.0) for path in paths]
    final_positions = [point_at_progress(path, 1.0) for path in paths]
    frames_per_player = ladder_frames_per_player(column_count)
    frames = []
    durations = []

    initial_frame = draw_ladder_frame(size, x_positions, y_top, row_gap, y_bottom, rungs, start_positions, players, bottom)
    frames.append(initial_frame)
    durations.append(LADDER_INITIAL_HOLD_MS)

    for active_index, path in enumerate(paths):
        for frame_index in range(frames_per_player):
            progress = frame_index / (frames_per_player - 1)
            dot_positions = []
            for index in range(column_count):
                if index < active_index:
                    dot_positions.append(final_positions[index])
                elif index == active_index:
                    dot_positions.append(point_at_progress(path, progress))
                else:
                    dot_positions.append(start_positions[index])
            frames.append(draw_ladder_frame(size, x_positions, y_top, row_gap, y_bottom, rungs, dot_positions, players, bottom))
            durations.append(LADDER_FRAME_DURATION_MS)

    final_frame = draw_ladder_frame(size, x_positions, y_top, row_gap, y_bottom, rungs, final_positions, players, bottom)
    frames.append(final_frame)
    durations.append(LADDER_FINAL_HOLD_MS)

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
    )
    return buffer.getvalue()


def post_ladder_result_later(channel: str, game: dict[str, Any]) -> None:
    def worker() -> None:
        try:
            time.sleep(LADDER_RESULT_DELAY_SECONDS)
            post_slack_message(channel, format_ladder_reveal_message(game))
        except Exception as exc:
            print(f"사다리 결과 지연 전송 실패: {exc}", file=sys.stderr)

    threading.Thread(target=worker, daemon=True).start()


def post_ladder_response(channel: str, game: dict[str, Any], thread_ts: str | None = None) -> None:
    try:
        gif_data = render_ladder_gif(game)
        upload_slack_file(channel, "ladder.gif", gif_data, "사다리타기 진행 중", format_ladder_pending_message(), "image/gif")
        post_ladder_result_later(channel, game)
    except Exception as exc:
        print(f"사다리 GIF 생성/업로드 실패: {exc}", file=sys.stderr)
        post_slack_message(channel, format_ladder_text(game), thread_ts)


def format_end_reminder(meal: str) -> str:
    meal_label = MEAL_LABELS[meal]
    return f"<!channel>\n:monkey: 몽키가 알려드려요! {meal_label}시간 종료까지 10분 남았어요."


def format_start_notice_reminder(meal: str) -> str:
    meal_label = MEAL_LABELS[meal]
    return f"<!channel>\n:monkey_face: 몽키가 알려드려요! {meal_label}시간 10분 전이에요."


def format_kakao_reminder(post: dict[str, Any], target: datetime, meal: str) -> tuple[str, str, str | None]:
    title = post.get("title") if isinstance(post.get("title"), str) else f"{target.month}월 {target.day}일({WEEKDAY_SHORT_LABELS[target.weekday()]}) {MEAL_SOURCE_LABELS[meal]} 메뉴"
    body = format_menu_lines(extract_post_text(post)) or "메뉴 본문이 비어 있어요."
    image_url = extract_post_image_url(post)
    message = (
        "<!channel>\n"
        f":monkey_face: 오늘 {MEAL_LABELS[meal]} 메뉴가 올라왔어요!\n"
        f"{title}\n{body}"
    )
    return message, title, image_url


def slack_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN이 설정되어 있지 않습니다.")

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(f"Slack API 오류: {result}")
    return result


def slack_form_api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN이 설정되어 있지 않습니다.")

    encoded_payload = {
        key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        for key, value in payload.items()
    }
    data = urllib.parse.urlencode(encoded_payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://slack.com/api/{method}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(f"Slack API 오류: {result}")
    return result


def post_slack_message(
    channel: str,
    text: str,
    thread_ts: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
    force_thread: bool = False,
) -> None:
    payload: dict[str, Any] = {
        "channel": channel,
        "text": text,
        "mrkdwn": True,
        "link_names": True,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    if blocks:
        payload["blocks"] = blocks
    if thread_ts and (force_thread or env_bool("SLACK_REPLY_IN_THREAD", False)):
        payload["thread_ts"] = thread_ts
    slack_api("chat.postMessage", payload)


def post_slack_ephemeral(channel: str, user_id: str, text: str) -> None:
    slack_api(
        "chat.postEphemeral",
        {
            "channel": channel,
            "user": user_id,
            "text": text,
            "mrkdwn": True,
            "link_names": True,
            "unfurl_links": False,
            "unfurl_media": False,
        },
    )


def upload_slack_file(
    channel: str,
    filename: str,
    data: bytes,
    title: str,
    initial_comment: str,
    content_type: str = "application/octet-stream",
) -> None:
    upload = slack_form_api(
        "files.getUploadURLExternal",
        {
            "filename": filename,
            "length": len(data),
            "alt_txt": title,
        },
    )
    upload_url = upload.get("upload_url")
    file_id = upload.get("file_id")
    if not isinstance(upload_url, str) or not isinstance(file_id, str):
        raise RuntimeError(f"Slack 업로드 URL 응답이 이상합니다: {upload}")

    req = urllib.request.Request(
        upload_url,
        data=data,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(data)),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Slack 파일 업로드 실패: HTTP {response.status}")

    slack_form_api(
        "files.completeUploadExternal",
        {
            "files": [{"id": file_id, "title": title}],
            "channel_id": channel,
            "initial_comment": initial_comment,
        },
    )


def post_kakao_reminder(channel: str, post: dict[str, Any], target: datetime, meal: str) -> bool:
    message, title, image_url = format_kakao_reminder(post, target, meal)
    if image_url:
        errors: list[str] = []
        for candidate in kakao_image_url_candidates(image_url):
            try:
                data, content_type = fetch_bytes(candidate)
                filename = f"kakao-{meal}-{target.strftime('%Y%m%d')}.jpg"
                upload_slack_file(channel, filename, data, title, message, content_type)
                return True
            except Exception as exc:
                errors.append(f"{candidate}: {exc}")
        raise RuntimeError("카카오 이미지 업로드 실패: " + " / ".join(errors))
    post_slack_message(channel, message)
    return False


def ask_openai(
    text: str,
    history: list[dict[str, str]] | None = None,
    user_memories: list[str] | None = None,
    persona_instruction: str | None = None,
    current_user_id: str | None = None,
) -> str | None:
    if not env_bool("OPENAI_ENABLED", True):
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    sections: list[str] = []
    if user_memories:
        memory_text = render_user_memory_text(user_memories)
        if memory_text:
            sections.append(f"사용자 기억:\n{memory_text}")
    if history:
        history_text = render_history_text(history)
        if history_text:
            sections.append(f"최근 대화 맥락:\n{history_text}")
    if current_user_id:
        sections.append(f"현재 말 건 사용자: <@{current_user_id}>")
    sections.append(f"최신 사용자 메시지:\n{text}")
    prompt_input = "\n\n".join(sections)

    instructions = (
        "너는 사내 슬랙 채널의 한국어 봇 '몽키'다. "
        "사람들 대화에 같이 있는 친구처럼 자연스럽게 답한다. "
        "짧게 받아치는 게 어울리면 짧게, 설명이나 추천이 필요하면 충분히 자세히 말한다. "
        "메뉴, 세탁, 예약, 공지 같은 기능성 명령은 별도 시스템 기능이 처리하므로 일반 대화에서는 실행한 척하지 않는다. "
        "Slack 마크다운 강조를 쓰지 않는다. 특히 **굵게**, *기울임* 같은 별표 강조를 쓰지 말고 일반 문장으로 답한다. "
        "사용자가 자신을 깎아내리면 단정하지 말고 부드럽게 받아준다. "
        "사용자 기억과 최근 대화 맥락이 있으면 자연스럽게 반영하되, 매번 노골적으로 들먹이지는 말고 필요한 만큼만 참고한다."
    )
    if persona_instruction:
        instructions += f" 대상 사용자 전용 말투 설정: {persona_instruction}"

    body: dict[str, Any] = {
        "model": os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
        "instructions": instructions,
        "input": prompt_input,
        "max_output_tokens": 700,
    }

    reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT")
    if reasoning_effort:
        body["reasoning"] = {"effort": reasoning_effort}

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"OpenAI API 오류: {exc.code} {detail}", file=sys.stderr)
        return None
    except Exception as exc:
        print(f"OpenAI 호출 실패: {exc}", file=sys.stderr)
        return None

    answer = response_output_text(result)
    return answer or None


def clean_openai_answer(text: str) -> str:
    text = re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\1", text)
    return text.strip()


def fallback_response(user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    return (
        f"{mention}:monkey_face: 메뉴는 `점심`, `저녁`, `내일 점심`, `토요일 저녁`처럼 물어봐 주세요.\n"
        f"잡담 답변까지 쓰려면 `.env`에 `OPENAI_API_KEY`를 넣으면 돼요 :banana:"
    )


def laundry_status_url() -> str:
    return os.getenv("LAUNDRY_STATUS_URL", DEFAULT_LAUNDRY_STATUS_URL).strip()


def parse_laundry_status_command(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.strip().lower())
    if not normalized:
        return False
    return any(keyword in normalized for keyword in LAUNDRY_COMMAND_KEYWORDS)


def fetch_laundry_status() -> dict[str, Any]:
    url = laundry_status_url()
    if not url:
        raise RuntimeError("세탁 API 주소가 설정되어 있지 않아요. `LAUNDRY_STATUS_URL`을 살아있는 `/api/status` 주소로 설정해야 해요.")
    payload = request_json("GET", url)
    if not isinstance(payload, dict):
        raise RuntimeError("세탁 API 응답 형식이 이상해요.")
    return payload


def format_laundry_fetch_error(exc: Exception) -> str:
    configured_url = laundry_status_url() or "(unset)"
    if isinstance(exc, urllib.error.HTTPError):
        return f":monkey_face: 세탁 서버가 HTTP {exc.code}로 응답했어요. `LAUNDRY_STATUS_URL`을 확인해야 해요."
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, socket.gaierror):
            return (
                ":monkey_face: 세탁 서버 주소를 못 찾고 있어요. "
                "전에 쓰던 임시 Cloudflare 주소가 꺼졌거나 바뀐 것 같아요. "
                f"`LAUNDRY_STATUS_URL`을 살아있는 주소로 바꿔야 해요. 현재 값: `{configured_url}`"
            )
        if isinstance(reason, TimeoutError):
            return ":monkey_face: 세탁 서버가 시간 안에 응답하지 않아요. 잠깐 뒤에 다시 시도해줘요."
        return f":monkey_face: 세탁 서버에 연결하지 못했어요. `{reason}`"
    if isinstance(exc, RuntimeError) and "LAUNDRY_STATUS_URL" in str(exc):
        return f":monkey_face: {exc}"
    return f":monkey_face: 세탁 현황을 가져오다가 오류가 났어요. `{exc}`"


def laundry_remaining_minutes(timer: Any) -> int:
    if not isinstance(timer, dict):
        return 0
    return int(timer.get("remainHour") or 0) * 60 + int(timer.get("remainMinute") or 0)


def laundry_timer_label(timer: Any) -> str:
    remaining = laundry_remaining_minutes(timer)
    if remaining <= 0:
        return ""
    hours, minutes = divmod(remaining, 60)
    if hours and minutes:
        return f"{hours}시간 {minutes}분"
    if hours:
        return f"{hours}시간"
    return f"{minutes}분"


def laundry_real_error(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip()
    if not normalized:
        return ""
    if normalized.upper() in {"0", "NONE", "NO_ERROR", "OK", "NORMAL"}:
        return ""
    return normalized


def laundry_machine_info(machine: Any) -> dict[str, Any]:
    if not isinstance(machine, dict):
        return {"state": "UNKNOWN", "label": "응답 없음", "timer": "", "available": False}

    run_state = machine.get("runState")
    raw_state = run_state.get("currentState") if isinstance(run_state, dict) else None
    state = str(raw_state or "POWER_OFF")
    timer = machine.get("timer")
    if state == "ERROR" and laundry_remaining_minutes(timer) > 0:
        state = "RUNNING"

    state_label = LAUNDRY_STATE_LABELS.get(state, state)
    error = laundry_real_error(machine.get("errorState"))
    if state == "ERROR" or (error and state not in LAUNDRY_RUNNING_STATES):
        return {
            "state": state,
            "label": f"{state_label} ({error})" if error else state_label,
            "timer": "",
            "available": False,
        }

    timer_label = laundry_timer_label(timer)
    return {
        "state": state,
        "label": state_label,
        "timer": timer_label if state in LAUNDRY_RUNNING_STATES else "",
        "available": state in LAUNDRY_AVAILABLE_STATES and not timer_label,
    }


def format_laundry_machine_compact(machine: Any) -> str:
    info = laundry_machine_info(machine)
    if info["available"]:
        return "가능"
    if info["timer"]:
        return f"{info['label']} {info['timer']}"
    return str(info["label"])


def format_laundry_device_field(device: dict[str, Any], tower: Any) -> dict[str, str]:
    if not isinstance(tower, dict):
        value = f"*No.{device['id']}*\n응답 없음"
    else:
        washer = format_laundry_machine_compact(tower.get("washer"))
        dryer = format_laundry_machine_compact(tower.get("dryer"))
        value = f"*No.{device['id']}*\n{LAUNDRY_MACHINE_EMOJIS['washer']} 세탁 `{washer}`\n{LAUNDRY_MACHINE_EMOJIS['dryer']} 건조 `{dryer}`"
    return {"type": "mrkdwn", "text": value}


def format_laundry_status(status_map: dict[str, Any], now: datetime, user_id: str | None = None) -> str:
    local_now = now.astimezone(get_timezone())
    lines = [f"🫧 *세탁 현황* 💨 `{local_now.strftime('%H:%M')}` 기준"]

    for zone in ("men", "common", "women"):
        devices = [device for device in LAUNDRY_DEVICES if device["zone"] == zone]
        device_ids = [str(device["id"]) for device in devices]
        lines.extend(["", f"*{LAUNDRY_ZONE_LABELS[zone]}* `No.{device_ids[0]}-{device_ids[-1]}`"])
        for device in devices:
            tower = status_map.get(device["name"])
            if not isinstance(tower, dict):
                lines.extend([f"*No.{device['id']}*", "응답 없음"])
                continue
            washer = format_laundry_machine_compact(tower.get("washer"))
            dryer = format_laundry_machine_compact(tower.get("dryer"))
            lines.extend(
                [
                    f"*No.{device['id']}*",
                    f"{LAUNDRY_MACHINE_EMOJIS['washer']} 세탁 `{washer}`",
                    f"{LAUNDRY_MACHINE_EMOJIS['dryer']} 건조 `{dryer}`",
                ]
            )

    return "\n".join(lines)


def format_laundry_status_blocks(status_map: dict[str, Any], now: datetime, user_id: str | None = None) -> list[dict[str, Any]]:
    local_now = now.astimezone(get_timezone())
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🫧 세탁 현황 💨", "emoji": True},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"`{local_now.strftime('%H:%M')}` 기준"}],
        },
    ]

    for zone in ("men", "common", "women"):
        devices = [device for device in LAUNDRY_DEVICES if device["zone"] == zone]
        device_ids = [str(device["id"]) for device in devices]
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{LAUNDRY_ZONE_LABELS[zone]}* `No.{device_ids[0]}-{device_ids[-1]}`",
                },
            }
        )
        blocks.append(
            {
                "type": "section",
                "fields": [format_laundry_device_field(device, status_map.get(device["name"])) for device in devices],
            }
        )

    return blocks

COACHING_ROOM_TIME_TOKEN_PATTERN = r"(?:(?:오전|오후)\s*)?[0-2]?\d(?::[0-5]\d|시(?:\s*[0-5]\d\s*분?)?)?"
COACHING_ROOM_TIME_RE = re.compile(
    r"^\s*(?:(오전|오후)\s*)?([0-2]?\d)(?::([0-5]\d)|시(?:\s*([0-5]\d)\s*분?)?)?\s*$"
)
COACHING_ROOM_RANGE_RE = re.compile(
    rf"(?P<start>{COACHING_ROOM_TIME_TOKEN_PATTERN})\s*(?:부터|에서|~|-|–|—)\s*"
    rf"(?P<end>{COACHING_ROOM_TIME_TOKEN_PATTERN})\s*(?:까지)?"
)


def coaching_room_base_url() -> str:
    return os.getenv("COACHING_ROOM_BASE_URL", DEFAULT_COACHING_ROOM_BASE_URL).strip().rstrip("/")


def coaching_room_nicknames() -> list[str]:
    configured = env_csv("COACHING_ROOM_NICKNAMES")
    if configured:
        return configured

    legacy = os.getenv("COACHING_ROOM_NICKNAME", "").strip()
    if legacy:
        return [legacy]

    return list(DEFAULT_COACHING_ROOM_NICKNAMES)


def coaching_room_nickname() -> str:
    return random.choice(coaching_room_nicknames())


def coaching_room_match_nicknames() -> set[str]:
    return set(coaching_room_nicknames()) | set(LEGACY_COACHING_ROOM_NICKNAMES)


def coaching_room_allowed(user_id: str | None) -> bool:
    allowed_user_ids = set(env_csv("COACHING_ROOM_ALLOWED_USER_IDS"))
    if not allowed_user_ids:
        return True
    return bool(user_id and user_id in allowed_user_ids)


def coaching_room_random_name_user_ids() -> set[str]:
    if "COACHING_ROOM_RANDOM_NAME_USER_IDS" in os.environ:
        return set(env_csv("COACHING_ROOM_RANDOM_NAME_USER_IDS"))
    return set(DEFAULT_COACHING_ROOM_RANDOM_NAME_USER_IDS)


def sanitize_coaching_room_nickname(value: str | None) -> str:
    nickname = re.sub(r"\s+", " ", value or "").strip()
    if len(nickname) > 20:
        nickname = nickname[:20].rstrip()
    return nickname if len(nickname) >= 2 else "코칭실 예약"


def slack_user_display_name(user_id: str | None) -> str:
    if not user_id:
        return "코칭실 예약"
    try:
        result = slack_api("users.info", {"user": user_id})
        user = result.get("user", {})
        profile = user.get("profile", {}) if isinstance(user, dict) else {}
        for key in ("display_name", "real_name", "display_name_normalized", "real_name_normalized"):
            value = profile.get(key) if isinstance(profile, dict) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
        value = user.get("name") if isinstance(user, dict) else None
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as exc:
        print(f"Slack user name lookup failed({user_id}): {exc}", file=sys.stderr)
    return user_id


def choose_coaching_room_nickname(user_id: str | None) -> str:
    if user_id and user_id in coaching_room_random_name_user_ids():
        return sanitize_coaching_room_nickname(coaching_room_nickname())
    return sanitize_coaching_room_nickname(slack_user_display_name(user_id))


def format_coaching_room_room_label(room_id: Any) -> str:
    text = str(room_id or "").strip()
    if not text:
        return "코칭실"
    if re.fullmatch(r"\d+", text):
        return f"{text}호"
    return text


def generate_coaching_room_cancel_pin() -> str:
    return f"{random.SystemRandom().randrange(0, 10000):04d}"


def open_slack_dm_channel(user_id: str) -> str:
    result = slack_api("conversations.open", {"users": user_id})
    channel = result.get("channel", {})
    channel_id = channel.get("id") if isinstance(channel, dict) else None
    if not isinstance(channel_id, str) or not channel_id:
        raise RuntimeError(f"DM 채널을 열지 못했어요: {result}")
    return channel_id


def format_coaching_room_pin_message(result: dict[str, Any]) -> str:
    reservation = result.get("reservation", {})
    pin = result.get("cancel_pin")
    room_id = result["room_id"]
    room_label = format_coaching_room_room_label(room_id)
    date = result["date"]
    start_time = result["start_time"]
    end_time = result["end_time"]
    nickname = reservation.get("nickname", "코칭실 예약") if isinstance(reservation, dict) else "코칭실 예약"
    text = (
        ":monkey_face: 코칭실 예약 비밀번호예요.\n"
        f"방: {room_label}\n"
        f"날짜: {date}\n"
        f"시간: {start_time}-{end_time}\n"
        f"제목: {nickname}\n"
        f"비밀번호: `{pin}`"
    )
    return text


def post_coaching_room_pin_dm(user_id: str, result: dict[str, Any]) -> None:
    channel = open_slack_dm_channel(user_id)
    post_slack_message(channel, format_coaching_room_pin_message(result))


def post_coaching_room_pin_private(
    user_id: str,
    result: dict[str, Any],
    fallback_channel: str | None = None,
) -> str:
    text = format_coaching_room_pin_message(result)
    if fallback_channel and fallback_channel.startswith("D"):
        post_slack_message(fallback_channel, text)
        return "dm"

    try:
        post_coaching_room_pin_dm(user_id, result)
        return "dm"
    except Exception:
        if not fallback_channel:
            raise
        ephemeral_text = text + "\n\n_이 메시지는 본인에게만 보여요._"
        post_slack_ephemeral(fallback_channel, user_id, ephemeral_text)
        return "ephemeral"


def coaching_room_period_hint(text: str) -> str | None:
    if re.search(r"\b오전\b|아침", text):
        return "오전"
    if re.search(r"\b오후\b|저녁|밤", text):
        return "오후"
    return None


def parse_coaching_room_time_token(
    token: str,
    inherited_period: str | None = None,
) -> tuple[int, int, str | None, bool] | None:
    match = COACHING_ROOM_TIME_RE.fullmatch(token.strip())
    if not match:
        return None

    period, hour_text, minute_a, minute_b = match.groups()
    hour = int(hour_text)
    minute = int(minute_a or minute_b or "0")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    effective_period = period
    if effective_period is None and inherited_period and 1 <= hour <= 11:
        effective_period = inherited_period

    if effective_period == "오전" and hour == 12:
        hour = 0
    elif effective_period == "오후" and 1 <= hour < 12:
        hour += 12

    ambiguous = False
    return hour, minute, effective_period, ambiguous


def format_coaching_room_time(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def coaching_room_site_minute(time_text: str) -> int:
    hour, minute = [int(part) for part in time_text.split(":")]
    return ((hour * 60 + minute) - 540) % 1440


def coaching_room_date_from_text(text: str, now: datetime) -> tuple[str | None, str | None]:
    local_now = now.astimezone(get_timezone())
    today = local_now.date()

    if re.search(r"\b(내일|모레)\b", text):
        return None, "코칭실 예약은 현재 당일 예약만 받을게요. 오전 9시 이후 당일 날짜로 다시 말해줘요."

    explicit = re.search(r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", text)
    if explicit:
        year, month, day = [int(part) for part in explicit.groups()]
        try:
            requested = datetime(year, month, day, tzinfo=local_now.tzinfo).date()
        except ValueError:
            return None, "날짜가 조금 이상해요. 예: `2026-06-05 307호 23:00부터 00:00까지 예약`"
        if requested != today:
            return None, "코칭실 예약은 현재 당일 예약만 받을게요."

    explicit_short = re.search(r"\b(\d{1,2})[./-](\d{1,2})\b", text)
    if explicit_short and not explicit:
        month, day = [int(part) for part in explicit_short.groups()]
        try:
            requested = datetime(today.year, month, day, tzinfo=local_now.tzinfo).date()
        except ValueError:
            return None, "날짜가 조금 이상해요. 예: `6/5 307호 23:00부터 00:00까지 예약`"
        if requested != today:
            return None, "코칭실 예약은 현재 당일 예약만 받을게요."

    if local_now.weekday() == 6:
        return None, "일요일은 코칭실 예약 대상에서 제외할게요."
    if local_now.hour < 9:
        return None, "코칭실 예약은 당일 오전 9시 이후에 열리면 잡을 수 있어요."

    return today.isoformat(), None


def compact_coaching_room_prefix_ok(prefix: str) -> bool:
    text = prefix.strip()
    if not text:
        return True
    text = re.sub(r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b", "", text)
    text = re.sub(r"\b\d{1,2}[./-]\d{1,2}\b", "", text)
    text = re.sub(r"\b(오늘|코칭실|코칭|예약)\b", "", text)
    return not text.strip()


def coaching_room_title_from_tail(tail: str) -> str | None:
    text = re.sub(r"\s+", " ", tail or "").strip()
    if not text:
        return None

    command_words = r"(?:예약(?:해(?:줘|주세요)?)?|잡아\s*(?:줘|주세요)?|잡아|해\s*(?:줘|주세요)|해줘|해주세요|부탁(?:해|드려요|드립니다)?)"
    label_words = r"(?:제목|방이름|방 이름|이름|닉네임)"
    while text:
        previous = text
        text = re.sub(rf"^{label_words}\s*[:：]?\s*", "", text).strip()
        text = re.sub(rf"^{command_words}(?:\s+|$)", "", text).strip()
        text = re.sub(rf"(?:^|\s+){command_words}$", "", text).strip()
        text = re.sub(r"\s*(?:으로|로)$", "", text).strip()
        if text == previous:
            break

    if len(text) < 2:
        return None
    return sanitize_coaching_room_nickname(text)


def compact_coaching_room_tail_ok(tail: str) -> bool:
    text = tail.strip()
    if not text:
        return True
    if coaching_room_title_from_tail(text):
        return True
    text = re.sub(r"^(예약|예약해|예약해줘|잡아|잡아줘|잡아 줘|해줘|부탁)\b", "", text).strip()
    return not text


def find_coaching_room_reference(text: str) -> tuple[str, int, int] | None:
    candidates: list[tuple[int, int, str]] = []

    number_match = COACHING_ROOM_NUMBER_RE.search(text)
    if number_match:
        candidates.append((number_match.start(), number_match.end(), number_match.group(1)))

    alias_match = COACHING_ROOM_SECOND_FLOOR_ALIAS_RE.search(text)
    if alias_match:
        alias_number = alias_match.group(1) or alias_match.group(2)
        candidates.append((alias_match.start(), alias_match.end(), f"회의실{alias_number}"))

    if not candidates:
        return None

    start, end, room_id = min(candidates, key=lambda item: item[0])
    return room_id, start, end


def parse_coaching_room_reservation_command(text: str, now: datetime) -> tuple[dict[str, str] | None, str | None]:
    stripped = text.strip()
    room_ref = find_coaching_room_reference(stripped)
    has_booking_word = bool(re.search(r"예약|잡아|잡아줘|잡아 줘", stripped))
    after_room = stripped[room_ref[2] :] if room_ref else ""
    range_match = COACHING_ROOM_RANGE_RE.search(after_room) if room_ref else None
    compact_command = False
    if room_ref and range_match:
        compact_command = compact_coaching_room_prefix_ok(stripped[: room_ref[1]]) and compact_coaching_room_tail_ok(after_room[range_match.end() :])

    looks_like_coaching_room = "코칭실" in stripped or "코칭" in stripped or bool(room_ref and (has_booking_word or compact_command))
    if not looks_like_coaching_room:
        return None, None
    if not room_ref:
        return None, "방 번호를 못 찾았어요. 예: `307호 23:00부터 00:00까지 예약 잡아줘`"

    room_id, room_start, _ = room_ref
    if room_id not in COACHING_ROOM_IDS:
        return None, f"{format_coaching_room_room_label(room_id)}는 예약 가능한 코칭실 목록에 없어요."

    if not range_match:
        return None, "시간 범위를 못 찾았어요. 예: `307호 오후 9시부터 오후 11시까지 예약 잡아줘`"

    period_hint = coaching_room_period_hint(stripped)
    start = parse_coaching_room_time_token(range_match.group("start"), period_hint)
    if start is None:
        return None, "시작 시간 형식을 다시 확인해줘요."

    start_hour, start_minute, start_period, start_ambiguous = start
    end_inherited_period = start_period if start_period else period_hint
    end = parse_coaching_room_time_token(range_match.group("end"), end_inherited_period)
    if end is None:
        return None, "종료 시간 형식을 다시 확인해줘요."

    end_hour, end_minute, _, end_ambiguous = end
    if start_ambiguous or end_ambiguous:
        return None, "시간을 다시 확인해줘요. 숫자만 쓰면 24시간제로 보고, 오후는 `13-15` 또는 `오후 2시부터 오후 3시까지`처럼 적어줘요."

    start_time = format_coaching_room_time(start_hour, start_minute)
    end_time = format_coaching_room_time(end_hour, end_minute)
    start_site_minute = coaching_room_site_minute(start_time)
    end_site_minute = coaching_room_site_minute(end_time)
    duration = end_site_minute - start_site_minute
    if duration <= 0:
        return None, "종료 시간이 시작 시간보다 뒤여야 해요. 자정은 `00:00`으로 적으면 돼요."
    if duration > COACHING_ROOM_MAX_DURATION_MINUTES:
        return None, f"코칭실 예약은 한 번에 최대 {COACHING_ROOM_MAX_DURATION_MINUTES // 60}시간까지만 받을게요."

    date_source = f"{stripped[: room_start]} {after_room[range_match.end() :]}"
    date, date_error = coaching_room_date_from_text(date_source, now)
    if date_error:
        return None, date_error
    if date is None:
        return None, "예약 날짜를 정하지 못했어요."

    title = coaching_room_title_from_tail(after_room[range_match.end() :])
    return {
        "room_id": room_id,
        "date": date,
        "start_time": start_time,
        "end_time": end_time,
        "title": title or "",
    }, None


def coaching_room_active_reservations(schedule: dict[str, Any], room_id: str) -> list[dict[str, Any]]:
    reservations = schedule.get("reservations", [])
    if not isinstance(reservations, list):
        return []
    return [
        item
        for item in reservations
        if isinstance(item, dict)
        and item.get("roomId") == room_id
        and item.get("status", "active") == "active"
    ]


def coaching_room_reservation_overlaps(reservation: dict[str, Any], start_minute: int, end_minute: int) -> bool:
    try:
        existing_start = int(reservation["startMinute"])
        existing_end = int(reservation["endMinute"])
    except (KeyError, TypeError, ValueError):
        return False
    return existing_start < end_minute and existing_end > start_minute


def create_coaching_room_reservation(command: dict[str, str], user_id: str | None = None) -> dict[str, Any]:
    base_url = coaching_room_base_url()
    match_nicknames = coaching_room_match_nicknames()
    room_id = command["room_id"]
    date = command["date"]
    start_time = command["start_time"]
    end_time = command["end_time"]
    explicit_title = command.get("title", "").strip()
    if explicit_title:
        explicit_title = sanitize_coaching_room_nickname(explicit_title)
    if explicit_title:
        match_nicknames.add(explicit_title)
    start_minute = coaching_room_site_minute(start_time)
    end_minute = coaching_room_site_minute(end_time)

    query = urllib.parse.urlencode({"date": date})
    schedule = request_json("GET", f"{base_url}/api/schedule?{query}")
    room_reservations = coaching_room_active_reservations(schedule, room_id)

    for reservation in room_reservations:
        if (
            reservation.get("nickname") in match_nicknames
            and reservation.get("date") == date
            and reservation.get("startTime") == start_time
            and reservation.get("endTime") == end_time
        ):
            return {"status": "already", "reservation": reservation, **command}

    conflicts = [
        reservation
        for reservation in room_reservations
        if coaching_room_reservation_overlaps(reservation, start_minute, end_minute)
    ]
    if conflicts:
        return {"status": "conflict", "conflicts": conflicts, **command}

    cancel_pin = generate_coaching_room_cancel_pin()
    nickname = explicit_title or choose_coaching_room_nickname(user_id)
    payload = {
        "roomId": room_id,
        "nickname": nickname,
        "date": date,
        "startTime": start_time,
        "endTime": end_time,
        "cancelPin": cancel_pin,
    }
    created = request_json("POST", f"{base_url}/api/reservations", payload)
    return {"status": "created", "reservation": created, "cancel_pin": cancel_pin, **command}


def format_coaching_room_result(
    result: dict[str, Any],
    user_id: str | None = None,
    pin_delivery: str | None = None,
) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    room_id = result["room_id"]
    room_label = format_coaching_room_room_label(room_id)
    date = result["date"]
    start_time = result["start_time"]
    end_time = result["end_time"]
    status = result["status"]

    if status == "created":
        reservation = result.get("reservation", {})
        reservation_id = reservation.get("id", "")
        nickname = reservation.get("nickname", "") if isinstance(reservation, dict) else ""
        id_line = f"\nID: `{reservation_id}`" if reservation_id else ""
        title_line = f"\n제목: {nickname}" if nickname else ""
        pin_line = "비밀번호는 개인 메시지로 보냈어요."
        if pin_delivery == "ephemeral":
            pin_line = "비밀번호는 본인에게만 보이는 메시지로 보냈어요."
        elif pin_delivery == "failed":
            pin_line = "예약은 됐는데 비밀번호 전송에 실패했어요. 관리자에게 바로 알려줘요."
        return (
            f"{mention}:monkey_face: 코칭실 예약 잡았어요.\n"
            f"방: {room_label}\n"
            f"날짜: {date}\n"
            f"시간: {start_time}-{end_time}"
            f"{title_line}"
            f"{id_line}\n"
            f"{pin_line}"
        )
    if status == "already":
        reservation = result.get("reservation", {})
        nickname = reservation.get("nickname", "") if isinstance(reservation, dict) else ""
        title_line = f"\n제목: {nickname}" if nickname else ""
        return (
            f"{mention}:monkey_face: 이미 같은 코칭실 예약이 잡혀 있어요.\n"
            f"방: {room_label}\n"
            f"날짜: {date}\n"
            f"시간: {start_time}-{end_time}"
            f"{title_line}"
        )
    if status == "conflict":
        lines = [
            f"{mention}:monkey_face: 그 시간은 이미 예약이랑 겹쳐요.",
            f"요청: {date} {room_label} {start_time}-{end_time}",
        ]
        for item in result.get("conflicts", [])[:5]:
            lines.append(f"- {item.get('nickname', '예약')} {item.get('startTime')}-{item.get('endTime')}")
        return "\n".join(lines)
    return f"{mention}:monkey_face: 코칭실 예약 처리 결과를 읽지 못했어요."


def format_coaching_room_usage(user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    return (
        f"{mention}:monkey_face: 코칭실 예약은 이렇게 말해줘요.\n"
        "- `307 21-23`\n"
        "- `307 21-23 알고리즘 스터디`\n"
        "- `307 23-00 제목 야간 회고`\n"
        "- `307 23-00`\n"
        "- `회의실5 13-15`\n"
        "- `307호 23:00부터 00:00까지 예약 잡아줘`\n"
        "- `307호 오후 9시부터 오후 11시까지 프로젝트 회의로 예약해줘`\n"
        "숫자만 쓰면 24시간제로 봐요. 오후는 `13-15`처럼 적거나 `오후 2시`처럼 말해줘요."
    )


def coaching_room_status_date_from_text(text: str, now: datetime) -> str:
    local_now = now.astimezone(get_timezone())
    today = local_now.date()

    relative_match = re.search(r"\b(오늘|내일|모레)\b", text)
    if relative_match:
        offset = {"오늘": 0, "내일": 1, "모레": 2}[relative_match.group(1)]
        return (today + timedelta(days=offset)).isoformat()

    explicit = re.search(r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", text)
    if explicit:
        year, month, day = [int(part) for part in explicit.groups()]
        return datetime(year, month, day, tzinfo=local_now.tzinfo).date().isoformat()

    explicit_short = re.search(r"\b(\d{1,2})[./-](\d{1,2})\b", text)
    if explicit_short:
        month, day = [int(part) for part in explicit_short.groups()]
        return datetime(today.year, month, day, tzinfo=local_now.tzinfo).date().isoformat()

    return today.isoformat()


def parse_coaching_room_status_command(text: str, now: datetime) -> dict[str, str | None] | None:
    stripped = text.strip()
    if not stripped:
        return None

    compact = re.sub(r"\s+", "", stripped)
    room_ref = find_coaching_room_reference(stripped)
    status_like = any(word in compact for word in ("현황", "상태", "비었", "비어", "예약현황"))
    room_context = "코칭" in stripped or "방" in stripped or "회의실" in stripped or bool(room_ref) or "예약현황" in compact
    if not (status_like and room_context):
        return None

    room_id = room_ref[0] if room_ref else None
    if room_id and room_id not in COACHING_ROOM_IDS:
        return {"error": f"{format_coaching_room_room_label(room_id)}는 코칭실 목록에 없어요.", "date": None, "room_id": None}

    try:
        date = coaching_room_status_date_from_text(stripped, now)
    except ValueError:
        return {"error": "날짜가 조금 이상해요. 예: `오늘 307 현황`, `6/8 코칭 현황`", "date": None, "room_id": room_id}

    return {"date": date, "room_id": room_id, "error": None}


def fetch_coaching_room_status(command: dict[str, str | None]) -> dict[str, Any]:
    date = command["date"]
    if not isinstance(date, str):
        raise RuntimeError("예약 현황 날짜를 정하지 못했어요.")

    query = urllib.parse.urlencode({"date": date})
    schedule = request_json("GET", f"{coaching_room_base_url()}/api/schedule?{query}")
    room_id = command.get("room_id")
    reservations = schedule.get("reservations", [])
    if not isinstance(reservations, list):
        reservations = []

    active = [
        item
        for item in reservations
        if isinstance(item, dict)
        and item.get("status", "active") == "active"
        and (room_id is None or item.get("roomId") == room_id)
    ]
    active.sort(key=lambda item: (int(item.get("startMinute", 0)), str(item.get("roomId", "")), int(item.get("endMinute", 0))))
    return {"date": date, "room_id": room_id, "reservations": active}


def format_coaching_room_status(result: dict[str, Any], user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    date = result["date"]
    room_id = result.get("room_id")
    room_label = format_coaching_room_room_label(room_id)
    title = f"{date} {room_label} 예약 현황" if room_id else f"{date} 코칭실 예약 현황"
    reservations = result.get("reservations", [])
    if not reservations:
        empty_target = room_label if room_id else "코칭실"
        return f"{mention}:monkey_face: {title}\n{empty_target} 예약이 없어요."

    lines = [f"{mention}:monkey_face: {title}"]
    for item in reservations[:30]:
        item_room_label = format_coaching_room_room_label(item.get("roomId"))
        lines.append(
            f"- {item_room_label} {item.get('startTime')}-{item.get('endTime')} {item.get('nickname', '예약')}"
        )
    if len(reservations) > 30:
        lines.append(f"외 {len(reservations) - 30}건 더 있어요.")
    return "\n".join(lines)


def parse_coaching_room_user_reservations_command(text: str) -> dict[str, str] | None:
    stripped = text.strip()
    compact = re.sub(r"\s+", "", stripped)
    if compact in {
        "내코칭예약",
        "내코칭실예약",
        "내코칭",
        "내코칭상태",
        "내코칭실상태",
        "내코칭현황",
        "내코칭실현황",
        "내예약",
        "내상태",
        "내현황",
        "내방",
        "내방예약",
        "내방상태",
        "내방현황",
        "내예약현황",
        "코칭예약목록",
        "코칭실예약목록",
        "코칭상태",
        "코칭실상태",
        "방예약목록",
    }:
        return {"action": "list"}

    register_match = re.match(
        r"^(?:코칭실?|방)\s*(?:예약\s*)?(?:등록|저장)\s+([0-9a-fA-F]{6,}(?:-[0-9a-fA-F-]+)?)\s+(\d{4,8})$",
        stripped,
    )
    if register_match:
        return {"action": "register", "target": register_match.group(1).strip(), "cancel_pin": register_match.group(2).strip()}

    if compact in {"취소", "예약취소"}:
        return {"action": "ambiguous_cancel"}
    if compact in {"코칭취소", "코칭실취소", "방취소", "코칭예약취소", "코칭실예약취소", "방예약취소"}:
        return {"action": "cancel", "target": ""}
    if compact in {"방금취소", "방금예약취소", "최근취소", "최근예약취소"}:
        return {"action": "cancel", "target": "__latest__"}

    cancel_match = re.match(r"^(?:코칭실?|방)\s*(?:예약\s*)?(?:취소|예약취소)\s+(.+)$", stripped, re.S)
    if cancel_match:
        target = cancel_match.group(1).strip()
        return {"action": "cancel", "target": target}

    prefix_cancel_match = re.match(r"^(?:취소|예약취소)\s+(?:코칭실?|방)\s+(.+)$", stripped, re.S)
    if prefix_cancel_match:
        target = prefix_cancel_match.group(1).strip()
        return {"action": "cancel", "target": target}

    if "취소" in stripped:
        if find_coaching_room_reference(stripped):
            return {"action": "cancel", "target": stripped}

    return None


def active_coaching_room_records_for_user(user_id: str | None, now: datetime) -> list[dict[str, str]]:
    if not user_id:
        return []
    today = now.astimezone(get_timezone()).date().isoformat()
    records = [
        record
        for record in load_coaching_room_reservations()
        if record.get("created_by") == user_id
        and record.get("status", "active") == "active"
        and record.get("date", "") >= today
    ]
    records.sort(key=lambda item: (item["date"], item["start_time"], item["room_id"]))
    return records


def format_my_coaching_room_reservations(records: list[dict[str, str]], user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    if not records:
        return f"{mention}:monkey_face: 몽키가 기억하는 내 코칭실 예약이 없어요."

    lines = [f"{mention}:monkey_face: 내 코칭실 예약이에요."]
    for record in records[:15]:
        short_id = record["id"][:8]
        room_label = format_coaching_room_room_label(record["room_id"])
        lines.append(
            f"- `{short_id}` / {record['date']} {room_label} {record['start_time']}-{record['end_time']} / {record['nickname']}"
        )
    if len(records) > 15:
        lines.append(f"외 {len(records) - 15}건 더 있어요.")
    lines.append("취소: `취소`, `방금 취소`, `306 취소`, `306 14-15 취소`")
    return "\n".join(lines)


def coaching_room_cancel_time_from_text(text: str, now: datetime) -> dict[str, str] | None:
    room_ref = find_coaching_room_reference(text)
    if not room_ref:
        return None
    room_id, room_start, room_end = room_ref
    if room_id not in COACHING_ROOM_IDS:
        return None

    after_room = text[room_end:]
    range_match = COACHING_ROOM_RANGE_RE.search(after_room)
    if not range_match:
        return None

    period_hint = coaching_room_period_hint(text)
    start = parse_coaching_room_time_token(range_match.group("start"), period_hint)
    if start is None:
        return None
    start_hour, start_minute, start_period, _ = start
    end = parse_coaching_room_time_token(range_match.group("end"), start_period if start_period else period_hint)
    if end is None:
        return None
    end_hour, end_minute, _, _ = end
    date_source = f"{text[: room_start]} {after_room[range_match.end() :]}"
    return {
        "room_id": room_id,
        "date": coaching_room_status_date_from_text(date_source, now),
        "start_time": format_coaching_room_time(start_hour, start_minute),
        "end_time": format_coaching_room_time(end_hour, end_minute),
    }


def find_coaching_room_record_to_cancel(
    records: list[dict[str, str]],
    target: str,
    now: datetime,
) -> tuple[dict[str, str] | None, str | None]:
    cleaned = target.strip()
    compact = re.sub(r"\s+", "", cleaned)
    if not records:
        return None, "몽키가 기억하는 내 코칭실 예약이 없어요."
    if not compact:
        if len(records) == 1:
            return records[0], None
        return None, "예약이 여러 개예요. `내예약`으로 확인하고 `306 취소` 또는 `306 14-15 취소`처럼 말해줘요."
    if compact == "__latest__":
        latest = sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)[0]
        return latest, None

    identifier_match = re.search(r"[0-9a-fA-F]{6,}(?:-[0-9a-fA-F-]+)?", cleaned)
    if identifier_match:
        identifier = identifier_match.group(0).lower()
        matches = [record for record in records if record["id"].lower().startswith(identifier)]
        if not matches:
            return None, "`내 코칭 예약`에서 취소할 예약 ID를 확인해줘요."
        if len(matches) > 1:
            return None, "예약 ID 앞부분이 겹쳐요. ID를 조금 더 길게 적어줘요."
        return matches[0], None

    by_time = coaching_room_cancel_time_from_text(cleaned, now)
    if by_time:
        matches = [
            record
            for record in records
            if record["room_id"] == by_time["room_id"]
            and record["date"] == by_time["date"]
            and record["start_time"] == by_time["start_time"]
            and record["end_time"] == by_time["end_time"]
        ]
        if not matches:
            return None, "그 시간대에 몽키가 기억하는 내 예약이 없어요. `내 코칭 예약`으로 확인해줘요."
        if len(matches) > 1:
            return None, "같은 시간 예약이 여러 개예요. `코칭 취소 예약ID앞8자리`로 취소해줘요."
        return matches[0], None

    room_ref = find_coaching_room_reference(cleaned)
    if room_ref:
        room_id = room_ref[0]
        room_label = format_coaching_room_room_label(room_id)
        matches = [record for record in records if record["room_id"] == room_id]
        if not matches:
            return None, f"몽키가 기억하는 내 {room_label} 예약이 없어요."
        if len(matches) > 1:
            return None, f"{room_label} 예약이 여러 개예요. `내예약`으로 확인하고 시간까지 같이 적어줘요."
        return matches[0], None

    if compact:
        matches = [record for record in records if record["id"].lower().startswith(compact.lower())]
        if len(matches) == 1:
            return matches[0], None

    return None, "`코칭 취소 예약ID앞8자리` 또는 `306 14-15 취소`처럼 말해줘요."


def cancel_coaching_room_reservation(record: dict[str, str], now: datetime) -> dict[str, Any]:
    result = request_json(
        "POST",
        f"{coaching_room_base_url()}/api/reservations/{urllib.parse.quote(record['id'])}/cancel",
        {"cancelPin": record["cancel_pin"]},
    )
    mark_coaching_room_reservation_canceled(record["id"], now)
    return {"status": "canceled", "record": record, "response": result}


def register_existing_coaching_room_reservation(
    reservation_id_prefix: str,
    cancel_pin: str,
    user_id: str,
    now: datetime,
) -> tuple[dict[str, str] | None, str | None]:
    identifier = reservation_id_prefix.strip().lower()
    if len(identifier) < 6:
        return None, "예약 ID는 앞 6자리 이상 적어줘요."

    date = now.astimezone(get_timezone()).date().isoformat()
    query = urllib.parse.urlencode({"date": date})
    schedule = request_json("GET", f"{coaching_room_base_url()}/api/schedule?{query}")
    reservations = schedule.get("reservations", [])
    if not isinstance(reservations, list):
        reservations = []

    matches = [
        item
        for item in reservations
        if isinstance(item, dict)
        and item.get("status", "active") == "active"
        and isinstance(item.get("id"), str)
        and item["id"].lower().startswith(identifier)
    ]
    if not matches:
        return None, "오늘 예약 중 그 ID를 찾지 못했어요. ID를 다시 확인해줘요."
    if len(matches) > 1:
        return None, "예약 ID 앞부분이 겹쳐요. ID를 조금 더 길게 적어줘요."

    reservation = matches[0]
    result = {
        "status": "created",
        "room_id": str(reservation.get("roomId", "")),
        "date": str(reservation.get("date", date)),
        "start_time": str(reservation.get("startTime", "")),
        "end_time": str(reservation.get("endTime", "")),
        "cancel_pin": cancel_pin,
        "reservation": {
            "id": str(reservation.get("id", "")),
            "nickname": str(reservation.get("nickname", "코칭실 예약")),
        },
    }
    save_created_coaching_room_reservation(result, user_id, now)

    records = [
        record
        for record in load_coaching_room_reservations()
        if record["id"] == result["reservation"]["id"] and record.get("created_by") == user_id
    ]
    if not records:
        return None, "예약은 찾았는데 몽키 저장소에 등록하지 못했어요."
    return records[0], None


def format_coaching_room_register_result(record: dict[str, str], user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    room_label = format_coaching_room_room_label(record["room_id"])
    return (
        f"{mention}:monkey_face: 코칭실 예약을 내 목록에 등록했어요.\n"
        f"ID: `{record['id'][:8]}`\n"
        f"방: {room_label}\n"
        f"날짜: {record['date']}\n"
        f"시간: {record['start_time']}-{record['end_time']}\n"
        f"제목: {record['nickname']}"
    )


def format_coaching_room_cancel_result(result: dict[str, Any], user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    record = result["record"]
    room_label = format_coaching_room_room_label(record["room_id"])
    return (
        f"{mention}:monkey_face: 코칭실 예약 취소했어요.\n"
        f"방: {room_label}\n"
        f"날짜: {record['date']}\n"
        f"시간: {record['start_time']}-{record['end_time']}\n"
        f"제목: {record['nickname']}"
    )


def parse_user_id_lookup_command(text: str) -> bool:
    stripped = re.sub(r"\s+", "", text.strip().lower())
    return stripped in {
        "내아이디",
        "내id",
        "내slackid",
        "내슬랙id",
        "내슬랙아이디",
        "아이디",
        "slackid",
    }


def format_user_id_lookup(user_id: str | None) -> str:
    if not user_id:
        return ":monkey_face: Slack user ID를 찾지 못했어요."
    return f"<@{user_id}> :monkey_face: 네 Slack user ID는 `{user_id}`예요."


SCHEDULE_TIME_PATTERN = r"(?:(오전|오후)\s*)?([0-2]?\d)(?::([0-5]\d)|시(?:\s*([0-5]\d)\s*분?)?)"


def parse_schedule_time_parts(period: str | None, hour_text: str, minute_text: str | None) -> tuple[int, int] | None:
    hour = int(hour_text)
    minute = int(minute_text or "0")
    if period == "오전" and hour == 12:
        hour = 0
    elif period == "오후" and hour < 12:
        hour += 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def localized_datetime_label(moment: datetime) -> str:
    local = moment.astimezone(get_timezone())
    weekday = WEEKDAY_SHORT_LABELS[local.weekday()]
    return local.strftime(f"%Y-%m-%d({weekday}) %H:%M")


def build_scheduled_datetime(base_date: datetime, hour: int, minute: int) -> datetime:
    return base_date.replace(hour=hour, minute=minute, second=0, microsecond=0)


def parse_schedule_request(raw: str, now: datetime) -> tuple[datetime | None, str, str | None]:
    text = raw.strip()
    if not text:
        return None, "", "예약할 시간과 내용을 같이 적어줘요."

    time_pattern = SCHEDULE_TIME_PATTERN

    match = re.match(rf"^(오늘|내일|모레)\s+{time_pattern}\s+(.+)$", text, re.S)
    if match:
        relative, period, hour_text, minute_a, minute_b, body = match.groups()
        parsed_time = parse_schedule_time_parts(period, hour_text, minute_a or minute_b)
        if parsed_time is None:
            return None, "", "시간 형식을 다시 확인해줘요."
        day_offset = {"오늘": 0, "내일": 1, "모레": 2}[relative]
        send_at = build_scheduled_datetime(now + timedelta(days=day_offset), *parsed_time)
        return validate_schedule_time(send_at, body, now)

    match = re.match(rf"^(\d{{4}})[./-](\d{{1,2}})[./-](\d{{1,2}})\s+{time_pattern}\s+(.+)$", text, re.S)
    if match:
        year_text, month_text, day_text, period, hour_text, minute_a, minute_b, body = match.groups()
        return parse_absolute_schedule_time(int(year_text), int(month_text), int(day_text), period, hour_text, minute_a or minute_b, body, now)

    match = re.match(rf"^(\d{{1,2}})[./-](\d{{1,2}})\s+{time_pattern}\s+(.+)$", text, re.S)
    if match:
        month_text, day_text, period, hour_text, minute_a, minute_b, body = match.groups()
        return parse_absolute_schedule_time(now.year, int(month_text), int(day_text), period, hour_text, minute_a or minute_b, body, now)

    match = re.match(rf"^(\d{{1,2}})월\s*(\d{{1,2}})일\s+{time_pattern}\s+(.+)$", text, re.S)
    if match:
        month_text, day_text, period, hour_text, minute_a, minute_b, body = match.groups()
        return parse_absolute_schedule_time(now.year, int(month_text), int(day_text), period, hour_text, minute_a or minute_b, body, now)

    match = re.match(rf"^{time_pattern}\s+(.+)$", text, re.S)
    if match:
        period, hour_text, minute_a, minute_b, body = match.groups()
        parsed_time = parse_schedule_time_parts(period, hour_text, minute_a or minute_b)
        if parsed_time is None:
            return None, "", "시간 형식을 다시 확인해줘요."
        send_at = build_scheduled_datetime(now, *parsed_time)
        if send_at <= now:
            send_at += timedelta(days=1)
        return validate_schedule_time(send_at, body, now)

    return None, "", "시간은 `오늘 18:00`, `내일 09:30`, `2026-04-27 18:00`처럼 적어줘요."


def parse_absolute_schedule_time(
    year: int,
    month: int,
    day: int,
    period: str | None,
    hour_text: str,
    minute_text: str | None,
    body: str,
    now: datetime,
) -> tuple[datetime | None, str, str | None]:
    parsed_time = parse_schedule_time_parts(period, hour_text, minute_text)
    if parsed_time is None:
        return None, "", "시간 형식을 다시 확인해줘요."
    try:
        send_at = datetime(year, month, day, parsed_time[0], parsed_time[1], tzinfo=now.tzinfo)
    except ValueError:
        return None, "", "날짜가 조금 이상해요. 월/일을 다시 확인해줘요."
    if send_at <= now and year == now.year:
        try:
            send_at = datetime(year + 1, month, day, parsed_time[0], parsed_time[1], tzinfo=now.tzinfo)
        except ValueError:
            return None, "", "날짜가 조금 이상해요. 월/일을 다시 확인해줘요."
    return validate_schedule_time(send_at, body, now)


def validate_schedule_time(send_at: datetime, body: str, now: datetime) -> tuple[datetime | None, str, str | None]:
    message = body.strip()
    if not message:
        return None, "", "예약할 메시지 내용도 같이 적어줘요."
    if send_at <= now:
        return None, "", "이미 지난 시간은 예약할 수 없어요."
    if send_at > now + timedelta(days=366):
        return None, "", "예약은 최대 1년 뒤까지만 받을게요."
    return send_at, message, None


def parse_scheduled_dm_command(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if re.fullmatch(r"예약\s*목록|예약목록", stripped):
        return {"action": "list"}

    cancel_match = re.fullmatch(r"예약\s*취소\s+(\S+)|예약취소\s+(\S+)", stripped)
    if cancel_match:
        return {"action": "cancel", "id": cancel_match.group(1) or cancel_match.group(2)}

    schedule_match = re.match(r"^(전체\s*예약|전체예약|예약\s*공지|예약공지|예약)\b(.*)$", stripped, re.S)
    if not schedule_match:
        return None

    command = schedule_match.group(1).replace(" ", "")
    default_target = "personal"
    if command == "전체예약":
        default_target = "announce_all"
    elif command == "예약공지":
        default_target = "announce"
    return {
        "action": "create",
        "target": default_target,
        "body": schedule_match.group(2).strip(),
    }


def resolve_scheduled_target(body: str, default_target: str) -> tuple[str, str]:
    text = body.strip()
    match = re.match(r"^(전체\s*공지|공지)\b(.*)$", text, re.S)
    if not match:
        return default_target, text
    command = match.group(1).replace(" ", "")
    message = match.group(2).strip()
    return ("announce_all" if command == "전체공지" else "announce"), message


def schedule_announcement_allowed(target: str, user_id: str | None) -> bool:
    if target == "personal":
        return True
    return announcement_allowed(user_id)


def generate_schedule_id(now: datetime) -> str:
    suffix = random.SystemRandom().randrange(0x1000, 0xFFFF)
    return f"R{now.strftime('%m%d%H%M%S')}{suffix:04X}"


def add_scheduled_message(
    channel: str,
    send_at: datetime,
    text: str,
    created_by: str | None,
    now: datetime,
    target: str,
) -> dict[str, str]:
    message = {
        "id": generate_schedule_id(now),
        "channel": channel,
        "text": text,
        "send_at": send_at.isoformat(),
        "created_at": now.isoformat(),
        "created_by": created_by or "",
        "target": target,
    }
    with SCHEDULED_MESSAGES_LOCK:
        messages = load_scheduled_messages_unlocked()
        messages.append(message)
        save_scheduled_messages_unlocked(messages)
    return message


def cancel_scheduled_message(message_id: str, user_id: str | None) -> bool:
    with SCHEDULED_MESSAGES_LOCK:
        messages = load_scheduled_messages_unlocked()
        remaining = [
            message
            for message in messages
            if message["id"] != message_id or (user_id and message.get("created_by") not in {"", user_id})
        ]
        if len(remaining) == len(messages):
            return False
        save_scheduled_messages_unlocked(remaining)
    return True


def scheduled_messages_for_user(user_id: str | None) -> list[dict[str, str]]:
    messages = load_scheduled_messages()
    if not user_id:
        return []
    return [message for message in messages if message.get("created_by") in {"", user_id}]


def scheduled_target_label(target: str) -> str:
    if target == "announce_all":
        return "채널 전체공지"
    if target == "announce":
        return "채널 공지"
    return "개인 DM"


def format_schedule_usage(user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    return (
        f"{mention}:monkey_face: 예약은 몽키 DM에서 이렇게 써요.\n"
        "- 예약 오늘 18:00 물 마시기\n"
        "- 예약 오늘 18:00 공지 칠판 투표 한 번만 확인해주세요\n"
        "- 예약 내일 09:00 전체공지 좋은 아침입니다\n"
        "- 예약목록\n"
        "- 예약취소 R0427180000ABCD"
    )


def format_schedule_created(message: dict[str, str]) -> str:
    send_at = datetime.fromisoformat(message["send_at"])
    preview = normalize_memory_text(message["text"], 120)
    return (
        ":monkey_face: 예약 걸어뒀어요.\n"
        f"ID: {message['id']}\n"
        f"대상: {scheduled_target_label(message.get('target', 'personal'))}\n"
        f"시간: {localized_datetime_label(send_at)}\n"
        f"내용: {preview}"
    )


def format_schedule_list(messages: list[dict[str, str]], user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    if not messages:
        return f"{mention}:monkey_face: 잡혀 있는 예약 메시지가 없어요."

    lines = [f"{mention}:monkey_face: 예약 메시지 목록이에요."]
    for message in messages[:10]:
        send_at = datetime.fromisoformat(message["send_at"])
        preview = normalize_memory_text(message["text"], 70)
        target = scheduled_target_label(message.get("target", "personal"))
        lines.append(f"- {message['id']} / {target} / {localized_datetime_label(send_at)} / {preview}")
    if len(messages) > 10:
        lines.append(f"외 {len(messages) - 10}개 더 있어요.")
    return "\n".join(lines)


def format_schedule_cancel_result(message_id: str, cancelled: bool, user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    if cancelled:
        return f"{mention}:monkey_face: {message_id} 예약을 취소했어요."
    return f"{mention}:monkey_face: {message_id} 예약을 못 찾았어요. `예약목록`으로 ID를 확인해줘요."


def parse_announcement_command(text: str) -> tuple[str, bool] | None:
    match = re.match(r"^\s*(전체\s*공지|공지)\b(.*)$", text, re.S)
    if not match:
        return None
    command = match.group(1).replace(" ", "")
    body = match.group(2).strip()
    return body, command == "전체공지"


def announcement_allowed(user_id: str | None) -> bool:
    allowed_user_ids = set(env_csv("ANNOUNCE_ALLOWED_USER_IDS"))
    if not allowed_user_ids:
        return True
    return bool(user_id and user_id in allowed_user_ids)


def announcement_target_channel(current_channel: str) -> str:
    return os.getenv("SLACK_CHANNEL_ID", "").strip() or current_channel


def format_announcement_usage(user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    return (
        f"{mention}:monkey_face: 공지는 이렇게 쓰면 돼요.\n"
        f"- `공지 오늘 7시에 모여요`\n"
        f"- `전체공지 회식 투표 아직 안 한 분들 부탁드려요`"
    )


def format_announcement_denied(user_id: str | None = None) -> str:
    mention = f"<@{user_id}> " if user_id else ""
    return f"{mention}:monkey_face: 이 공지 기능은 아직 허용된 사람만 쓸 수 있어요."


def prepare_announcement_text(body: str, notify_all: bool) -> str:
    message = body.strip()
    if notify_all and not re.match(r"^(?:<!channel>|@channel)\b", message):
        message = f"<!channel>\n{message}"
    return message


class BotRuntime:
    def __init__(self) -> None:
        self.tz = get_timezone()
        self.processed_event_ids: set[str] = set()
        self.processed_lock = threading.Lock()
        self.reset_lock = threading.Lock()
        self.memory_lock = threading.Lock()
        self.memory = load_memory_store()
        self.user_memory_lock = threading.Lock()
        self.user_memory = load_user_memory_store()
        self.passive_reply_lock = threading.Lock()
        self.passive_reply_at: dict[str, float] = {}
        today = day_key_for(datetime.now(self.tz))
        saved_day = load_memory_day()
        self.memory_day = saved_day or today
        if self.memory_day != today:
            self.memory = {}
            self.user_memory = {}
            save_memory_store(self.memory)
            save_user_memory_store(self.user_memory)
            self.memory_day = today
        save_memory_day(self.memory_day)

    def get_history(self, key: str) -> list[dict[str, str]]:
        with self.memory_lock:
            return [turn.copy() for turn in self.memory.get(key, [])]

    def remember_exchange(self, key: str, user_text: str, answer: str, speaker_id: str | None = None) -> None:
        user_text = user_text.strip()
        answer = strip_leading_reply_mentions(answer)
        if not user_text or not answer:
            return
        with self.memory_lock:
            turns = self.memory.setdefault(key, [])
            user_turn = {"role": "user", "text": user_text}
            if speaker_id:
                user_turn["speaker"] = speaker_id
            turns.append(user_turn)
            turns.append({"role": "assistant", "text": answer})
            self.memory[key] = turns[-MAX_MEMORY_TURNS:]
            save_memory_store(self.memory)

    def remember_observed_message(self, key: str, user_text: str, speaker_id: str | None = None) -> None:
        user_text = user_text.strip()
        if not should_store_channel_context_message(user_text):
            return
        with self.memory_lock:
            turns = self.memory.setdefault(key, [])
            if turns and turns[-1].get("role") == "user" and turns[-1].get("text") == user_text:
                if speaker_id:
                    turns[-1]["speaker"] = speaker_id
            else:
                user_turn = {"role": "user", "text": user_text}
                if speaker_id:
                    user_turn["speaker"] = speaker_id
                turns.append(user_turn)
            self.memory[key] = turns[-MAX_MEMORY_TURNS:]
            save_memory_store(self.memory)

    def passive_reply_allowed(self, channel: str, now: datetime) -> bool:
        cooldown = max(0, env_int("CHANNEL_PASSIVE_COOLDOWN_SECONDS", 10))
        if cooldown <= 0:
            return True
        timestamp = now.timestamp()
        with self.passive_reply_lock:
            last = self.passive_reply_at.get(channel, 0.0)
            if timestamp - last < cooldown:
                return False
            self.passive_reply_at[channel] = timestamp
        return True

    def get_user_memories(self, user_id: str | None) -> list[str]:
        if not user_id:
            return []
        with self.user_memory_lock:
            return list(self.user_memory.get(user_id, []))

    def remember_user_memory(self, user_id: str | None, user_text: str) -> None:
        if not user_id:
            return
        candidate = extract_user_memory(user_text)
        if not candidate:
            return
        with self.user_memory_lock:
            memories = self.user_memory.setdefault(user_id, [])
            memories = [item for item in memories if item != candidate]
            memories.append(candidate)
            self.user_memory[user_id] = memories[-MAX_USER_MEMORIES:]
            save_user_memory_store(self.user_memory)

    def mark_event_seen(self, event_id: str | None) -> bool:
        if not event_id:
            return False
        with self.processed_lock:
            if event_id in self.processed_event_ids:
                return True
            self.processed_event_ids.add(event_id)
            if len(self.processed_event_ids) > 1000:
                self.processed_event_ids = set(list(self.processed_event_ids)[-500:])
        return False

    def reset_memories_if_needed(self, now: datetime) -> None:
        today = day_key_for(now)
        if self.memory_day == today:
            return
        with self.reset_lock:
            if self.memory_day == today:
                return
            with self.memory_lock:
                self.memory = {}
                save_memory_store(self.memory)
            with self.user_memory_lock:
                self.user_memory = {}
                save_user_memory_store(self.user_memory)
            self.memory_day = today
            save_memory_day(today)

    def handle_dm_announcement(
        self,
        text: str,
        channel: str,
        user_id: str | None,
        event_ts: str | None,
    ) -> bool:
        command = parse_announcement_command(text)
        if command is None:
            return False

        body, notify_all = command
        if not announcement_allowed(user_id):
            post_slack_message(channel, format_announcement_denied(user_id), event_ts, force_thread=True)
            return True
        if not body:
            post_slack_message(channel, format_announcement_usage(user_id), event_ts, force_thread=True)
            return True

        target_channel = announcement_target_channel(channel)
        message = prepare_announcement_text(body, notify_all)
        post_slack_message(target_channel, message)
        return True

    def handle_coaching_room_reservation(
        self,
        text: str,
        channel: str,
        user_id: str | None,
        reply_ts: str | None,
        now: datetime,
    ) -> bool:
        command, error = parse_coaching_room_reservation_command(text, now)
        if command is None and error is None:
            return False
        if not coaching_room_allowed(user_id):
            post_slack_message(
                channel,
                f"<@{user_id}> :monkey_face: 코칭실 예약 기능은 아직 허용된 사람만 쓸 수 있어요." if user_id else ":monkey_face: 코칭실 예약 기능은 아직 허용된 사람만 쓸 수 있어요.",
                reply_ts,
                force_thread=True,
            )
            return True
        if error:
            post_slack_message(
                channel,
                f":monkey_face: {error}\n\n{format_coaching_room_usage(user_id)}",
                reply_ts,
                force_thread=True,
            )
            return True

        try:
            result = create_coaching_room_reservation(command, user_id)
            save_created_coaching_room_reservation(result, user_id, now)
            pin_delivery = None
            if result.get("status") == "created" and user_id:
                try:
                    pin_delivery = post_coaching_room_pin_private(user_id, result, channel)
                except Exception as dm_exc:
                    pin_delivery = "failed"
                    print(f"Coaching room PIN DM failed({user_id}): {dm_exc}", file=sys.stderr)
            post_slack_message(channel, format_coaching_room_result(result, user_id, pin_delivery), reply_ts, force_thread=True)
        except Exception as exc:
            post_slack_message(
                channel,
                f":monkey_face: 코칭실 예약 처리 중 오류가 났어요. `{exc}`",
                reply_ts,
                force_thread=True,
            )
        return True

    def handle_coaching_room_user_reservations(
        self,
        text: str,
        channel: str,
        user_id: str | None,
        reply_ts: str | None,
        now: datetime,
    ) -> bool:
        command = parse_coaching_room_user_reservations_command(text)
        if command is None:
            return False
        if not user_id:
            post_slack_message(channel, ":monkey_face: 누가 보낸 명령인지 확인하지 못했어요.", reply_ts, force_thread=True)
            return True

        records = active_coaching_room_records_for_user(user_id, now)
        if command["action"] == "list":
            post_slack_message(channel, format_my_coaching_room_reservations(records, user_id), reply_ts, force_thread=True)
            return True
        if command["action"] == "ambiguous_cancel":
            post_slack_message(
                channel,
                f"<@{user_id}> :monkey_face: 어떤 예약을 취소할지 조금만 더 구체적으로 말해줘요.\n"
                "`코칭 취소`, `방금 예약 취소`, `306 취소`, `306 14-15 취소`처럼 쓰면 돼요.",
                reply_ts,
                force_thread=True,
            )
            return True
        if command["action"] == "register":
            record, error = register_existing_coaching_room_reservation(
                command.get("target", ""),
                command.get("cancel_pin", ""),
                user_id,
                now,
            )
            if error:
                post_slack_message(channel, f"<@{user_id}> :monkey_face: {error}", reply_ts, force_thread=True)
                return True
            if record is None:
                post_slack_message(channel, f"<@{user_id}> :monkey_face: 등록할 예약을 찾지 못했어요.", reply_ts, force_thread=True)
                return True
            post_slack_message(channel, format_coaching_room_register_result(record, user_id), reply_ts, force_thread=True)
            return True

        record, error = find_coaching_room_record_to_cancel(records, command.get("target", ""), now)
        if error:
            post_slack_message(channel, f"<@{user_id}> :monkey_face: {error}", reply_ts, force_thread=True)
            return True
        if record is None:
            post_slack_message(channel, f"<@{user_id}> :monkey_face: 취소할 예약을 찾지 못했어요.", reply_ts, force_thread=True)
            return True

        try:
            result = cancel_coaching_room_reservation(record, now)
            post_slack_message(channel, format_coaching_room_cancel_result(result, user_id), reply_ts, force_thread=True)
        except Exception as exc:
            post_slack_message(
                channel,
                f"<@{user_id}> :monkey_face: 코칭실 예약 취소 중 오류가 났어요. `{exc}`",
                reply_ts,
                force_thread=True,
            )
        return True

    def handle_coaching_room_status(
        self,
        text: str,
        channel: str,
        user_id: str | None,
        reply_ts: str | None,
        now: datetime,
    ) -> bool:
        command = parse_coaching_room_status_command(text, now)
        if command is None:
            return False

        error = command.get("error")
        if error:
            post_slack_message(channel, f":monkey_face: {error}", reply_ts, force_thread=True)
            return True

        try:
            result = fetch_coaching_room_status(command)
            post_slack_message(channel, format_coaching_room_status(result, user_id), reply_ts, force_thread=True)
        except Exception as exc:
            post_slack_message(
                channel,
                f":monkey_face: 코칭실 현황을 가져오다가 오류가 났어요. `{exc}`",
                reply_ts,
                force_thread=True,
            )
        return True

    def handle_laundry_status(
        self,
        text: str,
        channel: str,
        user_id: str | None,
        reply_ts: str | None,
        now: datetime,
    ) -> bool:
        if not parse_laundry_status_command(text):
            return False

        try:
            result = fetch_laundry_status()
            post_slack_message(
                channel,
                format_laundry_status(result, now, user_id),
                blocks=format_laundry_status_blocks(result, now, user_id),
            )
        except Exception as exc:
            post_slack_message(
                channel,
                format_laundry_fetch_error(exc),
            )
        return True

    def handle_user_id_lookup(
        self,
        text: str,
        channel: str,
        user_id: str | None,
        reply_ts: str | None,
    ) -> bool:
        if not parse_user_id_lookup_command(text):
            return False
        post_slack_message(channel, format_user_id_lookup(user_id), reply_ts, force_thread=True)
        return True

    def handle_dm_schedule(
        self,
        text: str,
        channel: str,
        user_id: str | None,
        event_ts: str | None,
        now: datetime,
    ) -> bool:
        command = parse_scheduled_dm_command(text)
        if command is None:
            return False

        action = command["action"]
        if action == "list":
            post_slack_message(channel, format_schedule_list(scheduled_messages_for_user(user_id), user_id), event_ts, force_thread=True)
            return True
        if action == "cancel":
            message_id = command["id"]
            post_slack_message(channel, format_schedule_cancel_result(message_id, cancel_scheduled_message(message_id, user_id), user_id), event_ts, force_thread=True)
            return True

        send_at, body, error = parse_schedule_request(command["body"], now)
        if error:
            post_slack_message(channel, f":monkey_face: {error}\n\n{format_schedule_usage(user_id)}", event_ts, force_thread=True)
            return True

        target, message_body = resolve_scheduled_target(body, command.get("target", "personal"))
        if not message_body:
            post_slack_message(channel, f":monkey_face: 예약할 메시지 내용도 같이 적어줘요.\n\n{format_schedule_usage(user_id)}", event_ts, force_thread=True)
            return True
        if not schedule_announcement_allowed(target, user_id):
            post_slack_message(channel, format_announcement_denied(user_id), event_ts, force_thread=True)
            return True

        target_channel = channel if target == "personal" else announcement_target_channel(channel)
        message = prepare_announcement_text(message_body, target == "announce_all") if target != "personal" else message_body
        scheduled = add_scheduled_message(target_channel, send_at, message, user_id, now, target)
        post_slack_message(channel, format_schedule_created(scheduled), event_ts, force_thread=True)
        return True

    def handle_slack_event(self, payload: dict[str, Any]) -> None:
        event_id = payload.get("event_id")
        if self.mark_event_seen(event_id):
            return

        event = payload.get("event", {})
        subtype = event.get("subtype")
        if event.get("bot_id") or subtype == "bot_message":
            return
        if subtype not in {None, ""}:
            return

        channel = event.get("channel")
        if not isinstance(channel, str) or not channel:
            return

        event_type = event.get("type")
        raw_channel_type = event.get("channel_type")
        channel_type = raw_channel_type if isinstance(raw_channel_type, str) else None
        is_dm = is_direct_message(channel, channel_type)
        is_app_mention = event_type == "app_mention"
        is_message = event_type == "message"
        if not is_app_mention and not is_message:
            return

        raw_text = event.get("text", "")
        text = strip_slack_event_command_text(raw_text if isinstance(raw_text, str) else "")
        called_by_name = has_monkey_call(text)
        if called_by_name:
            text = strip_monkey_call(text)
        if not text and called_by_name:
            text = "몽키야"

        user_id = event.get("user")
        user_id = user_id if isinstance(user_id, str) else None
        event_ts = event.get("ts")
        event_ts = event_ts if isinstance(event_ts, str) else None
        thread_ts = event.get("thread_ts")
        reply_ts = thread_ts if isinstance(thread_ts, str) and thread_ts else event_ts
        is_direct_call = is_dm or is_app_mention or called_by_name
        memory_key = conversation_key(event)
        channel_reply_ts = reply_ts if (is_dm or is_app_mention) else None

        try:
            now = datetime.now(self.tz)
            self.reset_memories_if_needed(now)
            passive_reply = False
            if not is_direct_call:
                if contains_mention_required_command(text):
                    self.remember_observed_message(memory_key, text, user_id)
                    return
                if not should_passively_join_channel_message(text):
                    self.remember_observed_message(memory_key, text, user_id)
                    return
                if not self.passive_reply_allowed(channel, now):
                    self.remember_observed_message(memory_key, text, user_id)
                    return
                passive_reply = True

            if is_direct_call:
                if self.handle_user_id_lookup(text, channel, user_id, channel_reply_ts):
                    return
                if self.handle_dm_announcement(text, channel, user_id, event_ts):
                    return
                if self.handle_laundry_status(text, channel, user_id, channel_reply_ts, now):
                    return
                if self.handle_coaching_room_user_reservations(text, channel, user_id, channel_reply_ts, now):
                    return
                if self.handle_coaching_room_status(text, channel, user_id, channel_reply_ts, now):
                    return
                if self.handle_coaching_room_reservation(text, channel, user_id, channel_reply_ts, now):
                    return
                if is_dm and self.handle_dm_schedule(text, channel, user_id, event_ts, now):
                    return
                ladder_game, ladder_error = build_ladder_game(text)
                if ladder_game is not None:
                    ladder_answer = ":monkey_face: 사다리타기 결과예요!\n\n" + format_ladder_result_lines(ladder_game)
                    post_ladder_response(channel, ladder_game, channel_reply_ts)
                    self.remember_exchange(memory_key, text, ladder_answer, user_id)
                    return
                if ladder_error is not None:
                    post_slack_message(channel, ladder_error, channel_reply_ts)
                    return

            menu = load_menu()
            history = self.get_history(memory_key)
            user_memories = self.get_user_memories(user_id)
            answer = format_menu_response(menu, text, now, user_id=user_id) if is_direct_call else None
            if answer is None:
                ai_answer = ask_openai(text, history, user_memories, user_persona_instruction(user_id), user_id)
                ai_answer = clean_openai_answer(strip_leading_reply_mentions(ai_answer or ""))
                if ai_answer:
                    answer = f"<@{user_id}> {ai_answer}" if user_id and is_direct_call else ai_answer
            if answer is None:
                if passive_reply:
                    self.remember_observed_message(memory_key, text, user_id)
                    return
                answer = fallback_response(user_id=user_id)
            post_slack_message(channel, answer, channel_reply_ts if is_direct_call else None)
            self.remember_exchange(memory_key, text, answer, user_id)
            self.remember_user_memory(user_id, text)
        except Exception as exc:
            print(f"이벤트 처리 실패: {exc}", file=sys.stderr)
            try:
                post_slack_message(channel, f":monkey_face: 앗, 처리 중 오류가 났어요: `{exc}`")
            except Exception as post_exc:
                print(f"오류 안내 전송 실패: {post_exc}", file=sys.stderr)

runtime = BotRuntime()


def verify_slack_signature(headers: Any, body: bytes) -> bool:
    secret = os.getenv("SLACK_SIGNING_SECRET")
    if not secret:
        return True

    timestamp = headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("X-Slack-Signature")
    if not timestamp or not signature:
        return False

    try:
        ts = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - ts) > 60 * 5:
        return False

    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    expected = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class SlackHandler(BaseHTTPRequestHandler):
    server_version = "MonkeySlackBot/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, status: int, text: str) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/health":
            self.send_json(200, {"ok": True, "name": "monkey-slack-bot"})
            return
        self.send_text(404, "not found")

    def do_POST(self) -> None:
        if self.path != "/slack/events":
            self.send_text(404, "not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)

        if not verify_slack_signature(self.headers, body):
            self.send_text(401, "invalid slack signature")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_text(400, "invalid json")
            return

        if payload.get("type") == "url_verification":
            self.send_json(200, {"challenge": payload.get("challenge")})
            return

        if payload.get("type") == "event_callback":
            self.send_json(200, {"ok": True})
            threading.Thread(target=runtime.handle_slack_event, args=(payload,), daemon=True).start()
            return

        self.send_json(200, {"ok": True})


def post_due_scheduled_messages(now: datetime) -> None:
    messages = load_scheduled_messages()
    due_messages: list[dict[str, str]] = []
    for message in messages:
        try:
            send_at = datetime.fromisoformat(message["send_at"])
        except ValueError:
            continue
        if send_at <= now:
            due_messages.append(message)

    if not due_messages:
        return

    sent_ids: set[str] = set()
    for message in due_messages:
        try:
            post_slack_message(message["channel"], message["text"])
            sent_ids.add(message["id"])
        except Exception as exc:
            print(f"예약 메시지 전송 실패({message['id']}): {exc}", file=sys.stderr)

    if not sent_ids:
        return

    with SCHEDULED_MESSAGES_LOCK:
        current = load_scheduled_messages_unlocked()
        remaining = [message for message in current if message["id"] not in sent_ids]
        save_scheduled_messages_unlocked(remaining)


def post_default_schedule_messages(now: datetime, sent: set[str]) -> set[str]:
    channel = os.getenv("SLACK_CHANNEL_ID")
    if not channel or now.weekday() > 5:
        return sent

    current_time = now.strftime("%H:%M")
    for item in DEFAULT_SCHEDULE:
        if item["time"] != current_time:
            continue
        key = f"{now.date()}:{item['time']}:{item['kind']}:{item['meal']}"
        if key in sent:
            continue
        try:
            if item["kind"] == "start_notice":
                text = format_start_notice_reminder(item["meal"])
                post_slack_message(channel, text)
            else:
                text = format_end_reminder(item["meal"])
                post_slack_message(channel, text)
            sent.add(key)
            sent = {entry for entry in sent if entry.startswith(str(now.date()))}
        except Exception as exc:
            print(f"스케줄 알림 실패: {exc}", file=sys.stderr)
    return sent


def start_scheduler() -> None:
    if env_bool("ENABLE_SCHEDULER", True):
        threading.Thread(target=scheduler_loop, daemon=True).start()


def maybe_sync_kakao_menu_data(now: datetime, last_sync_at: datetime | None) -> datetime | None:
    if not env_bool("KAKAO_MENU_AUTO_SYNC", True):
        return last_sync_at
    interval = max(60, env_int("KAKAO_MENU_SYNC_INTERVAL_SECONDS", DEFAULT_KAKAO_SYNC_INTERVAL_SECONDS))
    if last_sync_at is not None and (now - last_sync_at).total_seconds() < interval:
        return last_sync_at
    try:
        result = sync_kakao_menu_data(now)
        if result.get("ok"):
            print(
                f"카카오 메뉴 동기화 완료: posts={result.get('posts')} changed_meals={result.get('changed_meals')} week_start={result.get('week_start')}"
            )
        else:
            print(f"카카오 메뉴 동기화 건너뜀: {result}", file=sys.stderr)
    except Exception as exc:
        print(f"카카오 메뉴 동기화 실패: {exc}", file=sys.stderr)
    return now


def maybe_sync_weekly_menu_image(now: datetime, last_sync_at: datetime | None) -> datetime | None:
    if not env_bool("KAKAO_WEEKLY_MENU_AUTO_SYNC", True):
        return last_sync_at
    if not weekly_menu_check_window(now):
        return last_sync_at
    try:
        if weekly_menu_image_completed(load_weekly_menu_image_state(), load_menu(), week_start_for(now)):
            return last_sync_at
    except Exception:
        pass
    interval = max(60, env_int("KAKAO_WEEKLY_MENU_SYNC_INTERVAL_SECONDS", DEFAULT_KAKAO_WEEKLY_MENU_SYNC_INTERVAL_SECONDS))
    if last_sync_at is not None and (now - last_sync_at).total_seconds() < interval:
        return last_sync_at
    try:
        result = sync_weekly_menu_image(now)
        if result.get("ok"):
            if result.get("skipped"):
                print(f"주간 식단표 이미지 동기화 건너뜀: {result.get('skipped')}")
            else:
                print(
                    f"주간 식단표 이미지 동기화 완료: changed_meals={result.get('changed_meals')} week_start={result.get('week_start')}"
                )
        else:
            print(f"주간 식단표 이미지 동기화 실패/건너뜀: {result}", file=sys.stderr)
    except Exception as exc:
        print(f"주간 식단표 이미지 동기화 실패: {exc}", file=sys.stderr)
    return now


def maybe_post_daily_menu_posts(now: datetime, last_sync_at: datetime | None) -> datetime | None:
    if not env_bool("KAKAO_DAILY_MENU_AUTO_POST", True):
        return last_sync_at
    if not daily_menu_post_check_window(now):
        return last_sync_at
    try:
        if daily_menu_posts_completed(prune_daily_menu_post_state(load_daily_menu_post_state(), now), now):
            return last_sync_at
    except Exception:
        pass
    interval = max(60, env_int("KAKAO_DAILY_MENU_POST_INTERVAL_SECONDS", DEFAULT_KAKAO_DAILY_MENU_POST_INTERVAL_SECONDS))
    if last_sync_at is not None and (now - last_sync_at).total_seconds() < interval:
        return last_sync_at
    try:
        result = sync_and_post_daily_menu_posts(now)
        if result.get("ok"):
            print(
                f"일별 메뉴 포스트 확인 완료: found={result.get('found')} posted={result.get('posted')} skipped={result.get('skipped')}"
            )
        else:
            print(f"일별 메뉴 포스트 확인 실패/건너뜀: {result}", file=sys.stderr)
    except Exception as exc:
        print(f"일별 메뉴 포스트 확인 실패: {exc}", file=sys.stderr)
    return now


def scheduler_loop() -> None:
    tz = get_timezone()
    sent: set[str] = set()
    last_kakao_sync_at: datetime | None = None
    last_weekly_menu_sync_at: datetime | None = None
    last_daily_menu_post_at: datetime | None = None

    while True:
        now = datetime.now(tz)
        last_weekly_menu_sync_at = maybe_sync_weekly_menu_image(now, last_weekly_menu_sync_at)
        last_daily_menu_post_at = maybe_post_daily_menu_posts(now, last_daily_menu_post_at)
        last_kakao_sync_at = maybe_sync_kakao_menu_data(now, last_kakao_sync_at)
        sent = post_default_schedule_messages(now, sent)
        post_due_scheduled_messages(now)
        time.sleep(15)


def run_socket_mode() -> None:
    app_token = os.getenv("SLACK_APP_TOKEN")
    if not app_token:
        raise RuntimeError("SLACK_APP_TOKEN is not set.")
    if SocketModeClient is None or SocketModeResponse is None or WebClient is None:
        raise RuntimeError("Socket Mode requires the slack_sdk package.")

    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("SLACK_BOT_TOKEN is not set.")

    start_scheduler()

    client = SocketModeClient(
        app_token=app_token,
        web_client=WebClient(token=bot_token),
    )

    def process(_: SocketModeClient, req: SocketModeRequest) -> None:
        if req.type != "events_api":
            return
        response = SocketModeResponse(envelope_id=req.envelope_id)
        client.send_socket_mode_response(response)
        threading.Thread(target=runtime.handle_slack_event, args=(req.payload,), daemon=True).start()

    client.socket_mode_request_listeners.append(process)
    print("Starting Slack Socket Mode client")
    print(f"Menu file: {menu_path()}")
    client.connect()
    threading.Event().wait()


def run_server() -> None:
    port = int(os.getenv("PORT", "3000"))
    start_scheduler()

    server = ThreadingHTTPServer(("0.0.0.0", port), SlackHandler)
    print(f"몽키 슬랙봇 실행 중: http://0.0.0.0:{port}")
    print(f"메뉴 파일: {menu_path()}")
    server.serve_forever()


def preview(text: str, now_arg: str | None) -> int:
    tz = get_timezone()
    now = datetime.fromisoformat(now_arg).astimezone(tz) if now_arg else datetime.now(tz)
    if parse_laundry_status_command(text):
        try:
            print(format_laundry_status(fetch_laundry_status(), now))
            return 0
        except Exception as exc:
            print(format_laundry_fetch_error(exc))
            return 1
    menu = load_menu()
    answer = format_menu_response(menu, text, now)
    print(answer or fallback_response())
    return 0


def check_menu() -> int:
    menu = load_menu()
    errors = validate_menu(menu)
    if errors:
        for error in errors:
            print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"메뉴 JSON 정상: {menu_path()}")
    return 0


def main() -> int:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="몽키 슬랙 점심/저녁 알림봇")
    parser.add_argument("--check", action="store_true", help="data/menu.json 문법과 구조를 검사합니다.")
    parser.add_argument("--sync-kakao-menu", action="store_true", help="카카오 채널 일별 메뉴 포스트를 읽어 data/menu.json을 자동 갱신합니다.")
    parser.add_argument("--sync-weekly-menu-image", action="store_true", help="카카오 주간 식단표 이미지를 읽어 data/menu.json을 자동 갱신합니다.")
    parser.add_argument("--post-daily-menu", action="store_true", help="오늘 일별 점심/저녁 카카오 포스트를 찾아 Slack에 전송합니다.")
    parser.add_argument("--preview", metavar="TEXT", help="슬랙 질문에 대한 메뉴 답변을 미리 봅니다.")
    parser.add_argument("--now", metavar="ISO_DATETIME", help="--preview 기준 시각입니다. 예: 2026-04-17T15:11:00+09:00")
    args = parser.parse_args()

    if args.check:
        return check_menu()
    if args.sync_kakao_menu:
        result = sync_kakao_menu_data()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.sync_weekly_menu_image:
        result = sync_weekly_menu_image(force=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.post_daily_menu:
        result = sync_and_post_daily_menu_posts(force=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.preview:
        return preview(args.preview, args.now)

    if os.getenv("SLACK_APP_TOKEN"):
        run_socket_mode()
        return 0

    run_server()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
