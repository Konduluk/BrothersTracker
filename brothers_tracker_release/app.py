import os
import queue
import random
import sqlite3
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox

from parser import parse_warriors

URL = 'http://87.228.3.220/brotherhood/warriors'
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'BrothersTracker'
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'history.sqlite3'

class Tracker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('Brothers Tracker · прототип')
        self.root.geometry('850x560')
        self.messages = queue.Queue()
        self.running = False
        self.busy = False
        self.next_run = None
        self.interval_min = tk.IntVar(value=28)
        self.interval_max = tk.IntVar(value=35)
        self.status = tk.StringVar(value='Ожидание подключения. Открой браузер мониторинга и войди в игру.')
        self.db_init()
        self.make_ui()
        self.root.after(400, self.tick)
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)

    def db_init(self):
        with sqlite3.connect(DB) as c:
            c.execute('CREATE TABLE IF NOT EXISTS scans (id INTEGER PRIMARY KEY, time TEXT NOT NULL, count INTEGER NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS readings (scan_id INTEGER, name TEXT, glory INTEGER, PRIMARY KEY(scan_id,name))')

    def make_ui(self):
        top = ttk.Frame(self.root, padding=12)
        top.pack(fill='x')
        ttk.Label(top, text='Brothers Tracker', font=('Segoe UI', 19, 'bold')).pack(anchor='w')
        ttk.Label(top, text='Подключение к одной заранее открытой вкладке Chrome/Edge (127.0.0.1:9222)').pack(anchor='w')
        controls = ttk.Frame(top)
        controls.pack(fill='x', pady=10)
        ttk.Button(controls, text='Считать сейчас', command=self.scan).pack(side='left', padx=3)
        ttk.Button(controls, text='Начать мониторинг', command=self.start).pack(side='left', padx=3)
        ttk.Button(controls, text='Остановить', command=self.stop).pack(side='left', padx=3)
        ttk.Label(controls, text='Интервал, мин:').pack(side='left', padx=(16, 4))
        ttk.Spinbox(controls, from_=5, to=1440, textvariable=self.interval_min, width=4).pack(side='left')
        ttk.Label(controls, text='—').pack(side='left')
        ttk.Spinbox(controls, from_=5, to=1440, textvariable=self.interval_max, width=4).pack(side='left')
        ttk.Label(top, textvariable=self.status, wraplength=800).pack(anchor='w')
        cols = ('name','glory','gain')
        self.tree = ttk.Treeview(self.root, columns=cols, show='headings')
        for col, title, width in [('name','Игрок',300),('glory','Последняя слава',180),('gain','Прирост с первого замера',220)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width)
        self.tree.pack(fill='both', expand=True, padx=12, pady=12)
        ttk.Label(self.root, text='Данные: '+str(DB), wraplength=800).pack(anchor='w', padx=12, pady=(0,8))
        self.refresh_table()

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
        for name,glory,gain in rows:
            self.tree.insert('', 'end', values=(name,f'{glory:,}'.replace(',',' '),f'{gain:+,}'.replace(',',' ')))

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
