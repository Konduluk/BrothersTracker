"""Brothers Tracker v0.4 — single-screen dark premium dashboard."""
import os
import queue
import random
import sqlite3
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, date
from pathlib import Path
from tkinter import ttk, messagebox

from parser import parse_warriors
from stats import rolling_gains, custom_range

URL = 'http://87.228.3.220/brotherhood/warriors'
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BrothersTracker'
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'history.sqlite3'
BG = '#0D1016'
PANEL = '#191E28'
PANEL_LIGHT = '#222936'
BORDER = '#343B49'
GOLD = '#E4BE78'
TEXT = '#F6F5F2'
MUTED = '#9DA8B7'
GREEN = '#71D9A1'
RED = '#F28E8E'


def fmt(value, signed=False):
    if value is None:
        return '—'
    return (f'{value:+,}' if signed and value else f'{value:,}').replace(',', ' ')


class SoftButton(tk.Canvas):
    """Anti-aliased-like rounded button built from Tk primitives, no dependencies."""
    def __init__(self, master, text, command, primary=False, width=152, height=40):
        super().__init__(master, width=width, height=height, bg=master.cget('bg'),
                         highlightthickness=0, bd=0, cursor='hand2')
        self.command = command
        self.primary = primary
        self.w, self.h = width, height
        self.caption = text
        self.active = False
        self.draw()
        self.bind('<Enter>', self.hover_on)
        self.bind('<Leave>', self.hover_off)
        self.bind('<Button-1>', self.invoke)

    def draw(self):
        self.delete('all')
        base = ('#F0CF91' if self.active else GOLD) if self.primary else ('#343D4C' if self.active else PANEL_LIGHT)
        fg = BG if self.primary else TEXT
        r = 15
        self.create_oval(1, 1, r*2, r*2, fill=base, outline=base)
        self.create_oval(self.w-r*2-1, 1, self.w-1, r*2, fill=base, outline=base)
        self.create_oval(1, self.h-r*2-1, r*2, self.h-1, fill=base, outline=base)
        self.create_oval(self.w-r*2-1, self.h-r*2-1, self.w-1, self.h-1, fill=base, outline=base)
        self.create_rectangle(r, 1, self.w-r, self.h-1, fill=base, outline=base)
        self.create_rectangle(1, r, self.w-1, self.h-r, fill=base, outline=base)
        self.create_text(self.w//2, self.h//2, text=self.caption, fill=fg,
                         font=('Segoe UI', 10, 'bold'))

    def hover_on(self, event):
        self.active = True
        self.draw()

    def hover_off(self, event):
        self.active = False
        self.draw()

    def invoke(self, event):
        self.command()


class Tracker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Brothers Tracker · v0.4')
        self.root.geometry('1370x850')
        self.root.minsize(1100, 700)
        self.root.configure(bg=BG)
        self.set_icon()
        self.messages = queue.Queue()
        self.running = False
        self.busy = False
        self.next_run = None
        self.last_error = None
        self.interval_min = tk.IntVar(value=28)
        self.interval_max = tk.IntVar(value=35)
        self.range_start = tk.StringVar(value=date.today().replace(day=1).isoformat())
        self.range_end = tk.StringVar(value=date.today().isoformat())
        self.status = tk.StringVar(value='МОНИТОРИНГ ВЫКЛЮЧЕН')
        self.detail = tk.StringVar(value='Открой браузер мониторинга и войди в игру')
        self.last_scan = tk.StringVar(value='—')
        self.next_scan = tk.StringVar(value='—')
        self.metric_members = tk.StringVar(value='—')
        self.metric_glory = tk.StringVar(value='—')
        self.metric_scans = tk.StringVar(value='—')
        self.metric_gain = tk.StringVar(value='—')
        self.range_summary = tk.StringVar(value='Выбери даты и нажми «Рассчитать».')
        self.range_mode = False
        self.sort_column = 'day'
        self.sort_reverse = True
        self.table_rows = []
        self.db_init()
        self.make_ui()
        self.refresh_table()
        self.root.after(400, self.tick)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def set_icon(self):
        base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        ico = base/'brothers_icon.ico'
        png = base/'brothers_icon.png'
        try:
            if sys.platform == 'win32' and ico.exists():
                self.root.iconbitmap(str(ico))
            elif png.exists():
                self._icon = tk.PhotoImage(file=str(png))
                self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass

    def db_init(self):
