---
name: process-game
description: Turn a Lada TK game video (YouTube wide cut) into a shift sheet and publish it on the team site. Use when the user asks to process, analyze or add a game, or gives a YouTube link to a game, e.g. "/process-game https://youtu.be/... vs RR".
---

# Process a Lada TK game

Turns one wide-cut game video into per-player shift stats and publishes them to the GitHub Pages site in `docs/`.
`RUNBOOK.md` has the details behind each step; this skill is the order of operations and the checks.

Budget about 2 hours of wall time on the Mac (the GPU does the detection; this can't run in the cloud) and a
fair amount of tokens for the visual review. Keep the user posted with one line per stage.

## 0. Ask up front (one message, then start)

- The YouTube link (if not given) and the opponent's short name (e.g. RR).
- Date and start time, rink (usually Renton) for the page header. The video title usually has them.
- Penalties we took: who and roughly when (period, minute). The video shows a penalty kill only as
  4 skaters, never who sat.
- New or substitute players (number and surname). Later, unknown numbers on the roster card also need a name.

Don't wait for answers to start step 1; you need them from step 3 on.

## 1. Environment and fetch (~90 min, background)

```sh
PY=~/.venvs/hockey/bin/python
[ -x $PY ] || sh pipeline/setup_env.sh
W=~/hockey-work/<YYYY-MM-DD>-vs-<opp>          # outside the repo; ~5 GB
$PY pipeline/run_game.py fetch "<url>" $W       # run_in_background: true
```

Fetch downloads the 4K video, calibrates the far boards, runs detection (it restarts itself from the last frame if
the Mac slows down), then OCR, then writes `$W/periods.json` with proposed period windows. Watch
`$W/full/log.txt` with a Monitor that also matches `Traceback|Error`. It is safe to re-run fetch after an
interruption, because it resumes. Don't run anything heavy on the Mac meanwhile, since OCR or other jobs starve
the video decoder.

## 2. Confirm the periods

Read `$W/break_*.jpg` (each break: the ice empties and both teams sit at their benches for about a minute) and
`$W/video_end.jpg`. `periods.json` boundaries are usually right to within a few seconds. Fix any that aren't.
`net` is where our goalie plays that period (540 = left, 3245 = right), and it switches each period. If the video
ends before the final horn, say so in the game notes later.

## 3. Penalty kills

For each penalty the user named, find the window where only 4 of our skaters are on the ice:

```sh
$PY pipeline/run_game.py skaters $W <t0> <t1>     # seconds of video around the penalty
```

It counts the goalie before `prepare`, so look for 5 → 4+goalie. A stopped-clock 2-minute penalty often
takes 3+ minutes of real time. Add it to that period in `periods.json`:
`"pk": [{"start": 3602, "end": 3798, "player": 4}]`.

## 4. Prepare the review

```sh
$PY pipeline/run_game.py prepare $W
```

This makes per-period tracks, review sheets and a roster card in `$W/rev_pN/`. Read one `roster_card.jpg`. Each
row should be one player with a consistent look. Get names for any number that isn't in `roster.json` and add
them. Never re-run `prepare` for a period once its review started (review rows point at segment numbers).

## 5. Visual review (subagents, parallel)

For every period, split its `sheet_*.jpg` files into chunks of about 6 and launch one general-purpose subagent
per chunk, all at once. Use letters a, b, c… per period. Prompt (fill the brackets):

> You are identifying rec-hockey players in image crops. Accuracy matters more than coverage: answer "?"
> whenever you are not sure.
>
> Directory: [W]/rev_[pN]/
>
> 1. First Read `roster_card.jpg`. Each row shows one player of the light-blue team (label "#N" = jersey number)
> in several views. Learn distinguishing features: number/name on the back (also sleeve numbers), sock
> color/stripes, pants (black shorts over white socks vs. long black), helmet color, glove color, skate color.
> Roster: [#N SURNAME list from roster.json]. If you clearly see another number on a light-blue jersey, report it.
> #58 is the goalie (big leg pads): report "G" for goalie rows.
>
> 2. Then Read ONLY these sheets: [sheet_XXX.jpg, …]. Each sheet has up to 8 rows. Each row = one tracked
> skater over time; every tile is labeled "R<id> <time>s". The tracker can make mistakes: a row may switch
> from one player to another partway through (a "swap"), and single tiles may show an overlapping player.
> For every row, decide who it is from numbers/names when visible, otherwise appearance matched against the
> roster card. Only give a number if reasonably confident (high = number/name visible on that player's part
> of the row, or a very distinctive look; med = appearance only, with no competing lookalike). If appearance
> fits several players, answer "?". If the row switches players, report both with the switch time in seconds.
> Tiles showing a white-jersey opponent or a referee are noise.
>
> 3. Write your answer with the Write tool to `[W]/rev_[pN]/review_[letter].txt` as CSV, header exactly:
> `row_id,player,confidence,switch_time,player2,confidence2,note`
> player/player2: a jersey number, "?" or "G"; confidence: high/med/low; switch fields empty unless the row
> switches; note: a few words, no commas. One line per row, every row on your sheets.
> Your final reply should be just one line: how many rows you wrote.

When all are back, check each period's review files together cover every row in its `manifest.csv`.

## 6. Solve and check

```sh
$PY pipeline/run_game.py solve $W
```

Read `$W/gantt_pN.png`. The bottom panel should sit at 5 (4 inside penalty kills). A stretch of 4 or 6
lasting more than ~20 s means a missed player, an unlisted penalty or a bad label. Look at the crops before
accepting it (`pipeline/sheet.py` makes contact sheets of any crops). The printed table is the result.
Sanity check: each period's total ice time ≈ 5 × period length (minus a skater per penalty-kill second).

## 7. Publish

```sh
$PY pipeline/run_game.py publish $W <YYYY-MM-DD>-vs-<opp> --opponent <OPP> --eyebrow "Sun Oct 4, 2026 · 7:50 PM · Renton"
```

This writes `games/<id>/game.json` + `shifts.csv` and rebuilds `docs/`. Add any notes to `game.json` (e.g. the
video ending early) and re-run `$PY pipeline/build_site.py`. Show the user the table and the notable fun stats,
then ask before committing and pushing: the site is public. After pushing, check that the page is live (Pages
takes about a minute; add `?v=<random>` to skip the CDN cache). Offer to delete `$W` (the video and crops) once
they're happy.
