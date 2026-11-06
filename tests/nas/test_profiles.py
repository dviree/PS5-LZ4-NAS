"""Custom profiles in state/profiles match a game by the files they list."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
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


if __name__ == "__main__":
    unittest.main()
