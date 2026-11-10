"""Custom profiles in state/profiles match a game by the files they list."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import re
import tomllib
import contextlib
import io
import json
from types import SimpleNamespace
from test_community import app


class CustomProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.profiles = base / "profiles"
        self.profiles.mkdir()
        (self.profiles / "Example Game 1.toml").write_text(
            '[pack]\ndefault_action = "loose"\n[[rule]]\naction = "compress"\n'
            'include = ["example1/content/paks/pakchunk0-ps5.pak"]\n')
        (self.profiles / "big_files.include.txt").write_text("Data/boot.forge\nData/main.forge\n")
        (self.profiles / "Example Game 2.toml").write_text(
            '[pack]\ndefault_action = "loose"\n[[rule]]\naction = "compress"\n'
            'include_from = ["big_files.include.txt"]\n')
        self.games = base / "games"

    def tearDown(self):
        self.tmp.cleanup()

    def game(self, name, files):
        root = self.games / name
        for f in files:
            (root / f).parent.mkdir(parents=True, exist_ok=True)
            (root / f).touch()
        return root

    def choose(self, root, name="Example"):
        with patch.object(app, "CUSTOM_PROFILES", self.profiles):
            return app.choose_profile("", name, root)

    def test_match_by_listed_files_any_letter_case(self):
        one = self.game("a", ["Example1/Content/Paks/pakchunk0-ps5.pak", "eboot.bin"])
        two = self.game("b", ["data/BOOT.forge", "data/main.forge", "eboot.bin"])
        self.assertEqual(Path(self.choose(one)[0]).name, "Example Game 1.toml")
        self.assertEqual(Path(self.choose(two)[0]).name, "Example Game 2.toml")

    def test_partial_files_do_not_match(self):
        half = self.game("c", ["Data/boot.forge", "eboot.bin"])
        self.assertIsNone(self.choose(half)[0])

    def test_name_match_when_files_differ(self):
        other = self.game("d", ["eboot.bin"])
        self.assertEqual(Path(self.choose(other, "Example Game 2 [PPSA00002]")[0]).name, "Example Game 2.toml")


class EditableProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.library = self.root / 'library'
        self.source = self.library / 'Game [PPSA26344]'
        self.source.mkdir(parents=True)
        (self.source / 'eboot.bin').write_bytes(b'fixture')
        (self.source / 'empty-language.bin').touch()
        self.entry = app.Entry.__new__(app.Entry)
        with patch.object(app, 'LIBRARY', self.library):
            app.Entry.__init__(self.entry, self.source, 'folder')
        self.stack = __import__('contextlib').ExitStack()
        self.addCleanup(self.stack.close)
        for key, value in {'CUSTOM_PROFILES': self.root/'profiles',
                           'WORK': self.root/'work'}.items():
            self.stack.enter_context(patch.object(app, key, value))
        self.stack.enter_context(patch.object(app, 'scan_library', return_value=[self.entry]))
        self.text = '[pack]\ndefault_action = "loose"\n[[rule]]\naction = "compress"\ninclude = ["*"]\n'

    def test_save_select_and_invalid_upload_preserves_previous(self):
        result = app.save_game_profile(self.entry.id, self.text)
        self.assertEqual(result['saved'], 'PPSA26344.toml')
        self.assertEqual(app.game_profile(self.entry.id)['content'], self.text)
        path, _ = app.choose_profile('PPSA26344', 'Game', self.source, self.entry.id)
        self.assertEqual(Path(path).read_text(), self.text)
        for invalid in ['[broken', 'rule = "bad"\n[pack]', '[pack]\n[[rule]]\ninclude_from=["/etc/passwd"]', 'x'*262145]:
            with self.assertRaises(ValueError):
                app.save_game_profile(self.entry.id, invalid)
            self.assertEqual(Path(path).read_text(), self.text)
        with self.assertRaises(ValueError):
            app.save_game_profile('../../escape', self.text)

    def test_zstd_uses_custom_profile_with_mandatory_fixes(self):
        app.save_game_profile(self.entry.id, self.text)
        for codec in ('zstd', 'lz4'):  # Forge packs both, with the chosen TOML as it is
            job = app.Job(self.entry, 5, True, False, codec, 'ng')
            job.work.mkdir(parents=True, exist_ok=True)
            with patch.object(app, 'ampr_status_folder', return_value=('compatible', 'fixture')):
                job.step_check(self.source)
            parsed = tomllib.loads(Path(job.state['profile_path']).read_text())
            self.assertEqual(parsed['pack']['default_action'], 'loose')
            self.assertEqual(parsed['rule'][0]['action'], 'compress')
            self.assertEqual(len(parsed['rule']), 1)  # nothing is added to the owner's TOML
            # User edits cannot alter the profile snapshot of an interrupted job.
            before = Path(job.state['profile_path']).read_text()
            app.save_game_profile(self.entry.id, '[pack]\ndefault_action="compress"')
            with patch.object(app, 'ampr_status_folder', return_value=('compatible', 'fixture')):
                job.step_check(self.source)
            self.assertEqual(Path(job.state['profile_path']).read_text(), before)
            app.save_game_profile(self.entry.id, self.text)

    def test_without_a_game_toml_forge_gets_no_profile(self):
        for codec in ('lz4', 'zstd'):
            job = app.Job(self.entry, 5, True, False, codec, 'ng', False)
            job.work.mkdir(parents=True, exist_ok=True)
            with patch.object(app, 'ampr_status_folder', return_value=('compatible', 'fixture')):
                job.step_check(self.source)
            self.assertIn("Forge's own packing rules", job.state['profile'])
            self.assertIsNone(job.state['profile_path'])
            self.assertNotIn('--pack-profile', app.forge_command(self.source, self.root/'o', codec, 5, profile=job.state['profile_path']))
            app.remove_work_path(job.work)

    def test_include_from_lists_are_written_into_the_job_profile(self):
        app.CUSTOM_PROFILES.mkdir()
        selected = app.CUSTOM_PROFILES/'legacy.toml'
        (app.CUSTOM_PROFILES/'files.txt').write_text('# comment\ndata/test.bin\n')
        selected.write_text('[pack]\ndefault_action="loose"\n[[rule]]\naction="compress"\ninclude_from=["files.txt"]')
        out = self.root/'snapshot.toml'
        app.ng_profile(self.source, str(selected), out)
        rules = tomllib.loads(out.read_text())['rule']
        self.assertEqual(rules, [{'action': 'compress', 'include': ['data/test.bin']}])
        self.assertIsNone(app.ng_profile(self.source, None, out))

    def test_ui_http_routes_load_and_save_game_profile(self):
        with patch.object(app, 'ensure_dirs'), patch.object(app, 'REQUESTS', self.root/'requests'), \
             patch('threading.Thread'), patch('http.server.ThreadingHTTPServer') as server, \
             contextlib.redirect_stdout(io.StringIO()):
            app.cmd_ui(SimpleNamespace(port=0))
        handler_type = server.call_args.args[1]
        handler = handler_type.__new__(handler_type)
        handler.send = __import__('unittest.mock', fromlist=['Mock']).Mock()
        handler.path = '/api/profile?id=' + __import__('urllib.parse', fromlist=['quote']).quote(self.entry.id)
        handler.do_GET()
        code, payload = handler.send.call_args.args
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(payload)['game'], self.entry.id)
        body = json.dumps({'action': 'profile_save', 'game': self.entry.id, 'content': self.text}).encode()
        handler.path = '/api/action'
        handler.headers = {'Content-Length': str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.do_POST()
        self.assertEqual(handler.send.call_args.args[0], 200)
        self.assertEqual(app.game_profile(self.entry.id)['content'], self.text)


if __name__ == "__main__":
    unittest.main()

