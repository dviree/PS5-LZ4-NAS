# Backlog

Bugs found, stubs, ideas and work that spans sessions. Update it when a task
ends (see `CLAUDE.md`). No real game names (Title IDs only), no personal data.

## >RESUME HERE

Nothing half-done. Last finished (2026-11-07): Compress all follows the
**Compress with** format; the TOML editor saves profiles with `include_from`
lists; memory files (CLAUDE.md, BACKLOG.md, SNAPSHOT.md) replace HANDOFF.md.
Next: ask the owner which open item comes first.

## Needs the owner

- Enable *Allow GitHub Actions to create and approve pull requests* (Settings ›
  Actions › General); until then the quer3q/James follower pushes a branch only.
- Test on the NAS/PS5 (the session can't reach the NAS): Compress dialog and
  estimates, TOML chooser, sub-tabs, LZ4 NG with theghostonline's packer +
  ampr-emu-ng `b6a54d1`, Start check (ShadowMountPlus fields `runtime_path`,
  `fakelib_mode` are taken from exFAT2AMPR's code, unverified).
- Old git tags still point to history before the personal-data rewrite (owner
  has the retag commands).
- PR #2 (Trail-Code + Claude Code in Codespaces) is open, not merged.

## Known issues

- A game's report (`state/reports/<id>.json`) describes only its last pack; the
  page now uses `copies` per folder and `requires_ng` checks the report's
  `output`, but other report readers (e.g. community report level) still see
  the last pack only.
- `cmd_remove` prints `HOST_OUTPUT` even for a Zstd copy in the Zstd folder.
- GitHub runs scheduled workflows rarely for this repo (~every 6 h).
- `trail note` can't save learnings: `.trail/` needs `trail init` (blocked as
  self-modification in an earlier session).
- `--learn` in the LZ4 pack writes learned profiles into `PROFILES`.

## Ideas

- Compress dialog: a real Zstd estimate per level (now zstd -5 only).
- Copies tab: show the exFAT image of a copy and its transfer state on the PS5.
- `.ffpfsc` sources: owner to decide whether only folder/exFAT may be packed.

## Done recently (newest first)

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
