"""theghostonline's packer (ampr_pack_cli), which packs every LZ4 copy, keeps
the disk and boot files loose whatever the profile says."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_community import app

PACKER = os.environ.get("PS5LZ4_PACKER", app.PACKER)


@unittest.skipUnless(Path(PACKER).is_file(), "needs ampr_pack_cli (make -f tests/host/Makefile)")
class PackerTests(unittest.TestCase):
    def test_packer_keeps_boot_files_loose(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, pack = Path(tmp) / "src", Path(tmp) / "pack"
            data = b"compressible data " * 60000
            files = {"eboot.bin": b"\x7fELF libSceAmpr.sprx", "sce_sys/param.json": b'{"titleId":"PPSA01234"}',
                     "data/empty-language.bin": b"", "cache_ps5/playgo.pgm": data, "data/x.rmdtoc": data,
                     "sce_module/libfoo.prx": data, "data/big.bin": data}
            for rel, body in files.items():
                (src / rel).parent.mkdir(parents=True, exist_ok=True)
                (src / rel).write_bytes(body)
            profile = Path(tmp) / "all.toml"
            profile.write_text('[pack]\ndefault_action = "compress"\n')
            subprocess.run([PACKER, "pack", str(src), str(pack), "--level", "9", "--workers", "2", "--embedded-runtime",
                            "--install-runtime-if-missing", "--verify-loose", "--profile", str(profile)],
                           check=True, capture_output=True)
            for rel in files:
                if rel == "data/big.bin":
                    self.assertFalse((pack / rel).exists(), rel)
                else:
                    self.assertEqual((pack / rel).read_bytes(), files[rel], rel)


if __name__ == "__main__":
    unittest.main()
