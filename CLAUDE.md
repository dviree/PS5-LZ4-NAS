# Notes for Claude Code

## Mandatory Trail-Code workflow

Always use [Trail-Code](https://github.com/trailhq/Trail-Code) as the primary codebase
navigation and context system.

At the start of every session, check `command -v trail`. If it is missing, install it with
`npm install -g @trailhq/trail-code` (cloud sessions: it belongs in the environment's setup
script), then run `trail build` if `graft/` is missing.

Before implementing changes:
- Consult Trail's code map (`trail ask`, `trail map`, `trail skeleton`, `trail grep`) and the
  relevant learnings in `.trail/`.
- Identify affected functions, callers and dependencies (`trail callers <symbol> -d N`).
- Check existing architectural decisions (learnings marked Decided / Tried and ruled out).

After modifying code:
- Review the impact radius (`trail blast --base origin/main`).
- Run `trail check` when applicable.
- Preserve and update relevant project learnings (`trail note --title "<about>"`).

If Trail-Code is unavailable, report that explicitly. Do not claim Trail checks were
performed unless they actually ran.

Privacy: run Trail with `DO_NOT_TRACK=1`, and never with the look-back over past sessions
(`TRAIL_NO_LOOK_BACK=1`): they hold personal data that must not reach the repo. A learning
never names a real game (Title IDs only), a person, a user name or a LAN address.
