import pandas as pd
import sqlite3

DB_NAME = "boardgames9_blank.db"

def create_tables():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # ---- Games ----
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS games (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        barcode TEXT UNIQUE NOT NULL
    )
    """)

    # ---- Components ----
    # NINCS lost_amount
    # NINCS currently_missing
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS components (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER,
        name TEXT NOT NULL,
        damaged_amount INTEGER DEFAULT 0,
        FOREIGN KEY(game_id) REFERENCES games(id)
    )
    """)

    # ---- Returns ----
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER,
        return_date TEXT,
        all_ok INTEGER,
        patron_barcode TEXT,
        FOREIGN KEY(game_id) REFERENCES games(id)
    )
    """)

    # ---- Missing Items (ESEMÉNYALAPÚ) ----
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS missing_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        return_id INTEGER,
        game_id INTEGER,
        game_name TEXT,
        component_id INTEGER,
        component_name TEXT,

        missing_amount INTEGER DEFAULT 1,
        replaced_amount INTEGER DEFAULT 0,
        lost_amount INTEGER DEFAULT 0,
        found_amount INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ACTIVE',
        -- ACTIVE | REPLACED | LOST

        replaced_on_date TEXT,
        closed_on_date TEXT,

        FOREIGN KEY(return_id) REFERENCES returns(id),
        FOREIGN KEY(game_id) REFERENCES games(id),
        FOREIGN KEY(component_id) REFERENCES components(id)
    )
    """)

    conn.commit()

    # ---- INDEXEK ----

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_components_game_id
        ON components(game_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_returns_game_id
        ON returns(game_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_missing_component_id
        ON missing_items(component_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_missing_return_id
        ON missing_items(return_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_missing_status
        ON missing_items(status)
    """)

    conn.commit()
    conn.close()
    print("Import kész.")

if __name__ == "__main__":
    create_tables()
