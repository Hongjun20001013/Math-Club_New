from __future__ import annotations
from answer_grader import grade_for_db, response_is_correct
from latex_parser import parse_placement_tex_file, parse_tex_file

import json
import os
import sqlite3
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from placement_report_pdf import build_placement_parent_pdf

# =====================================================
# BASIC CONFIG
# =====================================================

APP_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(APP_DIR, ".env"))

# SQLite file. Default: sat.db next to this app. For Render (or similar), mount a
# persistent disk and set DB_PATH to an absolute path on that volume, e.g.
#   /var/data/sat.db
# Otherwise redeploys / restarts may reset the container filesystem.
_db_env = os.environ.get("DB_PATH", "").strip()
if _db_env:
    DB_PATH = _db_env if os.path.isabs(_db_env) else os.path.normpath(os.path.join(APP_DIR, _db_env))
else:
    DB_PATH = os.path.join(APP_DIR, "sat.db")

COMPILED_BANK_PATH = os.path.join(APP_DIR, "data", "question_bank.json")
PLACEMENT_META_PATH = os.path.join(APP_DIR, "data", "placement_meta.json")
DESMOS_API_KEY = os.environ.get("DESMOS_API_KEY", "").strip()
COMPILED_BANK_CACHE = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")


def _production_config_guard() -> None:
    """Warn when obvious secrets misconfiguration on Render."""
    if os.environ.get("RENDER", "").lower() not in ("true", "1", "yes"):
        return
    sk = os.environ.get("SECRET_KEY", "").strip()
    if not sk or sk == "dev-secret-change-me":
        app.logger.warning(
            "SECRET_KEY is missing or still the dev default on Render. "
            "Set SECRET_KEY in Environment or use generateValue in render.yaml."
        )


_production_config_guard()

# =====================================================
# DATABASE
# =====================================================

def get_db() -> sqlite3.Connection:
    if "db" not in g:
        parent = os.path.dirname(os.path.abspath(DB_PATH))
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _table_columns(db: sqlite3.Connection, table: str) -> List[str]:
    cur = db.execute(f"PRAGMA table_info({table})")
    return [str(r[1]) for r in cur.fetchall()]


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS practice_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            domain TEXT NOT NULL,
            topic TEXT NOT NULL,
            qnum INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS practice_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            selected_answer TEXT NOT NULL,
            correct_answer TEXT,
            is_correct INTEGER,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (attempt_id) REFERENCES practice_attempts (id)
        );
        """
    )
    cols = _table_columns(db, "practice_responses")
    if "question_index" not in cols:
        db.execute("ALTER TABLE practice_responses ADD COLUMN question_index INTEGER")
    if "mistake_tags" not in cols:
        db.execute("ALTER TABLE practice_responses ADD COLUMN mistake_tags TEXT")
    if "mistake_note" not in cols:
        db.execute("ALTER TABLE practice_responses ADD COLUMN mistake_note TEXT")
    att_cols = _table_columns(db, "practice_attempts")
    if "placement_student_name" not in att_cols:
        db.execute(
            "ALTER TABLE practice_attempts ADD COLUMN placement_student_name TEXT"
        )
    if "placement_student_grade" not in att_cols:
        db.execute(
            "ALTER TABLE practice_attempts ADD COLUMN placement_student_grade TEXT"
        )
    if "placement_student_math_course" not in att_cols:
        db.execute(
            "ALTER TABLE practice_attempts ADD COLUMN placement_student_math_course TEXT"
        )
    db.commit()


@app.before_request
def ensure_db_initialized():
    if request.endpoint == "health":
        return
    init_db()


@app.before_request
def redirect_legacy_unit2_under_algebra():
    """Unit 2 now lives under domain advanced_math, not algebra."""
    p = request.path or ""
    prefix = "/practice/algebra/"
    if not p.startswith(prefix):
        return None
    tail = p[len(prefix) :]
    if tail.startswith("unit_2") or tail.startswith("2_"):
        return redirect("/practice/advanced_math/" + tail, code=301)
    return None


@app.context_processor
def inject_template_config():
    track_lookup = {t["key"]: t for t in LEARNING_TRACKS}
    active_track = session.get("active_track_label", "Platform")
    p = request.path or "/"
    if p == "/":
        active_track = "Platform"
    elif p.startswith("/practice"):
        active_track = "SAT Math"
    elif p.startswith("/placement"):
        active_track = "Course placement"
    elif p.startswith("/learn/"):
        k = p.split("/learn/", 1)[1].split("/", 1)[0]
        active_track = track_lookup.get(k, {}).get("title", "Platform")

    return {
        "desmos_api_key": DESMOS_API_KEY,
        "active_track_label": active_track,
        "nav_path": p,
        "learning_tracks": LEARNING_TRACKS,
    }


def require_login() -> bool:
    return "user_id" in session


def extract_correct_answer(question: dict) -> str | None:
    """
    Canonical key from compiled question (MCQ letter or SPR value), or None.
    """
    direct_key = question.get("correct_answer") or question.get("answer") or question.get("key")
    if direct_key is None:
        for index_field in ("answer_index", "correct_index"):
            idx = question.get(index_field)
            if isinstance(idx, int) and 0 <= idx < 4:
                return "ABCD"[idx]
        return None
    s = str(direct_key).strip()
    return s if s else None


def _load_placement_meta_file() -> dict:
    if not os.path.isfile(PLACEMENT_META_PATH):
        return {}
    try:
        with open(PLACEMENT_META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _placement_tier_for_course_key(course_key: str) -> int:
    return {
        "algebra_i": 1,
        "geometry": 2,
        "algebra_ii": 3,
        "precalculus": 4,
        "calculus_readiness": 5,
    }.get(course_key, 2)


def _placement_course_recommendation(score_pct: int, meta: dict) -> dict | None:
    for row in meta.get("rubric", []):
        if not isinstance(row, dict):
            continue
        lo = int(row.get("min_percent", 0))
        hi = int(row.get("max_percent", 100))
        if lo <= score_pct <= hi:
            return row
    return None


def _enrich_placement_rec(row: dict, raw_score: int, total_q: int) -> dict:
    out = dict(row)
    lo = int(out.get("min_score", 0))
    hi = int(out.get("max_score", total_q or 70))
    out["band_range"] = f"{lo}-{hi}"
    out["raw_score"] = raw_score
    out["total_q"] = total_q
    ck = str(out.get("course_key") or "")
    out["tier"] = int(out.get("tier") or _placement_tier_for_course_key(ck))
    if not isinstance(out.get("highlights"), list):
        out["highlights"] = []
    return out


def _placement_recommendation(meta: dict, raw_score: int, total_q: int) -> dict | None:
    """Prefer total-score bands (out of 70); fall back to percent rubric."""
    for row in meta.get("score_band_rubric") or []:
        if not isinstance(row, dict):
            continue
        lo = int(row.get("min_score", -1))
        hi = int(row.get("max_score", 999))
        if lo <= raw_score <= hi:
            return _enrich_placement_rec(row, raw_score, total_q)
    if total_q > 0:
        pct = round(100.0 * raw_score / total_q)
        fb = _placement_course_recommendation(pct, meta)
        if isinstance(fb, dict):
            out = dict(fb)
            out.setdefault("title", "Course recommendation")
            out.setdefault("headline", "Estimated placement (percent fallback)")
            out["band_range"] = "-"
            out["raw_score"] = raw_score
            out["total_q"] = total_q
            out["tier"] = int(
                out.get("tier") or _placement_tier_for_course_key(str(out.get("course_key") or ""))
            )
            if not isinstance(out.get("highlights"), list):
                out["highlights"] = []
            return out
    return None


def apply_placement_calculator_flags(questions: List[dict]) -> List[dict]:
    """Attach calculator_allowed from placement_meta (default false if unset)."""
    meta = _load_placement_meta_file()
    m = meta.get("calculator_by_index") or {}
    out: List[dict] = []
    for i, q in enumerate(questions):
        key = str(i + 1)
        raw = m.get(key)
        if raw is None:
            raw = m.get(i)
        allowed = bool(raw) if raw is not None else False
        qc = dict(q)
        qc["calculator_allowed"] = allowed
        out.append(qc)
    return out


def load_compiled_bank() -> Dict[str, Dict[str, List[dict]]]:
    global COMPILED_BANK_CACHE
    if COMPILED_BANK_CACHE is not None:
        return COMPILED_BANK_CACHE
    if not os.path.isfile(COMPILED_BANK_PATH):
        COMPILED_BANK_CACHE = {}
        return COMPILED_BANK_CACHE
    try:
        with open(COMPILED_BANK_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            COMPILED_BANK_CACHE = data
        else:
            COMPILED_BANK_CACHE = {}
    except (OSError, json.JSONDecodeError):
        COMPILED_BANK_CACHE = {}
    return COMPILED_BANK_CACHE


def get_questions_for_topic(domain: str, topic: str, file_path: str) -> List[dict]:
    compiled = load_compiled_bank()
    topic_questions = compiled.get(domain, {}).get(topic)
    if isinstance(topic_questions, list) and topic_questions:
        if domain == "placement":
            return apply_placement_calculator_flags([dict(q) for q in topic_questions])
        return topic_questions

    full_path = os.path.join(APP_DIR, file_path)
    if not os.path.isfile(full_path):
        return []
    try:
        if domain == "placement":
            qs = parse_placement_tex_file(full_path)
        else:
            qs = parse_tex_file(full_path)
    except OSError:
        return []
    if domain == "placement":
        return apply_placement_calculator_flags(qs)
    return qs


# =====================================================
# BANK STRUCTURE
# =====================================================

# Planned SAT Math domains in this workspace (used for roadmap chip counts).
PRACTICE_DOMAIN_TARGET_COUNT = 4

BANKS: Dict[str, Dict[str, str]] = {
    # Unit 1 only (linear equations through inequalities)
    "algebra": {
        "unit_1_all": "Unit_1_Algebra.tex",
        "1_1": "banks/algebra/1_1.tex",
        "1_2": "banks/algebra/1_2.tex",
        "1_3": "banks/algebra/1_3.tex",
        "1_4": "banks/algebra/1_4.tex",
        "1_5": "banks/algebra/1_5.tex",
    },
    # Unit 2 only (advanced math — separate domain from algebra)
    "advanced_math": {
        "unit_2_all": "Unit_2_Advanced_Math.tex",
        "2_1": "banks/algebra/2_1.tex",
        "2_2": "banks/algebra/2_2.tex",
        "2_3": "banks/algebra/2_3.tex",
    },
    "problem_solving": {
        "unit_3_all": "Unit_3_PS_and_Stats.tex",
        "3_1": "banks/problem_solving/3_1.tex",
        "3_2": "banks/problem_solving/3_2.tex",
        "3_3": "banks/problem_solving/3_3.tex",
        "3_4": "banks/problem_solving/3_4.tex",
        "3_5": "banks/problem_solving/3_5.tex",
        "3_6": "banks/problem_solving/3_6.tex",
        "3_7": "banks/problem_solving/3_7.tex",
    },
    # Unit 4: register when bank exists.
    # "geometry": { ... },
    # Course placement (Algebra I/II vs Precalculus vs Calc AB) — see /placement and data/placement_meta.json
    "placement": {
        "placement_full": "Placement_Test.tex",
    },
}

# Landing page copy for /placement — mirrors `latex_parser._placement_part_meta` ranges.
PLACEMENT_LANDING_PARTS: List[Dict[str, str]] = [
    {"code": "I", "range": "1–15", "label": "Foundations & algebra"},
    {"code": "II", "range": "16–30", "label": "Exponents, rationals & functions"},
    {"code": "III", "range": "31–45", "label": "Graphs, geometry & radicals"},
    {"code": "IV", "range": "46–60", "label": "Functions, trig & precalc"},
    {"code": "V", "range": "61–70", "label": "Geometry & advanced readiness"},
]

# Human-readable labels for /practice/<domain> headers
PRACTICE_DOMAIN_TITLES: Dict[str, str] = {
    "algebra": "Algebra — Unit 1",
    "advanced_math": "Advanced Math — Unit 2",
    "problem_solving": "Problem Solving & Data — Unit 3",
    "geometry": "Geometry — Unit 4",
    "placement": "Course placement diagnostic",
}

# Short labels for dashboard / compact UI (avoid repeating long domain strings).
DASHBOARD_TRACK_SHORT: Dict[str, str] = {
    "algebra": "SAT · Algebra",
    "advanced_math": "SAT · Adv. math",
    "problem_solving": "SAT · Data",
    "geometry": "SAT · Geometry",
    "placement": "Placement",
}

def _practice_session_key(domain: str, topic: str) -> str:
    return f"pa_{domain}_{topic}"


def _placement_profile_from_session() -> tuple[str, str, str]:
    """Student info collected on /placement/start before the diagnostic."""
    name = (session.get("placement_student_name") or "").strip()
    grade = (session.get("placement_student_grade") or "").strip()
    course = (session.get("placement_student_math_course") or "").strip()
    return name, grade, course


def _clear_placement_profile_session() -> None:
    session.pop("placement_student_name", None)
    session.pop("placement_student_grade", None)
    session.pop("placement_student_math_course", None)


def _clear_placement_full_session_attempt() -> None:
    """Drop in-progress placement attempt binding so the next run creates a new row."""
    session.pop(_practice_session_key("placement", "placement_full"), None)


def _backfill_placement_student_profile(
    db: sqlite3.Connection, attempt_id: int, domain: str
) -> None:
    """If the browser still holds an old attempt id, attach intake fields once the DB row is empty."""
    if domain != "placement":
        return
    name, grade, course = _placement_profile_from_session()
    if not name:
        return
    row = db.execute(
        "SELECT placement_student_name FROM practice_attempts WHERE id = ? AND domain = 'placement'",
        (attempt_id,),
    ).fetchone()
    if row is None:
        return
    if (str(row["placement_student_name"] or "")).strip():
        return
    db.execute(
        """
        UPDATE practice_attempts
        SET placement_student_name = ?, placement_student_grade = ?, placement_student_math_course = ?
        WHERE id = ?
        """,
        (name, grade or None, course or None, attempt_id),
    )
    db.commit()


# Quick reflection tags after a wrong attempt (shown on reflect + analytics pages).
MISTAKE_TAG_OPTIONS: List[Dict[str, str]] = [
    {"id": "careless", "label": "Careless slip"},
    {"id": "concept", "label": "Concept gap"},
    {"id": "setup", "label": "Setup / modeling error"},
    {"id": "algebra", "label": "Algebra / arithmetic error"},
    {"id": "reading", "label": "Misread the prompt"},
    {"id": "time", "label": "Ran out of time"},
    {"id": "guess", "label": "Guessed"},
    {"id": "other", "label": "Other"},
]

TOPIC_TITLES = {
    "unit_1_all": "Unit 1 – Algebra (full bank)",
    "1_1": "Unit 1.1 – Linear Equations in One Variable",
    "1_2": "Unit 1.2 – Linear Functions",
    "1_3": "Unit 1.3 – Linear Equations in Two Variables",
    "1_4": "Unit 1.4 – Systems of Linear Equations",
    "1_5": "Unit 1.5 – Linear Inequalities",
    "unit_2_all": "Unit 2 – Advanced Math (full bank)",
    "2_1": "Unit 2.1 – Equivalent Expressions",
    "2_2": "Unit 2.2 – Nonlinear Equations & Systems",
    "2_3": "Unit 2.3 – Nonlinear Functions",
    "unit_3_all": "Unit 3 – Problem Solving & Data (full bank)",
    "3_1": "Unit 3.1 – Ratios, rates, proportional relationships, and units",
    "3_2": "Unit 3.2 – Percentages",
    "3_3": "Unit 3.3 – One-variable data: distributions and center/spread",
    "3_4": "Unit 3.4 – Two-variable data: models and scatterplots",
    "3_5": "Unit 3.5 – Probability and conditional probability",
    "3_6": "Unit 3.6 – Inference from sample statistics and margin of error",
    "3_7": "Unit 3.7 – Evaluating statistical claims: studies and experiments",
    "geo_all": "Unit 4 – Geometry (full bank)",
    "psd_all": "Unit 3 – Problem Solving & Data (full bank)",
    "placement_full": "Course placement (full diagnostic)",
}

# catalog: "standardized" = admissions-style exams; "school" = in-school / college curriculum (placement gates level).
LEARNING_TRACKS = [
    {
        "key": "sat",
        "catalog": "standardized",
        "title": "SAT Math",
        "level": "Active",
        "description": "Full adaptive bank—timed feel, instant scoring, shareable session reports.",
        "cta_label": "Enter workspace",
        "cta_href": "/practice",
        "pill": "Live",
    },
    {
        "key": "isee",
        "catalog": "standardized",
        "title": "ISEE Math",
        "level": "Planned",
        "description": "Upper-level quantitative reasoning & QC—same polish as SAT when it ships.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/isee",
        "pill": "Roadmap",
    },
    {
        "key": "placement",
        "catalog": "school",
        "title": "Course placement",
        "level": "Active",
        "description": "70-item diagnostic with printable + in-app reports—lock the right level for honors or AP, then walk into advising with a polished PDF.",
        "cta_label": "Start placement",
        "cta_href": "/placement",
        "pill": "Live",
    },
    {
        "key": "ap_calc",
        "catalog": "school",
        "title": "AP Calculus AB / BC",
        "level": "Planned",
        "description": "AP-style calculus from limits through series. Full bank is on the roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/ap_calc",
        "pill": "Roadmap",
    },
    {
        "key": "ap_stats",
        "catalog": "school",
        "title": "AP Statistics",
        "level": "Planned",
        "description": "Inference-first AP Statistics storyline. Module on the roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/ap_stats",
        "pill": "Roadmap",
    },
    {
        "key": "ap_precalc",
        "catalog": "school",
        "title": "AP Precalculus",
        "level": "Planned",
        "description": "College Board–style precalculus—functions, modeling, trigonometry, and a bridge into AP Calculus. Question bank on the roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/ap_precalc",
        "pill": "Roadmap",
    },
    {
        "key": "multivariable",
        "catalog": "school",
        "title": "Multivariable Calculus",
        "level": "Planned",
        "description": "Honors or early college multivariable calculus—visual-first bank planned.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/multivariable",
        "pill": "Roadmap",
    },
    {
        "key": "linear_algebra",
        "catalog": "school",
        "title": "Linear Algebra",
        "level": "Planned",
        "description": "Matrices and eigensystems for advanced school or early college. Roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/linear_algebra",
        "pill": "Roadmap",
    },
    {
        "key": "diff_eq",
        "catalog": "school",
        "title": "Differential Equations",
        "level": "Planned",
        "description": "ODEs and modeling for honors STEM paths. Roadmap.",
        "cta_label": "Preview roadmap",
        "cta_href": "/learn/diff_eq",
        "pill": "Roadmap",
    },
]


def _pct(correct: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100.0 * correct / total)


def _practice_distinct_answered(db: sqlite3.Connection, user_id: Any, domain: str, topic: str) -> int:
    """How many distinct question indices in this full-bank topic have at least one saved response."""
    if user_id is not None:
        row = db.execute(
            """
            SELECT COUNT(DISTINCT pr.question_index) AS c
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pa.user_id IS ? AND pa.domain = ? AND pa.topic = ?
              AND pr.question_index IS NOT NULL
            """,
            (user_id, domain, topic),
        ).fetchone()
    else:
        row = db.execute(
            """
            SELECT COUNT(DISTINCT pr.question_index) AS c
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pa.user_id IS NULL AND pa.domain = ? AND pa.topic = ?
              AND pr.question_index IS NOT NULL
            """,
            (domain, topic),
        ).fetchone()
    if not row:
        return 0
    return int(row["c"] or 0)


def _dashboard_track_short(domain: str | None) -> str:
    d = (domain or "").strip()
    if not d:
        return "Practice"
    return DASHBOARD_TRACK_SHORT.get(d, d.replace("_", " ").title())


def _session_when_label(created_at: str | None) -> str:
    if not created_at:
        return ""
    s = str(created_at).strip()
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
        d_only = dt.date()
        today = date.today()
        if d_only == today:
            return "Today"
        if (today - d_only).days == 1:
            return "Yesterday"
        return f"{dt.strftime('%b')} {d_only.day}"
    except ValueError:
        return s[:10] if len(s) >= 10 else s


def _topic_practice_href(domain: str, topic_key: str) -> str | None:
    spec = BANKS.get(domain)
    if not isinstance(spec, dict) or topic_key not in spec:
        return None
    return url_for("practice_question", domain=domain, topic=topic_key, qnum=0)


def _build_focus_topics(rows: List[dict]) -> List[dict]:
    """Lowest-accuracy topics with enough graded items to be meaningful; cap list length."""
    min_sample = 3
    with_sample = [t for t in rows if int(t.get("total") or 0) >= min_sample]
    pool = with_sample if with_sample else list(rows)
    pool = sorted(
        pool,
        key=lambda x: (int(x.get("pct") or 0), -int(x.get("total") or 0)),
    )
    out: List[dict] = []
    for t in pool[:4]:
        dom = str(t.get("domain") or "")
        tk = str(t.get("topic_key") or "")
        if not dom or not tk:
            continue
        out.append(
            {
                "track_short": _dashboard_track_short(dom),
                "topic_title": TOPIC_TITLES.get(tk, tk),
                "correct": int(t.get("correct") or 0),
                "total": int(t.get("total") or 0),
                "pct": int(t.get("pct") or 0),
                "practice_href": _topic_practice_href(dom, tk),
            }
        )
    return out


def _dashboard_context() -> dict:
    db = get_db()
    user_id = session.get("user_id")
    where = "WHERE pa.user_id = ?" if user_id else ""
    params: tuple[Any, ...] = (user_id,) if user_id else ()

    attempts_total = db.execute(
        f"SELECT COUNT(*) AS c FROM practice_attempts pa {where}",
        params,
    ).fetchone()["c"]

    graded = db.execute(
        f"""
        SELECT
          SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
          SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        {where}
        """,
        params,
    ).fetchone()
    total_correct = int(graded["correct"] or 0)
    total_graded = int(graded["graded_total"] or 0)

    sat_topic_rows = db.execute(
        f"""
        SELECT pa.domain,
               pa.topic,
               SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
               SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        {where}
        GROUP BY pa.domain, pa.topic
        """,
        params,
    ).fetchall()

    sat_topics: List[dict] = []
    for row in sat_topic_rows:
        gt = int(row["graded_total"] or 0)
        c = int(row["correct"] or 0)
        dom = row["domain"] or "algebra"
        topic_key = str(row["topic"] or "")
        sat_topics.append(
            {
                "domain": dom,
                "topic_key": topic_key,
                "correct": c,
                "total": gt,
                "pct": _pct(c, gt),
            }
        )
    sat_topics.sort(key=lambda x: x["pct"])
    focus_topics = _build_focus_topics(sat_topics)

    recent_rows = db.execute(
        f"""
        SELECT
          pa.id,
          pa.domain,
          pa.topic,
          pa.created_at,
          SUM(CASE WHEN pr.is_correct = 1 THEN 1 ELSE 0 END) AS correct,
          SUM(CASE WHEN pr.is_correct IN (0, 1) THEN 1 ELSE 0 END) AS graded_total
        FROM practice_attempts pa
        LEFT JOIN practice_responses pr ON pr.attempt_id = pa.id
        {where}
        GROUP BY pa.id, pa.domain, pa.topic, pa.created_at
        ORDER BY pa.id DESC
        LIMIT 3
        """,
        params,
    ).fetchall()

    recent_sessions: List[dict] = []
    for row in recent_rows:
        gt = int(row["graded_total"] or 0)
        c = int(row["correct"] or 0)
        dom = row["domain"]
        topic_title = TOPIC_TITLES.get(row["topic"], row["topic"])
        recent_sessions.append(
            {
                "track_short": _dashboard_track_short(dom),
                "topic": topic_title,
                "score_label": f"{c}/{gt}" if gt else "Ungraded",
                "pct": _pct(c, gt),
                "summary_href": (
                    url_for("practice_session_summary", attempt_id=int(row["id"]))
                    if gt
                    else None
                ),
                "when_label": _session_when_label(row["created_at"]),
            }
        )

    compiled = load_compiled_bank()
    sat_bank_total = 0
    for key in ("1_1", "1_2", "1_3", "1_4", "1_5"):
        sat_bank_total += len(compiled.get("algebra", {}).get(key, []))
    for key in ("2_1", "2_2", "2_3"):
        sat_bank_total += len(compiled.get("advanced_math", {}).get(key, []))
    for u3k in ("3_1", "3_2", "3_3", "3_4", "3_5", "3_6", "3_7"):
        sat_bank_total += len(compiled.get("problem_solving", {}).get(u3k) or [])

    u1_all = len(compiled.get("algebra", {}).get("unit_1_all") or [])
    u2_all = len(compiled.get("advanced_math", {}).get("unit_2_all") or [])
    u3_all = len(compiled.get("problem_solving", {}).get("unit_3_all") or [])
    sat_bank_cap = u1_all + u2_all + u3_all
    if sat_bank_cap <= 0:
        sat_bank_cap = sat_bank_total
    sat_engaged = 0
    if sat_bank_cap > 0:
        sat_engaged += _practice_distinct_answered(db, user_id, "algebra", "unit_1_all")
        sat_engaged += _practice_distinct_answered(db, user_id, "advanced_math", "unit_2_all")
        sat_engaged += _practice_distinct_answered(db, user_id, "problem_solving", "unit_3_all")
    sat_engagement_pct = (
        min(100, int(round(100 * sat_engaged / sat_bank_cap))) if sat_bank_cap else 0
    )

    return {
        "stats": {
            "attempts_total": int(attempts_total or 0),
            "total_graded": total_graded,
            "accuracy_pct": _pct(total_correct, total_graded),
            "tracks_live": 1,
            "tracks_planned": len(LEARNING_TRACKS) - 1,
            "sat_bank_total": sat_bank_total,
            "sat_bank_cap": sat_bank_cap,
            "sat_engaged": sat_engaged,
            "sat_engagement_pct": sat_engagement_pct,
        },
        "recent_sessions": recent_sessions,
        "focus_topics": focus_topics,
    }

# =====================================================
# ROUTES
# =====================================================


@app.route("/health")
def health():
    """For load balancers and hosting probes (no DB hit)."""
    return "ok", 200


@app.route("/")
def index():
    return render_template(
        "dashboard.html",
        tracks=LEARNING_TRACKS,
        **_dashboard_context(),
    )


@app.route("/learn/<track_key>")
def learning_track(track_key: str):
    track = next((t for t in LEARNING_TRACKS if t["key"] == track_key), None)
    if track is None:
        return "Unknown learning track", 404
    session["active_track_label"] = track["title"]
    return render_template("learning_track.html", track=track)


def _full_bank_question_count(domain: str, full_key: str, tex_path: str) -> int:
    """Prefer compiled JSON slice; fall back to TeX parse only if missing."""
    compiled = load_compiled_bank()
    topic_questions = compiled.get(domain, {}).get(full_key)
    if isinstance(topic_questions, list) and topic_questions:
        return len(topic_questions)
    return len(get_questions_for_topic(domain, full_key, tex_path))


def _practice_workspace_counts() -> Dict[str, Any]:
    """Counts for /practice hero + cards; full-bank topics only (no double-counting slices)."""
    n_live = len(BANKS)
    out: Dict[str, Any] = {
        "pw_domains_live": n_live,
        "pw_domain_target": PRACTICE_DOMAIN_TARGET_COUNT,
        "pw_roadmap_units": max(0, PRACTICE_DOMAIN_TARGET_COUNT - n_live),
        "pw_workspace_progress_pct": min(
            100, int(round(100 * n_live / PRACTICE_DOMAIN_TARGET_COUNT))
        ),
        "pw_algebra_count": 0,
        "pw_advanced_math_count": 0,
        "pw_problem_solving_count": 0,
        "pw_total_questions": 0,
        "pw_algebra_touched": 0,
        "pw_advanced_math_touched": 0,
        "pw_problem_solving_touched": 0,
        "pw_algebra_progress_pct": 0,
        "pw_advanced_math_progress_pct": 0,
        "pw_problem_solving_progress_pct": 0,
        "pw_total_touched": 0,
        "pw_aggregate_progress_pct": 0,
    }
    for domain, topics in BANKS.items():
        full_key = (
            "unit_1_all"
            if domain == "algebra"
            else "unit_2_all"
            if domain == "advanced_math"
            else "unit_3_all"
            if domain == "problem_solving"
            else None
        )
        if not full_key or full_key not in topics:
            continue
        path = topics[full_key]
        n = _full_bank_question_count(domain, full_key, path)
        if domain == "algebra":
            out["pw_algebra_count"] = n
        elif domain == "advanced_math":
            out["pw_advanced_math_count"] = n
        elif domain == "problem_solving":
            out["pw_problem_solving_count"] = n
        out["pw_total_questions"] += n
    return out


def _practice_workspace_merge_progress(
    ctx: Dict[str, Any], db: sqlite3.Connection, user_id: Any
) -> None:
    """Fill per-unit and aggregate touched counts for the specialized workspace."""
    specs = (
        ("algebra", "unit_1_all", "pw_algebra"),
        ("advanced_math", "unit_2_all", "pw_advanced_math"),
        ("problem_solving", "unit_3_all", "pw_problem_solving"),
    )
    touched_sum = 0
    for domain, topic, prefix in specs:
        total = int(ctx.get(f"{prefix}_count") or 0)
        touched = _practice_distinct_answered(db, user_id, domain, topic)
        ctx[f"{prefix}_touched"] = touched
        pct = min(100, int(round(100 * touched / total))) if total else 0
        ctx[f"{prefix}_progress_pct"] = pct
        touched_sum += touched
    ctx["pw_total_touched"] = touched_sum
    tot = int(ctx.get("pw_total_questions") or 0)
    ctx["pw_aggregate_progress_pct"] = (
        min(100, int(round(100 * touched_sum / tot))) if tot else 0
    )
    ctx["pw_logged_in"] = user_id is not None


def _mistake_tags_json_from_form(form) -> str:
    allowed = {o["id"] for o in MISTAKE_TAG_OPTIONS}
    picked = sorted({x for x in form.getlist("mistake_tag") if x in allowed})
    return json.dumps(picked, ensure_ascii=False)


def _analytics_wrong_rows(db: sqlite3.Connection, user_id: Any) -> List[dict]:
    """Recent incorrect attempts for the mistake log (optionally scoped to user)."""
    if user_id is not None:
        rows = db.execute(
            """
            SELECT pr.id AS pr_id, pr.submitted_at, pr.question_index,
                   pr.selected_answer, pr.correct_answer, pr.mistake_tags, pr.mistake_note,
                   pa.domain, pa.topic
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0 AND pr.question_index IS NOT NULL
              AND pa.user_id IS ?
            ORDER BY pr.submitted_at DESC
            LIMIT 200
            """,
            (user_id,),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT pr.id AS pr_id, pr.submitted_at, pr.question_index,
                   pr.selected_answer, pr.correct_answer, pr.mistake_tags, pr.mistake_note,
                   pa.domain, pa.topic
            FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.is_correct = 0 AND pr.question_index IS NOT NULL
              AND pa.user_id IS NULL
            ORDER BY pr.submitted_at DESC
            LIMIT 200
            """,
        ).fetchall()

    id_to_label = {o["id"]: o["label"] for o in MISTAKE_TAG_OPTIONS}
    out: List[dict] = []
    for r in rows:
        tags_raw = r["mistake_tags"]
        tag_labels: List[str] = []
        if tags_raw:
            try:
                arr = json.loads(tags_raw)
                if isinstance(arr, list):
                    tag_labels = [id_to_label.get(x, x) for x in arr if isinstance(x, str)]
            except (json.JSONDecodeError, TypeError):
                tag_labels = [str(tags_raw)]
        tag_ids: List[str] = []
        if tags_raw:
            try:
                arr = json.loads(tags_raw)
                if isinstance(arr, list):
                    tag_ids = [x for x in arr if isinstance(x, str)]
            except (json.JSONDecodeError, TypeError):
                pass
        out.append(
            {
                "pr_id": r["pr_id"],
                "when": r["submitted_at"],
                "domain": r["domain"],
                "topic": r["topic"],
                "topic_title": TOPIC_TITLES.get(r["topic"], r["topic"]),
                "q_index": int(r["question_index"]),
                "yours": r["selected_answer"] or "—",
                "key": r["correct_answer"] or "—",
                "tag_labels": tag_labels,
                "tag_ids": tag_ids,
                "note": (r["mistake_note"] or "").strip(),
                "practice_href": url_for(
                    "practice_question",
                    domain=r["domain"],
                    topic=r["topic"],
                    qnum=int(r["question_index"]),
                ),
            }
        )
    return out


@app.route("/placement")
def placement_landing():
    session["active_track_label"] = "Course placement"
    return render_template(
        "placement_landing.html",
        placement_parts=PLACEMENT_LANDING_PARTS,
    )


@app.route("/placement/start")
def placement_start():
    session["active_track_label"] = "Course placement"
    # New intake = new diagnostic: do not resume an old in-browser attempt (fixes stale answers).
    _clear_placement_full_session_attempt()
    session.modified = True
    return render_template("placement_start.html")


@app.route("/placement/begin", methods=["POST"])
def placement_begin():
    session["active_track_label"] = "Course placement"
    _clear_placement_full_session_attempt()
    name = request.form.get("student_name", "").strip()
    grade = request.form.get("student_grade", "").strip()
    course = request.form.get("student_math_course", "").strip()
    if len(name) < 1:
        flash("Please enter the student name.")
        return redirect(url_for("placement_start"))
    if len(name) > 160:
        flash("Name is too long (160 characters max).")
        return redirect(url_for("placement_start"))
    grade = grade[:120]
    course = course[:400]
    session["placement_student_name"] = name[:160]
    session["placement_student_grade"] = grade
    session["placement_student_math_course"] = course
    session.modified = True
    return redirect(
        url_for("practice_question", domain="placement", topic="placement_full", qnum=0)
    )


@app.route("/practice")
def practice():
    """SAT Math home: four modules (specialized, challenge, exams, analytics)."""
    session["active_track_label"] = "SAT Math"
    return render_template("practice_hub.html")


@app.route("/practice/specialized")
def practice_specialized():
    session["active_track_label"] = "SAT Math"
    db = get_db()
    uid = session.get("user_id")
    ctx = _practice_workspace_counts()
    _practice_workspace_merge_progress(ctx, db, uid)
    return render_template("practice_specialized.html", **ctx)


@app.route("/practice/challenge")
def practice_challenge():
    session["active_track_label"] = "SAT Math"
    return render_template(
        "practice_module_placeholder.html",
        title="Hard problem drill",
        lead="A curated hard-question bank with stepped hints—shipping after the core topic banks stabilize.",
        pill="Coming soon",
    )


@app.route("/practice/exams")
def practice_exams():
    session["active_track_label"] = "SAT Math"
    return render_template(
        "practice_module_placeholder.html",
        title="Real exam mode",
        lead="Timed sections and full mock papers that mirror official pacing and layout.",
        pill="Coming soon",
    )


@app.route("/practice/analytics")
def practice_analytics():
    session["active_track_label"] = "SAT Math"
    db = get_db()
    uid = session.get("user_id")
    rows = _analytics_wrong_rows(db, uid)
    tag_totals: Dict[str, int] = defaultdict(int)
    for row in rows:
        for lab in row["tag_labels"]:
            tag_totals[lab] += 1
    top_tags = sorted(tag_totals.items(), key=lambda x: -x[1])[:8]
    return render_template(
        "practice_analytics.html",
        wrong_rows=rows,
        wrong_total=len(rows),
        top_mistake_tags=top_tags,
        mistake_tag_options=MISTAKE_TAG_OPTIONS,
    )


@app.route("/practice/analytics/update/<int:pr_id>", methods=["POST"])
def practice_analytics_update(pr_id: int):
    db = get_db()
    uid = session.get("user_id")
    row = db.execute(
        """
        SELECT pr.id FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pr.id = ? AND pr.is_correct = 0
          AND (pa.user_id IS ? OR (pa.user_id IS NULL AND ? IS NULL))
        """,
        (pr_id, uid, uid),
    ).fetchone()
    if row is None:
        flash("Could not update that record.")
        return redirect(url_for("practice_analytics"))
    tags_json = _mistake_tags_json_from_form(request.form)
    note = (request.form.get("mistake_note") or "").strip()[:2000]
    db.execute(
        """
        UPDATE practice_responses
        SET mistake_tags = ?, mistake_note = ?
        WHERE id = ?
        """,
        (tags_json, note, pr_id),
    )
    db.commit()
    flash("Mistake log updated.")
    return redirect(url_for("practice_analytics"))


@app.route("/practice/<domain>/<topic>/reflect/<int:q_index>", methods=["GET", "POST"])
def practice_mistake_reflect(domain: str, topic: str, q_index: int):
    """After a wrong answer: capture mistake tags + note before continuing."""
    domain_data = BANKS.get(domain)
    if not domain_data or topic not in domain_data:
        return "Unknown topic", 404
    tex_file = domain_data[topic]
    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions or q_index < 0 or q_index >= len(questions):
        return "Invalid question", 404

    db = get_db()
    if request.method == "POST":
        try:
            attempt_id = int(request.form.get("attempt_id") or 0)
        except ValueError:
            attempt_id = 0
        continue_to = (request.form.get("continue_to") or "").strip()
        if continue_to not in ("next", "summary"):
            continue_to = "next"
        tags_json = _mistake_tags_json_from_form(request.form)
        note = (request.form.get("mistake_note") or "").strip()[:2000]

        pr_row = db.execute(
            """
            SELECT pr.id FROM practice_responses pr
            JOIN practice_attempts pa ON pa.id = pr.attempt_id
            WHERE pr.attempt_id = ? AND pr.question_index = ?
              AND pa.domain = ? AND pa.topic = ?
              AND pr.is_correct = 0
            """,
            (attempt_id, q_index, domain, topic),
        ).fetchone()
        if pr_row is None:
            flash("Could not save reflection for this attempt.")
            return redirect(
                url_for("practice_question", domain=domain, topic=topic, qnum=q_index)
            )
        db.execute(
            """
            UPDATE practice_responses
            SET mistake_tags = ?, mistake_note = ?
            WHERE id = ?
            """,
            (tags_json, note, int(pr_row["id"])),
        )
        db.commit()

        sk = _practice_session_key(domain, topic)
        session[sk] = attempt_id
        session.modified = True

        if continue_to == "summary":
            return redirect(url_for("practice_session_summary", attempt_id=attempt_id))
        return redirect(
            url_for("practice_question", domain=domain, topic=topic, qnum=q_index + 1)
        )

    try:
        attempt_id = int(request.args.get("attempt_id") or 0)
    except ValueError:
        attempt_id = 0
    continue_to = (request.args.get("continue_to") or "").strip()
    if continue_to not in ("next", "summary"):
        continue_to = "next"

    pr_row = db.execute(
        """
        SELECT pr.id, pr.selected_answer, pr.correct_answer, pr.mistake_tags, pr.mistake_note
        FROM practice_responses pr
        JOIN practice_attempts pa ON pa.id = pr.attempt_id
        WHERE pr.attempt_id = ? AND pr.question_index = ?
          AND pa.domain = ? AND pa.topic = ?
          AND pr.is_correct = 0
        """,
        (attempt_id, q_index, domain, topic),
    ).fetchone()
    if pr_row is None:
        return redirect(
            url_for("practice_question", domain=domain, topic=topic, qnum=q_index)
        )

    q = questions[q_index]
    prev_tags: List[str] = []
    if pr_row["mistake_tags"]:
        try:
            raw = json.loads(pr_row["mistake_tags"])
            if isinstance(raw, list):
                prev_tags = [x for x in raw if isinstance(x, str)]
        except (json.JSONDecodeError, TypeError):
            prev_tags = []

    return render_template(
        "practice_mistake_reflect.html",
        domain=domain,
        topic=topic,
        topic_title=TOPIC_TITLES.get(topic, topic),
        q_index=q_index,
        attempt_id=attempt_id,
        continue_to=continue_to,
        total=len(questions),
        q=q,
        yours=(pr_row["selected_answer"] or "").strip(),
        key_disp=(pr_row["correct_answer"] or "").strip(),
        mistake_tag_options=MISTAKE_TAG_OPTIONS,
        prev_tags=prev_tags,
        prev_note=(pr_row["mistake_note"] or "").strip(),
    )


# -----------------------------------------------------
# Topic List Page
# -----------------------------------------------------
@app.route("/practice/<domain>")
def practice_topics(domain):

    domain_data = BANKS.get(domain)
    if not domain_data:
        return "Unknown domain", 404

    topic_list = []

    for topic_key, file_path in domain_data.items():
        questions = get_questions_for_topic(domain, topic_key, file_path)
        if not questions:
            continue
        topic_list.append({
            "key": topic_key,
            "title": TOPIC_TITLES.get(topic_key, topic_key),
            "count": len(questions),
        })

    return render_template(
        "topics.html",
        domain=domain,
        domain_title=PRACTICE_DOMAIN_TITLES.get(
            domain, domain.replace("_", " ").title()
        ),
        topics=topic_list,
    )


def _insert_practice_attempt(
    db: sqlite3.Connection, user_id: Any, domain: str, topic: str, q_index: int
) -> int:
    cols = ["user_id", "domain", "topic", "qnum"]
    vals: list[Any] = [user_id, domain, topic, q_index]
    if domain == "placement":
        name, grade, course = _placement_profile_from_session()
        cols.extend(
            [
                "placement_student_name",
                "placement_student_grade",
                "placement_student_math_course",
            ]
        )
        vals.extend([name or None, grade or None, course or None])
    placeholders = ", ".join(["?"] * len(vals))
    cur = db.execute(
        f"INSERT INTO practice_attempts ({', '.join(cols)}) VALUES ({placeholders})",
        tuple(vals),
    )
    db.commit()
    return int(cur.lastrowid)


# -----------------------------------------------------
# Question Page
# -----------------------------------------------------
@app.route("/practice/<domain>/<topic>/<int:qnum>")
def practice_question(domain, topic, qnum):
    domain_data = BANKS.get(domain)
    if not domain_data:
        return "Unknown domain", 404

    tex_file = domain_data.get(topic)
    if not tex_file:
        return "Unknown topic", 404

    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return "Question bank file not found", 404

    q = questions[qnum % len(questions)]
    question_index = qnum % len(questions)

    db = get_db()
    user_id = session.get("user_id")
    sk = _practice_session_key(domain, topic)
    attempt_id = session.get(sk)
    row = None
    if attempt_id is not None:
        row = db.execute(
            "SELECT id FROM practice_attempts WHERE id = ? AND domain = ? AND topic = ?",
            (attempt_id, domain, topic),
        ).fetchone()
    if row is None:
        if domain == "placement" and not _placement_profile_from_session()[0]:
            flash("Please complete the student information before starting the diagnostic.")
            return redirect(url_for("placement_start"))
        attempt_id = _insert_practice_attempt(
            db, user_id, domain, topic, question_index
        )
        session[sk] = attempt_id
    else:
        attempt_id = int(row["id"])
        _backfill_placement_student_profile(db, attempt_id, domain)

    answered_rows = db.execute(
        """
        SELECT DISTINCT question_index FROM practice_responses
        WHERE attempt_id = ? AND question_index IS NOT NULL
        """,
        (attempt_id,),
    ).fetchall()
    answered_qset = frozenset(
        int(r["question_index"])
        for r in answered_rows
        if r["question_index"] is not None
    )
    answered_count = len(answered_qset)
    answered_pct = (
        min(100, int(round(100 * answered_count / len(questions)))) if questions else 0
    )
    remaining_count = max(0, len(questions) - answered_count)

    is_last = question_index >= len(questions) - 1

    calc_ok = bool(q.get("calculator_allowed", True))
    placement_mode = domain == "placement"
    choice_letters = [chr(ord("A") + i) for i in range(len(q.get("choices") or []))]
    if placement_mode:
        practice_timer_seconds = 95 * 60
        practice_timer_summary_url = url_for(
            "practice_session_summary", attempt_id=attempt_id
        )
    else:
        practice_timer_seconds = 5 * 60
        practice_timer_summary_url = None

    return render_template(
        "practice_question.html",
        q=q,
        domain=domain,
        topic=topic,
        qnum=question_index,
        total=len(questions),
        attempt_id=attempt_id,
        answered_qset=answered_qset,
        answered_count=answered_count,
        answered_pct=answered_pct,
        remaining_count=remaining_count,
        is_last=is_last,
        calculator_allowed=calc_ok,
        placement_mode=placement_mode,
        choice_letters=choice_letters,
        practice_timer_seconds=practice_timer_seconds,
        practice_timer_summary_url=practice_timer_summary_url,
    )


@app.route("/practice/submit", methods=["POST"])
def submit_practice_answer():
    domain = request.form.get("domain", "").strip()
    topic = request.form.get("topic", "").strip()
    raw_answer = request.form.get("selected_answer", "").strip()
    attempt_id_raw = request.form.get("attempt_id", "").strip()
    qnum_raw = request.form.get("qnum", "0").strip()
    try:
        qnum_for_redirect = int(qnum_raw or 0)
    except ValueError:
        qnum_for_redirect = 0

    if not raw_answer:
        flash("Please enter or select an answer before submitting.")
        return redirect(url_for("practice_question", domain=domain, topic=topic, qnum=qnum_for_redirect))

    domain_data = BANKS.get(domain)
    if not domain_data:
        return "Unknown domain", 404

    tex_file = domain_data.get(topic)
    if not tex_file:
        return "Unknown topic", 404

    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return "No questions found", 500

    try:
        qnum = int(qnum_raw or 0)
    except ValueError:
        qnum = 0

    q_index = qnum % len(questions)
    question = questions[q_index]
    q_kind = question.get("question_kind", "mcq")
    if q_kind in ("mcq", "mcq5"):
        selected_answer = raw_answer.strip().upper()[:1]
        allowed = {"A", "B", "C", "D", "E"} if q_kind == "mcq5" else {"A", "B", "C", "D"}
        if selected_answer not in allowed:
            span = "A through E" if q_kind == "mcq5" else "A through D"
            flash(f"Please select one answer choice ({span}).")
            return redirect(
                url_for("practice_question", domain=domain, topic=topic, qnum=qnum_for_redirect)
            )
    else:
        selected_answer = raw_answer

    is_correct, correct_answer = grade_for_db(question, selected_answer)

    db = get_db()
    try:
        attempt_id = int(attempt_id_raw)
    except ValueError:
        attempt_id = None

    # If attempt_id is missing/invalid/nonexistent, create a fallback attempt row.
    attempt_exists = None
    if attempt_id is not None:
        attempt_exists = db.execute(
            "SELECT id FROM practice_attempts WHERE id = ?",
            (attempt_id,),
        ).fetchone()

    if attempt_id is None or attempt_exists is None:
        user_id = session.get("user_id")
        attempt_id = _insert_practice_attempt(db, user_id, domain, topic, q_index)

    db.execute(
        "DELETE FROM practice_responses WHERE attempt_id = ? AND question_index = ?",
        (attempt_id, q_index),
    )
    db.execute(
        """
        INSERT INTO practice_responses
        (attempt_id, question_index, selected_answer, correct_answer, is_correct)
        VALUES (?, ?, ?, ?, ?)
        """,
        (attempt_id, q_index, selected_answer, correct_answer, is_correct),
    )
    db.commit()

    is_last = q_index >= len(questions) - 1
    if not is_last:
        return redirect(
            url_for("practice_question", domain=domain, topic=topic, qnum=q_index + 1)
        )

    sk = _practice_session_key(domain, topic)
    session[sk] = attempt_id
    session.modified = True
    return redirect(url_for("practice_session_summary", attempt_id=attempt_id))


def _practice_session_summary_payload(attempt_id: int) -> dict[str, Any] | tuple[str, int]:
    """Shared data for HTML summary and placement PDF export."""
    db = get_db()
    att = db.execute(
        """
        SELECT id, domain, topic, placement_student_name, placement_student_grade,
               placement_student_math_course
        FROM practice_attempts WHERE id = ?
        """,
        (attempt_id,),
    ).fetchone()
    if att is None:
        return ("Session not found", 404)

    domain = att["domain"]
    topic = att["topic"]

    def _att_str(col: str) -> str:
        try:
            v = att[col]
        except (KeyError, IndexError, TypeError):
            return ""
        if v is None:
            return ""
        return str(v).strip()

    placement_student: dict[str, str] | None = None
    if domain == "placement":
        placement_student = {
            "name": _att_str("placement_student_name"),
            "grade": _att_str("placement_student_grade"),
            "math_course": _att_str("placement_student_math_course"),
        }
    else:
        placement_student = None
    sk = _practice_session_key(domain, topic)
    if session.get(sk) != attempt_id:
        session[sk] = attempt_id
        session.modified = True

    tex_file = BANKS.get(domain, {}).get(topic)
    if not tex_file:
        return ("Unknown topic", 404)

    questions = get_questions_for_topic(domain, topic, tex_file)
    if not questions:
        return ("No questions", 500)

    total_q = len(questions)
    resp_rows = db.execute(
        """
        SELECT question_index, selected_answer, correct_answer, is_correct
        FROM practice_responses
        WHERE attempt_id = ? AND question_index IS NOT NULL
        ORDER BY question_index
        """,
        (attempt_id,),
    ).fetchall()
    by_q: Dict[int, Any] = {}
    for r in resp_rows:
        qi = r["question_index"]
        if qi is not None:
            by_q[int(qi)] = r

    rows_out: List[dict] = []
    correct_count = 0
    for i, qobj in enumerate(questions):
        key = extract_correct_answer(qobj)
        r = by_q.get(i)
        disp = qobj.get("display_number", i + 1)
        sec = qobj.get("knowledge_section", "—")
        title_en = qobj.get("knowledge_section_title_en", "")
        expl = qobj.get("explanation_en", "")

        if r is None:
            status = "skipped"
            yours = "—"
            key_display = key if key else "—"
        else:
            yours_raw = (r["selected_answer"] or "").strip()
            yours = yours_raw if yours_raw else "—"
            key_display = key if key else (r["correct_answer"] or "—")
            if yours == "—":
                status = "skipped"
            elif not key:
                status = "nocheck"
            else:
                graded = response_is_correct(qobj, yours_raw)
                if graded is True:
                    status = "correct"
                    correct_count += 1
                elif graded is False:
                    status = "incorrect"
                else:
                    status = "nocheck"

        rows_out.append(
            {
                "q_display": str(disp),
                "session_q": str(i + 1),
                "row_id": f"summary-q-{i}",
                "knowledge_section": sec,
                "knowledge_title_en": title_en,
                "yours_display": yours,
                "key_display": key_display,
                "status": status,
                "explanation_en": expl,
            }
        )

    score_pct = round(100.0 * correct_count / total_q) if total_q else 0
    mistake_focus: List[dict] = []
    skipped_count = sum(1 for r in rows_out if r["status"] == "skipped")
    if domain != "placement":
        for i, row in enumerate(rows_out):
            if row["status"] == "incorrect":
                mistake_focus.append(
                    {
                        **row,
                        "stem_html": questions[i].get("stem") or "",
                    }
                )

    section_stats: List[dict] = []
    acc = defaultdict(lambda: {"correct": 0, "total": 0, "title": ""})
    for row, qobj in zip(rows_out, questions):
        sec = qobj.get("knowledge_section", "—")
        acc[sec]["total"] += 1
        acc[sec]["title"] = qobj.get("knowledge_section_title_en", "") or acc[sec]["title"]
        if row["status"] == "correct":
            acc[sec]["correct"] += 1
    if domain == "placement":
        part_order = ("I", "II", "III", "IV", "V")
    elif domain == "algebra":
        part_order = ("1.1", "1.2", "1.3", "1.4", "1.5")
    elif domain == "advanced_math":
        part_order = ("2.1", "2.2", "2.3")
    elif domain == "problem_solving":
        part_order = ("3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7")
    else:
        part_order = tuple(sorted(acc.keys(), key=lambda x: str(x)))
    for sec in part_order:
        if sec not in acc:
            continue
        a = acc[sec]
        t = a["total"]
        section_stats.append(
            {
                "section": sec,
                "title_en": a["title"],
                "correct": a["correct"],
                "total": t,
                "pct": round(100.0 * a["correct"] / t) if t else 0,
            }
        )

    placement_meta = _load_placement_meta_file()
    placement_rec = None
    placement_brand: dict | None = None
    if domain == "placement":
        placement_rec = _placement_recommendation(
            placement_meta, correct_count, total_q
        )
        b = placement_meta.get("brand")
        placement_brand = b if isinstance(b, dict) else None

    celebrate_confetti = bool(domain == "placement" or score_pct >= 55)

    topic_title = TOPIC_TITLES.get(topic, topic)
    render = {
        "domain": domain,
        "topic": topic,
        "topic_title": topic_title,
        "attempt_id": attempt_id,
        "rows": rows_out,
        "correct_count": correct_count,
        "total_q": total_q,
        "score_pct": score_pct,
        "section_stats": section_stats,
        "placement_rec": placement_rec,
        "placement_brand": placement_brand,
        "placement_student": placement_student,
        "celebrate_confetti": celebrate_confetti,
        "mistake_focus": mistake_focus,
        "skipped_count": skipped_count,
    }
    pdf_ctx = {
        "rows": rows_out,
        "placement_rec": placement_rec,
        "section_stats": section_stats,
        "placement_brand": placement_brand,
        "placement_student": placement_student,
        "correct_count": correct_count,
        "total_q": total_q,
        "score_pct": score_pct,
        "topic_title": topic_title,
        "attempt_id": attempt_id,
    }
    return {"render": render, "pdf_ctx": pdf_ctx}


@app.route("/practice/session/<int:attempt_id>/summary")
def practice_session_summary(attempt_id: int):
    payload = _practice_session_summary_payload(attempt_id)
    if isinstance(payload, tuple):
        return payload[0], payload[1]
    return render_template("practice_session_summary.html", **payload["render"])


@app.route("/practice/session/<int:attempt_id>/placement-report.pdf")
def practice_placement_report_pdf(attempt_id: int):
    payload = _practice_session_summary_payload(attempt_id)
    if isinstance(payload, tuple):
        abort(payload[1])
    render = payload["render"]
    if render["domain"] != "placement":
        abort(404)
    try:
        body = build_placement_parent_pdf(payload["pdf_ctx"])
    except ImportError as exc:
        return Response(
            str(exc),
            status=503,
            mimetype="text/plain; charset=utf-8",
        )
    name = f"novelprep-placement-report-{attempt_id}.pdf"
    return Response(
        body,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.route("/placement/blank-test.pdf")
def placement_blank_test_pdf():
    path = os.path.join(APP_DIR, "Placement_Test.pdf")
    if not os.path.isfile(path):
        abort(404)
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="NovelPrep-Course-Placement-Blank.pdf",
    )


@app.route("/practice/<domain>/<topic>/new-session")
def practice_new_session(domain: str, topic: str):
    session.pop(_practice_session_key(domain, topic), None)
    if domain == "placement" and topic == "placement_full":
        _clear_placement_profile_session()
        return redirect(url_for("placement_start"))
    return redirect(url_for("practice_question", domain=domain, topic=topic, qnum=0))


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    init_db()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        user = db.execute(
            "SELECT id FROM users WHERE username=? AND password=?",
            (username, password),
        ).fetchone()

        if user:
            session.clear()
            session["user_id"] = int(user["id"])
            return redirect(url_for("index"))

        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8888, debug=True)
