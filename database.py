from datetime import datetime, timedelta

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
    ("extra_instructions", "TEXT"),
    ("profile_ready", "INTEGER DEFAULT 0"),
    ("custom_instructions", "TEXT"),
    ("campaign_interval_min_seconds", "INTEGER DEFAULT 300"),
    ("campaign_interval_max_seconds", "INTEGER DEFAULT 900"),
    ("inactivity_timeout_hours", "INTEGER DEFAULT 24"),
    ("group_id", "INTEGER"),
]

# Added on top of the base `contacts` table for the "Активные"/"Корзина"
# categorization — 'active' while the conversation is live, 'trash' once the
# contact goes quiet past the account's inactivity timeout. Migrated the same
# idempotent way as the account profile columns.
_CONTACT_COLUMNS = [
    ("bucket", "TEXT DEFAULT 'active'"),
]

# NULL = still in the shared, unassigned pool; otherwise the id of the one
# account allowed to draw this contact into a campaign.
_PARSED_USER_COLUMNS = [
    ("assigned_account_id", "INTEGER"),
]


async def _ensure_account_columns(db):
    cursor = await db.execute("PRAGMA table_info(accounts)")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, decl in _ACCOUNT_PROFILE_COLUMNS:
        if name not in existing:
            await db.execute(f"ALTER TABLE accounts ADD COLUMN {name} {decl}")


async def _ensure_contact_columns(db):
    cursor = await db.execute("PRAGMA table_info(contacts)")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, decl in _CONTACT_COLUMNS:
        if name not in existing:
            await db.execute(f"ALTER TABLE contacts ADD COLUMN {name} {decl}")


async def _ensure_parsed_user_columns(db):
    cursor = await db.execute("PRAGMA table_info(parsed_users)")
    existing = {row[1] for row in await cursor.fetchall()}
    for name, decl in _PARSED_USER_COLUMNS:
        if name not in existing:
            await db.execute(f"ALTER TABLE parsed_users ADD COLUMN {name} {decl}")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS parsed_users (
                username TEXT PRIMARY KEY,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                assigned_account_id INTEGER
            )
        """)
        await _ensure_parsed_user_columns(db)
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
                auto_send INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                bucket TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_id, identifier)
            )
        """)
        await _ensure_contact_columns(db)
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS instruction_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS account_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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


async def clear_users():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM parsed_users")
        await db.commit()


async def remove_user(identifier: str):
    """Drops one identifier from the base — called once the bot has actually
    written to them, so they aren't offered again in a future campaign."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM parsed_users WHERE username = ?", (identifier,))
        await db.commit()


# ── распределение базы между аккаунтами ─────────────────────────────────────

async def get_base_counts() -> dict:
    """{'unassigned': N, 'by_account': {account_id: N, ...}}"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT assigned_account_id, COUNT(*) FROM parsed_users GROUP BY assigned_account_id"
        )
        rows = await cursor.fetchall()
    result = {"unassigned": 0, "by_account": {}}
    for account_id, count in rows:
        if account_id is None:
            result["unassigned"] = count
        else:
            result["by_account"][account_id] = count
    return result


async def get_users_for_account(account_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username FROM parsed_users WHERE assigned_account_id=? ORDER BY added_at DESC",
            (account_id,),
        )
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def get_unassigned_users() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT username FROM parsed_users WHERE assigned_account_id IS NULL ORDER BY added_at DESC"
        )
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def assign_users_to_account(usernames: list, account_id: int) -> list:
    """Adds each identifier to the base if new, and (re)assigns it to this
    account specifically. This takes priority over the even split — such
    contacts are never touched by distribute_unassigned_evenly."""
    touched = []
    async with aiosqlite.connect(DB_PATH) as db:
        for username in usernames:
            username = username.lower().strip()
            if not username:
                continue
            await db.execute("""
                INSERT INTO parsed_users (username, assigned_account_id) VALUES (?, ?)
                ON CONFLICT(username) DO UPDATE SET assigned_account_id=excluded.assigned_account_id
            """, (username, account_id))
            touched.append(username)
        await db.commit()
    return touched


async def distribute_unassigned_evenly(account_ids: list) -> dict:
    """Round-robins every currently-unassigned base contact across the given
    accounts. Contacts already assigned to a specific account (manually, or
    by an earlier distribution) are left untouched. Returns {account_id: N}."""
    counts = {aid: 0 for aid in account_ids}
    if not account_ids:
        return counts
    usernames = await get_unassigned_users()
    async with aiosqlite.connect(DB_PATH) as db:
        for i, username in enumerate(usernames):
            account_id = account_ids[i % len(account_ids)]
            await db.execute(
                "UPDATE parsed_users SET assigned_account_id=? WHERE username=?", (account_id, username)
            )
            counts[account_id] += 1
        await db.commit()
    return counts


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
        await db.execute(
            "UPDATE parsed_users SET assigned_account_id=NULL WHERE assigned_account_id=?", (account_id,)
        )
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
    goal: str | None = None, auto_send: bool = True,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO contacts (account_id, identifier, display_name, goal, auto_send, status, bucket)
            VALUES (?, ?, ?, ?, ?, 'active', 'active')
            ON CONFLICT(account_id, identifier) DO UPDATE SET
                display_name=excluded.display_name, goal=excluded.goal,
                auto_send=excluded.auto_send, status='active', bucket='active'
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


async def set_contact_ai_enabled(contact_id: int, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contacts SET ai_enabled=? WHERE id=?", (int(enabled), contact_id))
        await db.commit()


async def delete_contact(contact_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM contacts WHERE id=?", (contact_id,))
        await db.commit()


async def delete_contacts(contact_ids: list[int]):
    if not contact_ids:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        placeholders = ",".join("?" for _ in contact_ids)
        await db.execute(f"DELETE FROM contacts WHERE id IN ({placeholders})", contact_ids)
        await db.commit()


async def delete_all_contacts():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM contacts")
        await db.commit()


# ── "Активные" / "Корзина" ──────────────────────────────────────────────────

async def get_contacts_by_bucket(bucket: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM contacts WHERE bucket=? ORDER BY created_at DESC", (bucket,)
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def set_contact_bucket(contact_id: int, bucket: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE contacts SET bucket=? WHERE id=?", (bucket, contact_id))
        await db.commit()


async def set_contacts_bucket(contact_ids: list[int], bucket: str):
    if not contact_ids:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        placeholders = ",".join("?" for _ in contact_ids)
        await db.execute(
            f"UPDATE contacts SET bucket=? WHERE id IN ({placeholders})", [bucket, *contact_ids]
        )
        await db.commit()


async def get_stale_active_contacts() -> list[dict]:
    """Active contacts whose last message was outbound (we wrote, they never
    replied) longer ago than the owning account's inactivity timeout."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT c.id, c.account_id, c.identifier, c.display_name,
                   COALESCE(a.inactivity_timeout_hours, 24) AS timeout_hours,
                   lm.direction AS last_direction, lm.created_at AS last_at
            FROM contacts c
            JOIN accounts a ON a.id = c.account_id
            LEFT JOIN dialogue_messages lm ON lm.id = (
                SELECT dm.id FROM dialogue_messages dm
                WHERE dm.contact_id = c.id
                ORDER BY dm.id DESC LIMIT 1
            )
            WHERE c.bucket = 'active'
        """)
        rows = await cursor.fetchall()

    now = datetime.utcnow()
    stale = []
    for r in rows:
        if r["last_direction"] != "out" or not r["last_at"]:
            continue
        try:
            last_at = datetime.strptime(r["last_at"], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        timeout_hours = r["timeout_hours"] or 24
        if now - last_at >= timedelta(hours=timeout_hours):
            stale.append(dict(r))
    return stale


# ── шаблоны инструкций ───────────────────────────────────────────────────────

async def create_template(name: str, content: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO instruction_templates (name, content) VALUES (?, ?)", (name, content)
        )
        await db.commit()
        return cursor.lastrowid


async def get_templates() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM instruction_templates ORDER BY created_at DESC")
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_template(template_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM instruction_templates WHERE id=?", (template_id,))
        row = await cursor.fetchone()
    return dict(row) if row else None


async def delete_template(template_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM instruction_templates WHERE id=?", (template_id,))
        await db.commit()


# ── связки аккаунтов (общие инструкции) ─────────────────────────────────────

async def create_account_group() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("INSERT INTO account_groups DEFAULT VALUES")
        await db.commit()
        return cursor.lastrowid


async def delete_account_group(group_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET group_id=NULL WHERE group_id=?", (group_id,))
        await db.execute("DELETE FROM account_groups WHERE id=?", (group_id,))
        await db.commit()


async def set_account_group(account_id: int, group_id: int | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET group_id=? WHERE id=?", (group_id, account_id))
        await db.commit()


async def get_accounts_in_group(group_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE group_id=? ORDER BY created_at", (group_id,))
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def propagate_group_instructions(group_id: int, content: str | None):
    """Pushes one shared instructions document to every account in the group —
    used so that a fix learned on one linked account (e.g. via the unknown-
    pattern flow) is applied identically on all of them."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET custom_instructions=?, profile_ready=? WHERE group_id=?",
            (content, 1 if content else 0, group_id),
        )
        await db.commit()


async def dissolve_group_if_alone(group_id: int):
    """Cleans up a group left with 0-1 members after an unlink — a 'group' of
    one account is meaningless, so just dissolve it back to standalone."""
    members = await get_accounts_in_group(group_id)
    if len(members) <= 1:
        await delete_account_group(group_id)


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
