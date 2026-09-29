# Lada TK Analytics

Shift sheets for Lada TK's rec hockey games: shifts, ice time and average shift length for every skater, measured from the wide-cut game video on YouTube.

**Site:** https://kondrat52.github.io/lada-tk-analytics/

## What's here

| Path | What it is |
|---|---|
| `docs/` | The published site (GitHub Pages). Generated; don't edit by hand. |
| `games/<date>-vs-<opp>/` | One folder per game: `game.json` (periods, penalty kills, video link, notes) and `shifts.csv` (one row per shift). |
| `roster.json` | Jersey number → surname. Add new players here. |
| `pipeline/` | The scripts that turn a game video into `shifts.csv`, and `build_site.py`, which renders `docs/`. |
| `RUNBOOK.md` | The manual steps behind the skill, for debugging or running by hand. |
| `.claude/skills/process-game/` | The Claude Code skill for the weekly run. |

## Adding a game

The weekly run is driven by Claude Code. Open this repo and run the project skill:

> /process-game https://youtu.be/XXXXXXXXXXX vs RR

The skill (`.claude/skills/process-game/SKILL.md`) asks for the opponent, start time and any penalties, then
runs `pipeline/run_game.py` (fetch → prepare → review → solve → publish) and asks before pushing.

It takes about two hours on an M-series Mac: roughly 80 minutes of detection, then number reading, a visual review of the uncertain moments, and the final solve. Tell it about anything the video can't show, such as who took a penalty and when.

To rebuild the site after editing a game's files or the roster:

```sh
python pipeline/build_site.py
```

## How the numbers are made

1. Detect every person on the rink in the 4K video (YOLO, 8 fps) and split teams by jersey color.
2. Track our skaters frame to frame, and read jersey numbers and names from close-up crops (OCR).
3. Check uncertain or swapped tracks by eye against a reference card of each player's gear.
4. Solve for who is on the ice every second, assuming 5 skaters (4 on a penalty kill), with changes happening at the bench.
5. Clean up: gaps under 15 s are merged, and hops under 20 s don't count as shifts.

Times are real elapsed time on the ice, including stoppages, because the video has no game clock.
