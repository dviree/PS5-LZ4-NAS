"""A game's LZ4 and Zstd copies are judged on their own: its report describes the last pack only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_community import app


class CopyRuntimeTests(unittest.TestCase):
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
