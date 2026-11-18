import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from stats import rolling_gains, custom_range

class StatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name)/'history.sqlite3'
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('CREATE TABLE scans(id INTEGER PRIMARY KEY, time TEXT, count INTEGER)')
            c.execute('CREATE TABLE readings(scan_id INTEGER,name TEXT,glory INTEGER)')
            scans=[(1,'2026-11-01T10:00:00',2),(2,'2026-11-11T10:00:00',2),
                   (3,'2026-11-17T10:00:00',3),(4,'2026-11-18T10:00:00',3)]
            c.executemany('INSERT INTO scans VALUES(?,?,?)',scans)
            c.executemany('INSERT INTO readings VALUES(?,?,?)',[
                (1,'A',100),(1,'B',200), (2,'A',130),(2,'B',201),
                (3,'A',150),(3,'B',220),(3,'C',10),
                (4,'A',160),(4,'B',225),(4,'C',15)])
            c.commit()

    def test_rolling_does_not_invent_month(self):
        rows, stamp, members, count=rolling_gains(self.db)
        self.assertEqual((members,count),(3,4))
        self.assertEqual(rows['A'],(160,10,30,None))
        self.assertEqual(rows['C'],(15,5,None,None))

    def test_range_totals_only_comparable_members(self):
        rows, first, last, total=custom_range(self.db,'2026-11-01','2026-11-18')
        self.assertEqual(total,(300,385,85,2))
        self.assertEqual(rows['C'],(None,15,None))

    def test_invalid_and_empty(self):
        with self.assertRaises(ValueError): custom_range(self.db,'2026-11-20','2026-11-18')
        rows, first, last, total=custom_range(self.db,'2026-12-01','2026-12-31')
        self.assertEqual(rows,{})
        self.assertIsNone(total)

    def test_negative_is_not_normal_gain(self):
        with closing(sqlite3.connect(self.db)) as c:
            c.execute('UPDATE readings SET glory=50 WHERE scan_id=4 AND name="A"')
            c.commit()
        rows,_,_,_=rolling_gains(self.db)
        self.assertIsNone(rows['A'][1])
        r,_,_,total=custom_range(self.db,'2026-11-01','2026-11-18')
        self.assertIsNone(r['A'][2])
        self.assertEqual(total,(200,225,25,1))
