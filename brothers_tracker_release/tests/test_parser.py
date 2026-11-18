import unittest
from parser import parse_warriors
class ParserTests(unittest.TestCase):
    def test_simple(self):
        text='КаК_ТаК?\nУровень: 50\nСлава: 13 108\nМозгоклюечка\nУровень: 40\nСлава: 3 030'
        self.assertEqual(parse_warriors(text),{'КаК_ТаК?':13108,'Мозгоклюечка':3030})
if __name__ == '__main__': unittest.main()
