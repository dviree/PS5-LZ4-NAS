# Snapshot: how the code is laid out (2026-11-07)

Read this before scanning the repo. Find symbols with Trail (`trail ask/grep/
callers/skeleton`); line numbers below drift, names don't.

## Pieces

| Folder | What | Language |
|---|---|---|
| `nas-lz4/` | **The NAS app** (Docker): packing agent + web page. Main work happens here. | Python, HTML/JS |
| `src/` | theghostonline's LZ4 Compression engine (PS5 payload) and the packer `ampr_pack*.c` | C |
| `tests/host/` | builds `ampr_pack_cli` (the LZ4 packer the NAS uses) from `src/` | Make |
| `nas/` | NAS build of the engine (Linux) | C |
| `app/`, `assets/` | the original's PS5 app UI | JSX/JS |
| `pkg-receiver/` | Glass theme + extras for pkg-receiver (PS5 package installer payload) | C, JS, Py |
| `profiles/` | bundled TOML pack profiles (`nas-ng.toml` = NG/Zstd safety rules) | TOML |
| `tools/` | `quer3q_update.py` (follow quer3q/James), compat/asset generators | Python |
| `tests/nas/` | NAS tests (`python3 -m unittest discover -s tests/nas`, `node tests/nas/*.cjs`) | Py, JS |
| `.github/workflows/` | `build-image.yml` (NAS image on `nas-build`), `release.yml` (engine ELF), `sync-upstream.yml` (theghostonline, review-gated), `quer3q-update.yml`, `pkg-receiver.yml` | YAML |

## NAS app (`nas-lz4/`)

- `ps5lz4.py` (~8 300 lines, one file): CLI (`main`/`job_opts`), packing
  agent (`cmd_agent`, request files in `state/requests`), web server
  (`cmd_ui` → class `H`, port 5921) and catalog server (port 9898).
- `ui.html`: the whole page (vanilla JS; not indexed by Trail). Tabs: My games
  (sub-tabs Folder/exFAT · LZ4 · Zstd), Activity, PS5 games, PKG installer,
  PS4 games, ShadowMount, Saves, PS5 Upload, Community, Remote, FTP.
- `Dockerfile`: stage `ng-runtime` builds ampr-emu-ng (quer3q main + James's
  kernel-AIO patch from `patches/`), `build` builds `ampr_pack_cli`, `forge`
  installs PS5 Dump Forge (`install-forge.py`, pinned + SHA-256), final image
  adds `lz4`, `zstd`, `unrar`, MkPFS.
- `install.sh` (first install, writes compose), `lz4-ps5.sh` (`update`,
  `update --force`, wrapper for CLI commands in the container).

### Packing pipeline (class `Job`)

`step_source` (folder as is; `.exfat/.ffpfs/.ffpfsc` unpacked to a work folder)
→ `step_check` (AMPR check, profile via `choose_profile`) → `step_pack` →
`step_verify` → `step_restore` (full unpack + byte compare, games ≤ 25 GB) →
`step_publish` (boot files, permissions, report in `state/reports/<id>.json`).

- **LZ4** (APR-EMU or LZ4 NG): always `ampr_pack_cli` (theghostonline's packer,
  keeps boot/disk files loose itself). LZ4 NG: `install_ng_runtime` after verify.
- **Zstd**: PS5 Dump Forge (`forge_command`), profile = game TOML + `nas-ng.toml`
  merged by `ng_profile`; output in the Zstd output folder (`zstd_output`).
- Always from the original; never from an LZ4 copy.
- Queue: `state/queue.json`; `cmd_start` → background `run --from-queue`.

### Key helpers

- Paths: `output_roots/output_items/output_item/output_for`, `host_output_path`.
- Pack format: `is_packed`, `packed_codec`, `lz4_format_problem`,
  `runtime_sha/requires_ng/runtime_ok` (report counts only for the copy it
  describes), `update_runtime_index`.
- Library: `scan_library` → `Entry` (`kind` folder/exfat/ffpfs/ffpfsc),
  `classify`, `result_for`, `CheckDB` cache (`state/ps5lz4.db`).
- Profiles: `choose_profile` (page choice → game-hash/TitleID custom → TOML
  next to the game → matching custom → bundled → scan), `game_tomls`,
  `profile_options`, `set_profile_choice`, `upload_profile`, `save_game_profile`.
- Estimates: `estimate_game` (`/api/estimate`), `pack_speeds`.
- Page data: `dashboard_data` (`/api/dashboard`: `games` rows for originals,
  `copies` one per packed folder, `pkgs`, …), `game_detail`.
- PS5 side: FTP (`ps5_ftp_*`), pkg-receiver (`receiver_*`, port 12800),
  ShadowMountPlus via receiver (`smp`, `launch_check`), packages
  (`scan_pkgs`, `pkg_install*`, `ps5_installed`, `pkg_on_ps5`).
- Community: theghostonline.dev issues (`compat_*`, `report_url`).

### State on the NAS (`/volume2/docker/ps5-lz4/state`)

`queue.json`, `reports/`, `requests/`, `profiles/` (custom TOMLs + lists),
`profile-choice.json`, `verify/`, `transfers/`, `settings.json`, `ps5lz4.db`.

## Upstreams and pins

- theghostonline/PS5-LZ4-Compression (Forgejo): engine + packer in `src/`;
  `sync-upstream.yml` → `upstream-raw`/`upstream-sync`, review-gated.
- quer3q/ampr-emu-ng main (pin `NG_COMMIT` in Dockerfile) + kernel-AIO patch
  (from James's `fix/lz4-packed-open-boot` `fe97dce`).
- quer3q/ps5-dump-forge releases (pin in `install-forge.py`).
- `tools/quer3q_update.py` moves pins (checks patch/SHA256SUMS), reports James's
  branches (`tools/james-branches.json`).
