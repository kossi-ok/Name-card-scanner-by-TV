import sqlite3
import os
from typing import Optional, List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "contacts.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database table with per-user tenant isolation."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            job_title TEXT,
            company TEXT,
            phones TEXT,
            emails TEXT,
            website TEXT,
            address TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Index for fast user-specific lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON contacts (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_name ON contacts (user_id, full_name)")
    conn.commit()
    conn.close()

def add_contact(user_id: int, contact: Dict[str, Any]) -> int:
    """Inserts a contact tied to the specific user_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO contacts (user_id, full_name, job_title, company, phones, emails, website, address, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        contact.get("full_name") or "Unknown Contact",
        contact.get("job_title", ""),
        contact.get("company", ""),
        ", ".join(contact.get("phones", [])) if isinstance(contact.get("phones"), list) else contact.get("phones", ""),
        ", ".join(contact.get("emails", [])) if isinstance(contact.get("emails"), list) else contact.get("emails", ""),
        contact.get("website", ""),
        contact.get("address", ""),
        contact.get("notes", "")
    ))
    contact_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return contact_id

def get_user_contacts(user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetches paginated contacts for a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM contacts 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    """, (user_id, limit, offset))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def count_user_contacts(user_id: int) -> int:
    """Returns the total number of contacts for a specific user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM contacts WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def search_contacts(user_id: int, query: str) -> List[Dict[str, Any]]:
    """Searches a user's contacts by name, company, email, or title."""
    conn = get_connection()
    cursor = conn.cursor()
    q = f"%{query}%"
    cursor.execute("""
        SELECT * FROM contacts 
        WHERE user_id = ? AND (
            full_name LIKE ? OR 
            company LIKE ? OR 
            job_title LIKE ? OR 
            emails LIKE ? OR
            phones LIKE ?
        )
        ORDER BY created_at DESC
        LIMIT 20
    """, (user_id, q, q, q, q, q))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_contact_by_id(user_id: int, contact_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single contact belonging to user_id."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts WHERE user_id = ? AND id = ?", (user_id, contact_id))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_contact(user_id: int, contact_id: int) -> bool:
    """Deletes a contact ensuring it belongs to the user."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM contacts WHERE user_id = ? AND id = ?", (user_id, contact_id))
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_all_contacts_for_export(user_id: int) -> List[Dict[str, Any]]:
    """Returns all contacts for a user for CSV export."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM contacts WHERE user_id = ? ORDER BY full_name ASC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
