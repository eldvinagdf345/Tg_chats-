import aiosqlite
from config import DB_PATH

# Columns added on top of the base `accounts` table to hold the per-account
# communication profile (speech style + hard stop-rules + notifications +
# reply timing). Added via ALTER TABLE so existing DBs migrate in place.
_ACCOUNT_PROFILE_COLUMNS = [
    ("persona_name", "TEXT"),
    ("address_form", "TEXT DEFAULT 'ty'"),               # 'ty' | 'vy'
    ("tone", "TEXT DEFAULT 'friendly'"),                  # 'friendly' | 'neutral' | 'business'
    ("message_length", "TEXT DEFAULT 'short'"),           # 'short' | 'medium' | 'long'
    ("emoji_usage", "TEXT DEFAULT 'sometimes'"),          # 'none' | 'sometimes' | 'often'
    ("literacy", "TEXT DEFAULT 'casual'"),                # 'careful' | 'casual'
    ("taboo_topics", "TEXT"),
    ("fallback_behavior", "TEXT DEFAULT 'later'"),        # 'deflect' | 'later' | 'escalate'
    ("stop_keywords", "TEXT"),
    ("max_messages_per_dialogue", "INTEGER"),
    ("max_messages_per_day", "INTEGER"),
    ("work_hours_start", "INTEGER"),
    ("work_hours_end", "INTEGER"),
    ("notify_chat_id", "TEXT"),
    ("delay_min_seconds", "INTEGER DEFAULT 20"),
    ("delay_max_seconds", "INTEGER DEFAULT 90"),
    ("profile_ready", "INTEGER DEFAULT 0"),
]


async def _ensure_account_columns(db):
    cursor = await db.execute("PRAGMA table_info(accounts)")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, decl in _ACCOUNT_PROFILE_COLUMNS:
        if name not in existing:
            await db.execute(f"ALTER TABLE accounts ADD COLUMN {name} {decl}")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS parsed_users (
                username TEXT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                phone TEXT,
                api_id TEXT NOT NULL,
                api_hash TEXT NOT NULL,
                session_string TEXT NOT NULL,
                connected INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _ensure_account_columns(db)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                identifier TEXT NOT NULL,
                display_name TEXT,
                goal TEXT,
                ai_enabled INTEGER DEFAULT 1,
                auto_send INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_id, identifier)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dialogue_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
                direction TEXT NOT NULL,
                text TEXT NOT NULL,
                status TEXT DEFAULT 'sent',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


# ── parsed users ──────────────────────────────────────────────────────────────

async def add_users(usernames: list) -> list:
    new_users = []
    async with aiosqlite.connect(DB_PATH) as db:
        for username in usernames:
            username = username.lower().strip()
            if not username:
                continue
            cursor = await db.execute(
                "SELECT 1 FROM parsed_users WHERE username = ?", (username,)
            )
            if not await cursor.fetchone():
                await db.execute(
                    "INSERT OR IGNORE INTO parsed_users (username) VALUES (?)", (username,)
                )
                new_users.append(username)
        await db.commit()
    return new_users


async def get_all_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username FROM parsed_users ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def get_users_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM parsed_users")
        row = await cursor.fetchone()
    return row[0] if row else 0


# ── accounts ──────────────────────────────────────────────────────────────────

async def create_account(label: str, phone: str, api_id: int, api_hash: str, session_string: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO accounts (label, phone, api_id, api_hash, session_string, connected) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (label, phone, str(api_id), api_hash, session_string),
        )
        await db.commit()
        return cursor.lastrowid


async def get_accounts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts ORDER BY created_at")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_account(account_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE id=?", (account_id,))
        row = await cursor.fetchone()
    return dict(row) if row else None


async def set_account_connected(account_id: int, connected: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET connected=? WHERE id=?", (int(connected), account_id))
        await db.commit()


async def delete_account(account_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        await db.commit()


async def update_account_profile(account_id: int, **fields):
    """Partial update of the communication-profile columns on `accounts`."""
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [account_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE accounts SET {cols} WHERE id=?", values)
        await db.commit()


async def count_out_messages_for_contact(contact_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM dialogue_messages "
            "WHERE contact_id=? AND direction='out' AND status IN ('sent','draft')",
            (contact_id,),
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


async def count_out_messages_today_for_account(account_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            SELECT COUNT(*) FROM dialogue_messages dm
            JOIN contacts c ON c.id = dm.contact_id
            WHERE c.account_id=? AND dm.direction='out' AND dm.status IN ('sent','draft')
              AND dm.created_at >= date('now')
        """, (account_id,))
        row = await cursor.fetchone()
    return row[0] if row else 0


# ── contacts / dialogues ────────────────────────────────────────────────────

async def create_contact(
    account_id: int, identifier: str, display_name: str | None = None,
    goal: str | None = None, auto_send: bool = False,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO contacts (account_id, identifier, display_name, goal, auto_send, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            ON CONFLICT(account_id, identifier) DO UPDATE SET
                display_name=excluded.display_name, goal=excluded.goal,
                auto_send=excluded.auto_send, status='active'
        """, (account_id, identifier, display_name, goal, int(auto_send)))
        await db.commit()
        cursor = await db.execute(
            "SELECT id FROM contacts WHERE account_id=? AND identifier=?", (account_id, identifier)
        )
        row = await cursor.fetchone()
    return row[0]


async def get_contact(contact_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM contacts WHERE id=?", (contact_id,))
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_contact_by_identifier(account_id: int, identifier: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM contacts WHERE account_id=? AND identifier=?", (account_id, identifier)
        )
        row = await cursor.fetchone()
    return dict(row) if row else None


async def get_all_contacts() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM contacts ORDER BY created_at DESC")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def set_contact_status(contact_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contacts SET status=? WHERE id=?", (status, contact_id))
        await db.commit()


async def set_contact_auto_send(contact_id: int, auto_send: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contacts SET auto_send=? WHERE id=?", (int(auto_send), contact_id))
        await db.commit()


async def delete_contact(contact_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        await db.commit()


async def add_dialogue_message(contact_id: int, direction: str, text: str, status: str = "sent") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO dialogue_messages (contact_id, direction, text, status) VALUES (?, ?, ?, ?)",
            (contact_id, direction, text, status),
        )
        await db.commit()
        return cursor.lastrowid


async def get_dialogue_history(contact_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM dialogue_messages WHERE contact_id=? AND status != 'rejected' "
            "ORDER BY id DESC LIMIT ?",
            (contact_id, limit),
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in reversed(rows)]


async def get_message(message_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM dialogue_messages WHERE id=?", (message_id,))
        row = await cursor.fetchone()
    return dict(row) if row else None


async def set_message_status(message_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE dialogue_messages SET status=? WHERE id=?", (status, message_id))
        await db.commit()


async def set_message_text(message_id: int, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE dialogue_messages SET text=? WHERE id=?", (text, message_id))
        await db.commit()
