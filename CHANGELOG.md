# Changelog

## 1.3.0 - 2026-10-11

First release of LZ4 Compression. Release notes:
[RELEASE_NOTES_1.3.0.md](RELEASE_NOTES_1.3.0.md).

### LZ4 asset packs for APR-EMU games

- `Compress with LZ4`, `Verify LZ4 Packs` and `Uncompress LZ4`, all on the
  PS5. Packs use drakmor's AMPRPAK4 / AMPRDAT3 format (the packer is a C port
  of his `ampr_pack.py`): AMPR index, automatic scan-based profile with safety
  exclusions and auto-loose sampling, LZ4 or LZ4 HC compression on all cores,
  byte-for-byte verification against the originals, loose-file copy and the
  pinned APR-EMU 0.4.2.1 PackedStdio runtime in `fakelib`.
- Custom and trace-generated `ampr_pack` TOML profiles per title, with
  `include_from` list uploads, and loose patterns learned from every uploaded
  profile.
- `Pack in place`, which verifies the packs and then removes only the
  originals now stored in them, with a full rollback on failure.
- LZ4 output next to the game, to internal SSD or to external storage, keep or
  delete after verified, and in-place or new-folder uncompress.
- `Build AMPR Index`, APR-EMU version changes and original restores are
  blocked for LZ4 packed games, and compress or Make Image keep their
  `ampr_emu.index` untouched, since the packs are tied to it.

### The app

- Payload `lz4-compression.elf`, home-screen tile `PSLZ40001`, web UI on port
  `5920`, settings, caches and logs in `/data/LZ4Compression`.
- Black web UI: a left-to-right game library with a preview of the
  highlighted game and recent activity, a page per game with its options as
  grouped cards, and full-page screens for every action.
- Black `LZ4` block tile icon and home-screen art, plus a matching in-app logo
  and favicon.
- Launch splash, a done screen when a job finishes, and a closing screen.
- Arrow-key navigation along the library; browser back or Escape closes pages
  and returns to the library.
- Library tiles use 256 px icon thumbnails.

### Also included

- `.ffpfsc` compress and uncompress, exFAT/PFS images, validate and repair,
  APR-EMU index building and version switching, copy and move, and job
  history, on firmware 13.60 with ShadowMountPlus 1.7.

### Tooling

- Host build of the packer (`tests/host`), a PS5 self-test payload
  (`tests/ps5`) and a web UI test harness (`tests/ui`).
