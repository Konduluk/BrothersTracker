import sqlite3
import tempfile
import unittest
from pathlib import Path
from ranking import calculate_ranking

class RankingTests(unittest.TestCase):
    def test_range_and_missing_members(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'test.sqlite3'
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE scans (id INTEGER PRIMARY KEY,time TEXT,count INTEGER)')
                c.execute('CREATE TABLE readings (scan_id INTEGER,name TEXT,glory INTEGER)')
                c.executemany('INSERT INTO scans VALUES (?,?,?)',[(1,'2026-12-01T12:00:00',2),(2,'2026-12-20T12:00:00',2),(3,'2027-01-01T12:00:00',2)])
                c.executemany('INSERT INTO readings VALUES (?,?,?)',[(1,'A',100),(1,'B',30),(2,'A',180),(2,'C',40),(3,'A',999)])
            rows,first,last=calculate_ranking(db,'2026-12-01','2026-12-31')
            self.assertEqual(rows[0],('A',100,180,80,'Сравнен'))
            self.assertEqual(rows[1][3],None)
            self.assertEqual(len(rows),3)
            self.assertIn('2026-12-20',last)
    def test_invalid_dates(self):
        with self.assertRaises(ValueError):
            calculate_ranking('unused','2026-12-31','2026-12-01')
