"""Read-only snapshot comparisons. No estimated gains or invented zeroes."""
from contextlib import closing
from datetime import date, datetime, timedelta
import sqlite3


def snapshot(conn, scan_id):
    return dict(conn.execute('SELECT name,glory FROM readings WHERE scan_id=?', (scan_id,)))


def latest_scans(conn):
    return conn.execute('SELECT id,time FROM scans ORDER BY time DESC,id DESC').fetchall()


def rolling_gains(db_path):
    """For 24h, 7d, 30d: compare latest scan with last scan on/before cutoff.

    Require a snapshot within 90 minutes before the cutoff; never present partial periods as full periods.
    """
    with closing(sqlite3.connect(db_path)) as conn:
        scans = latest_scans(conn)
        if not scans:
            return {}, None, None, 0
        last_id, last_time = scans[0]
        current = snapshot(conn, last_id)
        latest_dt = datetime.fromisoformat(last_time)
        periods = {}
        for tag, delta in [('day', timedelta(days=1)), ('week', timedelta(days=7)), ('month', timedelta(days=30))]:
            cutoff = latest_dt - delta
            candidate = next((ident for ident, stamp in scans
                              if cutoff - timedelta(minutes=90) <= datetime.fromisoformat(stamp) <= cutoff), None)
            periods[tag] = snapshot(conn, candidate) if candidate is not None else None
        gains = {}
        for name, glory in current.items():
            vals = []
            for tag in ('day', 'week', 'month'):
                baseline = periods[tag]
                if baseline is None or name not in baseline:
                    vals.append(None)
                elif glory < baseline[name]:
                    vals.append(None)  # unexpected decrease: treat as unreadable, not negative progress
                else:
                    vals.append(glory - baseline[name])
            gains[name] = (glory, *vals)
        return gains, last_time, len(current), len(scans)


def custom_range(db_path, start_iso, end_iso):
    start, end = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    if end < start:
        raise ValueError('Дата окончания раньше даты начала.')
    with closing(sqlite3.connect(db_path)) as conn:
        scans = conn.execute('SELECT id,time FROM scans WHERE substr(time,1,10) BETWEEN ? AND ? ORDER BY time,id',
                             (start.isoformat(), end.isoformat())).fetchall()
        if not scans:
            return {}, None, None, None
        first_id, first_time = scans[0]
        last_id, last_time = scans[-1]
        first = snapshot(conn, first_id)
        last = snapshot(conn, last_id)
        result = {}
        for name in set(first) | set(last):
            before, after = first.get(name), last.get(name)
            valid = before is not None and after is not None and after >= before
            result[name] = (before, after, after - before if valid else None)
        matched = [row for row in result.values() if row[2] is not None]
        totals = (sum(row[0] for row in matched), sum(row[1] for row in matched), sum(row[2] for row in matched), len(matched)) if matched else None
        return result, first_time, last_time, totals
