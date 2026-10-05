# Runbook: processing a new game

Normally you run `/process-game <link>` in Claude Code, and `pipeline/run_game.py` chains these steps
(`fetch`, `prepare`, `solve`, `publish`). This page is the manual version, useful when something needs fixing.

Written for Claude Code (or anyone patient). Commands assume the repo root as the working directory,
`PY` = a Python ≥ 3.10 with `pipeline/requirements.txt` installed, and `W` = a per-game work folder
**outside** the repo (the video and crops take ~5 GB).

```sh
# one-time: macOS system python is 3.9, which is too old for current yt-dlp
uv venv --python 3.12 ~/.venvs/hockey && uv pip install --python ~/.venvs/hockey/bin/python -r pipeline/requirements.txt
PY=~/.venvs/hockey/bin/python
W=~/hockey-work/2026-10-04-vs-XX
```

## 1. Download (5 min)

```sh
mkdir -p $W/full
$PY -m yt_dlp -f 313 -o "$W/video.webm" "https://youtu.be/VIDEO_ID"   # 313 = 2160p VP9; the pipeline expects 3840 px wide
```

## 2. Calibrate the far boards (1 min)

```sh
FF=$($PY -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
$FF -loglevel error -ss 600 -i $W/video.webm -frames:v 1 $W/frame600.png
echo '{"rink": "snoqualmie"}' > $W/full/rink.json   # not for Renton, the default
# home games (white jerseys, right bench at Renton): {"rink": "renton", "jersey": "white", "bench": "right"}
# Kirkland (fisheye, benches behind the far boards, home right): {"rink": "kirkland", "jersey": "white", "bench": "right"}
$PY pipeline/boards.py $W/frame600.png $W/full     # writes boards_poly.npy
```

The camera geometry per rink (detection crop, board band, ice area, our bench, nets) lives in `pipeline/rink.py`.
Check the fitted boards line on the frame all the way to its edges, and that the benches are where the rink's class
expects them, by viewing a crop of the frame. Yellow lettering on signs above the boards pulls the fit up; a rink's
`board_lowest = True` makes `boards.py` keep only the lowest yellow run in each column (Kirkland). If the camera moved, or it's a new rink, adjust or add a class there before detecting: the
detection crop (`crop_top`) must include the heads of players standing at the far boards.

Our players are told apart by jersey colour (`JERSEYS` in `rink.py`: light blue by default, or white with blue
numbers). Detection only saves crops of players in that jersey, so set it before detecting. The bench we had
(`"bench": "right"` mirrors Renton's left bench about center ice) decides which track ends count as line changes. If it was wrong,
`run_game.py jersey $W white` fixes it afterwards: `crops.py` cuts the missing crops from the video using the
detections already in `dets.csv`, then OCR reads them.

## 3. Detect (~80 min on an M3)

```sh
nohup $PY pipeline/process.py $W/video.webm $W/full 8 > $W/full/log.txt 2>&1 &
```

- Progress lines go to `log.txt`; it ends with `DONE`.
- If it slows down badly (memory grows, swap), kill it, delete rows of the last frame from `dets.csv`,
  and restart from that time: `process.py $W/video.webm $W/full 8 <last t>` (frame numbers stay global).
- Don't run OCR at the same time: it starves the video decoder.

## 4. Read numbers (10–15 min)

```sh
for k in 0 1 2 3; do PYTHONHASHSEED=0 $PY pipeline/ocr_worker.py $W/full 1000000000 1 $k 4 > $W/full/ocr_$k.log 2>&1 & done
```

## 5. Find the periods

```sh
$PY pipeline/ovsheet.py $W/full/ov $W/ov.jpg 0 4000 30 3
```

Breaks show the ice empty with both teams at the benches for about a minute. Our goalie switches ends each
period. Net x: see `nets` in `pipeline/rink.py` (Renton ≈ 540 left, ≈ 3245 right). Narrow each break down to the
second with finer sheets.
Ask about penalties: who, and roughly when. A penalty kill shows up as 4 of our skaters on the ice.
The arena scoreboard is in frame at both rinks: `pipeline/scoreboard.py $W` keeps its brightest frame per second
(the LEDs flicker), and `pipeline/scoreboard.py $W out.jpg t1 t2 ...` sheets it. It shows the period clock, the
score, and each penalty with the player's number and time left. Check which team each penalty belongs to by who
skates into a penalty box: scorekeepers have put penalties on the wrong panel. When the empty-ice breaks aren't
found (Kirkland: short breaks with a referee on the ice), take the periods from the clock (00.0, a 1:00
intermission countdown, then 18:00). A penalty carried over an intermission is a penalty kill in both periods.

## 6. Track each period

```sh
$PY pipeline/run_period.py $W/full $W/p1 <P1 start> <P1 end> <net x>
$PY pipeline/review_sheets.py $W/p1 $W/rev_p1 8
$PY pipeline/roster_card.py $W/p1 $W/rev_p1/roster_card.jpg 8
```

Repeat for p2 and p3. Finish OCR (step 4) before this step, and never re-run `run_period.py` for a period
after its review (step 7) has started: review rows point at segment numbers, and a new segmentation scrambles
them. Look at `roster_card.jpg`. Every row should be one player. The card only has roster numbers, so run
`run_game.py unknown $W` before tracking to find new or sub players (numbers read hundreds of times that aren't
in `roster.json`, with a crop sheet each): add ours to `roster.json`, team members under `skaters` and subs under
`subs` (ask which); other teams' jerseys are opponents.

## 7. Visual review (Claude subagents, ~15 min in parallel)

Split each period's `sheet_*.jpg` across 4–5 subagents (~6 sheets each), with this prompt:

> You are identifying rec-hockey players in image crops. Accuracy matters more than coverage: answer "?"
> whenever you are not sure. Directory: `$W/rev_pN/`. First Read `roster_card.jpg` (one row per player, "#N" =
> jersey number) and learn each player's features: number/name on the back and sleeves, socks, pants,
> helmet, gloves, skates. Roster: (list from roster.json). #58 is the goalie; answer "G" for goalie rows.
> Then Read ONLY sheets X–Y. Each row = one tracked skater over time, tiles labeled "R<id> <time>s". A row may
> switch players partway through (a swap). Give a number only if reasonably confident (high = number or name
> visible; med = distinctive look with no lookalike); otherwise "?". Report swaps with the switch time.
> Opponents (white) and referees in tiles are noise. Write CSV to `$W/rev_pN/review_<letter>.txt` with header
> `row_id,player,confidence,switch_time,player2,confidence2,note`, one line per row, no commas in notes, row_id
> as on the tiles (R168).
> Reply with just the number of rows written.

## 8. Solve and check

```sh
$PY pipeline/run2.py $W/p1 $W/rev_p1 <P1 end> '[[<P1 start>,<P1 end>]]'
$PY pipeline/run2.py $W/p3 $W/rev_p3 <P3 end> '[[<P3 start>,<P3 end>]]' '[[<pk start>,<pk end>,4]]'  # with a penalty kill
$PY pipeline/gantt.py $W/p1/shifts_final.csv $W/p1/segs_final.csv $W/gantt_p1.png <P1 start> <P1 end>
```

In the Gantt chart the bottom panel should sit at 5 (4 on a PK). Long stretches at 4 or 6 mean a missed
player, a penalty, or a bad label: inspect with crop sheets before trusting the numbers. `run_game.py solve` lists
them (and goals without 5 of us on the ice) as a lineup check. Labels you decide by hand go in
`$W/rev_pN/review_zfix.txt` (same CSV), which overrides the reviewers' "?" answers.

## 9. Play time and highlights

`run_game.py solve` runs `pipeline/stoppages.py`, which adds a `play` column to `shifts_all.csv` and writes
`stoppages.json`. For highlights: `run_game.py goals` lists candidate goals, `run_game.py frames` renders frames
to check them, and `run_game.py clip` cuts a zoomed clip into `docs/games/<id>/clips/` (last argument: an x
position or `#N` to follow player N). List the clips in `$W/highlights.json`; see the skill for the format.

## 10. Publish

```sh
(cd $W && $PY $OLDPWD/pipeline/final_stats.py p1:P1 p2:P2 p3:P3)    # writes $W/shifts_all.csv, prints the table
mkdir -p games/<date>-vs-<opp> && cp $W/shifts_all.csv games/<date>-vs-<opp>/shifts.csv
# write games/<date>-vs-<opp>/game.json (copy the previous game's and edit periods, video, PKs, notes).
# Optional extras for the Fun stats section: "fun": {"name_reads": {number: count}} from load_reads()'s
# name reads, and "pipeline": {"detections", "crops", "reads", "reviewed"} counts from this run.
$PY pipeline/zones.py $W games/<date>-vs-<opp>/game.json   # time in offence/defence: add as "zones" in game.json
$PY pipeline/build_site.py                                  # also writes docs/trends.html
git add -A && git commit -m "Add <date> vs <opp>" && git push
```

GitHub Pages redeploys in about a minute. Then `run_game.py archive $W` drops the video, crops and sheets and keeps
the game's data (~100 MB), so it can be re-solved later. Keep every game's archive.
