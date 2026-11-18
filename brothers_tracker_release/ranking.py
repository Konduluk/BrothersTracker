"""Date-range leaderboards based only on stored, observed snapshots."""
import sqlite3
from datetime import date


def calculate_ranking(db_path, start_date, end_date):
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if end < start:
        raise ValueError('Дата окончания раньше даты начала.')
    with sqlite3.connect(db_path) as conn:
        scans = conn.execute('SELECT id, time FROM scans WHERE substr(time,1,10) BETWEEN ? AND ? ORDER BY time,id', (start.isoformat(),end.isoformat())).fetchall()
        if not scans:
            return [], None, None
        first_id, first_time = scans[0]
        last_id, last_time = scans[-1]
        first = dict(conn.execute('SELECT name,glory FROM readings WHERE scan_id=?',(first_id,)).fetchall())
        last = dict(conn.execute('SELECT name,glory FROM readings WHERE scan_id=?',(last_id,)).fetchall())
        result=[]
        for name, glory in last.items():
            if name in first:
                result.append((name,first[name],glory,glory-first[name],'Сравнен'))
            else:
                result.append((name,None,glory,None,'Нет в первом замере'))
        for name, glory in first.items():
            if name not in last:
                result.append((name,glory,None,None,'Нет в последнем замере'))
        result.sort(key=lambda r: (r[3] is None, -(r[3] or 0),r[0].casefold()))
        return result, first_time, last_time
