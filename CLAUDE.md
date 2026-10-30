# Notes for Claude Code

## Trail-code

This repo uses [Trail-code](https://github.com/trailhq/Trail-Code) for its code map and learnings.

- At the start of every session, check `command -v trail`. If it is missing, install it:
  `npm install -g @trailhq/trail-code` (cloud sessions: it belongs in the environment's setup script).
- Use `trail ask`, `trail callers`, `trail skeleton` and `trail grep` to find code before searching by hand.
- Run Trail with `DO_NOT_TRACK=1`, and never with the look-back over past sessions
  (`TRAIL_NO_LOOK_BACK=1`): they hold personal data that must not reach the repo.
