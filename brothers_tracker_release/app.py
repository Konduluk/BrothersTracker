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
        self.root.title('Brothers Tracker · v0.2')
        self.root.geometry('980x640')
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

    def make_ui(self):
        tabs = ttk.Notebook(self.root)
        tabs.pack(fill='both', expand=True)
        monitor = ttk.Frame(tabs)
        rating = ttk.Frame(tabs)
        contests = ttk.Frame(tabs)
        tabs.add(monitor, text='Мониторинг')
        tabs.add(rating, text='Рейтинг славы')
        tabs.add(contests, text='Конкурсы')
        top = ttk.Frame(monitor, padding=12)
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
        self.tree = ttk.Treeview(monitor, columns=cols, show='headings')
        for col, title, width in [('name','Игрок',300),('glory','Последняя слава',180),('gain','Прирост с первого замера',220)]:
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width)
        self.tree.pack(fill='both', expand=True, padx=12, pady=12)
        ttk.Label(monitor, text='Данные: '+str(DB), wraplength=800).pack(anchor='w', padx=12, pady=(0,8))
        self.make_rating_ui(rating)
        self.make_contest_ui(contests)
        self.refresh_table()

    def make_rating_ui(self, parent):
        header = ttk.Frame(parent, padding=12)
        header.pack(fill='x')
        ttk.Label(header, text='С даты (ГГГГ-ММ-ДД):').pack(side='left')
        ttk.Entry(header, textvariable=self.range_start, width=13).pack(side='left', padx=5)
        ttk.Label(header, text='По дату:').pack(side='left')
        ttk.Entry(header, textvariable=self.range_end, width=13).pack(side='left', padx=5)
        ttk.Button(header, text='Рассчитать', command=self.show_ranking).pack(side='left', padx=8)
        self.rating_info = tk.StringVar(value='Рейтинг рассчитывается по первому и последнему сохранённым замерам в выбранных датах.')
        ttk.Label(parent, textvariable=self.rating_info, wraplength=930).pack(anchor='w', padx=12, pady=4)
        cols = ('name','before','after','gain','note')
        self.rating_tree = ttk.Treeview(parent, columns=cols, show='headings')
        for key, title, width in [('name','Игрок',190),('before','Слава в начале',155),('after','Слава в конце',155),('gain','Прирост',150),('note','Статус',210)]:
            self.rating_tree.heading(key,text=title)
            self.rating_tree.column(key,width=width)
        self.rating_tree.pack(fill='both',expand=True,padx=12,pady=8)
        ttk.Label(parent, text='Если игрока нет в одном из крайних замеров, прирост не вычисляется. Промежуточные вступления не считаются нулевой славой.',wraplength=920).pack(anchor='w',padx=12,pady=6)

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

    def make_contest_ui(self,parent):
        frame=ttk.Frame(parent,padding=14)
        frame.pack(fill='x')
        ttk.Label(frame,text='Название конкурса:').grid(row=0,column=0,sticky='w')
        ttk.Entry(frame,textvariable=self.contest_name,width=34).grid(row=0,column=1,padx=8,pady=5)
        ttk.Label(frame,text='Начало и конец берутся из вкладки «Рейтинг славы».').grid(row=1,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Button(frame,text='Сохранить конкурс',command=self.save_contest).grid(row=2,column=0,pady=8,sticky='w')
        ttk.Button(frame,text='Открыть выбранный конкурс в рейтинге',command=self.open_contest).grid(row=2,column=1,pady=8,sticky='w')
        self.contest_tree=ttk.Treeview(parent,columns=('name','start','end'),show='headings',height=12)
        for key,title in [('name','Конкурс'),('start','Начало'),('end','Окончание')]:
            self.contest_tree.heading(key,text=title)
        self.contest_tree.pack(fill='both',expand=True,padx=14,pady=8)
        ttk.Label(parent,text='Пока вкладка хранит периоды конкурсов. Призы и итоговые места добавим после проверки рейтинга.',wraplength=920).pack(anchor='w',padx=14,pady=8)
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
        messagebox.showinfo('Конкурсы',f'Рейтинг «{name}» рассчитан. Открой вкладку «Рейтинг славы».')

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
