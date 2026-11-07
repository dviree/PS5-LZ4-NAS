"""Choosing a game's TOML: next to the game, in state/profiles, none, upload."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_community import app


class ProfileChoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.profiles, self.games = base / "profiles", base / "games"
        self.profiles.mkdir()
        self.game = self.games / "Example Game 1"
        (self.game / "sce_sys").mkdir(parents=True)
        (self.game / "data.bin").touch()
        (self.game / "game.toml").write_text('[pack]\n[[rule]]\naction = "compress"\ninclude = ["data.bin"]\n')
        img_dir = self.games / "Example Game 2"
        img_dir.mkdir()
        self.image = img_dir / "Example Game 2.exfat"
        self.image.touch()
        (img_dir / "Example Game 2.toml").write_text("[pack]\n")
        self.entry = type("E", (), {"id": "g1", "path": self.game, "title_id": "", "name": "Example Game 1"})()
        self.patches = [patch.object(app, "CUSTOM_PROFILES", self.profiles),
                        patch.object(app, "PROFILE_CHOICE", base / "choice.json"),
                        patch.object(app, "profile_entry", lambda gid: self.entry),
                        patch.object(app, "load_bundled_profiles", lambda: [])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_toml_next_to_folder_and_image_is_found_and_used(self):
        self.assertEqual([f.name for f in app.game_tomls(self.game)], ["game.toml"])
        self.assertEqual([f.name for f in app.game_tomls(self.image)], ["Example Game 2.toml"])
        path, why = app.choose_profile("", "Example Game 1", self.game, "g1", self.game)
        self.assertEqual(Path(path).name, "game.toml")
        self.assertIn("next to the game", why)

    def test_choice_none_and_nas_profile(self):
        app.set_profile_choice("g1", {"kind": "none"})
        self.assertIsNone(app.choose_profile("", "x", self.game, "g1", self.game)[0])
        (self.profiles / "Other.toml").write_text("[pack]\n")
        app.set_profile_choice("g1", {"kind": "nas", "name": "Other.toml"})
        self.assertEqual(Path(app.choose_profile("", "x", self.game, "g1", self.game)[0]).name, "Other.toml")
        app.set_profile_choice("g1", {"kind": "auto"})
        self.assertEqual(Path(app.choose_profile("", "x", self.game, "g1", self.game)[0]).name, "game.toml")
        with self.assertRaises(ValueError):
            app.set_profile_choice("g1", {"kind": "nas", "name": "../../etc/passwd"})

    def test_edited_text_may_use_include_from_lists(self):
        text = '[pack]\n[[rule]]\naction = "compress"\ninclude_from = ["big.include.txt"]\n'
        with patch.object(app, "editable_profile_path", lambda e: self.profiles / "G.toml"):
            with self.assertRaises(ValueError):  # the list is nowhere yet
                app.save_game_profile("g1", text)
            (self.game / "big.include.txt").write_text("data.bin\n")  # next to the game's own game.toml
            app.save_game_profile("g1", text)
            self.assertEqual((self.profiles / "big.include.txt").read_text(), "data.bin\n")
            with self.assertRaises(ValueError):
                app.save_game_profile("g1", text.replace("big.include.txt", "../x.txt"))

    def test_upload_needs_its_lists_and_saves_them(self):
        toml = {"name": "Up.toml", "content": '[pack]\n[[rule]]\naction = "compress"\ninclude_from = ["big.include.txt"]\n'}
        with self.assertRaises(ValueError):
            app.upload_profile("g1", [toml])
        app.upload_profile("g1", [{"name": "../x.toml", "content": "[pack]\n"}])  # the path is dropped
        self.assertTrue((self.profiles / "x.toml").is_file())
        self.assertFalse((self.profiles.parent / "x.toml").exists())
        with self.assertRaises(ValueError):
            app.upload_profile("g1", [{"name": "x.sh", "content": "echo"}])
        res = app.upload_profile("g1", [toml, {"name": "big.include.txt", "content": "data.bin\n"}])
        self.assertEqual(res["in_use"], "Up.toml")
        self.assertTrue((self.profiles / "big.include.txt").is_file())
        self.assertEqual(res["choice"], {"kind": "nas", "path": None, "name": "Up.toml"})


if __name__ == "__main__":
    unittest.main()
