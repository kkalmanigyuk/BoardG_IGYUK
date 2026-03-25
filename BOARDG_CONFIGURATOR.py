import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
import json
import os
import sqlite3
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox
import sqlite3

CONFIG_FILE = "boardg_config.json"


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

class ConfigApp:

    def __init__(self, root):
        self.root = root
        self.root.title("BOARDG Konfigurátor")
        self.icon = tk.PhotoImage(file="konfig16_icon.png")
        self.root.iconphoto(True, self.icon)

        self.config_data = load_config()

        # ===== Adatbázis elérése =====
        tk.Label(root, text="Adatbázis elérési út:").pack(anchor="w")

        self.db_var = tk.StringVar(
            value=self.config_data.get("database", {}).get("path", "")
        )

        tk.Entry(root, textvariable=self.db_var, width=50).pack()

        tk.Button(root, text="Tallózás", command=self.browse_db).pack(pady=5)

        # ===== Kölcsönzés mappa=====
        tk.Label(root, text="Kölcsönzések:").pack(anchor="w")

        self.checkout_var = tk.StringVar(
            value=self.config_data.get("paths", {}).get("kölcsönzések", "")
        )

        tk.Entry(root, textvariable=self.checkout_var, width=50).pack()

        tk.Button(root, text="Tallózás", command=self.browse_checkoutfolder).pack(pady=5)

        # ===== Visszavétel mappa=====
        tk.Label(root, text="Visszavételek:").pack(anchor="w")

        self.checkin_var = tk.StringVar(
            value=self.config_data.get("paths", {}).get("visszavételek", "")
        )

        tk.Entry(root, textvariable=self.checkin_var, width=50).pack()

        tk.Button(root, text="Tallózás", command=self.browse_checkinfolder).pack(pady=5)

        # ===== Hiányos visszavétel mappa=====
        tk.Label(root, text="Hiányos visszahozatalok:").pack(anchor="w")

        self.missingcheckinpath_var = tk.StringVar(
            value=self.config_data.get("paths", {}).get("hiánylisták", "")
        )

        tk.Entry(root, textvariable=self.missingcheckinpath_var, width=50).pack()

        tk.Button(root, text="Tallózás", command=self.browse_missingcheckinfolder).pack(pady=5)

        # ===== SIP CONFIG =====
        tk.Label(root, text="--- SIP Beállítások ---", font=("Arial", 10, "bold")).pack(pady=(10, 0), anchor="w")

        # ===== SIP ENABLE =====
        self.sip_enabled_var = tk.BooleanVar(
            value=self.config_data.get("SIP config", {}).get("SIP_ENABLED", True)
        )

        tk.Checkbutton(
            root,
            text="SIP kapcsolat engedélyezve",
            variable=self.sip_enabled_var
        ).pack(anchor="w", pady=(5, 10))

        # SIP2_SERVER
        tk.Label(root, text="SIP2 szerver:").pack(anchor="w")

        self.sip_server_var = tk.StringVar(
            value=self.config_data.get("SIP config", {}).get("SIP2_SERVER", "")
        )

        tk.Entry(root, textvariable=self.sip_server_var, width=50).pack()

        # SIP2_PORT
        tk.Label(root, text="SIP2 port:").pack(anchor="w")

        self.sip_port_var = tk.IntVar(
            value=self.config_data.get("SIP config", {}).get("SIP2_PORT", 0)
        )

        tk.Entry(root, textvariable=self.sip_port_var, width=20).pack()

        # TERMINAL_PASSWORD
        tk.Label(root, text="Terminál jelszó (AC mező):").pack(anchor="w")

        self.sip_password_var = tk.StringVar(
            value=self.config_data.get("SIP config", {}).get("TERMINAL_PASSWORD", "")
        )

        tk.Entry(root, textvariable=self.sip_password_var, width=30, show="*").pack()

        tk.Button(root, text="ÚJ adatbázis létrehozása", command=self.create_tables).pack(pady=10)

        tk.Button(
            root,
            text="Adatbázis feltöltése MARC XML-ből",
            command=self.import_from_marc_xml
        ).pack(pady=10)

        # ===== Save =====
        tk.Button(root, text="Mentés", command=self.save).pack(pady=10)


    def browse_db(self):
        path = filedialog.askopenfilename(
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if path:
            self.db_var.set(path)

    def browse_checkoutfolder(self):
        path = filedialog.askdirectory()
        if path:
            self.checkout_var.set(path)

    def browse_checkinfolder(self):
        path = filedialog.askdirectory()
        if path:
            self.checkin_var.set(path)

    def browse_missingcheckinfolder(self):
        path = filedialog.askdirectory()
        if path:
            self.missingcheckinpath_var.set(path)

    def import_from_marc_xml(self):

        # ===== DB kiválasztás =====
        db_path = filedialog.askopenfilename(
            title="Adatbázis kiválasztása",
            filetypes=[("SQLite DB", "*.db")]
        )

        if not db_path:
            return

        # ===== XML kiválasztás =====
        xml_path = filedialog.askopenfilename(
            title="MARC XML kiválasztása",
            filetypes=[("XML fájl", "*.xml")]
        )

        if not xml_path:
            return

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            tree = ET.parse(xml_path)
            root = tree.getroot()

            ns = {"marc": "http://www.loc.gov/MARC21/slim"}

            records = root.findall(".//marc:record", ns)

            inserted_games = 0

            for record in records:

                # ===== CÍM =====
                title = None
                df_245 = record.find("marc:datafield[@tag='245']", ns)
                if df_245 is not None:
                    sub = df_245.find("marc:subfield[@code='a']", ns)
                    if sub is not None and sub.text:
                        title = sub.text.strip()

                # ===== VONALKÓD =====
                barcode = None
                df_949 = record.find("marc:datafield[@tag='949']", ns)
                if df_949 is not None:
                    sub = df_949.find("marc:subfield[@code='z']", ns)
                    if sub is not None and sub.text:
                        barcode = sub.text.strip()

                if not title or not barcode:
                    continue  # kihagyjuk a hibás rekordot

                # ===== JÁTÉK INSERT =====
                try:
                    cursor.execute("""
                        INSERT INTO games (name, barcode)
                        VALUES (?, ?)
                    """, (title, barcode))

                    game_id = cursor.lastrowid

                except sqlite3.IntegrityError:
                    # már létezik a barcode → kihagyjuk
                    continue

                # ===== KOMPONENSEK =====
                components = []

                df_500 = record.find("marc:datafield[@tag='500']", ns)
                if df_500 is not None:
                    sub = df_500.find("marc:subfield[@code='a']", ns)
                    if sub is not None and sub.text:

                        text = sub.text.strip()
                        prefix = "A doboz tartalma:"

                        if text.startswith(prefix):
                            text = text[len(prefix):].strip()

                        components = [
                            c.strip()
                            for c in text.split(",")
                            if c.strip()
                        ]

                # ===== COMPONENTS INSERT =====
                for comp in components:
                    cursor.execute("""
                        INSERT INTO components (game_id, name)
                        VALUES (?, ?)
                    """, (game_id, comp))

                inserted_games += 1

            conn.commit()
            conn.close()

            messagebox.showinfo(
                "Kész",
                f"{inserted_games} játék importálva."
            )

        except Exception as e:
            messagebox.showerror("Hiba", str(e))

    def save(self):

        new_config = {
            "database": {
                "path": self.db_var.get()
            },
            "paths": {
                "kölcsönzések": self.checkout_var.get(),
                "visszavételek": self.checkin_var.get(),
                "hiánylisták": self.missingcheckinpath_var.get()
            },
            "SIP config": {
                "SIP_ENABLED": self.sip_enabled_var.get(),
                "SIP2_SERVER": self.sip_server_var.get(),
                "SIP2_PORT": self.sip_port_var.get(),
                "TERMINAL_PASSWORD": self.sip_password_var.get()
            }
        }

        save_config(new_config)

        messagebox.showinfo("OK", "Beállítások mentve!")


    def create_tables(self):

        # ===== fájl kiválasztása =====
        db_path = filedialog.asksaveasfilename(
            title="Új adatbázis létrehozása",
            defaultextension=".db",
            filetypes=[("SQLite adatbázis", "*.db")],
        )

        if not db_path:
            return  # felhasználó megszakította

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # ---- Games ----
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            barcode TEXT UNIQUE NOT NULL
        )
        """)

        # ---- Components ----
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

        # ---- Missing Items ----
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

        messagebox.showinfo("Kész", f"Adatbázis létrehozva:\n{db_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ConfigApp(root)
    root.mainloop()