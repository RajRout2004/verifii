import sqlite3
import json
import os
from datetime import datetime

# Anchor DB file to the backend directory regardless of CWD
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verifii.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            trust_score INTEGER,
            verdict TEXT,
            summary TEXT,
            reasons TEXT,
            recommendation TEXT,
            searched_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_result(query: str, verdict: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO searches (query, trust_score, verdict, summary, reasons, recommendation, searched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        query,
        verdict.get("trust_score", 0),
        verdict.get("verdict", "YELLOW"),
        verdict.get("summary", ""),
        json.dumps(verdict.get("reasons", [])),
        verdict.get("recommendation", ""),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


def get_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM searches ORDER BY searched_at DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "query": row["query"],
            "trust_score": row["trust_score"],
            "verdict": row["verdict"],
            "summary": row["summary"],
            "reasons": json.loads(row["reasons"]),
            "recommendation": row["recommendation"],
            "searched_at": row["searched_at"],
        })
    return results