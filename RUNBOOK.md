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
$PY pipeline/boards.py $W/frame600.png $W/full     # writes boards_poly.npy
```

Check the benches are where `shifts.py` expects them (`BENCH_X = (1340, 1760)`, our bench left of center on the
far side) by viewing a crop of the frame. If the camera moved, adjust `BENCH_X`.

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
period. Net x ≈ 540 (left) or ≈ 3245 (right). Narrow each break down to the second with finer sheets.
Ask about penalties: who, and roughly when. A penalty kill shows up as 4 of our skaters on the ice.

## 6. Track each period

```sh
$PY pipeline/run_period.py $W/full $W/p1 <P1 start> <P1 end> <net x>
$PY pipeline/review_sheets.py $W/p1 $W/rev_p1 8
$PY pipeline/roster_card.py $W/p1 $W/rev_p1/roster_card.jpg 8
```

Repeat for p2 and p3. Finish OCR (step 4) before this step, and never re-run `run_period.py` for a period
after its review (step 7) has started: review rows point at segment numbers, and a new segmentation scrambles
them. Look at `roster_card.jpg`. Every row should be one player. New numbers mean a new or
sub player: ask for the name and add it to `roster.json`.

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
> `row_id,player,confidence,switch_time,player2,confidence2,note`, one line per row, no commas in notes.
> Reply with just the number of rows written.

## 8. Solve and check

```sh
$PY pipeline/run2.py $W/p1 $W/rev_p1 <P1 end> '[[<P1 start>,<P1 end>]]'
$PY pipeline/run2.py $W/p3 $W/rev_p3 <P3 end> '[[<P3 start>,<P3 end>]]' '[[<pk start>,<pk end>,4]]'  # with a penalty kill
$PY pipeline/gantt.py $W/p1/shifts_final.csv $W/p1/segs_final.csv $W/gantt_p1.png <P1 start> <P1 end>
```

In the Gantt chart the bottom panel should sit at 5 (4 on a PK). Long stretches at 4 or 6 mean a missed
player, a penalty, or a bad label: inspect with crop sheets before trusting the numbers.

## 9. Publish

```sh
(cd $W && $PY $OLDPWD/pipeline/final_stats.py p1:P1 p2:P2 p3:P3)    # writes $W/shifts_all.csv, prints the table
mkdir -p games/<date>-vs-<opp> && cp $W/shifts_all.csv games/<date>-vs-<opp>/shifts.csv
# write games/<date>-vs-<opp>/game.json (copy the previous game's and edit periods, video, PKs, notes).
# Optional extras for the Fun stats section: "fun": {"name_reads": {number: count}} from load_reads()'s
# name reads, and "pipeline": {"detections", "crops", "reads", "reviewed"} counts from this run.
$PY pipeline/build_site.py
git add -A && git commit -m "Add <date> vs <opp>" && git push
```

GitHub Pages redeploys in about a minute.
