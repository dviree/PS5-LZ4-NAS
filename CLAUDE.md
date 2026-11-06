# Notes for Claude Code

## Mandatory Trail-Code workflow

Always use [Trail-Code](https://github.com/trailhq/Trail-Code) as the primary codebase
navigation and context system.

At the start of every session, check `command -v trail`. If it is missing, install it with
`npm install -g @trailhq/trail-code` (cloud sessions: it belongs in the environment's setup
script), then run `trail build` if `graft/` is missing.

Use Trail-Code only for finding code: `trail ask`, `trail grep`, `trail callers`,
`trail skeleton` and `trail map`, never grep, rg, find or reading whole files to search.
Read only the line ranges Trail points to (to edit them), and test with the repo's own
tools.

Before implementing changes:
- Consult Trail's code map (`trail ask`, `trail map`, `trail skeleton`, `trail grep`) and the
  relevant learnings in `.trail/`.
- Identify affected functions, callers and dependencies (`trail callers <symbol> -d N`).
- Check existing architectural decisions (learnings marked Decided / Tried and ruled out).

After modifying code:
- Review the impact radius (`trail blast --base origin/main`).
- Run `trail check` when applicable.
- Preserve and update relevant project learnings (`trail note --title "<about>"`).

Keep Trail's "[trail] tokens saved" lines in the output (don't filter them away) and end
every reply that used Trail with "🌱 trail saved ~N tokens this turn", N summed from them.

If Trail-Code is unavailable, report that explicitly. Do not claim Trail checks were
performed unless they actually ran.

Privacy: run Trail with `DO_NOT_TRACK=1`, and never with the look-back over past sessions
(`TRAIL_NO_LOOK_BACK=1`): they hold personal data that must not reach the repo. A learning
never names a real game (Title IDs only), a person, a user name or a LAN address.
