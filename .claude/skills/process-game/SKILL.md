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
- Date and start time, rink (Renton, Snoqualmie or Kirkland so far) for the page header. The video title usually
  has them, e.g. "LTKvsTTT 5:55 PM PDT - SEP 13, 2026 (Snoqualmie) - wide cut".
- Home or away. So far the home team has worn white (ours: blue numbers and trim) and, at Renton and Kirkland, sat
  on the bench right of center; away we wear light blue and sit left of center. LADA's API says which:
  `https://api.ladaseattle.com/api/v1/game/<id>` has `playHome` (the id: `.../api/v1/team/24/game/last`). The
  pipeline finds our players by jersey colour and their line changes by the bench, so check frame600.png (step 1)
  if unsure.
- New players, and for each whether they're on the team or a sub (they go in different parts of `roster.json`,
  step 4). The same game record has `lines`: the planned lines as LADA player ids. An id that isn't in
  `lada_player_ids` is a new player worth asking about, but the lines aren't attendance (a listed sub may not come).
- The final score, and roughly when goals were scored if they remember. It makes the goal check in step 7 quick.

Don't ask about penalties: find them from the video (step 3) and report what you found.

Don't wait for answers to start step 1; you need them from step 3 on.

## 1. Environment and fetch (~90 min, background)

```sh
PY=~/.venvs/hockey/bin/python
[ -x $PY ] || sh pipeline/setup_env.sh
W=~/hockey-work/<YYYY-MM-DD>-vs-<opp>          # outside the repo; ~5 GB
nohup caffeinate -dims -t 28800 >/dev/null 2>&1 &   # keep the Mac awake for the whole run (8 h)
$PY pipeline/run_game.py fetch "<url>" $W --rink <renton|snoqualmie|kirkland> [--jersey white --bench right]   # run_in_background: true
```

A sleeping Mac stalls everything: detection crawls, and subagents die mid-review ("your computer went to sleep").

`--jersey` picks the colour tests in `rink.JERSEYS` (default light blue). If you find out after detection that we
wore another jersey (prepare makes only a handful of review rows; the roster card is nearly empty), run
`$PY pipeline/run_game.py jersey $W white`: it records the jersey, cuts the missing crops from the video
(~5 min, no detection rerun) and OCRs them. Then carry on from step 2. `--bench` picks our bench: at Renton
`right` mirrors the usual left one about center ice; Kirkland's usual is `right` (home), and `left` is the away
bench. Check it on frame600.png: our jerseys sit on our bench. If it was wrong, add `"bench": "right"` to
`$W/full/rink.json` before `prepare` (it decides which detections are tracked at the bench), or at the latest
before `solve` (it decides which track ends count as line changes).

Each rink films from a different spot, so the camera geometry lives in `pipeline/rink.py` (detection crop, where
the far boards are, our bench, nets). Renton has both benches behind the far boards. Snoqualmie has them on the
near side at the frame edges, ours at the right. Kirkland films through a fisheye lens from low at center ice: the
far boards bow up toward center, both benches are behind them (home right of center, away left), and the penalty
boxes are the near corners at the bottom of the frame. For a rink not in `rink.py`, stop before detection. You
don't have to wait for the download: grab 4K frames straight from the stream,

```sh
U=$($PY -m yt_dlp -g -f 313 "<url>"); $FF -loglevel error -ss 600 -i "$U" -frames:v 1 $W/frame600.png   # FF: imageio_ffmpeg's ffmpeg
```

then add a class (crop above the heads of players at the far boards, board band, ice polygon, benches, nets,
scoreboard box), run `boards.py` on the frame and draw its curve over it. Check it all the way to the frame edges:
yellow lettering on signs above the boards pulls the fit up (Kirkland's HOCKEY sign), which `board_lowest = True`
fixes. A wrong crop silently loses the far-side players. Also run YOLO on a few frames and check the jersey
colour test (`rink.JERSEYS`) under that rink's lighting before starting detection.

Fetch downloads the 4K video, calibrates the far boards, runs detection (it restarts itself from the last frame if
the Mac slows down), then OCR, then writes `$W/periods.json` with proposed period windows. Watch
`$W/full/log.txt` with a Monitor that also matches `Traceback|Error`. It is safe to re-run fetch after an
interruption, because it resumes. A background shell job stops after 2 hours, and detection plus OCR can take
longer (1 h 46 min of detection at Snoqualmie). If the job is stopped, re-run fetch to finish. Don't run anything heavy on the Mac meanwhile, since OCR or other jobs starve
the video decoder.

## 2. Confirm the periods

Read `$W/break_*.jpg` (each break: the ice empties and both teams sit at their benches for about a minute) and
`$W/video_end.jpg`. `periods.json` boundaries are usually right to within a few seconds. Fix any that aren't.
`net` is where our goalie plays that period (`nets` in `rink.py`, e.g. Renton 540 = left, 3245 = right), and it
switches each period.

If `periods.json` has a single period, the breaks didn't look empty enough. At Kirkland they are about a minute long
and a referee stays out on the ice, so empty-ice detection can't find them. Take the periods from the scoreboard clock
instead: it runs down to 00.0 at the end of a period, then shows a 1:00 intermission countdown, then resets to
18:00. A period starts when the clock first counts down from 18:00 (that rink's clock runs through stoppages,
except in the last minute or two).

Every rink so far has the arena scoreboard in frame (`scoreboard` in `rink.py`): period clock, score, shots, and the
home/guest penalty panels with the player's number and the time left. Read it first. Its LEDs flicker (at Renton
most single frames show it dark), so take the brightest frame of each second:

```sh
$PY pipeline/scoreboard.py $W                                   # one pass over the video, ~5 min
$PY pipeline/scoreboard.py $W $W/sb.jpg $(seq 30 60 4000)        # the board every 60 s, as a sheet
```

From that sheet: which side we are (home/guest; LADA's `playHome` says too), when the score changed, which
penalty panels lit up and for whom, and the clock at the end. In the last minute it shows tenths, so you can tell
whether the video reaches the final horn. If it doesn't (play still going in `video_end.jpg` and time left on the
clock), pass `--video-ends-early` when publishing.

## 3. Penalty kills

The scoreboard sheet shows every penalty: a penalty panel lights with the player's number and counts down. Sheet it
every 1–2 s around each one: the panel appears at the whistle, and the penalty ends when it reaches 0:00 and goes
dark (LADA minors have been 2 or 3 minutes; the clock may stop meanwhile). That span is the penalty kill.

Don't trust which panel it's on. At Kirkland the scorekeeper put our penalties on the guest panel and one of theirs
on the home panel, while the score was on the right side. For every penalty on either panel, watch who skates into
a penalty box after the whistle (full-rink `frames` 1–3 s apart, then zoom on the box): our white or light-blue
jersey means it's ours. At Kirkland the boxes are the near corners, ours bottom-right and theirs bottom-left, and the
player drops out of the bottom of the frame as he sits. Read his number or name off the back on the way in.

A penalty can carry over an intermission. Then add a `pk` entry to both periods, from the whistle to the period's
end and from the next period's start until the panel goes dark. Use the moment the panel goes dark, not the time it
showed at the break: Kirkland's penalty clock jumped during the intermission (2:33 → 1:42).
Without a readable board, find the window where only 4 of our skaters are on the ice:

```sh
$PY pipeline/run_game.py skaters $W <t0> <t1>     # seconds of video around the penalty
```

It counts the goalie before `prepare`, so look for 5 → 4+goalie. A stopped-clock 2-minute penalty often
takes 3+ minutes of real time. Add it to that period in `periods.json`:
`"pk": [{"start": 3602, "end": 3798, "player": 4}]`.

## 4. Prepare the review

First look for players who aren't in `roster.json`. The roster card only has rows for roster numbers, so a new
or substitute player never shows up on it:

```sh
$PY pipeline/run_game.py unknown $W
```

It lists numbers the OCR read hundreds of times that aren't on the roster, with any surname read on the same
crops and a crop sheet `$W/unknown_<N>.jpg`. Read the sheet. Our jersey is ours (light blue, or white with blue
numbers and trim when we wear white). Another team's jersey that passes for ours (white with blue lettering against
our light blue) is an opponent: ignore it. Ask the user whether each new player of ours is on the team or a sub, and
don't assume: a number missing from `roster.json` can be a long-time player (the captain was). Team members go in
`skaters`, subs in `subs` (the site tags them "sub", and the feed lists them apart from the team), both as number →
surname on the back. Tell the user the spelling you used. Don't wait for the answer to prepare: put him in `subs`
for now, because moving him to `skaters` later changes only the site.

A surname two players share (a father and son) doesn't count as a name read for either, so only their digits tell
them apart. If only one of them played (check the crops read with that name), leave the other out of `roster.json`
for this game so the name reads count. Then:

```sh
$PY pipeline/run_game.py prepare $W
```

This makes per-period tracks, review sheets and a roster card in `$W/rev_pN/`. Read one `roster_card.jpg`. Each
row should be one player with a consistent look. A roster player with an empty row on every period's card most
likely didn't play: say so in the review prompt. Empty in one period only usually means he skated with his back
away from the camera that period (wingers swap sides): tell that period's reviewers to Read another period's
`roster_card.jpg` for him. If you add a player after `prepare`, delete `$W/p*` and `$W/rev_p*` and run it again, but
only before the review starts: never re-run `prepare` for a period once its review started (review rows point at
segment numbers).

## 5. Visual review (subagents, parallel)

For every period, split its `sheet_*.jpg` files into chunks of 3 and launch one general-purpose subagent per
chunk, about 6 at a time (start the next as each finishes). Bigger chunks or many more at once tend to stall
before writing anything; one file per sheet keeps whatever finished. Prompt (fill the brackets):

> You are identifying rec-hockey players in image crops. Accuracy matters more than coverage: answer "?"
> whenever you are not sure.
>
> Directory: [W]/rev_[pN]/
>
> 1. First Read `roster_card.jpg`. Each row shows one player of our team, in [light-blue jerseys | white jerseys
> with blue numbers and blue trim] (label "#N" = jersey number)
> in several views. Learn distinguishing features: number/name on the back (also sleeve numbers), sock
> color/stripes, pants (black shorts over white socks vs. long black), helmet color, glove color, skate color.
> Roster: [#N SURNAME list from roster.json]. [(#N and #M probably did not play this game.)] If you clearly see
> another number on our jersey, report it.
> #58 is the goalie (big leg pads): report "G" for goalie rows.
>
> 2. Then Read ONLY these sheets: [sheet_XXX.jpg, …]. Each sheet has up to 8 rows. Each row = one tracked
> skater over time; every tile is labeled "R<id> <time>s". The tracker can make mistakes: a row may switch
> from one player to another partway through (a "swap"), and single tiles may show an overlapping player.
> For every row, decide who it is from numbers/names when visible, otherwise appearance matched against the
> roster card. Only give a number if reasonably confident (high = number/name visible on that player's part
> of the row, or a very distinctive look; med = appearance only, with no competing lookalike). If appearance
> fits several players, answer "?". If the row switches players, report both with the switch time in seconds.
> Tiles showing an opponent ([white | dark/red] jerseys) or a referee (black and white stripes) are noise.
>
> 3. As soon as you have decided all rows of a sheet, and before reading the next one, Write that sheet's answer
> to `[W]/rev_[pN]/review_sNNN.txt` (sheet_007.jpg -> review_s007.txt) as CSV, header exactly:
> `row_id,player,confidence,switch_time,player2,confidence2,note`
> player/player2: a jersey number, "?" or "G"; confidence: high/med/low; switch fields empty unless the row
> switches; note: a few words, no commas. One line per row, every row on that sheet.
> row_id is exactly as on the tile labels, with the R (e.g. R168).
> If a Read of an image fails, retry it once. Never answer from other review files: they describe other rows.
> Your final reply should be just one line: how many rows you wrote.

When all are back, check each period's review files together cover every row in its `manifest.csv` (parse them with
`apply_review.parse_review`, as `solve` does), and relaunch the sheets that are missing. If a reviewer reports that
images failed to load, redo its sheets with a fresh one: move the old file aside as `old_review_sNNN.txt` (`solve`
reads only `review_*.txt`).

## 6. Solve and check

```sh
$PY pipeline/run_game.py solve $W
```

`solve` also estimates stoppages from player motion and adds live play time per shift (the video has no usable
audio, so whistles can't be heard). It ends with a lineup check: stretches of 15+ s where the shifts don't put 5 of
us on the ice (4 inside penalty kills), and goals in `highlights.json` without that many on (`publish` runs it
again, once the highlights exist). Each one is a missed player, an unlisted penalty or a bad label. Read
`$W/gantt_pN.png` for where it sits. Then look at the segments in that window (`$W/pN/segs_final.csv`: `num` -1 =
unlabeled; `$W/rev_pN/manifest.csv` maps a track `tid` to its review row) and their crops (`pipeline/sheet.py`
makes contact sheets of any crops; `$W/pN/tracks_v1.csv` gives each track's crop files). A whole unit with one
player missing usually means that player's tracks are unlabeled. The reviewers answer "?" when the back isn't
visible, but his gear (socks, pants, helmet) and who else is accounted for usually settle it.

Put what you decide in `$W/rev_pN/review_zfix.txt`, in the review CSV format, with a note starting "checked by hand".
It sorts after the reviewers' files and overrides their "?" answers, e.g.
`R326,69,med,3776,90,med,checked by hand: 69 look at the net for the goal; 90 white helmet from 3779`.
Then `solve` again. Tell the user which rows you labeled by hand.

The printed table is the result. Sanity check: each period's total ice time ≈ 5 × period length (minus a skater
per penalty-kill second).

## 7. Highlights: goals and penalties

```sh
$PY pipeline/run_game.py goals $W
```

This lists candidate goals: center-ice faceoffs that aren't period starts, and long stoppages that restart at
center. A goal is always followed by a center faceoff. The scoreboard narrows each one down: the clock stops a
second or two after the goal, and the score changes soon after. Check each candidate by eye:

```sh
# full rink every 3 s over the minute before the faceoff (Renton rows; Snoqualmie: y 380 1536; Kirkland: y 320 1536)
$PY pipeline/run_game.py frames $W $W/g.jpg 0 3840 700 1500 1000 2 <t-60> <t-57> ... <t>
# zoom on a net, 1 s apart (Renton: left net x 150-1450, right net x 2500-3800;
# Snoqualmie: y 380 760, left net x 200-1400, right net x 2600-3800; Kirkland: y 400 800, left net x 150-1350)
$PY pipeline/run_game.py frames $W $W/gz.jpg 150 1450 720 1070 660 3 <t1> <t2> ...
```

A real goal shows a scramble or shot at one net, the referee pointing at it, and one team celebrating before
the players drift to center. Most candidates that don't show this are false alarms. `goals` prints which net is
ours each period, so you can tell goals for from goals against. Tell the user the score you found and ask them
to confirm it.

For each of our penalties, find the infraction: the referee raises an arm right after it (a delayed penalty),
play continues until our team touches the puck, then the whistle and the penalty-kill faceoff. The scoreboard
clock stops at the whistle, so start 10–20 s before that. The referee may signal from the far end, so look at where
the penalized player was in the seconds before the arm went up (his track in `$W/pN/segs_final.csv`, `plabel` = his
number, and full-rink `frames` 1 s apart). An opponent going down near him is the usual sign.

Make a clip of about 22 s per event, ending a few seconds after the goal or call:

```sh
$PY pipeline/run_game.py clip $W <game-id> goal-1 <t-12> <t+10> <t>        # optional last arg: focus x
```

For a penalty, follow the player who took it: pass `#<number>` as the last argument, and start the clip a few
seconds before the infraction (the referee's arm goes up right after it; the infraction may be far from where
the referee stands). For goals the default framing follows the main group of players; a focus x (about 500 =
left corner, 3300 = right) keeps the camera on one end. A focus x can lock onto someone right by the camera instead
(at Kirkland, a referee in the near corner fills the frame), so start with the default and check a few frames of
each clip (cv2 can read the mp4). Then write `$W/highlights.json`:
`[{"type": "goal", "team": "for", "t": 3828, "clip": "clips/goal-3.mp4", "poster": "clips/goal-3.jpg", "note": "..."},
{"type": "penalty", "player": 4, "t": 3580, "clip": "clips/penalty-4.mp4", "poster": "clips/penalty-4.jpg", "note": "..."}]`
(t = seconds of video at the goal or infraction). The page shows who was on the ice for each goal. The recording's
audio is silent, so the clips have no sound.

## 8. Publish

```sh
$PY pipeline/run_game.py publish $W <YYYY-MM-DD>-vs-<opp> --opponent <OPP> --eyebrow "Sun Oct 4, 2026 · 7:50 PM · Renton" [--video-ends-early]
```

This writes `games/<id>/game.json` + `shifts.csv` (with play time, stoppages and highlights) and rebuilds `docs/`,
including the JSON feed in `docs/api/` (see API.md) and the trends page `docs/trends.html` (`build_trends.py`). It
also stores time in offence and defence as `zones` in `game.json` (`zones.py`, from the detections, so it works
until the work folder is gone and again from an archived one). It also looks up the game's LADA API id (`lada_game_id`, which
the LADA app uses to link the game) from LADA's public "last game" call. If it logs that it couldn't, find the id in
`https://api.ladaseattle.com/api/v1/game/<LADA id of any game vs this opponent>/opponentGames` (the team's upcoming
games and their ids: `.../api/v1/team/24/game/next/30`). Add it, and the opponent's full name if you know it, as
`"lada_game_id"` / `"opponent_name"` in `game.json`, then re-run `$PY pipeline/build_site.py`. A new opponent's
code and full name go in `opponents.json` (the user's spelling wins over LADA's). For a new player, also add their
LADA player id to `lada_player_ids` in `roster.json` if the user knows it. Write `notes` in `game.json` (they
survive a republish): the rink if it's new, who sat and when, where the goal times came from, the subs, and
anything you labeled by hand or read differently from the scoreboard.
The clips live in `docs/games/<id>/clips/` (about 5 MB each), served by GitHub Pages. Open the page locally
(`docs/games/<id>/index.html`) and look it over. Show the user the table and the notable fun stats,
then ask before committing and pushing: the site is public. After pushing, check that the page is live (Pages
takes about a minute; add `?v=<random>` to skip the CDN cache).

## 9. Archive

Once the user is happy, offer to free the disk space with

```sh
$PY pipeline/run_game.py archive $W
```

It deletes the video, crops, overview frames and sheets (~5 GB) and keeps the game's data in `$W` (~100 MB:
detections, OCR reads, tracks, reviews, periods, results, rink), so the game can be re-solved with a later
pipeline or used as a regression test. Never `rm -rf` the work folder: the user wants every game's data kept.
