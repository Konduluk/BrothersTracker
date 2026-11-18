"""Brothers Tracker v0.5 — single-screen dark premium dashboard."""
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
        self.root.title('Brothers Tracker · v0.5')
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
        self.metric_scans = tk.StringVar(value='—')
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
        # Keep v0.2 schema and all existing history untouched.
        with sqlite3.connect(DB) as c:
            c.execute('CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY, time TEXT NOT NULL, count INTEGER NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS readings (scan_id INTEGER, name TEXT, glory INTEGER, PRIMARY KEY(scan_id,name))')
            c.execute('CREATE TABLE IF NOT EXISTS contests (id INTEGER PRIMARY KEY, name TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL)')

    def make_ui(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('Premium.Treeview', background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=38, borderwidth=0, font=('Segoe UI', 10))
        style.map('Premium.Treeview', background=[('selected', '#53472F')],
                  foreground=[('selected', '#FFFFFF')])
        style.configure('Premium.Treeview.Heading', background=PANEL_LIGHT, foreground=GOLD,
                        padding=(8, 14), borderwidth=0, relief='flat', font=('Segoe UI', 10, 'bold'))
        style.map('Premium.Treeview.Heading', background=[('active', '#343C4A')])
        style.configure('Premium.Vertical.TScrollbar', troughcolor=BG, background=PANEL_LIGHT,
                        arrowcolor=GOLD, borderwidth=0)
        top = tk.Frame(self.root, bg=BG, padx=32, pady=20)
        top.pack(fill='x')
        tk.Label(top, text='BROTHERS', bg=BG, fg=GOLD,
                 font=('Segoe UI', 25, 'bold')).pack(side='left')
        tk.Label(top, text='  /  TRACKER', bg=BG, fg=TEXT,
                 font=('Segoe UI', 25)).pack(side='left')
        tk.Label(top, text='𝕭𝖗𝖔𝖙𝖍𝖊𝖗𝖘  ·  GLORY ANALYTICS', bg=BG, fg=MUTED,
                 font=('Segoe UI', 10)).pack(side='right', pady=10)
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', padx=32)
        body = tk.Frame(self.root, bg=BG, padx=32, pady=18)
        body.pack(fill='both', expand=True)

        metrics = tk.Frame(body, bg=BG)
        metrics.pack(fill='x', pady=(0, 16))
        metrics.grid_columnconfigure(0, weight=1, uniform='metric')
        metrics.grid_columnconfigure(1, weight=1, uniform='metric')
        metrics.grid_columnconfigure(2, weight=2)
        for i, (caption, value) in enumerate([
            ('БОЙЦОВ В БРАТСТВЕ', self.metric_members),
            ('СОХРАНЕНО ЗАМЕРОВ', self.metric_scans),
        ]):
            pane = self.card(metrics, 17)
            pane.grid(row=0, column=i, sticky='nsew', padx=(0, 12))
            self.label(pane, caption, 9, MUTED).pack(anchor='w')
            self.label(pane, value, 24, GOLD, bold=True).pack(anchor='w', pady=(6, 0))

        leader_card = self.card(metrics, 13)
        leader_card.grid(row=0, column=2, sticky='nsew')
        self.label(leader_card, 'ТОП-3 ПО ПРИРОСТУ ЗА 24 Ч', 9, MUTED).pack(anchor='w', pady=(0, 5))
        self.leader_rows = []
        for medal in ('🥇', '🥈', '🥉'):
            row = tk.Frame(leader_card, bg=PANEL)
            row.pack(fill='x', pady=1)
            medal_label = tk.Label(row, text=medal, font=('Segoe UI Emoji', 11),
                                   bg=PANEL, fg=GOLD, width=3, anchor='w')
            medal_label.pack(side='left')
            player = self.label(row, '—', 10, TEXT, True)
            player.pack(side='left', fill='x', expand=True, anchor='w')
            gain = self.label(row, '—', 10, GREEN, True)
            gain.pack(side='right')
            self.leader_rows.append((player, gain))

        control_row = tk.Frame(body, bg=BG)
        control_row.pack(fill='x', pady=(0, 14))
        monitor = self.card(control_row, 17)
        monitor.pack(side='left', fill='both', expand=True, padx=(0, 12))
        line = tk.Frame(monitor, bg=PANEL)
        line.pack(fill='x')
        self.light = tk.Canvas(line, width=22, height=22, bg=PANEL, highlightthickness=0)
        self.light.pack(side='left', padx=(0, 8))
        self.light_dot = self.light.create_oval(5, 5, 17, 17, fill=RED, outline='')
        self.label(line, self.status, 11, TEXT, True).pack(side='left')
        info = tk.Frame(monitor, bg=PANEL)
        info.pack(fill='x', pady=(10, 12))
        self.label(info, 'Последний замер: ', 10, MUTED).pack(side='left')
        self.label(info, self.last_scan, 10, TEXT).pack(side='left')
        self.label(info, '    Следующая проверка: ', 10, MUTED).pack(side='left')
        self.label(info, self.next_scan, 10, GOLD).pack(side='left')
        buttons = tk.Frame(monitor, bg=PANEL)
        buttons.pack(fill='x')
        SoftButton(buttons, 'Запустить', self.start, primary=True, width=133).pack(side='left', padx=(0, 8))
        SoftButton(buttons, 'Остановить', self.stop, width=133).pack(side='left', padx=(0, 8))
        SoftButton(buttons, 'Считать сейчас', self.scan, width=154).pack(side='left')
        self.label(monitor, self.detail, 9, MUTED).pack(anchor='w', pady=(9, 0))

        period = self.card(control_row, 17)
        period.pack(side='left', fill='both', expand=True)
        self.label(period, 'ПЕРИОД ДЛЯ РАСЧЁТА', 9, MUTED).pack(anchor='w')
        dates = tk.Frame(period, bg=PANEL)
        dates.pack(fill='x', pady=(8, 12))
        self.label(dates, 'От', 10, MUTED).pack(side='left')
        self.date_entry(dates, self.range_start).pack(side='left', padx=(8, 12))
        self.label(dates, 'До', 10, MUTED).pack(side='left')
        self.date_entry(dates, self.range_end).pack(side='left', padx=(8, 0))
        pbuttons = tk.Frame(period, bg=PANEL)
        pbuttons.pack(fill='x')
        SoftButton(pbuttons, 'Рассчитать', self.show_range, primary=True, width=138).pack(side='left', padx=(0, 8))
        SoftButton(pbuttons, 'Текущие данные', self.reset_range, width=173).pack(side='left')
        self.label(period, 'Формат дат: ГГГГ-ММ-ДД', 9, MUTED).pack(anchor='w', pady=(8, 0))

        self.label(body, 'РЕЙТИНГ БРАТСТВА', 14, TEXT, True, bg=BG).pack(anchor='w', pady=(0, 9))
        self.label(body, self.range_summary, 10, MUTED, bg=BG).pack(anchor='w', pady=(0, 10))
        table_box = tk.Frame(body, bg=PANEL, padx=2, pady=2)
        table_box.pack(fill='both', expand=True)
        columns = ('name','glory','day','week','month','before','after','custom')
        self.tree = ttk.Treeview(table_box, columns=columns, show='headings', style='Premium.Treeview', selectmode='browse')
        config = [
            ('name','Игрок',215), ('glory','Слава',135), ('day','24 часа',115),
            ('week','7 дней',115), ('month','30 дней',115), ('before','Было',135),
            ('after','Стало',135), ('custom','Прирост',130),
        ]
        for key, name, width in config:
            self.tree.heading(key, text=name, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, minwidth=85, anchor='center', stretch=True)
        bar = ttk.Scrollbar(table_box, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.tag_configure('even', background=PANEL)
        self.tree.tag_configure('odd', background='#1E2530')
        footer = tk.Frame(body, bg=BG)
        footer.pack(fill='x', pady=(12, 0))
        self.label(footer, 'Показатели за 24 ч / 7 / 30 дней доступны только при наличии полной истории.',
                   9, MUTED, bg=BG).pack(side='left')
        self.label(footer, 'Данные хранятся локально · v0.5', 9, MUTED, bg=BG).pack(side='right')
        self.update_status()

    def card(self, parent, padding):
        return tk.Frame(parent, bg=PANEL, padx=padding, pady=padding,
                        highlightbackground=BORDER, highlightthickness=1)

    @staticmethod
    def label(parent, value, size, color, bold=False, bg=PANEL):
        options = {'bg': bg, 'fg': color, 'font': ('Segoe UI', size, 'bold' if bold else 'normal')}
        if isinstance(value, tk.Variable):
            options['textvariable'] = value
        else:
            options['text'] = value
        return tk.Label(parent, **options)

    @staticmethod
    def date_entry(parent, variable):
        return tk.Entry(parent, textvariable=variable, width=12, bg=PANEL_LIGHT, fg=TEXT,
                        insertbackground=GOLD, relief='flat', borderwidth=0,
                        font=('Segoe UI', 11), justify='center', highlightthickness=1,
                        highlightbackground=BORDER, highlightcolor=GOLD)

    def show_range(self):
        try:
            self.custom_rows, first, last, totals = custom_range(
                DB, self.range_start.get().strip(), self.range_end.get().strip())
        except (ValueError, sqlite3.Error) as e:
            messagebox.showerror('Период', str(e))
            return
        self.range_mode = True
        self.range_times = (first, last)
        self.range_totals = totals
        if totals is None:
            self.range_summary.set('Для этого периода нет сопоставимых замеров игроков.')
        else:
            before, after, gain, matched = totals
            self.range_summary.set(f'С {first[:16]} по {last[:16]}   ·   Слава была: {fmt(before)}   ·   '
                                   f'Стала: {fmt(after)}   ·   Прирост: +{fmt(gain)}   ·   '
                                   f'Сопоставимых игроков: {matched}')
        self.refresh_table()

    def reset_range(self):
        self.range_mode = False
        self.range_summary.set('Текущие данные. Для сравнения выбери даты и нажми «Рассчитать».')
        self.refresh_table()

    def refresh_table(self):
        try:
            rolling, last_time, members, scan_count = rolling_gains(DB)
        except (ValueError, sqlite3.Error) as exc:
            self.detail.set('Ошибка чтения базы: '+str(exc))
            return
        self.metric_members.set(fmt(members) if members is not None else '—')
        self.metric_scans.set(fmt(scan_count))
        leaders = sorted(((name, row[1]) for name, row in rolling.items()
                          if row[1] is not None), key=lambda item: (-item[1], item[0].casefold()))
        # A day without sufficient historical coverage is not treated as zero gain.
        for rank, (player_label, gain_label) in enumerate(self.leader_rows):
            if rank < len(leaders):
                name, gained = leaders[rank]
                player_label.config(text=name)
                gain_label.config(text=fmt(gained, signed=True))
            else:
                player_label.config(text='Нет данных' if rank == 0 and not leaders else '—')
                gain_label.config(text='—')
        if last_time:
            try:
                self.last_scan.set(datetime.fromisoformat(last_time).strftime('%d.%m.%Y %H:%M'))
            except ValueError:
                self.last_scan.set(last_time[:16])
        extras = getattr(self, 'custom_rows', {}) if self.range_mode else {}
        names = set(rolling) | (set(extras) if self.range_mode else set())
        self.table_rows = []
        for name in names:
            current = rolling.get(name)
            r = extras.get(name)
            self.table_rows.append({
                'name':name, 'glory':current[0] if current else None,
                'day':current[1] if current else None,
                'week':current[2] if current else None,
                'month':current[3] if current else None,
                'before':r[0] if r else None,
                'after':r[1] if r else None,
                'custom':r[2] if r else None,
            })
        self.render_table()

    def sort_by(self, key):
        if self.sort_column == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = key
            self.sort_reverse = key != 'name'
        self.render_table()

    def render_table(self):
        self.tree.delete(*self.tree.get_children())
        key = self.sort_column
        present = [r for r in self.table_rows if r[key] is not None]
        absent = [r for r in self.table_rows if r[key] is None]
        present.sort(key=lambda r: r[key].casefold() if key=='name' else r[key], reverse=self.sort_reverse)
        absent.sort(key=lambda r: r['name'].casefold())
        for i, r in enumerate(present+absent):
            values = [r['name'], fmt(r['glory']), fmt(r['day'],True), fmt(r['week'],True),
                      fmt(r['month'],True), fmt(r['before']), fmt(r['after']), fmt(r['custom'],True)]
            self.tree.insert('', 'end', values=values, tags=('even' if i%2==0 else 'odd',))

    def update_status(self):
        if self.busy:
            label, color = '●  ИДЁТ СЧИТЫВАНИЕ', GOLD
        elif self.running and self.last_error:
            label, color = '●  МОНИТОРИНГ · ОШИБКА', RED
        elif self.running:
            label, color = '●  МОНИТОРИНГ ВКЛЮЧЁН', GREEN
        else:
            label, color = '●  МОНИТОРИНГ ВЫКЛЮЧЕН', RED
        self.status.set(label)
        self.light.itemconfig(self.light_dot, fill=color)
        if not self.running:
            self.next_scan.set('—')
        elif self.busy:
            self.next_scan.set('сейчас')
        elif self.next_run is not None:
            remaining = max(0, int(self.next_run-time.monotonic()))
            self.next_scan.set(f'через {remaining//60:02d}:{remaining%60:02d}')

    def start(self):
        try:
            a,b = self.interval_min.get(),self.interval_max.get()
            if a < 5 or b < a:
                raise ValueError('Диапазон интервала должен быть от 5 минут, максимум не меньше минимума.')
        except Exception as e:
            messagebox.showerror('Интервал',str(e))
            return
        self.running = True
        self.last_error = None
        self.detail.set('Мониторинг запущен. Подключаемся к браузеру...')
        if not self.busy:
            self.scan()
        self.update_status()

    def stop(self):
        self.running = False
        self.next_run = None
        self.detail.set('Мониторинг остановлен. Браузер остаётся открытым.')
        self.update_status()

    def scan(self):
        if self.busy:
            return
        self.busy = True
        self.detail.set('Подключение к браузеру и считывание страницы...')
        self.update_status()
        threading.Thread(target=self.scan_worker,daemon=True).start()

    def scan_worker(self):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222', timeout=12000)
                pages = [page for ctx in browser.contexts for page in ctx.pages if page.url.rstrip('/') == URL.rstrip('/')]
                if len(pages) != 1:
                    raise RuntimeError(f'Нужна ровно одна открытая вкладка {URL}. Найдено: {len(pages)}.')
                page = pages[0]
                page.reload(wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(1800)
                text = page.evaluate('document.body.innerText')
                result = parse_warriors(text)
                if len(result) < 2:
                    raise RuntimeError('Не удалось уверенно распознать участников. Данные НЕ сохранены. Нужен пример текста страницы для настройки парсера.')
                # Conservative: do not overwrite a full roster with an unexpectedly short page.
                with sqlite3.connect(DB) as c:
                    previous = c.execute('SELECT count FROM scans ORDER BY id DESC LIMIT 1').fetchone()
                    if previous and len(result) < previous[0] * 0.75:
                        raise RuntimeError('Список неожиданно сократился. Замер не сохранён во избежание ошибки.')
                    now = datetime.now().astimezone().isoformat(timespec='seconds')
                    scan_id = c.execute('INSERT INTO scans(time,count) VALUES (?,?)',(now,len(result))).lastrowid
                    c.executemany('INSERT INTO readings(scan_id,name,glory) VALUES (?,?,?)',[(scan_id,n,v) for n,v in result.items()])
                self.messages.put(('ok',len(result)))
                # Deliberately do not call browser.close(): leave user's browser running.
        except Exception as e:
            self.messages.put(('error',str(e)))

    def tick(self):
        try:
            while True:
                kind, val = self.messages.get_nowait()
                self.busy = False
                if kind == 'ok':
                    self.last_error = None
                    self.refresh_table()
                    self.detail.set(f'Успешно: {val} участников. История сохранена.')
                else:
                    self.last_error = val
                    self.detail.set('Ошибка: ' + val)
                if self.running:
                    minutes = random.randint(self.interval_min.get(), self.interval_max.get())
                    self.next_run = time.monotonic() + minutes * 60
        except queue.Empty:
            pass
        if self.running and self.next_run is not None and not self.busy:
            if self.next_run <= time.monotonic():
                self.next_run = None
                self.scan()
        self.update_status()
        self.root.after(500, self.tick)

    def on_close(self):
        self.running = False
        self.root.destroy()


if __name__ == '__main__':
    Tracker().root.mainloop()
