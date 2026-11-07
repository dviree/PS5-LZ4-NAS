#!/usr/bin/env python3
"""Install the pinned Forge CLI and NG runtime during the container build.

Release archives are checksum-verified; extract only the CLI (not the GUI).
Keep licenses and the runtime's corresponding source alongside the binaries.
"""
import hashlib
import io
import platform
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request

VERSION = '0.5.4'
REF = '70b488489fd289f48d857067490a998eec7d3f9a'
ASSETS = {
    'x86_64': ('x86-64', 'd7799ed26ed448f13fd87d7c57823c22e9a08d27489c33b5f6a4342f70f4e6d0'),
    'aarch64': ('arm64', '2565365005beb7b57ecd1a58acc5824b31652e6bef1509c5def48d4c90ee82fd'),
}
NG_SHA = '9a8f553a68d4e6e6be11bd9f8d5519b5faa68560761881966abff1dd65bf19f7'
SOURCE_SHA = 'e511cb1f3ff8079510c98f40fa0e8c1ceb282f038e6419514c44fad4e3355769'


def download(url, target, digest=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'PS5-LZ4-NAS-build'})
    with urllib.request.urlopen(req, timeout=120) as response, target.open('wb') as output:
        shutil.copyfileobj(response, output)
    if digest and hashlib.file_digest(target.open('rb'), 'sha256').hexdigest() != digest:
        target.unlink()
        raise RuntimeError(f'checksum mismatch: {target.name}')


def install(bin_dir=Path('/usr/local/bin'), data_dir=Path('/opt/ps5lz4')):
    arch, sha = ASSETS[platform.machine()]
    bin_dir.mkdir(parents=True, exist_ok=True)
    licenses = data_dir / 'licenses' / 'ps5-dump-forge'
    licenses.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / 'forge.tar.gz'
        download(f'https://github.com/quer3q/ps5-dump-forge/releases/download/v{VERSION}/ps5-dump-forge-{VERSION}-linux-{arch}.tar.gz', archive, sha)
        with tarfile.open(archive) as tar:
            matches = [m for m in tar.getmembers() if m.isfile() and Path(m.name).name == 'ps5-dump-forge']
            if len(matches) != 1:
                raise RuntimeError('release must contain exactly one Forge CLI')
            target = bin_dir / 'ps5-dump-forge'
            with tar.extractfile(matches[0]) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o755)
    raw = f'https://raw.githubusercontent.com/quer3q/ps5-dump-forge/{REF}'
    download(raw + '/vendor/ampr-emu-ng/libSceAmpr.sprx', data_dir / 'libSceAmpr-ng.sprx', NG_SHA)
    download(raw + '/vendor/ampr-emu-ng/ampr-emu-ng-0.3.2-src.tar.gz', licenses / 'ampr-emu-ng-0.3.2-src.tar.gz', SOURCE_SHA)
    for source, name in [('LICENSE', 'LICENSE'), ('THIRD-PARTY-NOTICES.md', 'THIRD-PARTY-NOTICES.md'),
                         ('vendor/ampr-emu-ng/README.md', 'ampr-emu-ng.md')]:
        download(raw + '/' + source, licenses / name)
    (licenses / 'SOURCE.txt').write_text(f'PS5 Dump Forge v{VERSION}: https://github.com/quer3q/ps5-dump-forge/tree/v{VERSION}\nRuntime provenance: https://github.com/quer3q/ps5-dump-forge/tree/{REF}/vendor/ampr-emu-ng\n')


if __name__ == '__main__':
    install()
