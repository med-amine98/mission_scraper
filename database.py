import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "missions.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        # 1. Missions table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT,
                company TEXT,
                description TEXT,
                location TEXT,
                skills TEXT,
                rate TEXT,
                published_date TEXT,
                url TEXT UNIQUE,
                score REAL DEFAULT 0,
                analysis TEXT,
                collected_at TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Safely ensure all columns exist if the table was created previously with fewer columns
        existing_cols = [r["name"] for r in conn.execute("PRAGMA table_info(missions)").fetchall()]
        cols_to_add = {
            "company": "TEXT",
            "score": "REAL DEFAULT 0",
            "analysis": "TEXT",
            "rate": "TEXT",
            "skills": "TEXT",
            "collected_at": "TEXT",
            "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        }
        for col, col_type in cols_to_add.items():
            if col not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE missions ADD COLUMN {col} {col_type}")
                except Exception:
                    pass

        # 2. CVs / Candidates table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cvs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                title TEXT,
                email TEXT,
                phone TEXT,
                experience_years INTEGER DEFAULT 0,
                skills TEXT,
                summary TEXT,
                raw_text TEXT,
                filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()


# ============================================================
# MISSIONS
# ============================================================

def save_mission(mission: Dict[str, Any]) -> bool:
    if not mission.get("url") or not mission.get("title"):
        return False
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO missions (
                source, title, company, description, location,
                skills, rate, published_date, url, collected_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                company = CASE WHEN excluded.company != '' THEN excluded.company ELSE missions.company END,
                description = CASE WHEN length(excluded.description) > length(missions.description) THEN excluded.description ELSE missions.description END,
                location = CASE WHEN excluded.location != '' THEN excluded.location ELSE missions.location END,
                skills = CASE WHEN excluded.skills != '' THEN excluded.skills ELSE missions.skills END,
                rate = CASE WHEN excluded.rate != '' THEN excluded.rate ELSE missions.rate END,
                published_date = CASE WHEN excluded.published_date != '' THEN excluded.published_date ELSE missions.published_date END
        """, (
            mission.get("source") or "Autre",
            mission.get("title") or "",
            mission.get("company") or "",
            mission.get("description") or "",
            mission.get("location") or "",
            mission.get("skills") or "",
            mission.get("rate") or "",
            mission.get("published_date") or "",
            mission.get("url")
        ))
        conn.commit()
        return cursor.rowcount > 0


def get_missions() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM missions ORDER BY id DESC"
            ).fetchall()
        ]


def get_missions_by_source(source: str) -> List[Dict[str, Any]]:
    """Retourne toutes les missions d'une source donnée."""
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM missions WHERE LOWER(source) LIKE ? ORDER BY id DESC",
                (f"%{source.lower()}%",)
            ).fetchall()
        ]


def get_mission(mission_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
        return dict(row) if row else None


def update_analysis(url: str, score: float, analysis: str):
    with get_connection() as conn:
        conn.execute("""
            UPDATE missions
            SET score = ?, analysis = ?
            WHERE url = ?
        """, (score, analysis, url))
        conn.commit()


def delete_mission_by_url(url: str) -> bool:
    """Supprime une mission par son URL. Retourne True si supprimée."""
    if not url:
        return False
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM missions WHERE url = ?", (url,))
        conn.commit()
        return cursor.rowcount > 0


def delete_mission(mission_id: int) -> bool:
    """Supprime une mission par son identifiant. Retourne True si supprimée."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_missions_by_urls(urls: List[str]) -> int:
    """Supprime plusieurs missions par leurs URLs. Retourne le nombre supprimé."""
    if not urls:
        return 0
    with get_connection() as conn:
        placeholders = ",".join("?" * len(urls))
        cursor = conn.execute(
            f"DELETE FROM missions WHERE url IN ({placeholders})",
            urls
        )
        conn.commit()
        return cursor.rowcount


def delete_all_missions() -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM missions")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='missions'")
        conn.commit()
        return cursor.rowcount


def count_missions() -> int:
    """Retourne le nombre total de missions en base."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM missions").fetchone()
        return int(row["total"]) if row else 0


def count_missions_by_source() -> Dict[str, int]:
    """Retourne le nombre de missions par source."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT source, COUNT(*) AS total
            FROM missions
            GROUP BY source
            ORDER BY total DESC
        """).fetchall()
        return {row["source"]: int(row["total"]) for row in rows}


# ============================================================
# CV & CANDIDATE FUNCTIONS
# ============================================================

def save_cv(cv: Dict[str, Any]) -> int:
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO cvs (
                name, title, email, phone,
                experience_years, skills, summary, raw_text, filename
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cv.get("name") or "Candidat Anonyme",
            cv.get("title") or "Consultant IT",
            cv.get("email") or "",
            cv.get("phone") or "",
            int(cv.get("experience_years") or 0),
            cv.get("skills") or "",
            cv.get("summary") or "",
            cv.get("raw_text") or "",
            cv.get("filename") or ""
        ))
        conn.commit()
        return cursor.lastrowid


def get_cvs() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM cvs ORDER BY id DESC"
            ).fetchall()
        ]


def get_cv(cv_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM cvs WHERE id = ?", (cv_id,)).fetchone()
        return dict(row) if row else None


def delete_cv(cv_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM cvs WHERE id = ?", (cv_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_all_cvs() -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM cvs")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='cvs'")
        conn.commit()
        return cursor.rowcount


def count_cvs() -> int:
    """Retourne le nombre total de CVs en base."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS total FROM cvs").fetchone()
        return int(row["total"]) if row else 0