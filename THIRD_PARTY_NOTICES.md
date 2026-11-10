# Third-party notices and credits

ps5lz4zstd builds on the projects below, each under its own terms.

- **[PS5 Dump Forge](https://github.com/quer3q/ps5-dump-forge)** and
  **[ampr-emu-ng](https://github.com/quer3q/ampr-emu-ng)** by quer3q
  (GPL-3.0-or-later), with fixes by James St-Pierre: the packer and the runtime.
  ampr-emu-ng is a hard fork of [ampr_emu](https://github.com/drakmor/ampr_emu)
  by Drakmor.
- **[pkg-sender](https://github.com/Loopayeh/pkg-sender)** (MIT): pkg-receiver,
  built here with the Glass theme in `pkg-receiver/`.
- **[PSBrew/MkPFS](https://github.com/PSBrew/MkPFS)**: reads exFAT and PFS images.
- **unrar** (RARLAB, freeware), **lz4** and **zstd** command-line tools in the image.
- **[ShadowMountPlus](https://github.com/drakmor/ShadowMountPlus)** by Drakmor is
  what mounts the games on the PS5.

This repository began as a fork of theghostonline's PS5-LZ4-Compression
(GPL-3.0-or-later). Its engine, PS5 app, LZ4 packer, APR-EMU runtime and bundled
profiles were removed on 2026-11-10; the NAS app here remains under the GNU GPL
v3 or later (`LICENSE`).

## PS5 Dump Forge and ampr-emu-ng (NAS packing)

The NAS image includes the unmodified PS5 Dump Forge 0.5.3 CLI (GPL-3.0-or-later):
https://github.com/quer3q/ps5-dump-forge/tree/v0.5.3

Zstd and the optional LZ4 NG mode install the unmodified ampr-emu-ng 0.3.0 release
runtime (GPL-3.0-or-later), SHA-256
`5f39ca8ebe169aa15d8a8ba8ec2f9cd4195f509d55daaf4b4edbfa80b145035c`:
https://github.com/quer3q/ampr-emu-ng/tree/v0.3.0

`nas-lz4/install-forge.py` pins the release archive hashes and runtime provenance.
The image includes Forge's license and dependency notices, NG's attribution, and
NG's corresponding source archive under `/opt/ps5lz4/licenses/ps5-dump-forge`.
Existing APR-EMU attribution above continues to apply to the legacy mode.

### James St-Pierre runtime fixes

NG packing and repair use ampr-emu-ng commit
`cbdafd8d87f6e904524142dca210f1d1334bf505` (v0.3.4, with James St-Pierre's
low-descriptor, packed-fd slot, synthetic fd range and event ring fixes merged, and kernel AIO on packed files) from https://github.com/quer3q/ampr-emu-ng
(GPL-3.0-or-later). The build checks out exactly that commit; a source archive made
from it and the upstream LICENSE are included in the image under
`/opt/ps5lz4/licenses/ampr-emu-ng-cbdafd8/`.
The binary is built from this source, not downloaded as an unpinned branch asset.

Kernel AIO on packed files is part of that upstream commit; no patch is applied.
