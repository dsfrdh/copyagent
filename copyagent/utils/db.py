"""SQLite database helpers for CopyAgent."""
import sqlite3
import json
from datetime import datetime
from config import DB_PATH

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_path TEXT,
            file_type TEXT,
            tags TEXT DEFAULT '',
            chunk_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS viral_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            source_url TEXT,
            raw_text TEXT NOT NULL,
            tags TEXT DEFAULT '',
            structure_type TEXT,
            hook_type TEXT,
            emotion_curve TEXT,
            golden_sentences TEXT,
            analysis_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS copies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            content TEXT NOT NULL,
            mode TEXT DEFAULT 'free',
            length TEXT DEFAULT '60秒',
            style TEXT DEFAULT '口语化',
            purpose TEXT DEFAULT '',
            source_chunks TEXT,
            reference_analysis_id INTEGER,
            rating INTEGER DEFAULT 0,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS copy_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            copy_id INTEGER NOT NULL,
            version_type TEXT NOT NULL,
            content TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(copy_id) REFERENCES copies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS copy_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            copy_id INTEGER NOT NULL,
            rating TEXT DEFAULT '',
            reason_tags TEXT DEFAULT '[]',
            note TEXT DEFAULT '',
            final_content TEXT DEFAULT '',
            is_shot INTEGER DEFAULT 0,
            performance_note TEXT DEFAULT '',
            analysis_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(copy_id) REFERENCES copies(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS preference_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_type TEXT NOT NULL,
            rule_text TEXT NOT NULL,
            product TEXT DEFAULT '',
            video_type TEXT DEFAULT '',
            people_count TEXT DEFAULT '',
            length_min INTEGER DEFAULT 0,
            length_max INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.5,
            status TEXT DEFAULT 'active',
            used_count INTEGER DEFAULT 0,
            source_feedback_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(source_feedback_id) REFERENCES copy_feedback(id) ON DELETE SET NULL
        );
    """)
    # Add wizard columns (safe migration)
    for col, dtype in [
        ("product", "TEXT DEFAULT ''"),
        ("selling_points", "TEXT DEFAULT ''"),
        ("pain_points", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE copies ADD COLUMN {col} {dtype}")
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    return conn

def _word_count(text: str) -> int:
    return len("".join((text or "").split()))

# --- Knowledge Doc CRUD ---

def add_knowledge_doc(title, file_path, file_type, tags=""):
    conn = get_conn()
    c = conn.execute(
        "INSERT INTO knowledge_docs (title, file_path, file_type, tags) VALUES (?,?,?,?)",
        (title, file_path, file_type, tags)
    )
    conn.commit()
    return c.lastrowid

def update_chunk_count(doc_id, count):
    conn = get_conn()
    conn.execute("UPDATE knowledge_docs SET chunk_count=? WHERE id=?", (count, doc_id))
    conn.commit()

def list_knowledge_docs():
    conn = get_conn()
    return [dict(r) for r in conn.execute("SELECT * FROM knowledge_docs ORDER BY created_at DESC").fetchall()]

def delete_knowledge_doc(doc_id):
    conn = get_conn()
    conn.execute("DELETE FROM knowledge_docs WHERE id=?", (doc_id,))
    conn.commit()

# --- Viral Analysis CRUD ---

def save_analysis(title, raw_text, analysis_json, source_url="", tags=""):
    conn = get_conn()
    a = analysis_json
    conn.execute("""
        INSERT INTO viral_analyses (title, source_url, raw_text, tags,
            structure_type, hook_type, emotion_curve, golden_sentences, analysis_json)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        title, source_url, raw_text, tags,
        a.get("structure_type", ""),
        a.get("hook_type", ""),
        json.dumps(a.get("emotion_curve", []), ensure_ascii=False),
        json.dumps(a.get("golden_sentences", []), ensure_ascii=False),
        json.dumps(a, ensure_ascii=False)
    ))
    conn.commit()

def list_analyses():
    conn = get_conn()
    return [dict(r) for r in conn.execute("SELECT * FROM viral_analyses ORDER BY created_at DESC").fetchall()]

def get_analysis(aid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM viral_analyses WHERE id=?", (aid,)).fetchone()
    return dict(r) if r else None

def delete_analysis(aid):
    conn = get_conn()
    conn.execute("DELETE FROM viral_analyses WHERE id=?", (aid,))
    conn.commit()

# --- Copy CRUD ---

def save_copy(title, content, mode="free", length="60秒", style="口语化",
              purpose="", source_chunks=None, ref_analysis_id=None,
              product="", selling_points=None, pain_points=None):
    conn = get_conn()
    c = conn.execute("""
        INSERT INTO copies (title, content, mode, length, style, purpose,
            source_chunks, reference_analysis_id, product, selling_points, pain_points)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        title, content, mode, length, style, purpose,
        json.dumps(source_chunks or [], ensure_ascii=False),
        ref_analysis_id, product,
        json.dumps(selling_points or [], ensure_ascii=False),
        json.dumps(pain_points or [], ensure_ascii=False)
    ))
    copy_id = c.lastrowid
    conn.execute(
        "INSERT INTO copy_versions (copy_id, version_type, content, word_count) VALUES (?,?,?,?)",
        (copy_id, "ai_original", content, _word_count(content))
    )
    conn.commit()
    return copy_id

def list_copies(limit=50, status=None):
    conn = get_conn()
    q = "SELECT * FROM copies"
    params = []
    if status:
        q += " WHERE status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(q, params).fetchall()]

def update_copy_status(copy_id, status):
    conn = get_conn()
    conn.execute("UPDATE copies SET status=? WHERE id=?", (status, copy_id))
    conn.commit()

def update_copy_rating(copy_id, rating):
    conn = get_conn()
    conn.execute("UPDATE copies SET rating=? WHERE id=?", (rating, copy_id))
    conn.commit()

def delete_copy(copy_id):
    conn = get_conn()
    conn.execute("DELETE FROM copy_versions WHERE copy_id=?", (copy_id,))
    conn.execute("DELETE FROM copy_feedback WHERE copy_id=?", (copy_id,))
    conn.execute("DELETE FROM copies WHERE id=?", (copy_id,))
    conn.commit()

def get_copy(copy_id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM copies WHERE id=?", (copy_id,)).fetchone()
    return dict(r) if r else None

# --- Feedback Memory ---

def save_copy_version(copy_id, version_type, content):
    conn = get_conn()
    c = conn.execute(
        "INSERT INTO copy_versions (copy_id, version_type, content, word_count) VALUES (?,?,?,?)",
        (copy_id, version_type, content, _word_count(content))
    )
    conn.commit()
    return c.lastrowid

def list_copy_versions(copy_id):
    conn = get_conn()
    return [
        dict(r) for r in conn.execute(
            "SELECT * FROM copy_versions WHERE copy_id=? ORDER BY created_at DESC, id DESC",
            (copy_id,)
        ).fetchall()
    ]

def save_copy_feedback(copy_id, rating="", reason_tags=None, note="", final_content="",
                       is_shot=False, performance_note="", analysis_json=None):
    conn = get_conn()
    c = conn.execute("""
        INSERT INTO copy_feedback (
            copy_id, rating, reason_tags, note, final_content, is_shot,
            performance_note, analysis_json
        )
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        copy_id, rating, json.dumps(reason_tags or [], ensure_ascii=False),
        note, final_content, 1 if is_shot else 0, performance_note,
        json.dumps(analysis_json or {}, ensure_ascii=False)
    ))
    conn.commit()
    return c.lastrowid

def list_copy_feedback(copy_id=None, limit=50):
    conn = get_conn()
    params = []
    q = "SELECT * FROM copy_feedback"
    if copy_id is not None:
        q += " WHERE copy_id=?"
        params.append(copy_id)
    q += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(q, params).fetchall()]

def save_preference_rule(rule_type, rule_text, product="", video_type="", people_count="",
                         length_min=0, length_max=0, confidence=0.5, source_feedback_id=None):
    rule_text = (rule_text or "").strip()
    if not rule_text:
        return None
    conn = get_conn()
    c = conn.execute("""
        INSERT INTO preference_rules (
            rule_type, rule_text, product, video_type, people_count,
            length_min, length_max, confidence, source_feedback_id
        )
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        rule_type, rule_text, product, video_type, people_count,
        length_min or 0, length_max or 0, confidence, source_feedback_id
    ))
    conn.commit()
    return c.lastrowid

def save_preference_rules_from_analysis(analysis, source_feedback_id=None, product="",
                                        video_type="", people_count="", length_min=0, length_max=0):
    saved = []
    if not isinstance(analysis, dict):
        return saved

    conditions = analysis.get("applicable_conditions") or {}
    product = product or conditions.get("product", "")
    video_type = video_type or conditions.get("video_type", "")
    people_count = people_count or conditions.get("people_count", "")

    for text in analysis.get("prefer_rules", []) or []:
        rid = save_preference_rule(
            "prefer", text, product, video_type, people_count,
            length_min, length_max, 0.7, source_feedback_id
        )
        if rid:
            saved.append(rid)
    for text in analysis.get("avoid_rules", []) or []:
        rid = save_preference_rule(
            "avoid", text, product, video_type, people_count,
            length_min, length_max, 0.7, source_feedback_id
        )
        if rid:
            saved.append(rid)
    return saved

def list_preference_rules(limit=100, status="active"):
    conn = get_conn()
    q = "SELECT * FROM preference_rules"
    params = []
    if status:
        q += " WHERE status=?"
        params.append(status)
    q += " ORDER BY confidence DESC, created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(q, params).fetchall()]

def update_preference_rule_status(rule_id, status):
    conn = get_conn()
    conn.execute("UPDATE preference_rules SET status=? WHERE id=?", (status, rule_id))
    conn.commit()

def get_relevant_preference_rules(product="", video_type="", people_count="", length_label="", limit=8):
    rules = list_preference_rules(limit=200, status="active")
    product_l = (product or "").lower()
    video_l = (video_type or "").lower()
    people_l = (people_count or "").lower()

    scored = []
    for rule in rules:
        score = float(rule.get("confidence") or 0.5)
        rp = (rule.get("product") or "").lower()
        rv = (rule.get("video_type") or "").lower()
        rpeople = (rule.get("people_count") or "").lower()

        if rp and product_l and (rp in product_l or product_l in rp):
            score += 3
        elif rp:
            score -= 0.5

        if rv and video_l and (rv in video_l or video_l in rv):
            score += 2
        elif rv:
            score -= 0.25

        if rpeople and people_l and (rpeople in people_l or people_l in rpeople):
            score += 1

        scored.append((score, rule))

    scored.sort(key=lambda x: (x[0], x[1].get("created_at") or ""), reverse=True)
    return [r for score, r in scored[:limit] if score > 0]

def build_preference_memory_text(product="", video_type="", people_count="", length_label="", limit=8):
    rules = get_relevant_preference_rules(product, video_type, people_count, length_label, limit)
    if not rules:
        return "", []

    prefer = [r["rule_text"] for r in rules if r.get("rule_type") == "prefer"]
    avoid = [r["rule_text"] for r in rules if r.get("rule_type") == "avoid"]
    lines = ["【用户历史修改偏好】", "请优先参考以下规则，避免重复用户过去修改过的问题。"]
    if prefer:
        lines.append("应该这样写：")
        lines.extend(f"- {r}" for r in prefer[:5])
    if avoid:
        lines.append("不要这样写：")
        lines.extend(f"- {r}" for r in avoid[:5])
    return "\n".join(lines), rules

# --- Settings ---

def get_setting(key, default=None):
    conn = get_conn()
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
        (key, str(value))
    )
    conn.commit()

def get_recent_products(limit=10):
    """Get distinct recent product names for autocomplete."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT product FROM copies WHERE product != '' ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [r["product"] for r in rows]

# Initialize on import
init_db()
