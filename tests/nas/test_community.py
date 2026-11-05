"""Regression checks: python -m unittest discover -s tests/nas -v."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ps5lz4', Path(__file__).resolve().parents[2] / 'nas-lz4/ps5lz4.py')
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)


def report(status='Works', markdown=True, tid='PPSA01234', number=1, date='2026-11-01'):
    rows = [('Title ID', tid), ('Game', 'Test game'), ('How does it run?', status),
            ('Game version', ''), ('Firmware', '13.60')]
    return dict(number=number, title='[Game report] Test game', user={'login': 'tester'},
                created_at=date, body='\r\n\r\n'.join(('### ' if markdown else '') + k + '\r\n\r\n' + v for k, v in rows))


class CommunityTests(unittest.TestCase):
    def test_plain_and_markdown(self):
        for markdown in (True, False):
            g = app.compat_aggregate([report(markdown=markdown)])['games']['PPSA01234']
            self.assertEqual(g['works'], 1)
            self.assertEqual(g['lastReport']['gameVersion'], '')
            self.assertEqual(g['lastReport']['firmware'], '13.60')

    def test_negative_and_mixed_results(self):
        for text, expected in [('Not work', 'noStart'), ('not working', 'noStart'),
                               ("Doesn't work", 'noStart'), ('Works with issues', 'issues'),
                               ('Works well most of the time, but the game crashes', 'crash')]:
            with self.subTest(text=text):
                self.assertEqual(app.compat_status(text), expected)

    def test_long_description_keeps_crash(self):
        text = 'Works most of the time. ' + 'Additional details. ' * 10 + 'But crashes in game.'
        self.assertEqual(app.compat_aggregate([report(text)])['games']['PPSA01234']['crash'], 1)

    def test_latest_vote_and_invalid_id(self):
        games = app.compat_aggregate([report(), report('Crashes in game', number=2, date='2026-11-02'),
                                      report(tid='PPSA1234')])['games']
        self.assertEqual(list(games), ['PPSA01234'])
        self.assertEqual(games['PPSA01234']['reports'], 1)
        self.assertEqual(games['PPSA01234']['crash'], 1)

    def test_outage_preserves_newer_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live = {'updated': '2026-11-05', 'source': 'live', 'games': {'PPSA01234': {'reports': 1}}}
            bundled = {'updated': '2026-10-01', 'games': {}}
            app.write_json(root / 'live.json', live)
            app.write_json(root / 'bundled.json', bundled)
            with patch.object(app, 'COMPAT_LIVE', root / 'live.json'), patch.object(app, 'COMPAT_FILE', root / 'bundled.json'), \
                 patch.object(app, 'COMPAT_BUNDLED', root / 'bundled.json'), \
                 patch.object(app, 'compat_refresh_issues', side_effect=OSError('Offline')), \
                 patch('urllib.request.urlopen', side_effect=OSError('Offline')):
                data = app.compat_refresh()
                self.assertEqual(data['games'], live['games'])
                self.assertEqual(data['refresh_error'], 'Offline')
                self.assertEqual(app.compat_data(), data)


if __name__ == '__main__':
    unittest.main()
