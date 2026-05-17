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
    conn.execute("""
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
    conn.commit()

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
    conn.execute("DELETE FROM copies WHERE id=?", (copy_id,))
    conn.commit()

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
