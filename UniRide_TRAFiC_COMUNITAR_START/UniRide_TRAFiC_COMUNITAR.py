import tkinter as tk
from tkinter import messagebox
import math
import os
import queue
import threading
import time
import asyncio
import sqlite3
import subprocess
import base64
from pathlib import Path
from datetime import datetime, timedelta

import requests

try:
    import tkintermapview
except ImportError:
    tkintermapview = None

# ── Paleta UniRide ──────────────────────────────────────────

BG = "#F2F9FF"           # fundal albastru foarte deschis
WHITE = "#FFFFFF"
TEXT = "#203A50"         # text inchis pentru contrast
MUTED = "#587287"
PURPLE = "#D9EFFF"       # albastru pastel (pastram numele pentru compatibilitate)
PURPLE_DARK = "#216A9A"  # albastru pentru titluri si butoane
GREEN = "#DDF5E5"        # verde pal pentru carduri
GREEN_DARK = "#218345"   # verde inchis pentru text
PEACH = "#FFFF99"        # galben cerut
BLUE = "#E5F5FF"         # albastru deschis
BORDER = "#CDE4F1"
ACCENT_GREEN = "#33AC58" # verde cerut

FONT = "Segoe UI"

# Servicii publice pentru demonstrații locale; nu sunt pentru utilizare intensă.
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
ROUTE_URL = "https://router.project-osrm.org/route/v1/driving"
HEADERS = {"User-Agent": "UniRideStudentPrototype/0.1 (educational local testing)"}
DATABASE = Path(__file__).with_name("uniride_curse_locale.db")
TRAFFIC_SERVER = os.environ.get("UNIRIDE_TRAFFIC_URL", "").rstrip("/")
TRAFFIC_KEY = os.environ.get("UNIRIDE_TRAFFIC_KEY", "local-test-only")

def trafic_colaborativ(puncte):
    """Solicită agregatele de trafic; fără server sau acoperire -> Date insuficiente."""
    if not TRAFFIC_SERVER or len(puncte) < 2:
        return "Date insuficiente", 0.0
    # Sample maximum 300 coordinates to limit payload.
    pas = max(1, len(puncte) // 300)
    esantion = puncte[::pas]
    if esantion[-1] != puncte[-1]: esantion.append(puncte[-1])
    try:
        r = requests.post(TRAFFIC_SERVER + "/v1/route-traffic",
            json={"points": esantion, "baseline_kmh": 40},
            headers={"X-API-Key": TRAFFIC_KEY}, timeout=5)
        r.raise_for_status()
        data = r.json()
        return data.get("status", "Date insuficiente"), float(data.get("coverage",0))
    except (requests.RequestException, ValueError, TypeError):
        return "Date insuficiente", 0.0


AVERTISMENT_RIDE = (
    "ATENȚIE — SIGURANȚA TA CONTEAZĂ!\n\n"
    "UniRide facilitează doar găsirea unor persoane cu destinații și ore similare. "
    "Nu verificăm în acest prototip identitatea, statutul de student, permisul, "
    "vehiculul sau comportamentul celorlalți utilizatori.\n\n"
    "Orice întâlnire sau călătorie cu altă persoană implică riscuri și este "
    "o decizie personală. Nu împărtăși adresa exactă de acasă sau locația "
    "live. Întâlnește-te într-un loc public și anunță o persoană de încredere.\n\n"
    "Această informare nu elimină drepturile utilizatorilor și nici "
    "eventualele obligații legale ale operatorilor aplicației.\n\n"
    "Dorești să continui?"
)

def deschide_baza():
    db = sqlite3.connect(DATABASE)
    db.execute("""CREATE TABLE IF NOT EXISTS curse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pseudonim TEXT NOT NULL, facultate TEXT NOT NULL,
        zona_plecare TEXT NOT NULL, zona_sosire TEXT NOT NULL,
        zi TEXT NOT NULL, ora TEXT NOT NULL, rol TEXT NOT NULL,
        locuri INTEGER NOT NULL, mesaj TEXT NOT NULL DEFAULT '',
        creat_la TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS istoric_trasee (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        origine TEXT NOT NULL, destinatie TEXT NOT NULL,
        plecare TEXT NOT NULL, distanta_km REAL NOT NULL,
        durata_min INTEGER NOT NULL, sosire_normala TEXT NOT NULL,
        sosire_prudenta TEXT NOT NULL, creat_la TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS rezervari (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cursa_id INTEGER NOT NULL REFERENCES curse(id),
        pasager TEXT NOT NULL,
        locuri INTEGER NOT NULL DEFAULT 1 CHECK(locuri > 0),
        status TEXT NOT NULL DEFAULT 'activa',
        creat_la TEXT NOT NULL,
        UNIQUE(cursa_id, pasager)
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS predictii (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        origine TEXT NOT NULL, destinatie TEXT NOT NULL,
        plecare TEXT NOT NULL, tip TEXT NOT NULL,
        rezultat TEXT NOT NULL, metoda TEXT NOT NULL,
        creat_la TEXT NOT NULL
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS istoric_curse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cursa_id INTEGER, durata_reala_min INTEGER,
        traseu_real TEXT, creat_la TEXT NOT NULL
    )""")
    db.commit()
    return db


def coordonate(adresa):
    raspuns = requests.get(
        GEOCODE_URL,
        params={"q": adresa, "format": "jsonv2", "limit": 1},
        headers=HEADERS, timeout=20,
    )
    raspuns.raise_for_status()
    date = raspuns.json()
    if not date:
        raise ValueError(f"Nu am găsit adresa: {adresa}")
    return float(date[0]["lon"]), float(date[0]["lat"])


def calculeaza_rute(start, destinatie):
    puncte = f"{start[0]},{start[1]};{destinatie[0]},{destinatie[1]}"
    raspuns = requests.get(
        f"{ROUTE_URL}/{puncte}",
        params={"overview": "full", "geometries": "geojson", "alternatives": "true", "steps": "true"},
        headers=HEADERS, timeout=30,
    )
    raspuns.raise_for_status()
    date = raspuns.json()
    if date.get("code") != "Ok" or not date.get("routes"):
        raise ValueError("Nu există un traseu auto disponibil între aceste puncte.")
    return date["routes"]


def label(parent, text, size=11, color=TEXT, bold=False, bg=None):
    return tk.Label(
        parent,
        text=text,
        font=(FONT, size, "bold" if bold else "normal"),
        fg=color,
        bg=bg or parent.cget("bg"),
        anchor="w",
        justify="left",
    )


def button(parent, text, command, bg=PURPLE, fg=PURPLE_DARK):
    return tk.Button(
        parent,
        text=text,
        command=command,
        font=(FONT, 11, "bold"),
        bg=bg,
        fg=fg,
        activebackground=bg,
        activeforeground=fg,
        relief="flat",
        borderwidth=0,
        padx=18,
        pady=11,
        cursor="hand2",
        takefocus=True,
        highlightthickness=2,
        highlightbackground=bg,
        highlightcolor=PURPLE_DARK,
    )


def card(parent, bg=WHITE):
    return tk.Frame(
        parent,
        bg=bg,
        padx=20,
        pady=18,
        highlightbackground=BORDER,
        highlightthickness=1,
    )


class UniRide(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("UniRide • Drumul spre facultate, mai simplu")
        self.geometry("1320x900")
        self.minsize(1000, 730)
        self.configure(bg=BG)

        self.option_add("*Font", (FONT, 11))

        self.origine = tk.StringVar(value="Palatul Culturii, Iași, România")
        self.destinatie = tk.StringVar(value="Universitatea Alexandru Ioan Cuza, Iași, România")
        self.ora_plecare = tk.StringVar(value=datetime.now().strftime("%H:%M"))
        self.route_status = tk.StringVar(value="Introdu două adrese și calculează traseul.")
        self.route_text = "Aici vor apărea variantele de traseu, distanțele și duratele estimate."
        self.device_coords = None  # (lon, lat); doar după acord explicit
        self.route_busy = False
        self.traffic_scenario = tk.StringVar(value="Moderat")
        self.route_options = []
        self.selected_route_index = 0
        self.route_map = None
        self.nav_steps = []
        self.nav_index = 0
        self.nav_speech = tk.BooleanVar(value=True)
        self.nav_window = None
        self.nav_big_map = None
        self.nav_big_path = None
        self.nav_big_marker = None
        self.nav_follow = False
        self.nav_gps_busy = False
        self.nav_last_announced = -1
        self.nav_approach_announced = set()
        self.nav_last_position = None
        self.nav_last_gps_time = None
        self.nav_gps_after = None
        self.nav_gps_accuracy_limit = 35
        self.speech_lock = threading.Lock()
        self.route_queue = queue.Queue()
        self.after(150, self.verifica_rute)

        self.init_curse_locale()
        self.navigation = {}
        self.build_sidebar()

        self.main = tk.Frame(self, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)

        self.build_header()

        self.content = tk.Frame(self.main, bg=BG, padx=20, pady=10)
        self.content.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self.inchide_aplicatia)
        self.show_page("Acasă")

    def demo(self, title):
        messagebox.showinfo(
            title,
            "Aceasta este o previzualizare de design.\n\n"
            "Funcția va fi conectată într-o etapă ulterioară.",
            parent=self,
        )

    def build_sidebar(self):
        sidebar = tk.Frame(self, bg=WHITE, width=225)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=WHITE, padx=24, pady=28)
        brand.pack(fill="x")

        label(brand, "UniRide", 27, PURPLE_DARK, True).pack(anchor="w")
        label(brand, "Împreună spre campus", 10, MUTED).pack(anchor="w")

        pages = [
            "Acasă",
            "Orarul meu",
            "Rute & trafic",
            "Carpooling",
            "FlowFriends",
            "FlowPoints",
            "FlowShop",
            "Siguranță",
            "Profil",
        ]

        for index, name in enumerate(pages, start=1):
            item = button(
                sidebar,
                f"{index:02d}   {name}",
                lambda page=name: self.show_page(page),
                bg=WHITE,
                fg=MUTED,
            )
            item.configure(anchor="w", padx=20, pady=9)
            item.pack(fill="x", padx=14, pady=3)
            self.navigation[name] = item

        footer = tk.Frame(sidebar, bg=GREEN, padx=14, pady=14)
        footer.pack(side="bottom", fill="x", padx=18, pady=22)

        label(
            footer, "Un drum împărțit.", 11, GREEN_DARK, True
        ).pack(anchor="w")
        label(
            footer, "O comunitate mai aproape.", 9, GREEN_DARK
        ).pack(anchor="w", pady=(5, 0))

    def build_header(self):
        header = tk.Frame(self.main, bg=WHITE, padx=28, pady=18)
        header.pack(fill="x")

        label(
            header, "Mai puțin stres. Mai mult timp pentru tine.",
            11, MUTED
        ).pack(side="left")

        badge = label(
            header, "  MOD DEMO  ", 9, PURPLE_DARK, True, PURPLE
        )
        badge.configure(padx=9, pady=6)
        badge.pack(side="right")

    def show_page(self, name):
        for item, widget in self.navigation.items():
            selected = item == name
            color = PURPLE if selected else WHITE
            foreground = PURPLE_DARK if selected else MUTED
            widget.configure(
                bg=color,
                fg=foreground,
                activebackground=color,
                activeforeground=foreground,
                highlightbackground=color,
            )

        # Nu mai păstrăm referința către o hartă distrusă la schimbarea paginii.
        self.route_map = None
        for child in self.content.winfo_children():
            child.destroy()

        if name == "Acasă":
            self.home()
        elif name == "Rute & trafic":
            self.pagina_rute()
        elif name == "Carpooling":
            self.pagina_carpooling()
        else:
            self.detail_page(name)

    def heading(self, title, subtitle):
        label(self.content, title, 25, TEXT, True).pack(anchor="w")
        label(self.content, subtitle, 11, MUTED).pack(
            anchor="w", pady=(6, 20)
        )

    def home(self):
        self.heading(
            "Salut! Încotro mergem astăzi?",
            "Planifică-ți drumul și ajungi în campus cu mai multă liniște.",
        )

        hero = card(self.content, PURPLE)
        hero.pack(fill="x", pady=(0, 18))

        text = tk.Frame(hero, bg=PURPLE)
        text.pack(side="left", fill="x", expand=True)

        label(text, "O dimineață fără grabă", 19, TEXT, True).pack(
            anchor="w"
        )
        label(
            text,
            "Următorul curs: Programare • ora 10:00\n"
            "Plecare sugerată: 09:15 • exemplu demonstrativ",
            11,
            PURPLE_DARK,
        ).pack(anchor="w", pady=(8, 0))

        button(
            hero,
            "Vezi traseele  →",
            lambda: self.show_page("Rute & trafic"),
            WHITE,
        ).pack(side="right", padx=(16, 0))

        stats = tk.Frame(self.content, bg=BG)
        stats.pack(fill="x", pady=(0, 18))

        data = [
            ("URMĂTORUL CURS", "10:00", "Programare • Sala A204", BLUE),
            ("DRUM ESTIMAT", "25 min", "Estimare demonstrativă", GREEN),
            ("FLOWPOINTS", "240", "Puncte de exemplu", PEACH),
        ]

        for column, (title, value, note, color) in enumerate(data):
            stats.columnconfigure(column, weight=1, uniform="stats")
            block = card(stats, color)
            block.grid(
                row=0, column=column, sticky="nsew",
                padx=(0 if column == 0 else 7, 0 if column == 2 else 7),
            )
            label(block, title, 9, MUTED, True).pack(anchor="w")
            label(block, value, 25, TEXT, True).pack(
                anchor="w", pady=(7, 3)
            )
            label(block, note, 9, MUTED).pack(anchor="w")

        lower = tk.Frame(self.content, bg=BG)
        lower.pack(fill="both", expand=True)
        lower.columnconfigure(0, weight=3)
        lower.columnconfigure(1, weight=2)
        lower.rowconfigure(0, weight=1)

        map_card = card(lower)
        map_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))

        label(map_card, "Drumul tău spre campus", 14, TEXT, True).pack(
            anchor="w"
        )
        label(
            map_card, "Ilustrație de interfață • nu este o hartă reală",
            9, MUTED
        ).pack(anchor="w", pady=(4, 12))

        canvas = tk.Canvas(
            map_card, bg="#EFF4EF", highlightthickness=0, height=200
        )
        canvas.pack(fill="both", expand=True)
        canvas.bind("<Configure>", lambda event: self.draw_map(canvas))

        button(
            map_card, "Explorează rutele",
            lambda: self.show_page("Rute & trafic"), BLUE, TEXT
        ).pack(anchor="w", pady=(12, 0))

        community = card(lower)
        community.grid(row=0, column=1, sticky="nsew")

        label(
            community, "Mai bine împreună", 14, TEXT, True
        ).pack(anchor="w")
        label(
            community,
            "Găsește colegi care merg\nîn aceeași direcție.",
            11, MUTED,
        ).pack(anchor="w", pady=(8, 18))

        for initials, name, info, color in [
            ("AM", "Alex M.", "09:15 • 2 locuri disponibile", GREEN),
            ("ID", "Ioana D.", "09:25 • 1 loc disponibil", PEACH),
        ]:
            row = tk.Frame(community, bg=WHITE)
            row.pack(fill="x", pady=8)

            avatar = label(row, initials, 11, TEXT, True, color)
            avatar.configure(padx=10, pady=10)
            avatar.pack(side="left", padx=(0, 10))

            details = tk.Frame(row, bg=WHITE)
            details.pack(side="left")
            label(details, name, 11, TEXT, True).pack(anchor="w")
            label(details, info, 9, MUTED).pack(anchor="w", pady=3)

        label(
            community, "Profiluri și curse fictive", 9, MUTED
        ).pack(anchor="w", pady=(8, 14))

        button(
            community, "Caută o cursă",
            lambda: self.show_page("Carpooling"),
        ).pack(fill="x")

    def draw_map(self, canvas):
        canvas.delete("all")
        w = canvas.winfo_width()
        h = canvas.winfo_height()

        # Ilustrație decorativă, fără date geografice.
        canvas.create_oval(
            w * .04, h * .08, w * .38, h * .55,
            fill="#D7E8D6", outline=""
        )
        canvas.create_oval(
            w * .65, h * .55, w * .98, h * .95,
            fill="#D7E8D6", outline=""
        )

        for fraction in (.25, .55, .80):
            canvas.create_line(
                w * fraction, 0, w * (fraction - .12), h,
                fill=WHITE, width=17
            )

        for fraction in (.30, .70):
            canvas.create_line(
                0, h * fraction, w, h * (fraction + .08),
                fill=WHITE, width=17
            )

        route = [
            w * .16, h * .75,
            w * .36, h * .75,
            w * .48, h * .37,
            w * .80, h * .37,
        ]

        canvas.create_line(
            *route, fill="#927BB9", width=7,
            capstyle="round", joinstyle="round"
        )

        for x, y, text in [
            (w * .16, h * .75, "Plecare"),
            (w * .80, h * .37, "Campus"),
        ]:
            canvas.create_oval(
                x - 8, y - 8, x + 8, y + 8,
                fill=ACCENT_GREEN, outline=WHITE, width=3,
            )
            canvas.create_text(
                x, y - 21, text=text,
                fill=TEXT, font=(FONT, 10, "bold")
            )

    def pagina_rute(self):
        self.heading(
            "Rute & trafic",
            "Hartă interactivă și navigație auto • fără cheie Google API.",
        )
        panel = tk.Frame(self.content, bg=WHITE, padx=10, pady=8)
        panel.pack(fill="both", expand=True)

        label(panel, "Planifică drumul spre facultate", 17, TEXT, True).pack(anchor="w")
        label(panel, "OSRM + trafic colaborativ (dacă există suficiente date reale)", 10, MUTED).pack(
            anchor="w", pady=(4, 7)
        )

        label(panel, "📍 De unde pleci?", 11, TEXT, True).pack(anchor="w", pady=(0, 5))
        origin_row = tk.Frame(panel, bg=WHITE)
        origin_row.pack(fill="x", pady=(0, 10))
        self.origin_entry = tk.Entry(
            origin_row, textvariable=self.origine, font=(FONT, 11),
            relief="solid", bd=1, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT_GREEN,
        )
        self.origin_entry.pack(side="left", fill="x", expand=True, ipady=8)
        button(origin_row, "📍 Locația mea (Windows)", self.cere_locatia, BLUE, TEXT).pack(
            side="left", padx=(8, 0)
        )
        label(panel, "🎓 Unde mergi?", 11, TEXT, True).pack(anchor="w", pady=(0, 5))
        destination_entry = tk.Entry(
            panel, textvariable=self.destinatie, font=(FONT, 11),
            relief="solid", bd=1, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT_GREEN,
        )
        destination_entry.pack(fill="x", ipady=8, pady=(0, 10))

        plecare_row = tk.Frame(panel, bg=WHITE)
        plecare_row.pack(fill="x", pady=(0, 8))
        label(plecare_row, "🕒 Ora plecării (HH:MM):", 10, TEXT, True).pack(side="left", padx=(0, 12))
        tk.Entry(plecare_row, textvariable=self.ora_plecare, width=9,
                 font=(FONT, 11)).pack(side="left", ipady=5)
        label(plecare_row, "Două estimări: normală și prudentă (+20% și 5 min)",
              9, MUTED).pack(side="left", padx=15)

        scenariu = tk.Frame(panel, bg=WHITE)
        scenariu.pack(fill="x", pady=(0, 6))
        label(scenariu, "Scenariu pentru durata estimată (DEMO):", 10, TEXT, True).pack(side="left", padx=(0, 8))
        tk.OptionMenu(scenariu, self.traffic_scenario, "Liber", "Moderat", "Aglomerat").pack(side="left")
        label(scenariu, "Verde / galben / roșu = simulare, nu măsurare reală", 9, MUTED).pack(side="left", padx=10)
        self.route_button = button(
            panel, "Se calculează..." if self.route_busy else "Calculează traseul  →",
            self.porneste_rute, ACCENT_GREEN, WHITE,
        )
        self.route_button.pack(fill="x", pady=(2, 5))
        if self.route_busy:
            self.route_button.configure(state="disabled")
        label_status = label(panel, "", 10, MUTED)
        label_status.configure(textvariable=self.route_status, wraplength=730)
        label_status.pack(anchor="w", pady=(0, 5))

        # Harta are prioritate vizuală: apare deasupra indicațiilor text.
        rezultate = tk.Frame(panel, bg="#F7FBFD", highlightbackground=BORDER, highlightthickness=1)
        rezultate.pack(fill="both", expand=True)
        cap = label(rezultate, "HARTĂ INTERACTIVĂ • TRASEUL TĂU", 10, TEXT, True, PEACH)
        cap.configure(padx=14, pady=9)
        cap.pack(fill="x")

        if tkintermapview is not None:
            self.route_map = tkintermapview.TkinterMapView(
                rezultate, width=1050, height=540, corner_radius=0
            )
            self.route_map.pack(fill="x", expand=False, padx=2, pady=(2, 2))
            self.route_map.configure(height=320)
            self.route_map.set_tile_server(
                "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
                max_zoom=19,
            )
            self.route_map.set_position(47.1585, 27.6014)
            self.route_map.set_zoom(12)
        else:
            self.route_map = None
            label(rezultate, "Instalează harta: python -m pip install tkintermapview", 10, MUTED).pack(pady=12)

        self.route_choices_frame = tk.Frame(rezultate, bg=WHITE)
        self.route_choices_frame.pack(fill="x", padx=8, pady=4)
        # Navigator pas-cu-pas: pașii provin din ruta OSRM, nu din exemple fictive.
        nav = tk.Frame(rezultate, bg=BLUE, padx=8, pady=4)
        nav.pack(fill="x", padx=4, pady=(2, 5))
        self.nav_title = tk.StringVar(value="Calculează un traseu pentru indicații pas cu pas.")
        self.nav_counter = tk.StringVar(value="")
        tk.Label(nav, textvariable=self.nav_title, bg=BLUE, fg=TEXT,
                 font=(FONT, 13, "bold"), anchor="w", justify="left",
                 wraplength=720).pack(fill="x")
        tk.Label(nav, textvariable=self.nav_counter, bg=BLUE, fg=MUTED,
                 font=(FONT, 9), anchor="w").pack(fill="x", pady=(2, 4))
        controls = tk.Frame(nav, bg=BLUE)
        controls.pack(fill="x")
        button(controls, "◀ Pasul anterior", self.pas_anterior, WHITE, TEXT).pack(side="left", padx=(0, 6))
        button(controls, "Pasul următor ▶", self.pas_urmator, ACCENT_GREEN, WHITE).pack(side="left", padx=(0, 6))
        button(controls, "🔊 Citește pasul", self.citeste_pasul, WHITE, TEXT).pack(side="left")

        label(rezultate, "DISTANȚĂ, DURATĂ ȘI INDICAȚII", 10, TEXT, True).pack(
            anchor="w", padx=12, pady=(5, 3)
        )
        text_frame = tk.Frame(rezultate, bg="#F7FBFD")
        text_frame.pack(fill="x", padx=8, pady=(0, 8))
        scroll = tk.Scrollbar(text_frame)
        scroll.pack(side="right", fill="y")
        self.route_results = tk.Text(
            text_frame, bg="#F7FBFD", fg=TEXT, font=(FONT, 10),
            relief="flat", wrap="word", padx=10, pady=7,
            height=3, state="disabled", yscrollcommand=scroll.set,
        )
        self.route_results.pack(side="left", fill="x", expand=True)
        scroll.config(command=self.route_results.yview)
        self.afiseaza_rute(self.route_text)
        button(panel, "📋 Ultimele trasee salvate", self.vezi_istoric_rute, BLUE, TEXT).pack(
            anchor="w", pady=(2, 3))

        avertisment = label(
            panel,
            "⚠ Estimările nu includ trafic în timp real sau transport public. "
            "Serviciile gratuite sunt destinate doar testării prototipului.",
            9, "#A43139",
        )
        avertisment.configure(wraplength=740)
        avertisment.pack(anchor="w", pady=(12, 0))

    def arata_pasul(self):
        if not self.nav_steps:
            if hasattr(self, "nav_title"):
                self.nav_title.set("Calculează un traseu pentru indicații pas cu pas.")
                self.nav_counter.set("")
            return
        self.nav_index = max(0, min(self.nav_index, len(self.nav_steps) - 1))
        pas = self.nav_steps[self.nav_index]
        self.nav_title.set(pas["text"])
        mod = "Urmărire GPS activă" if self.nav_follow else "Parcurgere manuală"
        self.nav_counter.set(f"Pasul {self.nav_index + 1} din {len(self.nav_steps)} • {mod}")
        if self.nav_window is not None and self.nav_window.winfo_exists():
            self.nav_big_title.set(pas['text'])
            self.nav_big_counter.set(f'Pasul {self.nav_index + 1} din {len(self.nav_steps)}')
            # În navigația GPS urmărim poziția actuală, nu sărim la intersecții.
            if not self.nav_follow and self.nav_big_map is not None and pas.get('location'):
                self.nav_big_map.set_position(*pas['location'])
                self.nav_big_map.set_zoom(16)

    def pas_urmator(self):
        if self.nav_steps and self.nav_index < len(self.nav_steps) - 1:
            self.nav_index += 1
            self.arata_pasul()
            if self.nav_speech.get():
                self.citeste_pasul()

    def pas_anterior(self):
        if self.nav_steps and self.nav_index > 0:
            self.nav_index -= 1
            self.arata_pasul()
            if self.nav_speech.get():
                self.citeste_pasul()

    def citeste_pasul(self):
        if self.nav_steps:
            self._rosteste(self.nav_steps[self.nav_index]["text"])

    def _rosteste(self, mesaj):
        """Folosește vocea Windows, fără dependențe Python suplimentare."""
        def worker():
            try:
                # -EncodedCommand transmite Unicode corect și evită erorile de quoting.
                script = ("Add-Type -AssemblyName System.Speech; "
                          "$v=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                          "$v.Volume=100; $v.Rate=-1; "
                          "$v.Speak('" + mesaj.replace("'", "''") + "')")
                encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
                with self.speech_lock:
                    proc = subprocess.run(['powershell.exe', '-NoProfile', '-EncodedCommand', encoded],
                                          capture_output=True, timeout=35)
                if proc.returncode != 0:
                    raise RuntimeError(proc.stderr.decode('utf-8', errors='replace')[-250:])
            except Exception as eroare:
                self.route_queue.put(('SPEECH_ERROR', f'Vocea Windows nu a pornit: {eroare}'))
        threading.Thread(target=worker, daemon=True).start()

    def deschide_navigatia(self, puncte, start, final):
        """Deschide automat o hartă mare, separată de formular."""
        if tkintermapview is None:
            self.route_status.set('Harta lipsește. Instalează: python -m pip install tkintermapview')
            return
        if self.nav_window is not None and self.nav_window.winfo_exists():
            self.nav_window.destroy()
        self.nav_window = tk.Toplevel(self)
        self.nav_window.title('UniRide • Navigație interactivă')
        self.nav_window.geometry('1280x860')
        self.nav_window.minsize(850, 600)
        self.nav_window.configure(bg=BG)
        self.nav_window.protocol('WM_DELETE_WINDOW', self.inchide_navigatia)
        self.nav_window.lift()
        self.nav_window.focus_force()

        banner = tk.Frame(self.nav_window, bg=PURPLE_DARK, padx=16, pady=12)
        banner.pack(fill='x')
        self.nav_big_title = tk.StringVar(value='Se pregătește navigația...')
        self.nav_big_counter = tk.StringVar(value='')
        tk.Label(banner, textvariable=self.nav_big_title, bg=PURPLE_DARK, fg=WHITE,
                 font=(FONT, 19, 'bold'), wraplength=1080, justify='left', anchor='w').pack(fill='x')
        tk.Label(banner, textvariable=self.nav_big_counter, bg=PURPLE_DARK, fg=WHITE,
                 font=(FONT, 10), anchor='w').pack(fill='x')

        self.nav_big_map = tkintermapview.TkinterMapView(self.nav_window, corner_radius=0)
        self.nav_big_map.pack(fill='both', expand=True, padx=6, pady=6)
        # Serverul implicit al bibliotecii este folosit pentru compatibilitate.
        self.nav_big_map.set_marker(start[1], start[0], text='Plecare')
        self.nav_big_map.set_marker(final[1], final[0], text='Destinație')
        if len(puncte) >= 2:
            self.nav_big_path = self.nav_big_map.set_path(puncte, color=ACCENT_GREEN, width=7)
            self.nav_big_map.fit_bounding_box(
                (max(lat for lat, lon in puncte), min(lon for lat, lon in puncte)),
                (min(lat for lat, lon in puncte), max(lon for lat, lon in puncte)))
        else:
            self.nav_big_map.set_position(start[1], start[0])
            self.nav_big_map.set_zoom(14)

        bar = tk.Frame(self.nav_window, bg=WHITE, padx=12, pady=8)
        bar.pack(fill='x')
        button(bar, '◀ Anterior', self.pas_anterior, BLUE, TEXT).pack(side='left', padx=3)
        button(bar, 'Următor ▶', self.pas_urmator, ACCENT_GREEN, WHITE).pack(side='left', padx=3)
        button(bar, '🔊 Repetă indicația', self.citeste_pasul, BLUE, TEXT).pack(side='left', padx=3)
        tk.Checkbutton(bar, text='Voce activă', variable=self.nav_speech, bg=WHITE,
                       font=(FONT, 10)).pack(side='left', padx=12)
        self.nav_gps_button = button(bar, '📍 Pornește urmărirea GPS', self.comuta_urmarirea_gps, BLUE, TEXT)
        self.nav_gps_button.pack(side='left', padx=3)
        button(bar, 'Închide navigația', self.inchide_navigatia, PEACH, TEXT).pack(side='right')
        tk.Label(self.nav_window, bg=BG, fg=MUTED, font=(FONT, 9),
                 text='Prototip: fără trafic live. Poziția Windows poate fi prea imprecisă pentru viraje în siguranță.').pack(fill='x')
        self.nav_follow = (self.origine.get().strip() == '📍 Locația dispozitivului')
        self.nav_approach_announced = set()
        self.nav_last_announced = -1
        self.nav_last_position = None
        if self.nav_follow:
            self.nav_gps_button.configure(text='⏹ Oprește urmărirea GPS')
        self.arata_pasul()
        if self.nav_speech.get():
            self.citeste_pasul()
        if self.nav_follow:
            self.nav_gps_after = self.after(1000, self.actualizeaza_navigatia_gps)

    def comuta_urmarirea_gps(self):
        """Urmărirea pornește numai la alegerea explicită a utilizatorului."""
        if self.nav_follow:
            self.nav_follow = False
            self.nav_gps_button.configure(text='📍 Pornește urmărirea GPS')
            if self.nav_gps_after is not None:
                self.after_cancel(self.nav_gps_after)
                self.nav_gps_after = None
            self.nav_big_counter.set('Urmărirea GPS este oprită.')
        else:
            self.nav_follow = True
            self.nav_gps_button.configure(text='⏹ Oprește urmărirea GPS')
            self.nav_big_counter.set('Se solicită poziția Windows...')
            self.actualizeaza_navigatia_gps()
        self.arata_pasul()

    def inchide_navigatia(self):
        self.nav_follow = False
        if self.nav_gps_after is not None:
            self.after_cancel(self.nav_gps_after)
            self.nav_gps_after = None
        if self.nav_window is not None and self.nav_window.winfo_exists():
            self.nav_window.destroy()
        self.nav_window = None
        self.nav_big_map = None

    def actualizeaza_navigatia_gps(self):
        """Urmărește locația numai dacă utilizatorul a ales explicit Windows."""
        if not self.nav_follow or self.nav_window is None or not self.nav_window.winfo_exists():
            return
        if not self.nav_gps_busy:
            self.nav_gps_busy = True
            threading.Thread(target=self._citeste_locatia_windows, daemon=True).start()
        self.nav_gps_after = self.after(5000, self.actualizeaza_navigatia_gps)

    def navigheaza_cu_pozitia(self, lat, lon, accuracy):
        """Afișează poziția și anunță manevre numai cu precizie GPS adecvată.

        Folosește distanța până la punctele OSRM, fără a pretinde map-matching.
        """
        self.nav_gps_busy = False
        if not self.nav_follow or self.nav_big_map is None or not self.nav_big_map.winfo_exists():
            return
        if self.nav_big_marker is not None:
            self.nav_big_marker.delete()
        self.nav_big_marker = self.nav_big_map.set_marker(
            lat, lon, text=f'Poziția Windows (±{accuracy:.0f} m)')
        self.nav_big_map.set_position(lat, lon)
        self.nav_big_map.set_zoom(17)
        self.nav_last_position = (lat, lon)
        self.nav_last_gps_time = datetime.now()
        if accuracy > self.nav_gps_accuracy_limit:
            self.nav_big_counter.set(
                f'Poziție aproximativă ±{accuracy:.0f} m. '
                'Indicațiile automate sunt suspendate pentru siguranță.')
            return
        if not self.nav_steps:
            return
        # Fiecare pas conține locația manevrei curente. Ne raportăm la următoarea
        # manevră; după depășirea ei trecem la pasul următor.
        next_idx = min(self.nav_index + 1, len(self.nav_steps) - 1)
        target = self.nav_steps[next_idx].get('location')
        if not target:
            self.nav_big_counter.set('GPS activ • urmărim poziția aproximativă')
            return
        distance = self.distanta_metri(lat, lon, *target)
        self.nav_big_counter.set(
            f'GPS ±{accuracy:.0f} m • ~{distance:.0f} m până la următoarea manevră '
            f'• pasul {self.nav_index + 1}/{len(self.nav_steps)}')
        # Anunțăm apropierea o singură dată; nu reluăm la fiecare actualizare.
        if 90 <= distance <= 220 and next_idx not in self.nav_approach_announced:
            self.nav_approach_announced.add(next_idx)
            if self.nav_speech.get():
                self._rosteste(f'În aproximativ {round(distance / 10) * 10} de metri. '
                              + self.nav_steps[next_idx]['text'].split(' • ')[0])
        # La precizie <=35m, toleranța de 45m rămâne doar un prag experimental.
        if distance <= 45 and self.nav_index < len(self.nav_steps) - 1:
            self.nav_index += 1
            self.arata_pasul()
            if self.nav_speech.get():
                self.citeste_pasul()

    @staticmethod
    def distanta_metri(lat1, lon1, lat2, lon2):
        r = 6371000
        a = (math.sin(math.radians(lat2-lat1)/2)**2 +
             math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*
             math.sin(math.radians(lon2-lon1)/2)**2)
        return 2*r*math.asin(min(1, math.sqrt(a)))

    def vezi_istoric_rute(self):
        with deschide_baza() as db:
            rows = db.execute("""SELECT origine, destinatie, plecare, distanta_km,
                sosire_normala, sosire_prudenta FROM istoric_trasee
                ORDER BY id DESC LIMIT 8""").fetchall()
        if not rows:
            messagebox.showinfo("Istoric trasee", "Nu ai calculat încă niciun traseu.", parent=self)
            return
        lines = [f"{a} → {b}\n  Plecare {t} • {km:.1f} km • "
                 f"sosire normală {n} / prudentă {pr}"
                 for a, b, t, km, n, pr in rows]
        messagebox.showinfo("Ultimele trasee salvate local", "\n\n".join(lines), parent=self)

    def afiseaza_rute(self, text):
        if not hasattr(self, "route_results") or not self.route_results.winfo_exists():
            return
        self.route_results.configure(state="normal")
        self.route_results.delete("1.0", "end")
        self.route_results.insert("1.0", text)
        self.route_results.configure(state="disabled")

    def porneste_rute(self):
        if self.route_busy:
            return
        origine = self.origine.get().strip()
        destinatie = self.destinatie.get().strip()
        coordonate_dispozitiv = self.device_coords if origine == "📍 Locația dispozitivului" else None
        if not origine or not destinatie:
            self.route_status.set("⚠ Completează ambele adrese.")
            return
        try:
            plecare = datetime.strptime(self.ora_plecare.get().strip(), "%H:%M")
            if self.ora_plecare.get().strip() != plecare.strftime("%H:%M"):
                raise ValueError()
        except ValueError:
            self.route_status.set("⚠ Ora plecării trebuie să fie HH:MM, de exemplu 09:15.")
            return
        self.route_busy = True
        self.route_status.set("Căutăm adresele și calculăm traseele...")
        self.route_text = "Se încarcă rezultatele..."
        self.afiseaza_rute(self.route_text)
        self.route_button.configure(state="disabled", text="Se calculează...")
        threading.Thread(
            target=self.lucrator_rute, args=(origine, destinatie, coordonate_dispozitiv,
                                                  self.ora_plecare.get().strip(), self.traffic_scenario.get()), daemon=True,
        ).start()

    def lucrator_rute(self, origine, destinatie, coordonate_dispozitiv=None, ora_plecare="09:00", scenariu="Moderat"):
        # Toate operațiile Tkinter se execută doar în firul principal.
        try:
            if coordonate_dispozitiv is not None:
                start = coordonate_dispozitiv
            else:
                start = coordonate(origine)
                time.sleep(1.1)  # Limită de 1 cerere/secundă pentru Nominatim public.
            final = coordonate(destinatie)
            rute = calculeaza_rute(start, final)
            linii = []
            coeficient = {"Liber": 1.0, "Moderat": 1.2, "Aglomerat": 1.55}.get(scenariu, 1.2)
            for i, ruta in enumerate(rute[:2], 1):
                linii.append(
                    f"Varianta {i}  •  {ruta['distance']/1000:.1f} km"
                    f"  •  {math.ceil(ruta['duration']/60 * coeficient)} min (scenariu {scenariu}, DEMO)"
                )
            rapida = min(rute, key=lambda ruta: ruta["duration"])
            scurta = min(rute, key=lambda ruta: ruta["distance"])
            durata_normala = max(1, math.ceil(rapida["duration"] / 60 * coeficient))
            durata_prudenta = math.ceil(durata_normala * 1.2 + 5)
            baza = datetime.strptime(ora_plecare, "%H:%M")
            sosire_normala = (baza + timedelta(minutes=durata_normala)).strftime("%H:%M")
            sosire_prudenta = (baza + timedelta(minutes=durata_prudenta)).strftime("%H:%M")
            linii.extend([
                "", "PREDICȚIA 1 — ORA SOSIRII (scenariu demonstrativ, fără trafic live):",
                f"🕒 Plecare: {ora_plecare}",
                f"🟢 Scenariu normal: {durata_normala} min • sosire {sosire_normala}",
                f"🟡 Scenariu prudent: {durata_prudenta} min • sosire {sosire_prudenta}",
                "Scenariul prudent adaugă 20% + 5 min; nu este o predicție din trafic real.",
                "",
                f"⚡ Cea mai rapidă: {rapida['distance']/1000:.1f} km, "
                f"{math.ceil(rapida['duration']/60)} minute",
                f"📏 Cea mai scurtă: {scurta['distance']/1000:.1f} km, "
                f"{math.ceil(scurta['duration']/60)} minute",
                "",
                "Estimările nu includ trafic live sau așteptarea unui șofer.",
                "PREDICȚIA 2 — TRASEU: ruta recomandată este cea cu durata OSRM minimă; nu este ML antrenat.",
            ])
            linii.extend(["", "INDICAȚII DE DEPLASARE (traseul cel mai rapid):"])
            pasi_navigatie = []
            for leg in rapida.get("legs", []):
                for pas in leg.get("steps", []):
                    manevra = pas.get("maneuver", {})
                    tip = manevra.get("type", "continue")
                    directie = manevra.get("modifier", "")
                    strada = pas.get("name") or "drumul indicat"
                    directii = {"left": "la stânga", "right": "la dreapta",
                               "straight": "înainte", "slight left": "ușor la stânga",
                               "slight right": "ușor la dreapta", "sharp left": "accentuat la stânga",
                               "sharp right": "accentuat la dreapta", "uturn": "înapoi"}
                    orientare = directii.get(directie, "")
                    if tip == "depart":
                        instructiune = f"Pornește pe {strada}"
                    elif tip == "arrive":
                        instructiune = "Ai ajuns la destinație"
                    elif tip in ("turn", "end of road"):
                        instructiune = f"Virează {orientare} pe {strada}"
                    elif tip == "roundabout":
                        iesire = manevra.get("exit")
                        instructiune = f"Intră în sensul giratoriu" + (f" și ieși la ieșirea {iesire}" if iesire else "")
                    elif tip in ("fork", "merge", "on ramp", "off ramp"):
                        instructiune = f"Urmează {orientare} spre {strada}"
                    else:
                        instructiune = f"Continuă {orientare} pe {strada}"
                    distanta = float(pas.get("distance", 0))
                    if tip != "arrive":
                        instructiune += f" • {distanta:.0f} m până la următoarea manevră"
                    location = manevra.get("location")
                    coord = (float(location[1]), float(location[0])) if location and len(location) == 2 else None
                    pasi_navigatie.append({"text": instructiune, "location": coord})
                    linii.append(f" • {instructiune}")
            geometrie = rapida.get("geometry", {}).get("coordinates", [])
            puncte = [(lat, lon) for lon, lat in geometrie]
            # Salvăm doar adresele introduse; coordonatele Windows nu intră în baza locală.
            with deschide_baza() as db:
                db.execute("""INSERT INTO istoric_trasee
                    (origine, destinatie, plecare, distanta_km, durata_min,
                     sosire_normala, sosire_prudenta, creat_la)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("Locația dispozitivului" if coordonate_dispozitiv is not None else origine,
                     destinatie, ora_plecare, round(rapida["distance"] / 1000, 2),
                     durata_normala, sosire_normala, sosire_prudenta,
                     datetime.now().isoformat(timespec="seconds")))
            optiuni = []
            for ruta in rute[:2]:
                geometrie_opt = ruta.get("geometry", {}).get("coordinates", [])
                puncte_opt = [(lat, lon) for lon, lat in geometrie_opt]
                stare, acoperire = trafic_colaborativ(puncte_opt)
                optiuni.append({"puncte": puncte_opt,
                                "km": ruta["distance"] / 1000,
                                "minute": math.ceil(ruta["duration"] / 60 * coeficient),
                                "trafic": stare, "acoperire": acoperire})
            with deschide_baza() as db:
                stamp = datetime.now().isoformat(timespec="seconds")
                db.execute("INSERT INTO predictii (origine,destinatie,plecare,tip,rezultat,metoda,creat_la) VALUES (?,?,?,?,?,?,?)",
                           (origine, destinatie, ora_plecare, "ora", sosire_normala, "OSRM + coeficient scenariu DEMO", stamp))
                db.execute("INSERT INTO predictii (origine,destinatie,plecare,tip,rezultat,metoda,creat_la) VALUES (?,?,?,?,?,?,?)",
                           (origine, destinatie, ora_plecare, "traseu", "Ruta cu durata OSRM minimă", "Comparare alternative OSRM, nu ML", stamp))
            self.route_queue.put(("ROUTE_OK", "\n".join(linii),
                                  "Traseele au fost calculate cu succes! 💚", puncte, start, final,
                                  pasi_navigatie, optiuni))
        except (requests.RequestException, ValueError, KeyError, TypeError, sqlite3.Error) as eroare:
            self.route_queue.put((
                f"Nu am putut calcula traseul.\n{eroare}",
                "Verifică adresele sau conexiunea la internet.",
            ))

    def arata_optiuni_trasee(self):
        """Compară două rute; trafic real doar dacă există suficiente observații."""
        frame = getattr(self, "route_choices_frame", None)
        if frame is None or not frame.winfo_exists():
            return
        for copil in frame.winfo_children():
            copil.destroy()
        culori = {"Liber": ("#DDF5E5", "#218345"),
                  "Moderat": ("#FFF2AD", "#755700"),
                  "Aglomerat": ("#FFE0E0", "#B32029")}
        for i, ruta in enumerate(self.route_options):
            fundal, text_color = culori.get(ruta["trafic"], (BLUE, TEXT))
            linie = tk.Frame(frame, bg=fundal, padx=10, pady=7)
            linie.pack(fill="x", pady=2)
            prefix = "✓ " if i == self.selected_route_index else ""
            tk.Label(linie, text=f"{prefix}Traseul {i+1} · {ruta['km']:.1f} km · {ruta['minute']} min",
                     font=(FONT, 11, "bold"), bg=fundal, fg=TEXT).pack(side="left")
            tk.Label(linie, text=f"  ● {ruta['trafic']} (date comunitare: {ruta.get('acoperire',0):.0%} din segmente)",
                     font=(FONT, 10, "bold"), bg=fundal, fg=text_color).pack(side="left", padx=8)
            button(linie, "Arată pe hartă", lambda j=i: self.alege_traseu(j), WHITE, TEXT).pack(side="right")
        if len(self.route_options) < 2:
            label(frame, "OSRM a furnizat o singură rută distinctă pentru aceste adrese.", 9, MUTED).pack(anchor="w")

    def alege_traseu(self, index):
        if index >= len(self.route_options):
            return
        self.selected_route_index = index
        ruta = self.route_options[index]
        harta = getattr(self, "route_map", None)
        if harta is not None and harta.winfo_exists() and len(ruta["puncte"]) > 1:
            harta.delete_all_path()
            harta.set_path(ruta["puncte"], color="#33AC58" if index == 0 else "#216A9A", width=5)
            puncte = ruta["puncte"]
            harta.fit_bounding_box((max(x for x,y in puncte), min(y for x,y in puncte)),
                                   (min(x for x,y in puncte), max(y for x,y in puncte)))
        self.arata_optiuni_trasee()
        self.route_status.set("Traseu afișat. Indicațiile vocale rămân pentru ruta OSRM cea mai rapidă.")

    def verifica_rute(self):
        try:
            while True:
                mesaj = self.route_queue.get_nowait()
                if mesaj[0] == "SPEECH_ERROR":
                    self.route_status.set(mesaj[1])
                    continue
                if mesaj[0] == "LOCATION_ERROR":
                    self.nav_gps_busy = False
                    if self.nav_follow and self.nav_window is not None and self.nav_window.winfo_exists():
                        self.nav_big_counter.set('Localizarea Windows a eșuat. Verifică permisiunile.')
                    self.route_status.set(mesaj[1])
                    continue
                if mesaj[0] == "LOCATION":
                    _, lat, lon, accuracy = mesaj
                    self.device_coords = (lon, lat)
                    self.navigheaza_cu_pozitia(lat, lon, accuracy)
                    self.origine.set("📍 Locația dispozitivului")
                    if not self.nav_follow:
                        self.route_status.set(
                            f"Locație primită (precizie estimată ±{accuracy:.0f} m). "
                            "Apasă «Calculează traseul»."
                        )
                    if getattr(self, "route_map", None) is not None and self.route_map.winfo_exists():
                        self.route_map.set_position(lat, lon)
                        self.route_map.set_zoom(16)
                        self.route_map.delete_all_marker()
                        self.route_map.set_marker(lat, lon, text="Locația mea (aproximativ)")
                    continue
                if mesaj[0] == "ROUTE_OK":
                    _, self.route_text, status, puncte, start, final, self.nav_steps, self.route_options = mesaj
                    self.selected_route_index = 0
                    self.arata_optiuni_trasee()
                    self.nav_index = 0
                else:
                    self.route_text, status = mesaj[:2]
                    puncte = start = final = None
                    self.nav_steps = []
                if (puncte is not None and getattr(self, "route_map", None) is not None
                        and self.route_map.winfo_exists()):
                    self.route_map.delete_all_path()
                    self.route_map.delete_all_marker()
                    self.route_map.set_marker(start[1], start[0], text="Plecare")
                    self.route_map.set_marker(final[1], final[0], text="Destinație")
                    if len(puncte) >= 2:
                        self.route_map.set_path(puncte, color="#33AC58", width=5)
                        self.route_map.fit_bounding_box(
                            (max(lat for lat, lon in puncte), min(lon for lat, lon in puncte)),
                            (min(lat for lat, lon in puncte), max(lon for lat, lon in puncte)),
                        )
                self.route_status.set(status)
                self.arata_pasul()
                if puncte is not None:
                    self.deschide_navigatia(puncte, start, final)
                self.route_busy = False
                self.afiseaza_rute(self.route_text)
                if hasattr(self, "route_button") and self.route_button.winfo_exists():
                    self.route_button.configure(state="normal", text="Calculează traseul  →")
        except queue.Empty:
            pass
        self.after(150, self.verifica_rute)

    def cere_locatia(self):
        """Citește poziția oferită de Windows, doar la apăsarea butonului."""
        self.route_status.set("Se solicită locația de la Windows...")
        threading.Thread(target=self._citeste_locatia_windows, daemon=True).start()

    def _citeste_locatia_windows(self):
        try:
            from winrt.windows.devices.geolocation import Geolocator

            async def obtine():
                locator = Geolocator()
                locator.desired_accuracy_in_meters = 25
                position = await asyncio.wait_for(
                    locator.get_geoposition_async(), timeout=30
                )
                point = position.coordinate.point.position
                accuracy = float(position.coordinate.accuracy)
                return float(point.latitude), float(point.longitude), accuracy

            lat, lon, accuracy = asyncio.run(obtine())
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Windows a returnat coordonate invalide.")
            self.route_queue.put(("LOCATION", lat, lon, accuracy))
        except ImportError:
            self.route_queue.put(("LOCATION_ERROR",
                "Lipsește biblioteca Windows. Instalează: python -m pip install winrt-Windows.Devices.Geolocation"))
        except Exception as eroare:
            self.route_queue.put(("LOCATION_ERROR",
                "Windows nu a putut determina locația. Verifică permisiunile "
                "din Settings > Privacy & security > Location. "
                f"Detalii: {eroare}"))

    def inchide_aplicatia(self):
        self.nav_follow = False
        if self.nav_gps_after is not None:
            self.after_cancel(self.nav_gps_after)
            self.nav_gps_after = None
        self.destroy()

    def init_curse_locale(self):
        with deschide_baza() as db:
            db.execute("SELECT 1 FROM curse LIMIT 1").fetchone()

    def confirma_siguranta(self):
        return messagebox.askyesno("UniRide • Avertisment important", AVERTISMENT_RIDE, parent=self)

    def pagina_carpooling(self):
        self.heading("Carpooling • studenți pe aceeași direcție",
                     "Găsește ore și zone compatibile. Datele sunt salvate numai pe acest calculator.")
        outer = tk.Frame(self.content, bg=BG)
        outer.pack(fill="both", expand=True)

        aviso = card(outer, "#FFF0EF")
        aviso.pack(fill="x", pady=(0, 9))
        label(aviso, "⚠ Întâlnirile și cursele presupun riscuri", 13, "#A43139", True).pack(anchor="w")
        w = label(aviso, "Înainte de a contacta pe cineva, vei primi o avertizare și ți se va cere acordul. "
                  "Nu publica adresa exactă sau coordonatele dispozitivului.", 10, "#A43139")
        w.configure(wraplength=850)
        w.pack(anchor="w", pady=(5, 0))

        form = card(outer)
        form.pack(fill="x", pady=(0, 9))
        label(form, "Publică o cursă sau o cerere de transport", 14, TEXT, True).pack(anchor="w", pady=(0, 8))
        self.ride_values = {
            "pseudonim": tk.StringVar(), "facultate": tk.StringVar(),
            "zona_plecare": tk.StringVar(), "zona_sosire": tk.StringVar(),
            "zi": tk.StringVar(value="Luni"), "ora": tk.StringVar(value="09:00"),
            "rol": tk.StringVar(value="Pasager"), "locuri": tk.StringVar(value="1"),
            "mesaj": tk.StringVar(),
        }
        fields = tk.Frame(form, bg=WHITE)
        fields.pack(fill="x")
        for i, (key, title) in enumerate([
            ("pseudonim", "Pseudonim"), ("facultate", "Facultatea"),
            ("zona_plecare", "Zona plecării (fără adresă exactă)"),
            ("zona_sosire", "Zona destinației / campus"),
            ("zi", "Ziua (ex. Luni)"), ("ora", "Ora (HH:MM)"),
            ("rol", "Rol: Șofer sau Pasager"), ("locuri", "Locuri disponibile (șofer)"),
        ]):
            r, c = divmod(i, 2)
            fields.grid_columnconfigure(c, weight=1)
            cell = tk.Frame(fields, bg=WHITE)
            cell.grid(row=r, column=c, sticky="ew", padx=(0, 12), pady=3)
            label(cell, title, 9, MUTED).pack(anchor="w")
            tk.Entry(cell, textvariable=self.ride_values[key], font=(FONT, 10)).pack(fill="x", ipady=4)
        button(form, "Publică local (după avertisment)", self.publica_cursa, ACCENT_GREEN, WHITE).pack(
            anchor="w", pady=(10, 0))

        results = card(outer)
        results.pack(fill="both", expand=True)
        label(results, "Caută persoane cu program comun", 14, TEXT, True).pack(anchor="w")
        filters = tk.Frame(results, bg=WHITE)
        filters.pack(fill="x", pady=7)
        self.ride_filter_zone = tk.StringVar()
        self.ride_filter_zi = tk.StringVar()
        self.ride_filter_ora = tk.StringVar()
        for title, var in [("Zonă destinație", self.ride_filter_zone),
                           ("Zi", self.ride_filter_zi), ("Ora HH:MM (±60 min)", self.ride_filter_ora)]:
            group = tk.Frame(filters, bg=WHITE)
            group.pack(side="left", fill="x", expand=True, padx=(0, 8))
            label(group, title, 9, MUTED).pack(anchor="w")
            tk.Entry(group, textvariable=var, font=(FONT, 10)).pack(fill="x", ipady=4)
        button(results, "Caută potriviri", self.cauta_curse, BLUE, TEXT).pack(anchor="w", pady=(1, 8))
        listing = tk.Frame(results, bg=WHITE)
        listing.pack(fill="both", expand=True)
        self.ride_list = tk.Listbox(listing, font=(FONT, 10), height=5, exportselection=False,
                                    selectbackground=PURPLE_DARK, selectforeground=WHITE)
        self.ride_list.pack(side="left", fill="both", expand=True)
        scr = tk.Scrollbar(listing, command=self.ride_list.yview)
        scr.pack(side="right", fill="y")
        self.ride_list.configure(yscrollcommand=scr.set)
        self.ride_hits = []
        button(results, "Vezi detalii / Interacționează", self.vezi_cursa, PEACH, TEXT).pack(
            anchor="w", pady=(8, 2))
        button(results, "🎟 Rezervă un loc", self.rezerva_loc, ACCENT_GREEN, WHITE).pack(anchor="w", pady=3)
        button(results, "📋 Rezervările mele / anulare", self.rezervarile_mele, BLUE, TEXT).pack(anchor="w", pady=3)
        label(results, "Demo local: nu există încă utilizatori conectați între calculatoare.",
              9, MUTED).pack(anchor="w")
        self.cauta_curse()

    def publica_cursa(self):
        d = {key: var.get().strip() for key, var in self.ride_values.items()}
        if any(not d[k] for k in ("pseudonim", "facultate", "zona_plecare", "zona_sosire", "zi", "ora")):
            messagebox.showwarning("Date incomplete", "Completează numele, facultatea, zonele, ziua și ora.", parent=self)
            return
        try:
            datetime.strptime(d["ora"], "%H:%M")
            n = int(d["locuri"])
            if not 0 <= n <= 8:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Date invalide", "Ora trebuie să fie HH:MM; locurile între 0 și 8.", parent=self)
            return
        if d["rol"].casefold() not in ("șofer", "sofer", "pasager"):
            messagebox.showwarning("Rol invalid", "Introdu Șofer sau Pasager.", parent=self)
            return
        if not self.confirma_siguranta():
            return
        with deschide_baza() as db:
            db.execute("INSERT INTO curse (pseudonim, facultate, zona_plecare, zona_sosire, zi, ora, rol, locuri, mesaj, creat_la) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (d["pseudonim"][:45], d["facultate"][:80], d["zona_plecare"][:100],
                        d["zona_sosire"][:100], d["zi"][:24], d["ora"], d["rol"][:15],
                        n, "", datetime.now().isoformat(timespec="seconds")))
        messagebox.showinfo("Publicată local", "Cursa/cererea este salvată doar pe acest calculator.", parent=self)
        self.cauta_curse()

    def cauta_curse(self):
        zona = self.ride_filter_zone.get().strip().casefold()
        zi = self.ride_filter_zi.get().strip().casefold()
        ora = self.ride_filter_ora.get().strip()
        if ora:
            try:
                parsed = datetime.strptime(ora, "%H:%M")
                minutes = parsed.hour * 60 + parsed.minute
            except ValueError:
                messagebox.showwarning("Oră invalidă", "Filtrul de oră trebuie să fie HH:MM.", parent=self)
                return
        self.ride_list.delete(0, "end")
        self.ride_hits = []
        with deschide_baza() as db:
            rows = db.execute("""SELECT c.id, c.pseudonim, c.facultate, c.zona_plecare, c.zona_sosire, c.zi, c.ora, c.rol,
                   CASE WHEN lower(c.rol) IN ('șofer','sofer') THEN
                   c.locuri - COALESCE((SELECT SUM(r.locuri) FROM rezervari r WHERE r.cursa_id=c.id AND r.status='activa'),0)
                   ELSE c.locuri END AS locuri FROM curse c ORDER BY c.id DESC""").fetchall()
        for row in rows:
            _, pseudonim, facultate, start, final, day, hour, rol, locuri = row
            if zona and zona not in final.casefold():
                continue
            if zi and zi not in day.casefold():
                continue
            if ora:
                hh, mm = map(int, hour.split(":"))
                if abs(hh * 60 + mm - minutes) > 60:
                    continue
            self.ride_hits.append(row)
            self.ride_list.insert("end", f"{pseudonim} • {day} {hour} • {rol} • {start} → {final} • {locuri} locuri")
        if not self.ride_hits:
            self.ride_list.insert("end", "Nicio potrivire locală încă. Creează prima ofertă sau cerere.")

    def vezi_cursa(self):
        select = self.ride_list.curselection()
        if not select or select[0] >= len(self.ride_hits):
            messagebox.showinfo("Alege o cursă", "Selectează mai întâi o persoană din listă.", parent=self)
            return
        if not self.confirma_siguranta():
            return
        _, pseudonim, facultate, start, final, zi, ora, rol, locuri = self.ride_hits[select[0]]
        messagebox.showinfo("Detalii cursă • demo local",
            f"Pseudonim: {pseudonim}\nFacultate: {facultate}\n"
            f"Zonă plecare: {start}\nZonă destinație: {final}\n"
            f"Program: {zi}, {ora}\nRol: {rol}\nLocuri: {locuri}\n\n"
            "Mesajele directe și acceptarea unei curse între utilizatori reali "
            "vor necesita conturi verificate și un server. În acest demo nu se contactează nimeni.",
            parent=self)

    def rezerva_loc(self):
        from tkinter import simpledialog
        selectie = self.ride_list.curselection()
        if not selectie or selectie[0] >= len(self.ride_hits):
            messagebox.showwarning("Rezervare", "Selectează o cursă din listă.", parent=self)
            return
        cursa = self.ride_hits[selectie[0]]
        cursa_id, sofer, _, _, _, _, _, rol, disponibile = cursa
        if rol.casefold() not in ("șofer", "sofer"):
            messagebox.showwarning("Rezervare", "Poți rezerva doar la un șofer.", parent=self)
            return
        if disponibile < 1:
            messagebox.showwarning("Rezervare", "Nu mai sunt locuri disponibile.", parent=self)
            return
        pasager = simpledialog.askstring("Rezervă un loc", "Pseudonimul tău (diferit de șofer):", parent=self)
        if pasager is None:
            return
        pasager = pasager.strip()[:45]
        if not pasager or pasager.casefold() == sofer.casefold():
            messagebox.showwarning("Rezervare", "Introdu un pseudonim valid, diferit de al șoferului.", parent=self)
            return
        if not self.confirma_siguranta():
            return
        try:
            with deschide_baza() as db:
                db.execute("BEGIN IMMEDIATE")
                ramase = db.execute("""SELECT c.locuri - COALESCE((SELECT SUM(r.locuri) FROM rezervari r
                    WHERE r.cursa_id=c.id AND r.status='activa'),0) FROM curse c WHERE c.id=?""", (cursa_id,)).fetchone()
                if not ramase or ramase[0] < 1:
                    raise ValueError("Nu mai sunt locuri disponibile.")
                existing = db.execute("SELECT id,status FROM rezervari WHERE cursa_id=? AND pasager=?",
                                      (cursa_id, pasager)).fetchone()
                if existing and existing[1] == "activa":
                    raise ValueError("Ai deja o rezervare activă la această cursă.")
                if existing:
                    db.execute("UPDATE rezervari SET status='activa',locuri=1,creat_la=? WHERE id=?",
                               (datetime.now().isoformat(timespec="seconds"), existing[0]))
                else:
                    db.execute("INSERT INTO rezervari (cursa_id,pasager,locuri,creat_la) VALUES (?,?,1,?)",
                               (cursa_id,pasager,datetime.now().isoformat(timespec="seconds")))
            messagebox.showinfo("Rezervare locală", "Ai rezervat un loc în baza de date locală!", parent=self)
            self.cauta_curse()
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showwarning("Rezervare", str(exc), parent=self)

    def rezervarile_mele(self):
        from tkinter import simpledialog
        pasager = simpledialog.askstring("Rezervările mele", "Introdu pseudonimul folosit la rezervare:", parent=self)
        if not pasager or not pasager.strip():
            return
        pasager = pasager.strip()[:45]
        with deschide_baza() as db:
            rows = db.execute("""SELECT r.id,c.zona_plecare,c.zona_sosire,c.zi,c.ora,c.pseudonim
                FROM rezervari r JOIN curse c ON c.id=r.cursa_id
                WHERE r.pasager=? AND r.status='activa' ORDER BY r.id DESC""", (pasager,)).fetchall()
        if not rows:
            messagebox.showinfo("Rezervările mele", "Nu ai rezervări active pe acest calculator.", parent=self)
            return
        continut = "\n".join(f"#{r[0]} · {r[1]} → {r[2]} · {r[3]} {r[4]} · șofer {r[5]}" for r in rows)
        if messagebox.askyesno("Rezervările mele", continut + "\n\nVrei să anulezi o rezervare?", parent=self):
            identificator = simpledialog.askinteger("Anulare", "ID rezervare (numărul după #):", parent=self)
            if identificator is None:
                return
            with deschide_baza() as db:
                rezultat = db.execute("UPDATE rezervari SET status='anulata' WHERE id=? AND pasager=? AND status='activa'",
                                     (identificator,pasager))
                modificat = rezultat.rowcount
            messagebox.showinfo("Anulare", "Rezervare anulată." if modificat else "Nu am găsit rezervarea activă.", parent=self)
            self.cauta_curse()

    def detail_page(self, name):
        pages = {
            "Orarul meu": (
                "Săptămâna ta, mai ușor de organizat.",
                [
                    ("Luni • 10:00", "Programare — curs • Sala A204"),
                    ("Luni • 12:00", "Matematică — seminar • Sala B102"),
                    ("Marți • 09:00", "Baze de date — laborator • Sala C301"),
                ],
                "Adaugă un curs",
            ),
            "Rute & trafic": (
                "Alege un drum potrivit pentru programul tău.",
                [
                    ("Ruta A • 25 min", "Plecare sugerată: 09:15"),
                    ("Ruta B • 30 min", "Variantă alternativă spre campus"),
                    ("Date demonstrative", "Traficul live nu este conectat."),
                ],
                "Calculează traseul",
            ),
            "Carpooling": (
                "Drumuri comune, colegi noi.",
                [
                    ("Alex M. • 09:15", "Spre campus • 2 locuri"),
                    ("Ioana D. • 09:25", "Spre campus • 1 loc"),
                    (
                        "Preluare cu grijă",
                        "În produsul final, punctul de preluare va fi afișat "
                        "doar persoanelor eligibile.",
                    ),
                ],
                "Oferă o cursă",
            ),
            "FlowFriends": (
                "Rămâneți aproape, cu acordul fiecăruia.",
                [
                    ("Lista de prieteni", "Colegi și drumuri împreună"),
                    ("Partajarea locației • oprită", "Nu se colectează locația în acest demo."),
                    ("Tu alegi", "Viitoarea partajare va necesita acord explicit."),
                ],
                "Adaugă un prieten",
            ),
            "FlowPoints": (
                "Contribuțiile tale la comunitate contează.",
                [
                    ("240 FlowPoints", "Sold demonstrativ"),
                    ("Curse finalizate", "Istoricul va apărea aici."),
                    ("Comunitate", "Regulile de acordare a punctelor vor fi definite."),
                ],
                "Vezi activitatea",
            ),
            "FlowShop": (
                "Un profil care să te reprezinte.",
                [
                    ("Rama Lavender", "O atingere discretă de mov pastel"),
                    ("Fundal Mint", "Verde delicat, pentru un profil relaxant"),
                    ("Insigna Campus Buddy", "Un detaliu pentru spiritul de comunitate"),
                ],
                "Previzualizează personalizarea",
            ),
            "Siguranță": (
                "Grija pentru comunitate începe cu fiecare dintre noi.",
                [
                    (
                        "Informare de siguranță",
                        "Ecran demonstrativ. Textul legal și acceptarea "
                        "responsabilităților trebuie definite înainte de lansare.",
                    ),
                    ("Raportarea incidentelor", "Acces rapid la semnalarea unei probleme"),
                    ("Evaluări", "Feedback după cursele finalizate"),
                ],
                "Raportează un incident",
            ),
            "Profil": (
                "Locul tău în comunitatea UniRide.",
                [
                    ("Student Demo", "Facultatea nu este selectată."),
                    ("Verificare universitară", "Neverificat • nicio verificare efectuată"),
                    ("Preferințe de confidențialitate", "Partajarea locației este oprită."),
                ],
                "Editează profilul",
            ),
        }

        subtitle, items, action = pages[name]
        self.heading(name, subtitle)

        for index, (title, description) in enumerate(items):
            warning = name == "Siguranță" and index == 0
            block = card(self.content, "#FFF0EF" if warning else WHITE)
            block.pack(fill="x", pady=(0, 14))

            label(
                block, title, 14,
                "#A43139" if warning else TEXT, True
            ).pack(anchor="w")

            detail = label(block, description, 11, MUTED)
            detail.configure(wraplength=680)
            detail.pack(anchor="w", pady=(8, 0))

        button(
            self.content, action, lambda: self.demo(action)
        ).pack(anchor="w", pady=(8, 14))

        label(
            self.content,
            "Previzualizare vizuală • informațiile afișate sunt exemple.",
            10, MUTED,
        ).pack(anchor="w")


if __name__ == "__main__":
    app = UniRide()
    app.mainloop()