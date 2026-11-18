import os
import queue
import random
import sqlite3
import threading
import time
import tkinter as tk
from datetime import datetime, date
from pathlib import Path
from tkinter import ttk, messagebox

from parser import parse_warriors
from ranking import calculate_ranking

URL = 'http://87.228.3.220/brotherhood/warriors'
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BrothersTracker'
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'history.sqlite3'


class Tracker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Brothers Tracker · v0.3')
        self.root.geometry('1100x740')
        self.root.minsize(920, 610)
        self.messages = queue.Queue()
        self.running = False
        self.busy = False
        self.next_run = None
        self.interval_min = tk.IntVar(value=28)
        self.interval_max = tk.IntVar(value=35)
        self.status = tk.StringVar(value='Ожидание подключения. Открой браузер мониторинга и войди в игру.')
        self.db_init()
        self.range_start = tk.StringVar(value=date.today().replace(day=1).isoformat())
        self.range_end = tk.StringVar(value=date.today().isoformat())
        self.contest_name = tk.StringVar(value='Декабрьский конкурс')
        self.make_ui()
        self.root.after(400, self.tick)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def db_init(self):
        with sqlite3.connect(DB) as c:
            c.execute('CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY, time TEXT NOT NULL, count INTEGER NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS readings (scan_id INTEGER, name TEXT, glory INTEGER, PRIMARY KEY(scan_id,name))')
            c.execute('CREATE TABLE IF NOT EXISTS contests (id INTEGER PRIMARY KEY, name TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL)')

    def setup_theme(self):
        self.bg = '#101318'
        self.panel = '#1A2029'
        self.panel_alt = '#26303C'
        self.gold = '#D9B66E'
        self.text = '#F4F2ED'
        self.muted = '#ADB4C0'
        self.root.configure(bg=self.bg)
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background=self.bg, foreground=self.text)
        style.configure('TFrame', background=self.bg)
        style.configure('Panel.TFrame', background=self.panel)
        style.configure('TLabel', background=self.bg, foreground=self.text)
        style.configure('Muted.TLabel', background=self.bg, foreground=self.muted)
        style.configure('Panel.TLabel', background=self.panel, foreground=self.text)
        style.configure('PanelMuted.TLabel', background=self.panel, foreground=self.muted)
        style.configure('Title.TLabel', font=('Segoe UI', 23, 'bold'), foreground=self.gold)
        style.configure('Section.TLabel', font=('Segoe UI', 13, 'bold'))
        style.configure('Value.TLabel', background=self.panel, foreground=self.gold, font=('Segoe UI', 23, 'bold'))
        style.configure('TButton', background=self.panel_alt, foreground=self.text, padding=(14, 9), borderwidth=0)
        style.map('TButton', background=[('active', '#374353'), ('pressed', '#465366')], foreground=[('disabled', self.muted)])
        style.configure('Gold.TButton', background=self.gold, foreground='#171A20', font=('Segoe UI', 10, 'bold'))
        style.map('Gold.TButton', background=[('active', '#EAC986'), ('pressed', '#C19A50')])
        style.configure('TEntry', fieldbackground=self.panel_alt, foreground=self.text, insertcolor=self.gold,
                        bordercolor='#455263', padding=7)
        style.configure('TSpinbox', fieldbackground=self.panel_alt, foreground=self.text, arrowcolor=self.gold,
                        bordercolor='#455263', padding=4)
        style.configure('TNotebook', background=self.bg, borderwidth=0, tabmargins=(0, 8, 0, 0))
        style.configure('TNotebook.Tab', background=self.panel, foreground=self.muted,
                        padding=(23, 12), borderwidth=0, font=('Segoe UI', 10, 'bold'))
        style.map('TNotebook.Tab', background=[('selected', self.panel_alt), ('active', '#303B49')],
                  foreground=[('selected', self.gold), ('active', self.text)])
        style.configure('Treeview', background=self.panel, fieldbackground=self.panel, foreground=self.text,
                        rowheight=34, borderwidth=0)
        style.map('Treeview', background=[('selected', '#6F5630')], foreground=[('selected', '#FFFFFF')])
        style.configure('Treeview.Heading', background=self.panel_alt, foreground=self.gold,
                        font=('Segoe UI', 10, 'bold'), padding=(10, 10), relief='flat')
        style.map('Treeview.Heading', background=[('active', '#364457')])

    def make_ui(self):
        self.setup_theme()
        outer = ttk.Frame(self.root, padding=(20, 14))
        outer.pack(fill='both', expand=True)
        brand = ttk.Frame(outer)
        brand.pack(fill='x', pady=(0, 10))
        ttk.Label(brand, text='BROTHERS  /  TRACKER', style='Title.TLabel').pack(side='left')
        ttk.Label(brand, text='𝕭𝖗𝖔𝖙𝖍𝖊𝖗𝖘    •    v0.3  DARK GOLD', style='Muted.TLabel').pack(side='right', pady=13)

        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill='both', expand=True)
        monitor = ttk.Frame(self.tabs, padding=(0, 14))
        rating = ttk.Frame(self.tabs, padding=(0, 14))
        contests = ttk.Frame(self.tabs, padding=(0, 14))
        self.tabs.add(monitor, text='  МОНИТОРИНГ  ')
        self.tabs.add(rating, text='  РЕЙТИНГ СЛАВЫ  ')
        self.tabs.add(contests, text='  КОНКУРСЫ  ')

        stats = ttk.Frame(monitor)
        stats.pack(fill='x', pady=(0, 16))
        self.stat_members = tk.StringVar(value='—')
        self.stat_glory = tk.StringVar(value='—')
        self.stat_scans = tk.StringVar(value='—')
        for col, (caption, variable) in enumerate((
            ('УЧАСТНИКОВ', self.stat_members),
            ('ОБЩАЯ СЛАВА', self.stat_glory),
            ('СОХРАНЕНО ЗАМЕРОВ', self.stat_scans),
        )):
            stats.columnconfigure(col, weight=1, uniform='stats')
            tile = ttk.Frame(stats, style='Panel.TFrame', padding=17)
            tile.grid(row=0, column=col, sticky='ew', padx=(0, 9) if col < 2 else 0)
            ttk.Label(tile, text=caption, style='PanelMuted.TLabel').pack(anchor='w')
            ttk.Label(tile, textvariable=variable, style='Value.TLabel').pack(anchor='w', pady=(7, 0))

        controls = ttk.Frame(monitor)
        controls.pack(fill='x', pady=(0, 10))
        ttk.Button(controls, text='Считать сейчас', style='Gold.TButton', command=self.scan).pack(side='left', padx=(0, 8))
        ttk.Button(controls, text='Начать мониторинг', command=self.start).pack(side='left', padx=(0, 8))
        ttk.Button(controls, text='Остановить', command=self.stop).pack(side='left')
        ttk.Label(controls, text='Интервал, мин:', style='Muted.TLabel').pack(side='left', padx=(16, 5))
        ttk.Spinbox(controls, from_=5, to=1440, textvariable=self.interval_min, width=5).pack(side='left')
        ttk.Label(controls, text=' — ').pack(side='left')
        ttk.Spinbox(controls, from_=5, to=1440, textvariable=self.interval_max, width=5).pack(side='left')
        ttk.Label(monitor, textvariable=self.status, style='Muted.TLabel', wraplength=1040).pack(anchor='w', pady=(0, 14))
        ttk.Label(monitor, text='СЛАВА БРАТСТВА', style='Section.TLabel').pack(anchor='w', pady=(0, 7))
        cols = ('name', 'glory', 'gain')
        self.tree = ttk.Treeview(monitor, columns=cols, show='headings')
        for col, title, width in [('name', 'Игрок', 350), ('glory', 'Последняя слава', 250),
                                  ('gain', 'Прирост с первого замера', 320)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width)
        self.tree.pack(fill='both', expand=True)
        ttk.Label(monitor, text='История: ' + str(DB), style='Muted.TLabel', wraplength=1030).pack(anchor='w', pady=(9, 0))
        self.make_rating_ui(rating)
        self.make_contest_ui(contests)
        self.refresh_table()

    def make_rating_ui(self, parent):
        ttk.Label(parent, text='РЕЙТИНГ СЛАВЫ', style='Section.TLabel').pack(anchor='w', pady=(0, 13))
        header = ttk.Frame(parent)
        header.pack(fill='x', pady=(0, 12))
        ttk.Label(header, text='С даты:', style='Muted.TLabel').pack(side='left')
        ttk.Entry(header, textvariable=self.range_start, width=14).pack(side='left', padx=(7, 18))
        ttk.Label(header, text='По дату:', style='Muted.TLabel').pack(side='left')
        ttk.Entry(header, textvariable=self.range_end, width=14).pack(side='left', padx=(7, 18))
        ttk.Button(header, text='Рассчитать рейтинг', style='Gold.TButton', command=self.show_ranking).pack(side='left')
        self.rating_info = tk.StringVar(value='Рейтинг рассчитывается по первому и последнему сохранённым замерам в выбранном периоде.')
        ttk.Label(parent, textvariable=self.rating_info, style='Muted.TLabel', wraplength=1030).pack(anchor='w', pady=(0, 13))
        cols = ('name', 'before', 'after', 'gain', 'note')
        self.rating_tree = ttk.Treeview(parent, columns=cols, show='headings')
        for key, title, width in [('name', 'Игрок', 210), ('before', 'Слава в начале', 165),
                                  ('after', 'Слава в конце', 165), ('gain', 'Прирост', 160), ('note', 'Статус', 220)]:
            self.rating_tree.heading(key, text=title)
            self.rating_tree.column(key, width=width)
        self.rating_tree.pack(fill='both', expand=True)
        ttk.Label(parent, text='Если игрока нет в одном из крайних замеров, прирост не вычисляется.',
                  style='Muted.TLabel').pack(anchor='w', pady=(10, 0))

    def show_ranking(self):
        try:
            rows, first_time, last_time = calculate_ranking(DB,self.range_start.get().strip(),self.range_end.get().strip())
        except (ValueError,sqlite3.Error) as exc:
            messagebox.showerror('Рейтинг',str(exc))
            return
        for item in self.rating_tree.get_children():
            self.rating_tree.delete(item)
        for name, before, after, gain, note in rows:
            fmt=lambda n: '—' if n is None else f'{n:,}'.replace(',',' ')
            self.rating_tree.insert('', 'end',values=(name,fmt(before),fmt(after),'—' if gain is None else f'{gain:+,}'.replace(',',' '),note))
        self.rating_info.set(f'Замеры: {first_time} → {last_time}. Участников в отчёте: {len(rows)}.' if first_time else 'За выбранные даты замеров пока нет. История собирается только после запуска мониторинга.')

    def make_contest_ui(self, parent):
        ttk.Label(parent, text='КОНКУРСЫ БРАТСТВА', style='Section.TLabel').pack(anchor='w', pady=(0, 13))
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=(0, 15))
        ttk.Label(frame, text='Название конкурса:', style='Muted.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Entry(frame, textvariable=self.contest_name, width=38).grid(row=0, column=1, padx=10, pady=6, sticky='w')
        ttk.Label(frame, text='Начало и конец берутся из вкладки «Рейтинг славы».',
                  style='Muted.TLabel').grid(row=1, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Button(frame, text='Сохранить конкурс', style='Gold.TButton', command=self.save_contest).grid(
            row=2, column=0, sticky='w', pady=(2, 0))
        ttk.Button(frame, text='Открыть выбранный конкурс в рейтинге', command=self.open_contest).grid(
            row=2, column=1, sticky='w', padx=10, pady=(2, 0))
        self.contest_tree = ttk.Treeview(parent, columns=('name', 'start', 'end'), show='headings', height=12)
        for key, title in [('name', 'Конкурс'), ('start', 'Начало'), ('end', 'Окончание')]:
            self.contest_tree.heading(key, text=title)
        self.contest_tree.pack(fill='both', expand=True)
        ttk.Label(parent, text='Сейчас сохраняются периоды конкурсов. Призы и итоговые места добавим отдельно.',
                  style='Muted.TLabel', wraplength=1000).pack(anchor='w', pady=(10, 0))
        self.refresh_contests()

    def refresh_contests(self):
        for item in self.contest_tree.get_children(): self.contest_tree.delete(item)
        with sqlite3.connect(DB) as c:
            for ident,name,start,end in c.execute('SELECT id,name,start_date,end_date FROM contests ORDER BY id DESC'):
                self.contest_tree.insert('','end',iid=str(ident),values=(name,start,end))

    def save_contest(self):
        try:
            name=self.contest_name.get().strip()
            if not name: raise ValueError('Укажи название конкурса.')
            start=date.fromisoformat(self.range_start.get().strip())
            end=date.fromisoformat(self.range_end.get().strip())
            if end < start: raise ValueError('Дата окончания раньше даты начала.')
            with sqlite3.connect(DB) as c:
                c.execute('INSERT INTO contests(name,start_date,end_date) VALUES (?,?,?)',(name,start.isoformat(),end.isoformat()))
            self.refresh_contests()
            messagebox.showinfo('Конкурсы','Конкурс сохранён.')
        except (ValueError,sqlite3.Error) as exc:
            messagebox.showerror('Конкурсы',str(exc))

    def open_contest(self):
        selection=self.contest_tree.selection()
        if not selection:
            messagebox.showinfo('Конкурсы','Сначала выбери конкурс в таблице.')
            return
        name,start,end=self.contest_tree.item(selection[0],'values')
        self.range_start.set(start)
        self.range_end.set(end)
        self.show_ranking()
        self.tabs.select(1)

    def start(self):
        try:
            a,b = self.interval_min.get(), self.interval_max.get()
            if a < 5 or b < a:
                raise ValueError('Диапазон интервала должен быть от 5 минут, максимум не меньше минимума.')
        except Exception as e:
            messagebox.showerror('Интервал', str(e)); return
        self.running = True
        self.status.set('Мониторинг включён. Проверяем вкладку...')
        self.scan()

    def stop(self):
        self.running = False
        self.next_run = None
        self.status.set('Мониторинг остановлен. Браузер не закрыт.')

    def scan(self):
        if self.busy:
            return
        self.busy = True
        self.status.set('Подключение и чтение страницы...')
        threading.Thread(target=self.scan_worker, daemon=True).start()

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

    def refresh_table(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        with sqlite3.connect(DB) as c:
            rows = c.execute('''SELECT r.name,r.glory,r.glory-(SELECT r2.glory FROM readings r2 JOIN scans s2 ON s2.id=r2.scan_id WHERE r2.name=r.name ORDER BY s2.id LIMIT 1) AS gain FROM readings r WHERE r.scan_id=(SELECT MAX(id) FROM scans) ORDER BY gain DESC, r.name''').fetchall()
            scan_count = c.execute('SELECT COUNT(*) FROM scans').fetchone()[0]
        for name,glory,gain in rows:
            self.tree.insert('', 'end', values=(name,f'{glory:,}'.replace(',',' '),f'{gain:+,}'.replace(',',' ')))
        self.stat_members.set(str(len(rows)))
        self.stat_glory.set(f'{sum(glory for _, glory, _ in rows):,}'.replace(',', ' '))
        self.stat_scans.set(f'{scan_count:,}'.replace(',', ' '))

    def tick(self):
        try:
            while True:
                kind, val = self.messages.get_nowait()
                self.busy = False
                if kind == 'ok':
                    self.refresh_table()
                    self.status.set(f'Успешно: {val} участников. Замер сохранён в {datetime.now():%H:%M:%S}.')
                else:
                    self.status.set('Ошибка: '+val)
                if self.running:
                    minutes = random.randint(self.interval_min.get(),self.interval_max.get())
                    self.next_run = time.monotonic()+minutes*60
        except queue.Empty:
            pass
        if self.running and self.next_run is not None and not self.busy:
            remaining = self.next_run-time.monotonic()
            if remaining <= 0:
                self.next_run = None
                self.scan()
            else:
                self.root.title(f'Brothers Tracker · следующая проверка через {int(remaining//60)}:{int(remaining%60):02d}')
        self.root.after(500,self.tick)

    def on_close(self):
        self.running = False
        self.root.destroy()

if __name__ == '__main__':
    Tracker().root.mainloop()
