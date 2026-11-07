# Handoff (2026-11-07)

Notes for the next session working on this repository. The rules in
`CLAUDE.md` still apply (Trail-Code only for finding code, privacy).

## What this is

`nas-lz4/` is a NAS (Docker) web app that packs PS5 games with LZ4 or Zstd
(AMPR packs), sends them to the PS5 and manages packages. Two containers:
`ps5-lz4` (packing agent) and `ps5-lz4-ui` (web page, port 5921). Install
folder on the NAS: `/volume2/docker/ps5-lz4`; library `/volume1/games/roms/ps5`;
packages also from `/volume1/games/backport-updates-dlc`.

Update on the NAS (after the image build on `nas-build` is green):

```sh
cd /volume2/docker/ps5-lz4 && ./lz4-ps5.sh update --force
```

## Standing rules from the owner

- Chat in Swedish; product, UI, repo and docs text in English. Short answers.
- Push to `nas-build`, then `main`. No force-push without permission.
- No real game names in the repo (Title IDs only), no personal data, no
  model IDs in commits.
- Never delete or overwrite original games; deletes only with
  `DELETE_ORIGINALS=yes`. Keep temporary data after a failed run.
- Don't change other Docker containers or NAS settings.
- Tell "verified on the NAS" apart from "playable on the PS5".
- Packs are always made from the original: folder/exFAT → LZ4 or folder/exFAT
  → Zstd, never LZ4 → Zstd.
- Third-party code (theghostonline, quer3q, James St-Pierre) only after review
  and the owner's OK. Don't route around proxy 403s.
- Use Trail-Code (`trail ask/grep/callers/skeleton/blast/check`); end replies
  that used it with "🌱 trail saved ~N tokens this turn". Trail doesn't index
  `ui.html`, Dockerfile, YAML or Markdown: say so, read only that file.

## Recent work (newest first)

- PR #6 (LZ4 folder → Zstd conversion) was reverted at the owner's request:
  packs are always made from the original.
- **Follow quer3q and James** workflow (`.github/workflows/quer3q-update.yml`,
  `tools/quer3q_update.py`): every 3 h moves the pins for quer3q/ampr-emu-ng
  `main` and quer3q/ps5-dump-forge releases (AIO patch must apply with no fuzz,
  Forge assets must match upstream SHA256SUMS), adds Trail blast radius, runs
  tests and the image build, and proposes a branch/PR. James St-Pierre's
  branches are reported only; seen heads in `tools/james-branches.json`.
- **Compress dialog** (My games): LZ4 vs Zstd side by side with sizes from
  `/api/estimate` (sampled, each 256 KiB piece compressed alone with the `lz4`
  and `zstd` tools, added to the image), pack time from earlier reports,
  runtime choice (APR-EMU / ampr-emu-ng), Remember for every game.
- **TOML chooser**: per game Automatic / No TOML / a `.toml` next to the game /
  one in `state/profiles` (match badge) / upload with `.include.txt` lists;
  choice in `state/profile-choice.json`.
- **Compress with** switch (LZ4 · Zstd · LZ4 NG) in My games; the Zstd tab is gone.
- Pins: ampr-emu-ng `b6a54d1` (v0.3.2 + James's PRs #23/#24) + James's kernel-AIO patch
  (`nas-lz4/patches/ampr-emu-ng-kernel-aio.patch`, from `fe97dce`); PS5 Dump
  Forge v0.5.4.
- Earlier: PKG installer and PS4 games tabs (Install all skips what is on the
  PS5), Start check, custom profiles, report buttons, sync with theghostonline
  (`sync-upstream.yml`, review-gated).

## Open items

- **Actions can't open pull requests**: the owner must enable *Allow GitHub
  Actions to create and approve pull requests* (Settings › Actions › General).
  Until then the follower pushes a branch only (the owner opened PR #5 from
  the first one, `quer3q-7a0afd26e6`, and merged it).
- James's `fix/no-inline-cache-completion` and `fix/debug-event-ring-race` are in
  quer3q's main now (PRs #23, #24) and in our runtime from `b6a54d1`; the
  kernel-AIO patch was ported to that base (only a doc comment's context moved).
- **Compress all** still packs LZ4 only (`UI_ACTIONS["fix"]` takes no format).
- TOML editor can't save a profile that uses `include_from`; uploads can.
- Not tested on the owner's NAS or PS5: the Compress dialog, estimates, TOML
  chooser, NG/Zstd runtime b3373e7, Start check field names from
  ShadowMountPlus (`runtime_path`, `fakelib_mode`).
- Old tags still point to the history before the personal-data rewrite; the
  owner has the retag commands.
- `trail note` can't save learnings until `trail init` runs (blocked earlier as
  self-modification); `.trail/` doesn't exist.

## How to check things

```sh
python3 -m unittest discover -s tests/nas          # NAS tests (5 skip without Forge)
for t in tests/nas/*.cjs; do node "$t"; done          # page tests
python3 tools/quer3q_update.py                        # anything new upstream?
```

Forge tests need `FORGE_TEST_BINARY=<ps5-dump-forge>`, `PS5LZ4_NG_RUNTIME`,
`PS5LZ4_NG_MANIFEST` and `PS5LZ4_FREE_MARGIN_GB=0`. A local page:
`PS5LZ4_LIBRARY=… PS5LZ4_OUTPUT=… PS5LZ4_STATE=… python3 nas-lz4/ps5lz4.py ui --port 5931`
(restart it after editing `ui.html`; it is read at start).
