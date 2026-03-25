import tkinter as tk
from tkinter import messagebox, ttk
import sqlite3
from tkinter import simpledialog
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from datetime import datetime
import socket
import os
import json
import re

CONFIG_FILE = "boardg_config.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()

DB_NAME = config["database"]["path"]
SIP_ENABLED = config["SIP config"]["SIP_ENABLED"]
SIP2_SERVER = config["SIP config"]["SIP2_SERVER"]
SIP2_PORT = config["SIP config"]["SIP2_PORT"]
TERMINAL_PASSWORD = config["SIP config"]["TERMINAL_PASSWORD"]
CHECKOUT_PDF_PATH = config["paths"]["kölcsönzések"]
CHECKIN_PDF_PATH = config["paths"]["visszavételek"]
MISSING_PDF_PATH = config["paths"]["hiánylisták"]

# ---- Hardcoded elérési utak ----
# # SIP2 szerver adatok
# SIP2_SERVER = 'corvina.igyuk.hu'
# SIP2_PORT = 5192
# TERMINAL_PASSWORD = 'EXTPROG'  # Add meg a terminál jelszavát, ha szükséges
# DB_NAME = "boardgames5.db"




class GameCheckApp:


    def __init__(self, root):
        self.root = root
        self.root.title("BOARDG V1.5 - Társasjátékok a könyvtárban")
        self.root.geometry("500x760")
        self.icon = tk.PhotoImage(file="favicon16.png")
        self.root.iconphoto(True, self.icon)

        self.conn = sqlite3.connect(DB_NAME)
        self.current_game_id = None

        self.build_ui()
        self.refresh_game_dropdown()

    def build_ui(self):
        # ===== Olvasó vonalkód =====
        tk.Label(self.root, text="Olvasó vonalkód:").pack(pady=(10, 2))
        self.patron_entry = tk.Entry(self.root, width=40)
        self.patron_entry.pack()
        self.patron_name_label = tk.Label(self.root, text="", fg="blue")
        self.patron_name_label.pack(pady=(2))

        # ENTER-re induljon a lekérdezés
        self.patron_entry.bind("<Return>", self.lookup_patron)

        # ===== Vonalkód beolvasás =====
        tk.Label(self.root, text="Játék vonalkód:").pack(pady=5)
        self.barcode_entry = tk.Entry(self.root, width=40)
        self.barcode_entry.pack()
        self.barcode_entry.bind("<Return>", self.load_game_by_barcode)

        # ===== Játék kiválasztása név szerint =====
        tk.Label(self.root, text="Játék kiválasztása:").pack(pady=5)
        self.game_selector = ttk.Combobox(self.root, width=47)
        self.game_selector.pack()
        self.game_selector.bind("<<ComboboxSelected>>", self.select_game_from_dropdown)

        # ===== Játék neve =====
        self.game_label = tk.Label(self.root, text="", font=("Arial", 14, "bold"))
        self.game_label.pack(pady=10)

        # ===== Checklist (görgethető) =====
        self.checklist_container = tk.Frame(self.root)
        self.checklist_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.checklist_container)
        self.scrollbar = tk.Scrollbar(self.checklist_container, orient="vertical", command=self.canvas.yview)

        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # ===== Egérgörgő csak a checklist fölött működjön =====

        def _on_mousewheel(event):
            canvas_height = self.canvas.winfo_height()
            content_height = self.scrollable_frame.winfo_height()

            if content_height <= canvas_height:
                return

            first, last = self.canvas.yview()

            # Ha fent vagyunk és felfelé próbál scrollozni
            if first <= 0 and event.delta > 0:
                return

            # Ha lent vagyunk és lefelé próbál scrollozni
            if last >= 1 and event.delta < 0:
                return

            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(event):
            self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event):
            self.canvas.unbind_all("<MouseWheel>")

        self.canvas.bind("<Enter>", _bind_mousewheel)
        self.canvas.bind("<Leave>", _unbind_mousewheel)

        self.check_vars = []

        # ===== Gombok =====
        self.save_button = tk.Button(
            self.root, text="Visszavétel & bizonylat",
            command=self.checkin_and_save, bg="#6fa8dc", fg="black"
        )
        self.save_button.pack(pady=5)

        self.save_button_no_checkin = tk.Button(
            self.root,
            text="Hiánybizonylat kiállítása",
            command=self.save_return_to_db_and_print_no_SIP,
            bg="#9fc5e8",
            fg="black"
        )

        self.save_button_no_checkin.pack(pady=5)


        tk.Button(
            self.root,
            text="Kölcsönzés & bizonylat",
            command=self.checkout_and_print,
            bg="#2ecc71",
            fg="black"
        ).pack(pady=5)

        btn_new_game = tk.Button(
            self.root,
            text="Új játék rögzítése",
            command=self.open_new_game_window,
            bg="#f3af1a",
            fg="black"
        )
        btn_new_game.pack(pady=5)

        btn_edit_components = tk.Button(
            self.root,
            text="Kiegészítők szerkesztése",
            command=self.open_components_editor,
        bg = "#ffd966",
        fg = "black"
        )
        btn_edit_components.pack(pady=5)

        self.view_missing_button = tk.Button(
            self.root, text="Hiánylista megtekintése",
            command=self.show_missing_items, bg="#dc1814", fg="black"
        )
        self.view_missing_button.pack(pady=5)

        self.view_returns_button = tk.Button(
            self.root, text="Visszavételi tranzakciók",
            command=self.show_returns, bg="#e06666", fg="black"
        )
        self.view_returns_button.pack(pady=5)
        self.canvas.bind_all("<MouseWheel>",
                             lambda event: self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units"))

    def reset_ui(self):
        self.game_label.config(text="")
        self.barcode_entry.delete(0, tk.END)
        self.game_selector.set("")
        self.patron_entry.delete(0, tk.END)
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.current_game_id = None



    def load_game_list(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM games ORDER BY name")
        games = [row[0] for row in cursor.fetchall()]
        self.game_selector["values"] = games

    def select_game_from_dropdown(self, event=None):
        selected_name = self.game_selector.get()
        if selected_name in self.game_map:
            self.load_game(self.game_map[selected_name])


    def refresh_game_dropdown(self, select_game_id=None):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name FROM games ORDER BY name")
        games = cursor.fetchall()

        # name → id mapping
        self.game_map = {name: gid for gid, name in games}

        # Combobox frissítése
        self.game_selector["values"] = list(self.game_map.keys())

        # Ha meg van adva ID, automatikusan kiválasztjuk
        if select_game_id:
            for name, gid in self.game_map.items():
                if gid == select_game_id:
                    self.game_selector.set(name)
                    self.load_game(gid)
                    break

    # ===== Vonalkód alapján =====
    def load_game_by_barcode(self, event=None):
        barcode = self.barcode_entry.get().strip()
        cursor = self.conn.cursor()
        cursor.execute("SELECT id FROM games WHERE barcode = ?", (barcode,))
        result = cursor.fetchone()
        if not result:
            messagebox.showerror("Hiba", "Nem található játék ezzel a vonalkóddal.")
            return
        self.load_game(result[0])

    # ===== Játék betöltése ID alapján =====
    def load_game(self, game_id):
        self.current_game_id = game_id
        cursor = self.conn.cursor()
        cursor.execute("SELECT name, barcode FROM games WHERE id = ?", (game_id,))
        game = cursor.fetchone()
        if not game:
            return
        name, barcode = game
        self.game_label.config(text=name)
        self.barcode_entry.delete(0, tk.END)
        self.barcode_entry.insert(0, barcode)

        # Checklist üresen indul
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.check_vars.clear()

        cursor.execute("""
            SELECT 
                c.id,
                c.name,

                -- összes elveszett
                IFNULL(SUM(mi.lost_amount), 0) AS total_lost,

                -- sérült (maradt components-ben)
                IFNULL(c.damaged_amount, 0),

                -- aktív hiány
(
    IFNULL(SUM(mi.missing_amount), 0)
    - IFNULL(SUM(mi.replaced_amount), 0)
    - IFNULL(SUM(mi.lost_amount), 0)
) AS still_missing

            FROM components c

            LEFT JOIN missing_items mi
                ON c.id = mi.component_id

            WHERE c.game_id = ?

            GROUP BY c.id
        """, (game_id,))
        components = cursor.fetchall()

        for comp_id, comp_name, lost_amount, damaged_amount, still_missing in components:
            var = tk.BooleanVar(value=False)
            frame = tk.Frame(self.scrollable_frame)
            frame.pack(anchor="w", fill="x")

            # ===== STÁTUSZ SZÖVEG =====
            status_parts = []

            if lost_amount > 0:
                status_parts.append(f"❌ elveszett: {lost_amount}")

            if still_missing > 0:
                status_parts.append(f"🔄 kallódik: {still_missing}")

            if damaged_amount > 0:
                status_parts.append(f"⚠️ sérült: {damaged_amount}")

            display_name = comp_name
            if status_parts:
                display_name += " (" + " | ".join(status_parts) + ")"

            chk = tk.Checkbutton(
                frame,
                text=display_name,
                variable=var
            )

            # belső adatok megőrzése
            chk.var = var
            chk.component_id = comp_id
            chk.component_name = comp_name  # TISZTA név
            chk.pack(side="left")

            # hiányzó darabszám Entry
            amount_var = tk.StringVar(value="1")
            entry = tk.Entry(frame, width=4, textvariable=amount_var)
            entry.pack(side="left", padx=5)

            chk.amount_var = amount_var


    def create_patron_status_request(self, patron_id):
        current_datetime = datetime.now().strftime("%Y%m%d    %H%M%S")
        message = f'23000{current_datetime}|AO|AAEMELT{patron_id}|AC{TERMINAL_PASSWORD}|AD|\r'
        return message

    def parse_sip2_response(self, response):
        fields = response.strip().split('|')
        parsed_fields = {}
        for field in fields:
            if len(field) >= 2:
                key = field[:2]
                value = field[2:]
                parsed_fields[key] = value
        return parsed_fields



    def extract_due_date(self, sip_response):
        fields = sip_response.split("|")

        for field in fields:
            if field.startswith("AH"):
                return field[2:].strip()

        return None

    def extract_field(self, sip_response, field_code):
        fields = sip_response.split("|")
        for field in fields:
            if field.startswith(field_code):
                return field[len(field_code):].strip()
        return None

    def lookup_patron(self, event=None):
        patron_id = self.patron_entry.get().strip()
        if not SIP_ENABLED:
            self.patron_name_label.config(
                text="Offline mód (SIP kikapcsolva)",
                fg="orange"
            )
            return

        if not patron_id:
            return

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((SIP2_SERVER, SIP2_PORT))

                message = self.create_patron_status_request(patron_id)
                print (message)
                s.sendall(message.encode("utf-8"))

                response = s.recv(4096).decode("utf-8")

                print("=== SIP PATRON STATUS RESPONSE ===")
                print(response)
                print("==================================")

            parsed = self.parse_sip2_response(response)

            patron_name = parsed.get("AE")
            validity = parsed.get("BL")  # Y vagy N

            # ===== Ha nincs találat / nincs AE mező =====
            if not patron_name:
                self.patron_name_label.config(
                    text="Az olvasónak nincs EMELT tagsága",
                    fg="red"
                )
                return

            # ===== Ha van név =====
            if validity == "Y":
                self.patron_name_label.config(
                    text=f"Olvasó neve: {patron_name}",
                    fg="green"
                )
            else:
                self.patron_name_label.config(
                    text=f"Olvasó neve: {patron_name} (Lejárt EMELT tagság)",
                    fg="red"
                )

        except Exception as e:
            self.patron_name_label.config(
                text="SIP kapcsolat hiba!",
                fg="red"
            )
            print("SIP hiba:", e)

    def create_login_request(self):
        message = (
            f"9300"
            f"CNEXTPROG|"
            f"CO|"
            "\r"
        )
        return message

    def create_checkout_request(self, patron_id, item_barcode):
        current_datetime = datetime.now().strftime("%Y%m%d    %H%M%S")

        nb_due_date = " " * 18  # 18 space

        message = (
            f"11YN"
            f"{current_datetime}"
            f"{nb_due_date}"
            f"AO|"  # lehet üres is
            f"AA{patron_id}|"
            f"AB{item_barcode}|"
            f"AC{TERMINAL_PASSWORD}|"
            f"AD|"
            "\r"
        )

        return message

    def send_checkout(self):
        patron_id = self.patron_entry.get().strip()
        item_barcode = self.barcode_entry.get().strip()

        if not SIP_ENABLED:
            return "OFFLINE_OK"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((SIP2_SERVER, SIP2_PORT))

                # ===== LOGIN =====
                login_msg = self.create_login_request()
                print(">>>", login_msg.strip())
                s.sendall(login_msg.encode("utf-8"))

                login_response = s.recv(4096).decode("utf-8")
                print("<<<", login_response.strip())

                # ===== CHECKOUT =====
                checkout_msg = self.create_checkout_request(patron_id, item_barcode)
                print(">>>", checkout_msg.strip())
                s.sendall(checkout_msg.encode("utf-8"))

                response = s.recv(4096).decode("utf-8")
                print("<<<", response.strip())

            return response

        except Exception as e:
            print("Checkout hiba:", e)
            return None

    def create_checkin_request(self, item_barcode):
        current_datetime = datetime.now().strftime("%Y%m%d    %H%M%S")

        return_date = " " * 18  # 18 space

        message = (
            f"09N"
            f"{current_datetime}"
            f"{return_date}"
            f"AO|"
            f"AB{item_barcode}|"
            f"AC{TERMINAL_PASSWORD}|"
            f"AP|"
            "\r"
        )

        return message

    def send_checkin(self):
        item_barcode = self.barcode_entry.get().strip()
        if not SIP_ENABLED:
            return "OFFLINE_OK"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((SIP2_SERVER, SIP2_PORT))

                # ===== LOGIN =====
                login_msg = self.create_login_request()
                print(">>>", login_msg.strip())
                s.sendall(login_msg.encode("utf-8"))
                print("<<<", s.recv(4096).decode("utf-8").strip())

                # ===== CHECKIN =====
                checkin_msg = self.create_checkin_request(item_barcode)
                print(">>>", checkin_msg.strip())
                s.sendall(checkin_msg.encode("utf-8"))

                response = s.recv(4096).decode("utf-8")
                print("<<<", response.strip())

            return response

        except Exception as e:
            print("Checkin hiba:", e)
            return None


    def generate_checkout_pdf(self, due_date):
        patron = self.patron_entry.get().strip()
        checkout_timestamp = datetime.now().strftime("%Y%m%d")
        game = self.game_label.cget("text")


        def safe_filename(text):
            return re.sub(r'[\\/*?:"<>|]', "_", text)


        game_safe = safe_filename(game)

        filename = f"kolcsonzes_{patron}_{checkout_timestamp}_{game_safe}.pdf"

        os.makedirs(CHECKOUT_PDF_PATH, exist_ok=True)

        file_path = os.path.join(CHECKOUT_PDF_PATH, filename)

        def shorten(text, length=24):
            return text if len(text) <= length else text[:length - 3] + "..."

        # ===== MEGJEGYZÉS BEKÉRÉSE =====
        note = simpledialog.askstring(
            "Megjegyzés",
            "Szeretne megjegyzést hozzáadni a bizonylathoz?\n(Ha nem, hagyja üresen.)"
        )

        if note is None:
            # Felhasználó megszakította (Cancel)
            return


        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))

        doc = SimpleDocTemplate(
            file_path,
            pagesize=A4
        )

        elements = []
        styles = getSampleStyleSheet()

        styles = getSampleStyleSheet()

        normal = ParagraphStyle(
            "NormalUnicode",
            parent=styles["Normal"],
            fontName="DejaVuSans",
            fontSize=11
        )

        title_style = ParagraphStyle(
            "TitleUnicode",
            parent=styles["Heading1"],
            fontName="DejaVuSans",
            alignment=TA_CENTER
        )


        # ===== FEJLÉC =====
        elements.append(Paragraph("Illyés Gyula Könyvtár", title_style))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Kölcsönzési bizonylat - Társasjáték", title_style))
        elements.append(Spacer(1, 12))

        # ===== ALAP ADATOK =====
        patron = self.patron_entry.get()
        full_text = self.patron_name_label.cget("text")

        if ":" in full_text:
            stripped_patron_name = full_text.split(":", 1)[1].strip()
        else:
            stripped_patron_name = full_text if full_text else "Ismeretlen"

        if ":" in full_text:
            stripped_patron_name = full_text.split(":", 1)[1].strip()
        else:
            stripped_patron_name = full_text  # fallback (offline vagy hiba esetén)
        barcode = self.barcode_entry.get()
        game = self.game_label.cget("text")

        elements.append(Paragraph(f"<b>Kölcsönző:</b> {patron} - {stripped_patron_name} ", normal))
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(f"<b>Vonalkód:</b> {barcode}", normal))
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(f"<b>Játék neve:</b> {game}", normal))
        elements.append(Spacer(1, 5))
        if due_date:
            elements.append(Paragraph(f"<b>Visszahozatal határideje:</b> {due_date}", normal))
        elements.append(Spacer(1, 12))

        # ===== CHECKLIST =====
        elements.append(Paragraph("<b>Kiegészítők:</b>", normal))
        elements.append(Spacer(1, 6))

        checklist_data = [["Tétel", "Sérült", "Kallódik"]]

        cursor = self.conn.cursor()
        cursor.execute("""
SELECT 
    c.name,
    IFNULL(c.damaged_amount,0),
    IFNULL(SUM(mi.missing_amount),0) -
    IFNULL(SUM(mi.replaced_amount),0) AS currently_missing

FROM components c

LEFT JOIN missing_items mi 
    ON c.id = mi.component_id

WHERE c.game_id = ?

GROUP BY c.id
ORDER BY c.name
        """, (self.current_game_id,))

        rows = cursor.fetchall()

        for name, damaged, currently_missing in rows:
            checklist_data.append([
                shorten(name),
                str(damaged or 0),
                str(currently_missing or 0)
            ])


        table = Table(
            checklist_data,
            colWidths=[90 * mm, 25 * mm, 25 * mm]
        )
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 24))

        if note.strip():
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("<b>Megjegyzés:</b>", normal))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(note, normal))
            elements.append(Spacer(1, 12))

        # ===== ALÁÍRÁS RÉSZ =====
        signature_table = Table(
            [
                ["", "\n\n\n____________________", "\n\n\n____________________"],
                ["", "   Átadó aláírása", "   Átvevő aláírása"]
            ],
            colWidths=[6 * mm, 80 * mm, 80 * mm]
        )
        signature_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
        ]))


        elements.append(signature_table)
        elements.append(Spacer(1, 24))

        # ===== KELTEZÉS =====
        today = datetime.now().strftime("%Y.%m.%d")
        elements.append(Paragraph(f"Keltezés: {today}", normal))

        doc.build(elements)

        full_path = os.path.abspath(file_path)
        os.startfile(full_path)

#        messagebox.showinfo("PDF kész", f"Bizonylat elkészült:\n{os.path.abspath(file_path)}")

    def checkout_and_print(self):

        # ===== OFFLINE =====
        if not SIP_ENABLED:
            messagebox.showinfo("Offline mód", "SIP kikapcsolva – csak bizonylat készül.")
            self.generate_checkout_pdf(due_date=None)
            return

        # ===== ONLINE =====
        response = self.send_checkout()



        if not response:
            messagebox.showerror("Hiba", "Nincs válasz a SIP szervertől.")
            return

        if response.startswith("121"):
            due_date = self.extract_due_date(response)
            messagebox.showinfo("Sikeres kölcsönzés", "A kölcsönzés sikeres")
            self.generate_checkout_pdf(due_date)
            return

        af_message = self.extract_field(response, "AF") or "Ismeretlen hiba történt."
        messagebox.showerror("Sikertelen kölcsönzés", af_message)

        if not response:
            messagebox.showerror("Hiba", "Nincs válasz a SIP szervertől.")
            return

        print("=== SIP CHECKOUT RESPONSE ===")
        print(response)
        print("==================================")

        # ===== SIKER =====
        if response.startswith("121"):
            due_date = self.extract_due_date(response)
            messagebox.showinfo("Sikeres kölcsönzés", "A kölcsönzés sikeres")
            self.generate_checkout_pdf(due_date)
            return

        # ===== HIBA =====
        af_message = self.extract_field(response, "AF")

        if not af_message:
            af_message = "Ismeretlen hiba történt."

        messagebox.showerror(
            "Sikertelen kölcsönzés",
            af_message
        )

    def generate_checkin_pdf(self, patron, barcode, game, missing_items):
        if not SIP_ENABLED:
            messagebox.showinfo("Offline mód", "SIP kikapcsolva – csak visszavételi bizonylat készül.")
            self.generate_checkin_pdf(...)
            return
        patron = self.patron_entry.get().strip()
        checkin_timestamp = datetime.now().strftime("%Y%m%d")


        def safe_filename(text):
            return re.sub(r'[\\/*?:"<>|]', "_", text)

        game_safe = safe_filename(game)

        filename = f"visszavetel_{patron}_{checkin_timestamp}_{game_safe}.pdf"

        os.makedirs(MISSING_PDF_PATH, exist_ok=True)

        file_path = os.path.join(MISSING_PDF_PATH, filename)
        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))

        # ===== MEGJEGYZÉS BEKÉRÉSE =====
        note = simpledialog.askstring(
            "Megjegyzés",
            "Szeretne megjegyzést hozzáadni a bizonylathoz?\n(Ha nem, hagyja üresen.)"
        )

        if note is None:
            # Felhasználó megszakította (Cancel)
            return

        doc = SimpleDocTemplate(
            file_path,
            pagesize=A4
        )

        elements = []
        styles = getSampleStyleSheet()

        normal = ParagraphStyle(
            "NormalUnicode",
            parent=styles["Normal"],
            fontName="DejaVuSans",
            fontSize=11
        )

        title_style = ParagraphStyle(
            "TitleUnicode",
            parent=styles["Heading1"],
            fontName="DejaVuSans",
            alignment=TA_CENTER
        )

        # ===== FEJLÉC =====
        elements.append(Paragraph("Illyés Gyula Könyvtár", title_style))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Visszavételi bizonylat - Társasjáték", title_style))
        elements.append(Spacer(1, 12))

        patron = self.patron_entry.get()
        full_text = self.patron_name_label.cget("text")

        if ":" in full_text:
            stripped_patron_name = full_text.split(":", 1)[1].strip()
        else:
            stripped_patron_name = full_text if full_text else "Ismeretlen"

        barcode = self.barcode_entry.get()
        game = self.game_label.cget("text")

        elements.append(Paragraph(f"<b>Kölcsönző:</b> {patron} - {stripped_patron_name} ", normal))
        elements.append(Paragraph(f"<b>Vonalkód:</b> {barcode}", normal))
        elements.append(Paragraph(f"<b>Játék neve:</b> {game}", normal))
        elements.append(Spacer(1, 12))

        # ===== HIÁNYZÓ TÉTELEK =====
        elements.append(Paragraph("<b>Hiányzó / nem visszahozott tételek:</b>", normal))
        elements.append(Spacer(1, 6))

        checklist_data = [["Tétel (eredeti mennyiséggel)", "Hiányzó darabszám"]]

        def shorten(text, length=24):
            return text if len(text) <= length else text[:length - 3] + "..."

        for item in missing_items:
            name = shorten(item["component_name"])
            amount = item["missing_amount"]
            checklist_data.append([name, str(amount)])

        # Ha minden visszaérkezett
        if len(checklist_data) == 1:
            checklist_data.append(["Minden tétel visszaérkezett.", ""])

        table = Table(checklist_data, colWidths=[100 * mm, 30 * mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 24))

        if note.strip():
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("<b>Megjegyzés:</b>", normal))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(note, normal))
            elements.append(Spacer(1, 12))


        # ===== ALÁÍRÁS =====
        signature_table = Table(
            [
                ["", "\n\n\n____________________", "\n\n\n____________________"],
                ["", "   Átadó aláírása", "   Átvevő aláírása"]
            ],
            colWidths=[6 * mm, 80 * mm, 80 * mm]
        )

        signature_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
        ]))

        elements.append(signature_table)
        elements.append(Spacer(1, 24))

        today = datetime.now().strftime("%Y.%m.%d")
        elements.append(Paragraph(f"Keltezés: {today}", normal))

        doc.build(elements)
        full_path = os.path.abspath(file_path)
        os.startfile(full_path)

#        messagebox.showinfo("PDF kész", f"Bizonylat elkészült:\n{os.path.abspath(file_path)}")


    #Hiányos visszahozatal esetén ez a PDF készül el
    def generate_checkin_pdf_no_SIP(self, patron, barcode, game, missing_items):
        patron = self.patron_entry.get().strip()
        checkin_timestamp = datetime.now().strftime("%Y%m%d")

        def safe_filename(text):
            return re.sub(r'[\\/*?:"<>|]', "_", text)

        game_safe = safe_filename(game)

        filename = f"kolcsonzes_{patron}_{checkin_timestamp}_{game_safe}.pdf"

        os.makedirs(CHECKOUT_PDF_PATH, exist_ok=True)

        file_path = os.path.join(CHECKOUT_PDF_PATH, filename)

        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))

        # ===== MEGJEGYZÉS BEKÉRÉSE =====
        note = simpledialog.askstring(
            "Megjegyzés",
            "Szeretne megjegyzést hozzáadni a bizonylathoz?\n(Ha nem, hagyja üresen.)"
        )

        if note is None:
            # Felhasználó megszakította (Cancel)
            return

        doc = SimpleDocTemplate(
            file_path,
            pagesize=A4
        )

        elements = []
        styles = getSampleStyleSheet()

        normal = ParagraphStyle(
            "NormalUnicode",
            parent=styles["Normal"],
            fontName="DejaVuSans",
            fontSize=11
        )

        title_style = ParagraphStyle(
            "TitleUnicode",
            parent=styles["Heading1"],
            fontName="DejaVuSans",
            alignment=TA_CENTER
        )

        # ===== FEJLÉC =====
        elements.append(Paragraph("Illyés Gyula Könyvtár", title_style))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Hiányos kölcsönzés - Társasjáték", title_style))
        elements.append(Spacer(1, 12))

        patron = self.patron_entry.get()
        full_text = self.patron_name_label.cget("text")

        if ":" in full_text:
            stripped_patron_name = full_text.split(":", 1)[1].strip()
        else:
            stripped_patron_name = full_text if full_text else "Ismeretlen"
        barcode = self.barcode_entry.get()
        game = self.game_label.cget("text")

        elements.append(Paragraph(f"<b>Kölcsönző:</b> {patron} - {stripped_patron_name} ", normal))
        elements.append(Paragraph(f"<b>Vonalkód:</b> {barcode}", normal))
        elements.append(Paragraph(f"<b>Játék neve:</b> {game}", normal))
        elements.append(Spacer(1, 12))

        # ===== HIÁNYZÓ TÉTELEK =====
        elements.append(Paragraph("<b>Hiányzó / nem visszahozott tételek:</b>", normal))
        elements.append(Spacer(1, 6))

        checklist_data = [["Tétel (eredeti mennyiséggel)", "Hiányzó darabszám"]]

        def shorten(text, length=24):
            return text if len(text) <= length else text[:length - 3] + "..."

        for item in missing_items:
            name = shorten(item["component_name"])
            amount = item["missing_amount"]
            checklist_data.append([name, str(amount)])

        # Ha minden visszaérkezett
        if len(checklist_data) == 1:
            checklist_data.append(["Minden tétel visszaérkezett.", ""])

        table = Table(checklist_data, colWidths=[100 * mm, 30 * mm])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 24))

        if note.strip():
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("<b>Megjegyzés:</b>", normal))
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(note, normal))
            elements.append(Spacer(1, 12))

        elements.append(Paragraph(f"A játék a hiány pótlásáig az olvasó nevén marad.", normal))

        # ===== ALÁÍRÁS =====
        signature_table = Table(
            [
                ["", "\n\n\n____________________", "\n\n\n____________________"],
                ["", "   Átadó aláírása", "   Átvevő aláírása"]
            ],
            colWidths=[6 * mm, 80 * mm, 80 * mm]
        )

        signature_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
        ]))

        elements.append(signature_table)
        elements.append(Spacer(1, 24))

        today = datetime.now().strftime("%Y.%m.%d")
        elements.append(Paragraph(f"Keltezés: {today}", normal))

        doc.build(elements)
        full_path = os.path.abspath(file_path)
        os.startfile(full_path)

 #       messagebox.showinfo("PDF kész", f"Bizonylat elkészült:\n{os.path.abspath(file_path)}")

    def checkin_and_save(self):

        # ===== OFFLINE =====
        if not SIP_ENABLED:
            messagebox.showinfo("Offline mód", "SIP kikapcsolva – csak mentés történik.")
            self.save_return_to_db_and_print_no_SIP()
            return

        # ===== ONLINE =====
        response = self.send_checkin()

        if not response:
            messagebox.showerror("Hiba", "Nincs válasz a SIP szervertől.")
            return

        print("=== SIP CHECKIN RESPONSE ===")
        print(response)
        print("==================================")

        if not response.startswith("10"):
            messagebox.showerror("Hiba", "Érvénytelen SIP válasz.")
            return

        success_flag = response[2]
        af_message = self.extract_field(response, "AF")

        if success_flag != "1":
            messagebox.showerror(
                "Sikertelen visszavétel",
                af_message if af_message else "A visszavétel nem sikerült."
            )
            return

        messagebox.showinfo(
            "Sikeres visszavétel",
            af_message if af_message else "A visszavétel sikeresen megtörtént."
        )

        self.save_return_to_db_and_print()

    def save_and_print_no_checkin(self):


        self.save_return_to_db_and_print()

    def save_return_to_db_and_print(self):
        patron = self.patron_entry.get()
        barcode = self.barcode_entry.get()
        game = self.game_label.cget("text")

        cursor = self.conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("SELECT name FROM games WHERE id = ?", (self.current_game_id,))
        row = cursor.fetchone()
        if not row:
            messagebox.showerror("Hiba", "Nem található a játék.")
            return

        game_name = row[0]

        missing_items = self.collect_missing_items()

        all_ok = 1 if len(missing_items) == 0 else 0

        cursor.execute("""
            INSERT INTO returns (game_id, return_date, all_ok, patron_barcode)
            VALUES (?, ?, ?, ?)
        """, (self.current_game_id, now, all_ok, patron.strip()))

        return_id = cursor.lastrowid

        for item in missing_items:
            cursor.execute("""
                INSERT INTO missing_items
                (return_id, game_id, game_name, component_id, component_name, missing_amount)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                return_id,
                self.current_game_id,
                game_name,
                item["component_id"],
                item["component_name"],
                item["missing_amount"]
            ))

        self.conn.commit()

        self.generate_checkin_pdf(patron, barcode, game, missing_items)
        self.reset_ui()


    #Hiányos visszahozatal esetén ez a függvény él: nincs SIP-en keresztüli visszavétel, csak a hiányzó tételek kerülnek nyomtatásra
    def save_return_to_db_and_print_no_SIP(self):
        patron = self.patron_entry.get()
        barcode = self.barcode_entry.get()
        game = self.game_label.cget("text")

        cursor = self.conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("SELECT name FROM games WHERE id = ?", (self.current_game_id,))
        row = cursor.fetchone()
        if not row:
            messagebox.showerror("Hiba", "Nem található a játék.")
            return

        game_name = row[0]

        missing_items = self.collect_missing_items()

        all_ok = 1 if len(missing_items) == 0 else 0

        cursor.execute("""
            INSERT INTO returns (game_id, return_date, all_ok, patron_barcode)
            VALUES (?, ?, ?, ?)
        """, (self.current_game_id, now, all_ok, patron.strip()))

        return_id = cursor.lastrowid

        for item in missing_items:
            cursor.execute("""
                INSERT INTO missing_items
                (return_id, game_id, game_name, component_id, component_name, missing_amount)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                return_id,
                self.current_game_id,
                game_name,
                item["component_id"],
                item["component_name"],
                item["missing_amount"]
            ))

        self.conn.commit()

        self.generate_checkin_pdf_no_SIP(patron, barcode, game, missing_items)
        self.reset_ui()

    def collect_missing_items(self):
        missing_items = []

        for widget in self.scrollable_frame.winfo_children():
            for child in widget.winfo_children():
                if isinstance(child, tk.Checkbutton):
                    if not child.var.get():
                        try:
                            missing_amount = int(child.amount_var.get())
                            if missing_amount < 1:
                                missing_amount = 1
                        except:
                            missing_amount = 1

                        missing_items.append({
                            "component_id": child.component_id,
                            "component_name": child.cget("text"),
                            "missing_amount": missing_amount
                        })

        return missing_items

    # ===== Hiánylista (összes játék) =====
    def show_missing_items(self):
        top = tk.Toplevel(self.root)
        top.title("Összes hiányzó komponens")
        top.geometry("1300x400")  # kicsit szélesebb, hogy elférjen minden

        columns = (
            "game_id",
            "game_name",
            "component_name",
#            "missing_amount",
#            "replaced_amount",
#            "lost_amount",
            "damaged_amount",
            "still_missing",
            "return_date",
            "patron_barcode"
        )

        tree = ttk.Treeview(top, columns=columns, show="headings", selectmode="extended")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        tree.heading("game_id", text="Játék ID")
        tree.heading("game_name", text="Játék neve")
        tree.heading("component_name", text="Hiányzó komponens")
        tree.heading("still_missing", text="Kallódik")
        tree.heading("damaged_amount", text="Sérült")
        tree.heading("return_date", text="Utolsó visszavétel")
        tree.heading("patron_barcode", text="Olvasó vonalkód")

        tree.column("game_id", width=50)
        tree.column("game_name", width=150)
        tree.column("component_name", width=200)
        tree.column("damaged_amount", width=70)
        tree.column("return_date", width=100)
        tree.column("patron_barcode", width=70)

        cursor = self.conn.cursor()
        cursor.execute("""
SELECT
    c.id AS component_id,
    c.game_id,
    g.name AS game_name,
    c.name AS component_name,

    IFNULL(SUM(mi.missing_amount),0) AS total_missing,
    IFNULL(SUM(mi.replaced_amount),0) AS total_replaced,
    IFNULL(c.damaged_amount,0) AS damaged_amount,

    (
        IFNULL(SUM(mi.missing_amount),0)
        - IFNULL(SUM(mi.replaced_amount),0)
    ) AS still_missing,

    (
        SELECT r.return_date
        FROM missing_items mi2
        JOIN returns r ON mi2.return_id = r.id
        WHERE mi2.component_id = c.id
        ORDER BY r.return_date DESC
        LIMIT 1
    ) AS last_return_date,

    (
        SELECT r.patron_barcode
        FROM missing_items mi2
        JOIN returns r ON mi2.return_id = r.id
        WHERE mi2.component_id = c.id
        ORDER BY r.return_date DESC
        LIMIT 1
    ) AS last_patron

FROM components c
JOIN games g ON c.game_id = g.id
LEFT JOIN missing_items mi ON c.id = mi.component_id

GROUP BY c.id

HAVING
    still_missing > 0
    OR damaged_amount > 0

ORDER BY g.name, c.name
        """)
        rows = cursor.fetchall()

        for (
                comp_id,
                game_id,
                game_name,
                comp_name,
                total_missing,
                total_replaced,
                damaged_amount,
                still_missing,
                return_date,
                patron_barcode
        ) in rows:

            # ===== STÁTUSZ SZÖVEG =====
            status_parts = []

#            lost_display = lost_amount - found_amount

            # if lost_display > 0:
            #     status_parts.append(f"❌ elveszett: {lost_display}")

            if still_missing > 0:
                status_parts.append(f"❌ kallódik: {still_missing}")

            if damaged_amount > 0:
                status_parts.append(f"⚠️ sérült: {damaged_amount}")

            status_text = " | ".join(status_parts)

            display_comp_name = comp_name
            if status_text:
                display_comp_name += f" ({status_text})"

            tree.insert(
                "",
                tk.END,
                iid=comp_id,
                values=(
                    game_id,
                    game_name,
                    display_comp_name,
                    damaged_amount,
                    still_missing,
                    return_date,
                    patron_barcode
                )
            )

        def refresh_missing_row(component_id):

            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT
                    c.game_id,
                    g.name,
                    c.name,
                    IFNULL(SUM(mi.missing_amount),0),
                    IFNULL(SUM(mi.replaced_amount),0),
                    IFNULL(c.damaged_amount,0)
                FROM components c
                JOIN games g ON c.game_id = g.id
                LEFT JOIN missing_items mi ON c.id = mi.component_id
                WHERE c.id = ?
                GROUP BY c.id
            """, (component_id,))

            row = cursor.fetchone()
            if not row:
                return

            (
                game_id,
                game_name,
                comp_name,
                total_missing,
                total_replaced,
#                total_lost,
                damaged_amount
            ) = row

            still_missing = total_missing - total_replaced

            status_parts = []

            # if total_lost > 0:
            #     status_parts.append(f"❌ elveszett: {total_lost}")

            if still_missing > 0:
                status_parts.append(f"❌ kallódik: {still_missing}")

            if damaged_amount > 0:
                status_parts.append(f"⚠️ sérült: {damaged_amount}")

            display_name = comp_name
            if status_parts:
                display_name += " (" + " | ".join(status_parts) + ")"

            tree.item(component_id, values=(
                game_id,
                game_name,
                display_name,
#                total_lost,
                damaged_amount,
                still_missing,
                tree.set(component_id, "return_date"),
                tree.set(component_id, "patron_barcode")
            ))

        from datetime import date

        def remove_selected():

            selected = tree.selection()
            if not selected:
                return

            component_id = selected[0]
            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT id, missing_amount, replaced_amount
                FROM missing_items
                WHERE component_id = ?
                ORDER BY id DESC
                LIMIT 1
            """, (component_id,))

            row = cursor.fetchone()
            if not row:
                return

            missing_id, missing_amount, replaced_amount = row

            max_add = missing_amount - replaced_amount

            if max_add <= 0:
                messagebox.showinfo("Nincs pótolható", "Nincs pótolható hiány.")
                return

            add_amount = simpledialog.askinteger(
                "Pótlás",
                f"Hány darabot pótoltak?\n(Még hiányzik: {max_add})",
                minvalue=1,
                maxvalue=max_add
            )

            if not add_amount:
                return

            new_replaced = replaced_amount + add_amount
            today = date.today().isoformat()

            # ===== LEZÁRÁS =====
            if new_replaced == missing_amount:

                cursor.execute("""
                    UPDATE missing_items
                    SET
                        replaced_amount = ?,
                        replaced_on_date = ?,
                        closed_on_date = ?
                    WHERE id = ?
                """, (new_replaced, today, today, missing_id))

            # ===== RÉSZLEGES PÓTLÁS =====
            else:

                cursor.execute("""
                    UPDATE missing_items
                    SET
                        replaced_amount = ?,
                        replaced_on_date = ?
                    WHERE id = ?
                """, (new_replaced, today, missing_id))

            self.conn.commit()

            refresh_missing_row(component_id)

        def repair_damaged_in_show_missing_items():

            selected = tree.selection()
            if not selected:
                return

            component_id = selected[0]

            component_name = tree.set(component_id, "component_name")
            current_damaged = int(tree.set(component_id, "damaged_amount"))

            if current_damaged <= 0:
                messagebox.showinfo(
                    "Nincs javítható",
                    "Nincs sérültként nyilvántartott darab."
                )
                return

            amount = simpledialog.askinteger(
                "Javított darab",
                f"Hány darabot cseréltek ki a(z) {component_name} komponensből?\n"
                f"(Maximum: {current_damaged})",
                minvalue=1,
                maxvalue=current_damaged
            )

            if not amount:
                return

            cursor = self.conn.cursor()

            cursor.execute("""
                UPDATE components
                SET damaged_amount = damaged_amount - ?
                WHERE id = ?
            """, (amount, component_id))

            self.conn.commit()

            refresh_missing_row(component_id)

        def mark_found():

            selected = tree.selection()
            if not selected:
                return

            component_id = selected[0]
            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT id, lost_amount
                FROM missing_items
                WHERE component_id = ?
                AND lost_amount > 0
                ORDER BY id DESC
                LIMIT 1
            """, (component_id,))

            row = cursor.fetchone()

            if not row:
                messagebox.showinfo("Nincs elveszett", "Nincs elveszettként jelölt darab.")
                return

            missing_id, lost_amount = row

            found_amount = simpledialog.askinteger(
                "Megtalált darab",
                f"Hány darabot találtak meg?\n(Elveszett: {lost_amount})",
                minvalue=1,
                maxvalue=lost_amount
            )

            if not found_amount:
                return

            cursor.execute("""
                UPDATE missing_items
                SET lost_amount = lost_amount - ?
                WHERE id = ?
            """, (found_amount, missing_id))

            self.conn.commit()

            refresh_missing_row(component_id)

        def mark_lost():

            selected = tree.selection()
            if not selected:
                return

            component_id = selected[0]
            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT id, missing_amount, replaced_amount, lost_amount
                FROM missing_items
                WHERE component_id = ?
                ORDER BY id DESC
                LIMIT 1
            """, (component_id,))

            row = cursor.fetchone()

            if not row:
                messagebox.showwarning("Hiba", "Nincs hiány rekord.")
                return

            missing_id, missing_amount, replaced_amount, lost_amount = row

            still_missing = missing_amount - replaced_amount - lost_amount

            if still_missing <= 0:
                messagebox.showinfo("Nincs hiány", "Nincs jelölhető kallódó tétel.")
                return

            add_lost = simpledialog.askinteger(
                "Elveszett darabok",
                f"Hány darabot jelölsz elveszettnek?\n(Még hiányzik: {still_missing})",
                minvalue=1,
                maxvalue=still_missing
            )

            if not add_lost:
                return

            cursor.execute("""
                UPDATE missing_items
                SET lost_amount = lost_amount + ?
                WHERE id = ?
            """, (add_lost, missing_id))

            self.conn.commit()

            refresh_missing_row(component_id)

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=5)

        btn_remove = tk.Button(
            btn_frame,
            text="Pótolva / Visszahozva",
            command=remove_selected,
            bg="#27ae60",
            fg="white"
        )
        btn_remove.pack(side="left", padx=5)

        btn_remove = tk.Button(
            btn_frame,
            text="Sérült cserélve",
            command=repair_damaged_in_show_missing_items,
            bg="#446AA5",
            fg="white"
        )
        btn_remove.pack(side="left", padx=5)

        # btn_lost = tk.Button(
        #     btn_frame,
        #     text="Végleg elveszett",
        #     command=mark_lost,
        #     bg="#e67e22",
        #     fg="white"
        # )
        # btn_lost.pack(side="left", padx=5)

        # btn_found = tk.Button(
        #     btn_frame,
        #     text="Megtalálva",
        #     command=mark_found,
        #     bg="#3498db",
        #     fg="white"
        # )
        # btn_found.pack(side="left", padx=5)

    # ===== Returns riport =====
    def show_returns(self):
        top = tk.Toplevel(self.root)
        top.title("Visszavételek megtekintése")
        top.geometry("1250x450")

        columns = ("return_id", "game_id", "game_name", "return_date", "all_ok", "patron_barcode")
        tree = ttk.Treeview(top, columns=columns, show="headings", selectmode="browse")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        tree.heading("return_id", text="Tranzakció ID")
        tree.heading("game_id", text="Játék ID")
        tree.heading("game_name", text="Játék neve")
        tree.heading("return_date", text="Utolsó visszavétel dátuma")
        tree.heading("all_ok", text="Hiány?")
        tree.heading("patron_barcode", text="Olvasó vonalkód")

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT r.id, r.game_id, g.name, r.return_date, r.all_ok, r.patron_barcode
            FROM returns r
            JOIN games g ON r.game_id = g.id
            ORDER BY r.return_date DESC
        """)

        rows = cursor.fetchall()

        for row in rows:
            return_id, game_id, game_name, return_date, all_ok, patron_barcode = row

            # 0 → "Hiányos", 1 → "Hiánytalan"
            all_ok_text = "Hiánytalan" if all_ok == 1 else "Hiányos"

            tree.insert("", tk.END, values=(return_id, game_id, game_name, return_date, all_ok_text, patron_barcode))

        # ===== DUPLA KATTINTÁS ESEMÉNY =====
        def open_details(event):
            selected = tree.selection()
            if not selected:
                return

            item = tree.item(selected[0])
            values = item["values"]

            return_id = values[0]
            game_name = values[2]
            return_date = values[3]
            patron_barcode = patron_barcode = str(values[5]).zfill(7)

            detail_win = tk.Toplevel(top)
            detail_win.title("Visszavétel részletei")
            detail_win.geometry("550x300")

            tk.Label(detail_win, text=f"Játék: {game_name}", font=("Arial", 12, "bold")).pack(pady=5)
            tk.Label(detail_win, text=f"Utolsó visszavétel: {return_date}").pack()
            tk.Label(detail_win, text=f"Olvasó: {patron_barcode}").pack()

            tk.Label(detail_win, text="").pack()

            tk.Label(detail_win, text="Hiányzó komponensek:", font=("Arial", 11, "bold")).pack()

            cursor.execute("""
SELECT
    mi.component_name,
    mi.missing_amount,
    mi.replaced_amount,
    mi.replaced_on_date,
    IFNULL(c.damaged_amount, 0)
FROM missing_items mi
JOIN components c ON mi.component_id = c.id
WHERE mi.return_id = ?
            """, (return_id,))

            missing = cursor.fetchall()

            for (
                    comp_name,
                    missing_amount,
                    replaced_amount,
                    replaced_on,
                    damaged_amount
            ) in missing:

                still_missing = missing_amount - replaced_amount

                text = (
                    f"- {comp_name}: "
                    f"hiányzott {missing_amount} db, "
                    f"pótolva {replaced_amount} db"
                )

                if damaged_amount > 0:
                    text += f", sérült {damaged_amount} db"

                if missing_amount == replaced_amount:

                    if replaced_on:
                        text += f" → lezárva ({replaced_on})"
                    else:
                        text += " → lezárva"

                else:
                    text += f", még hiányzik {still_missing} db"

                tk.Label(detail_win, text=text).pack(anchor="w", padx=20)

        tree.bind("<Double-1>", open_details)

    def _update_component_amount(self, tree, column_key, db_column, title):
        selected = tree.selection()
        if not selected:
            return

        comp_id = selected[0]
        comp_name = tree.set(comp_id, "name")
        current_value = int(tree.set(comp_id, column_key))

        add = simpledialog.askinteger(
            title,
            f"Hány darabot jelölsz a(z) {comp_name} tételből?",
            minvalue=1
        )

        if add is None:
            return

        new_value = current_value + add

        cursor = self.conn.cursor()
        cursor.execute(
            f"UPDATE components SET {db_column} = ? WHERE id = ?",
            (new_value, comp_id)
        )
        self.conn.commit()

        tree.set(comp_id, column_key, new_value)

    def open_new_game_window(self):
        win = tk.Toplevel(self.root)
        win.title("Új játék rögzítése")
        win.geometry("500x500")

        tk.Label(win, text="Játék neve:").pack(anchor="w", padx=10, pady=(10, 0))
        name_entry = tk.Entry(win, width=50)
        name_entry.pack(padx=10, pady=5)

        tk.Label(win, text="Vonalkód:").pack(anchor="w", padx=10, pady=(10, 0))
        barcode_entry = tk.Entry(win, width=50)
        barcode_entry.pack(padx=10, pady=5)

        tk.Label(win, text="Kiegészítők (egy sor egy tétel):").pack(anchor="w", padx=10, pady=(10, 0))

        components_text = tk.Text(win, height=15)
        components_text.pack(fill="both", expand=True, padx=10, pady=5)


        def import_game_from_xml():
            file_path = filedialog.askopenfilename(
                title="XML fájl kiválasztása",
                filetypes=[("XML fájl", "*.xml")]
            )

            if not file_path:
                return

            try:
                tree = ET.parse(file_path)
                root = tree.getroot()

                ns = {"marc": "http://www.loc.gov/MARC21/slim"}

                # ---- 245$a ----
                title = None
                for df in root.findall(".//marc:datafield[@tag='245']", ns):
                    sub = df.find("marc:subfield[@code='a']", ns)
                    if sub is not None and sub.text:
                        title = sub.text.strip()
                        break

                # ---- 949$z ----
                barcode = None
                for df in root.findall(".//marc:datafield[@tag='949']", ns):
                    sub = df.find("marc:subfield[@code='z']", ns)
                    if sub is not None and sub.text:
                        barcode = sub.text.strip()
                        break

                # ---- 500$a (csak az első 500 mező) ----
                components = []

                first_500 = root.find(".//marc:datafield[@tag='500']", ns)

                if first_500 is not None:
                    sub = first_500.find("marc:subfield[@code='a']", ns)
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

                # ---- Mezők kitöltése ----
                if title:
                    name_entry.delete(0, tk.END)
                    name_entry.insert(0, title)

                if barcode:
                    barcode_entry.delete(0, tk.END)
                    barcode_entry.insert(0, barcode)

                if components:
                    components_text.delete("1.0", tk.END)
                    components_text.insert("1.0", "\n".join(components))

                messagebox.showinfo("Siker", "XML adatok betöltve.\nEllenőrizd és nyomj Mentést!")

            except Exception as e:
                messagebox.showerror("Hiba", f"Import hiba:\n{e}")


        tk.Button(
            win,
            text="Importálás MARC XML-ből",
            command=import_game_from_xml
        ).pack(pady=5)

        def save_new_game():
            name = name_entry.get().strip()
            barcode = barcode_entry.get().strip()
            components_raw = components_text.get("1.0", tk.END).strip()

            if not name or not barcode:
                messagebox.showerror("Hiba", "A név és a vonalkód kötelező!")
                return

            if not components_raw:
                messagebox.showerror("Hiba", "Adj meg legalább egy komponenst!")
                return

            cursor = self.conn.cursor()

            try:
                cursor.execute(
                    "INSERT INTO games (name, barcode) VALUES (?, ?)",
                    (name, barcode)
                )
            except sqlite3.IntegrityError:
                messagebox.showerror("Hiba", "Ez a vonalkód már létezik!")
                return

            game_id = cursor.lastrowid

            component_lines = [
                line.strip()
                for line in components_raw.split("\n")
                if line.strip()
            ]

            for comp_name in component_lines:
                cursor.execute("""
                    INSERT INTO components (
                        game_id,
                        name,
                        damaged_amount
                    )
                    VALUES (?, ?, 0)
                """, (game_id, comp_name))

            self.conn.commit()

            # dropdown frissítése és az új játék kiválasztása
            self.refresh_game_dropdown(select_game_id=game_id)

            messagebox.showinfo("Siker", "Az új játék rögzítve lett!")

            win.destroy()

        tk.Button(
            win,
            text="Mentés",
            command=save_new_game,
            bg="#27ae60",
            fg="white"
        ).pack(pady=10)

    def open_components_editor(self):

        if not self.current_game_id:
            messagebox.showwarning(
                "Nincs játék kiválasztva",
                "Előbb válassz ki egy játékot!"
            )
            return

        win = tk.Toplevel(self.root)
        win.title("Kiegészítők szerkesztése")
        win.geometry("800x400")

        columns = ("name", "missing", "damaged")

        tree = ttk.Treeview(win, columns=columns, show="headings")
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        tree.heading("name", text="Komponens")
        tree.heading("missing", text="Kallódik")
        tree.heading("damaged", text="Sérült")

        tree.column("name", width=350)
        tree.column("damaged", width=80, anchor="center")

        cursor = self.conn.cursor()

        cursor.execute("""
SELECT
    c.id,
    c.name,

    IFNULL(SUM(mi.missing_amount),0)
    -
    IFNULL(SUM(mi.replaced_amount),0)
    AS still_missing,

    IFNULL(c.damaged_amount,0)

FROM components c
LEFT JOIN missing_items mi
    ON mi.component_id = c.id

WHERE c.game_id = ?

GROUP BY c.id
ORDER BY c.name
        """, (self.current_game_id,))

        rows = cursor.fetchall()

        for comp_id, name, missing, damaged in rows:
            tree.insert(
                "",
                tk.END,
                iid=comp_id,
                values=(name, missing, damaged)
            )

        # ===== GOMBOK =====

        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=5)

        def refresh_component_row(component_id):

            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT
                    c.name,

                    IFNULL(SUM(mi.missing_amount),0)
                    -
                    IFNULL(SUM(mi.replaced_amount),0),

                    IFNULL(c.damaged_amount,0)

                FROM components c
                LEFT JOIN missing_items mi
                    ON mi.component_id = c.id

                WHERE c.id = ?

                GROUP BY c.id
            """, (component_id,))

            row = cursor.fetchone()

            if not row:
                return

            name, missing, damaged = row

            tree.item(
                component_id,
                values=(name, missing, damaged)
            )

        def mark_damaged():

            selected = tree.selection()
            if not selected:
                return

            comp_id = selected[0]
            component_name = tree.set(comp_id, "name")

            amount = simpledialog.askinteger(
                "Sérült darab",
                f"Hány darab sérült a(z) {component_name} komponensből?",
                minvalue=1
            )

            if not amount:
                return

            cursor = self.conn.cursor()

            cursor.execute("""
                UPDATE components
                SET damaged_amount = IFNULL(damaged_amount,0) + ?
                WHERE id = ?
            """, (amount, comp_id))

            self.conn.commit()

            current = int(tree.set(comp_id, "damaged"))
            tree.set(comp_id, "damaged", current + amount)

            refresh_component_row(comp_id)

        def repair_damaged():

            selected = tree.selection()
            if not selected:
                return

            comp_id = selected[0]
            component_name = tree.set(comp_id, "name")

            current_damaged = int(tree.set(comp_id, "damaged"))

            if current_damaged <= 0:
                messagebox.showinfo(
                    "Nincs javítható",
                    "Nincs sérültként nyilvántartott darab."
                )
                return

            amount = simpledialog.askinteger(
                "Javított darab",
                f"Hány darabot cseréltek ki a(z) {component_name} komponensből?\n"
                f"(Maximum: {current_damaged})",
                minvalue=1,
                maxvalue=current_damaged
            )

            if not amount:
                return

            cursor = self.conn.cursor()

            cursor.execute("""
                UPDATE components
                SET damaged_amount = damaged_amount - ?
                WHERE id = ?
            """, (amount, comp_id))

            self.conn.commit()

            # TreeView frissítés
            tree.set(comp_id, "damaged", current_damaged - amount)

            refresh_component_row(comp_id)


        # ===== KALLÓDÓ =====

        def mark_missing():

            selected = tree.selection()
            if not selected:
                return

            comp_id = selected[0]
            component_name = tree.set(comp_id, "name")

            amount = simpledialog.askinteger(
                "Kallódó tétel",
                f"Hány darab kallódik a(z) {component_name} komponensből?",
                minvalue=1
            )

            if not amount:
                return

            cursor = self.conn.cursor()

            cursor.execute("""
                INSERT INTO missing_items
                (component_id, missing_amount, replaced_amount)
                VALUES (?, ?, 0)
            """, (comp_id, amount))

            self.conn.commit()

            refresh_component_row(comp_id)

            messagebox.showinfo("Rögzítve", "A hiány rögzítve.")

        # ===== PÓTLÁS =====

        def replace_missing():

            selected = tree.selection()
            if not selected:
                return

            comp_id = selected[0]

            cursor = self.conn.cursor()

            cursor.execute("""
                SELECT id, missing_amount, replaced_amount
                FROM missing_items
                WHERE component_id = ?
                ORDER BY id DESC
                LIMIT 1
            """, (comp_id,))

            row = cursor.fetchone()

            if not row:
                messagebox.showinfo(
                    "Nincs hiány",
                    "Ehhez a komponenshez nincs hiány rögzítve."
                )
                return

            missing_id, missing_amount, replaced_amount = row

            max_replace = missing_amount - replaced_amount

            if max_replace <= 0:
                messagebox.showinfo("Nincs pótolható", "Nincs pótolható hiány.")
                return

            amount = simpledialog.askinteger(
                "Pótlás",
                f"Hány darabot pótoltak?\n(Még hiányzik: {max_replace})",
                minvalue=1,
                maxvalue=max_replace
            )

            if not amount:
                return

            cursor.execute("""
                UPDATE missing_items
                SET replaced_amount = replaced_amount + ?
                WHERE id = ?
            """, (amount, missing_id))

            self.conn.commit()

            refresh_component_row(comp_id)

            messagebox.showinfo("Rögzítve", "A pótlás rögzítve.")

        def on_tree_double_click(event):

            item = tree.identify_row(event.y)
            column = tree.identify_column(event.x)

            if not item:
                return

            # csak a név oszlop szerkeszthető
            if column != "#1":
                return

            x, y, width, height = tree.bbox(item, column)

            value = tree.set(item, "name")

            entry = tk.Entry(tree)
            entry.place(x=x, y=y, width=width, height=height)
            entry.insert(0, value)
            entry.focus()

            def save_edit(event=None):

                new_value = entry.get().strip()
                entry.destroy()

                if not new_value:
                    return

                cursor = self.conn.cursor()

                cursor.execute("""
                    UPDATE components
                    SET name = ?
                    WHERE id = ?
                """, (new_value, item))

                self.conn.commit()

                refresh_component_row(item)

            def cancel_edit(event=None):
                entry.destroy()

            entry.bind("<Return>", save_edit)
            entry.bind("<Escape>", cancel_edit)

        tree.bind("<Double-1>", on_tree_double_click)

        # ===== GOMBOK =====

        tk.Button(
            btn_frame,
            text="Sérült jelölése",
            command=mark_damaged,
            bg="#f1c40f"
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Sérült cseréje",
            command=repair_damaged,
            bg="#446AA5"
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Kallódik",
            command=mark_missing,
            bg="#e67e22"
        ).pack(side="left", padx=5)

        tk.Button(
            btn_frame,
            text="Pótlás",
            command=replace_missing,
            bg="#2ecc71"
        ).pack(side="left", padx=5)

    def close(self):
        self.conn.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = GameCheckApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()
