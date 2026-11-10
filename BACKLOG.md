# Backlog

Bugs found, stubs, ideas and work that spans sessions. Update it when a task
ends (see `CLAUDE.md`). No real game names (Title IDs only), no personal data.

## >RESUME HERE

IN PROGRESS (owner, 2026-11-10): remove theghostonline's code. Step 1 done:
Forge packs LZ4 NG, APR-EMU mode gone from page/CLI. Step 2 open: delete `src/`,
`app/`, `assets/`, `nas/`, `tests/host`, `third_party/ampr_emu`, `compat/`,
`release.yml`, `sync-upstream.yml`, the `build` Docker stage and every `PACKER`/
APR-EMU use in ps5lz4.py (verify-lz4, apr disk-files, doctor, app_install);
decide with the owner what existing APR-EMU copies may still do.

Also waiting on the owner: the PPSA26344 folder went missing. The code can't
remove an original (only `delete-original` with `DELETE_ORIGINALS=yes`); the
owner is to run the log commands from chat (logs, `state/requests`, Recent
actions; PS5: ShadowMount *Hide* renames to `.name`). Last finished
(2026-11-07): Compress all and Repair buttons removed from the page (CLI
`lz4 --fix` / `apr --fix` stay); quer3q/James pins up to date.

## Needs the owner

- Enable *Allow GitHub Actions to create and approve pull requests* (Settings ›
  Actions › General); until then the quer3q/James follower pushes a branch only.
- Test on the NAS/PS5 (the session can't reach the NAS): Compress dialog and
  estimates, TOML chooser, sub-tabs, LZ4 NG with theghostonline's packer +
  ampr-emu-ng `cbdafd8`, Start check (ShadowMountPlus fields `runtime_path`,
  `fakelib_mode` are taken from exFAT2AMPR's code, unverified); LZ4 NG/Zstd games
  on ampr-emu-ng v0.3.4 (upstream kernel AIO, save-load hang fix, 192 MiB pool:
  check save loading and memory-tight games).
- quer3q reports: the fetch (GitHub REST, no token) and the pre-filled issue form
  are built from the form's file and fixtures; the session's proxy blocks the
  API, so check on the NAS that counts appear and the link fills the form.
- Old git tags still point to history before the personal-data rewrite (owner
  has the retag commands).
- PR #2 (Trail-Code + Claude Code in Codespaces) is open, not merged.

## Known issues

- A game's report (`state/reports/<id>.json`) describes only its last pack; the
  page now uses `copies` per folder and `requires_ng` checks the report's
  `output`, but other report readers (e.g. community report level) still see
  the last pack only.
- With Repair gone from the page, a wrong APR-EMU is fixed by repacking or
  `./lz4-ps5.sh apr --fix`.
- GitHub runs scheduled workflows rarely for this repo (~every 6 h).
- `trail note` can't save learnings: `.trail/` needs `trail init` (blocked as
  self-modification in an earlier session).
- `src/lzc_api.c` (upstream) names a real game in a comment (`.ffpfsc` example);
  owner to decide whether to patch upstream's text.

## Ideas

- Compress dialog: a real Zstd estimate per level (now zstd -5 only).
- Copies tab: show the exFAT image of a copy and its transfer state on the PS5.
- `.ffpfsc` sources: owner to decide whether only folder/exFAT may be packed.

## Done recently (newest first)

- LZ4 NG is packed by Forge (`--to lz4 --lz4-runtime ng`), with the mandatory
  loose-file rules like Zstd; APR-EMU LZ4 can no longer be chosen or queued.
- Game reports tab: quer3q's reports as a compatibility list (search, filters,
  in-your-library mark); list-style reports (a table of Title IDs) count per row.
- quer3q's game reports (issues labelled `test report` on quer3q/ampr-emu-ng):
  counts per Title ID for Zstd/LZ4 in the game sheet, and a filled-in report
  link after setting the PS5 result of a Zstd or LZ4 NG copy.
- theghostonline community reports off: no tab, counts, share link or fetching
  (`PS5LZ4_COMMUNITY=yes` turns the backend on again; the page parts are gone).
  The PS5 result is still saved on the NAS. The `.ffpfsc` sheet stays.
- Forge → v0.5.5 (`8a3c7d3`: .ini files never packed, bundles ampr-emu-ng
  v0.3.4, naming template); round trips pass with the real binary.
- Removing a copy keeps the report (and PS5 result) of the other format's copy.
- Follower no longer crashes when a Forge tag has no release files yet. (`--learn`
  only reads the bundled profiles; the old known issue was wrong.)
- ampr-emu-ng → `cbdafd8` (v0.3.4). Delete packed copy names and sends the exact
  folder; `cmd_remove` prints the right folder; `state/actions.log` keeps every
  page action (the page still shows the last 20).
- TOML switch off no longer drops theghostonline's bundled game/engine profiles
  (e.g. Insomniac layout) for LZ4 or Zstd.
- ampr-emu-ng → `e18a703` (v0.3.3, quer3q's own kernel AIO); our AIO patch removed.
- Removed Compress all (header) and Repair (after Check all) from the page.
- Compress all in the chosen format (`run_request` passes codec/runtime/level/
  profile to `lz4 --fix`; Zstd/LZ4 NG queue every AMPR original without that copy).
- TOML editor: `include_from` lists allowed (from state/profiles or copied from
  next to the TOML in use).
- Owner: legacy packed-folder cache refresh; copies classified by actual format.
- My games sub-tabs Folder/exFAT · LZ4 · Zstd; `requires_ng` per copy.
- LZ4 always with theghostonline's packer (LZ4 NG too); Forge = Zstd only.
- PR #6 (LZ4 → Zstd conversion) reverted: packs always from originals.
- ampr-emu-ng `b6a54d1` (James PRs #23/#24), AIO patch ported; Forge v0.5.4.
- Follow quer3q and James workflow; Compress dialog with estimates; TOML chooser.
