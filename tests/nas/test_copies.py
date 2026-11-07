"""A game's LZ4 and Zstd copies are judged on their own: its report describes the last pack only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_community import app


class CopyRuntimeTests(unittest.TestCase):
    def test_refreshes_legacy_folder_cache_without_pack_codec(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch.object(app, "DB_PATH", base / "checks.db"), \
                    patch.object(app, "CHECKS_PATH", base / "checks.json"), \
                    patch.object(app, "OUTPUT", base), patch.object(app, "HOST_OUTPUT", str(base)):
                for codec, index_name, magic in (("lz4", "ampr_assets.index", b"AMPRPAK4"),
                                                 ("zstd", "ampr_zstd.index", b"AMPRZPK1")):
                    with self.subTest(codec=codec):
                        out = base / f"G-{codec}"
                        out.mkdir()
                        index = out / index_name
                        index.write_bytes(magic)
                        key = "out:" + str(out)
                        sig = f"{int(out.stat().st_mtime)}:{int(index.stat().st_mtime)}"
                        cache = app.CheckDB()
                        cache[key] = {"sig": sig, "info": {"path": str(out), "files": 1,
                                                           "bytes": len(magic), "paks": 0,
                                                           "problem": "no .pak volumes"}}
                        cache.close()

                        cache = app.CheckDB()
                        info = app.lz4_folder_info(out, cache)
                        cache.close()
                        self.assertEqual(info["pack_codec"], codec)

                        cache = app.CheckDB()
                        with patch.object(app, "tree_bytes", side_effect=AssertionError("cache miss")):
                            self.assertEqual(app.lz4_folder_info(out, cache), info)
                        cache.close()

    def test_requires_ng_reads_only_this_copys_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out, zout, reports = base / "out", base / "zout", base / "reports"
            for d in (out / "G-lz4" / "fakelib", zout / "G-zstd" / "fakelib", reports):
                d.mkdir(parents=True)
            (out / "G-lz4" / "ampr_assets.index").write_bytes(b"AMPRPAK4")
            (zout / "G-zstd" / "ampr_zstd.index").write_bytes(b"AMPRZPK1")
            for c in (out / "G-lz4", zout / "G-zstd"):
                (c / "fakelib" / "libSceAmpr.sprx").write_bytes(b"runtime")
            with patch.object(app, "OUTPUT", out), patch.object(app, "ZSTD_OUTPUT", zout), \
                    patch.object(app, "REPORTS", reports), patch.object(app, "HOST_OUTPUT", str(out)):
                # the last pack was the Zstd copy (ampr-emu-ng)
                (reports / "G.json").write_text(json.dumps({"pack_codec": "zstd", "pack_runtime": "ng",
                                                            "output": app.host_output_path(zout / "G-zstd")}))
                self.assertTrue(app.requires_ng(zout / "G-zstd"))
                self.assertFalse(app.requires_ng(out / "G-lz4"))  # APR-EMU stays valid for the LZ4 copy
                (reports / "G.json").write_text(json.dumps({"pack_runtime": "ng", "output": app.host_output_path(out / "G-lz4")}))
                self.assertTrue(app.requires_ng(out / "G-lz4"))


if __name__ == "__main__":
    unittest.main()
