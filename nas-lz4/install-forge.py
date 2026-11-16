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

VERSION = '0.5.6'
REF = '2dc0a29071fd909e30b00bce34e2cfe28ac05767'
ASSETS = {
    'x86_64': ('x86-64', '7bc7d1bc323f6b803f923a563696be0e64a733ceac551fadbff3f18495dcb3ae'),
    'aarch64': ('arm64', 'c7ddfe308d23051ec15de465a34ce6c8f7def152d801b0f310ec6e68454f8d6d'),
}
NG_SHA = '9c7c41b3216bc4f877d67e3c2e5c9c8f9ffabdd5065f4f3fe0dd98fa7228386f'
SOURCE_SHA = '322f4c923439bf963ea02774d70a70e2e5cf276489253f8fbd9842e5f87058f3'


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
    download(raw + '/vendor/ampr-emu-ng/ampr-emu-ng-0.4.1-src.tar.gz', licenses / 'ampr-emu-ng-0.4.1-src.tar.gz', SOURCE_SHA)
    for source, name in [('LICENSE', 'LICENSE'), ('THIRD-PARTY-NOTICES.md', 'THIRD-PARTY-NOTICES.md'),
                         ('vendor/ampr-emu-ng/README.md', 'ampr-emu-ng.md')]:
        download(raw + '/' + source, licenses / name)
    (licenses / 'SOURCE.txt').write_text(f'PS5 Dump Forge v{VERSION}: https://github.com/quer3q/ps5-dump-forge/tree/v{VERSION}\nRuntime provenance: https://github.com/quer3q/ps5-dump-forge/tree/{REF}/vendor/ampr-emu-ng\n')


if __name__ == '__main__':
    install()
