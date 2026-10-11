# Changelog

## 1.3.0 - 2026-10-11

First release of LZ4 Compression. Release notes:
[RELEASE_NOTES_1.3.0.md](RELEASE_NOTES_1.3.0.md).

### LZ4 asset packs

- `Compress with LZ4`, `Verify LZ4 Packs` and `Uncompress LZ4`, all on the
  PS5. Packs use drakmor's AMPRPAK4 / AMPRDAT3 format (the packer is a C port
  of his `ampr_pack.py`): AMPR index, automatic scan-based profile with safety
  exclusions and auto-loose sampling, LZ4 or LZ4 HC compression on all cores,
  byte-for-byte verification against the originals, loose-file copy and the
  pinned APR-EMU 0.4.2.1 PackedStdio runtime in `fakelib`.
- LZ4 is the main action for every game that imports `libSceAmpr`, including
  games that ship no APR-EMU: packing adds the runtime to `fakelib`. The
  import check is cached in `/data/LZ4Compression/ampr-imports.txt`.
- Compression level 1 to 12 like Lazy_AMPR (1 to 4 LZ4 fast mode, 5 to 12
  LZ4 HC, default 9).
- Custom and trace-generated `ampr_pack` TOML profiles per title: upload
  them with their `include_from` lists, or `Import config` from a USB drive
  or `/data/LZ4Compression/import` (matched to the game by name like
  Lazy_AMPR). The automatic profile learns loose patterns from every profile.
- `.exfat` and `.ffpfs` images that ShadowMountPlus mounts only while playing
  are mounted for the job and released afterwards.
- `Pack in place`, which verifies the packs and then removes only the
  originals now stored in them, with a full rollback on failure.
- LZ4 output next to the game, to internal SSD or to external storage, keep or
  delete after verified, and in-place or new-folder uncompress.
- `Build AMPR Index`, APR-EMU version changes and original restores are
  blocked for LZ4 packed games, and compress or Make Image keep their
  `ampr_emu.index` untouched, since the packs are tied to it.

### The app

- Native PS5 app `PPSA99420` built with PS5 React: left-to-right library,
  a page per game with its options as grouped cards, full-page screens for
  every action, D-pad and stick navigation with controller vibration, and a
  done screen when a job finishes. It starts the engine through Payload
  Manager when needed.
- Engine `lz4-compression.elf`, web page on port `5920`, settings, caches and
  logs in `/data/LZ4Compression`. The web page has the same black UI.
- Black `LZ4` block tile icon and home-screen art, plus a matching in-app logo
  and favicon.

### Also included

- `.ffpfsc` compress and uncompress, exFAT/PFS images, validate and repair,
  APR-EMU index building and version switching, copy and move, and job
  history, on firmware 13.60 with ShadowMountPlus 1.7.

### Tooling

- Host build of the packer (`tests/host`), a PS5 self-test payload
  (`tests/ps5`) and a web UI test harness (`tests/ui`).
