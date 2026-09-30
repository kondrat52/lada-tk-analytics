# Shift sheet JSON feed

Read-only JSON, published with the site on GitHub Pages and rebuilt on every push. No login and no keys. Pages sends
`Access-Control-Allow-Origin: *` and caches for up to 10 minutes.

Base URL: `https://kondrat52.github.io/lada-tk-analytics/api/`

| File | What's in it |
|---|---|
| `index.json` | Team, list of games (newest first) with links to each game's JSON and page |
| `games/<id>.json` | One game: periods, per-player stats, every shift, highlights (clip URLs), stoppages |
| `season.json` | Season totals per player |
| `roster.json` | Jersey numbers, surnames and LADA player ids |

## Conventions

- **Times are seconds.** Shift and highlight times (`start`, `end`, `t`) are seconds into the game video
  (`video_url`), the same timestamps YouTube uses. `*_in_period` fields count from that period's start.
- **Ice time vs play time.** `toi` is ice time: real elapsed time on the ice from stepping on to stepping off,
  stoppages included (there is no game clock in the video). `play` is live play only, estimated from the video.
  It's an upper bound, since quick whistles can slip through.
- **Players** appear as `{number, name, lada_player_id}`. `name` is the surname as printed on the jersey.
  `lada_player_id` is the player's id on the LADA team roster (team 24), or `null` if not matched yet. Join on
  `lada_player_id` when it's there; jersey numbers can differ between the jersey and the LADA roster.
- **Games** have a date-slug `id` (`2026-09-27-vs-rr`). `lada_game_id` is the LADA API game id, or `null` until
  someone fills it in. Match on date + opponent when it's `null`.
- `schema` changes only when a field is removed or changes meaning. New fields can appear at any time, so ignore
  the ones you don't know.
- Missing numbers are `null` (e.g. `play` for a game without stoppage data, `shortest_shift` when every shift
  was cut off by the recording ending).

## `index.json`

```json
{
  "schema": 1,
  "team": {"name": "LADA Turbo Kings", "short_name": "Lada TK", "lada_team_id": 24},
  "site_url": "https://kondrat52.github.io/lada-tk-analytics/",
  "updated": "2026-09-27",
  "season_url": ".../api/season.json",
  "roster_url": ".../api/roster.json",
  "games": [{
    "id": "2026-09-27-vs-rr", "date": "2026-09-27", "title": "...", "subtitle": "Sun Sep 27, 2026 · 7:50 PM · Renton",
    "opponent": {"code": "RR", "name": null}, "lada_game_id": null,
    "goals_on_video": {"for": 1, "against": 2}, "highlights": 4,
    "page_url": ".../games/2026-09-27-vs-rr/", "json_url": ".../api/games/2026-09-27-vs-rr.json"
  }]
}
```

`goals_on_video` counts the goals found in the recording. It isn't the official score: the recording can end
before the final horn (`video_ends_early` in the game file).

## `games/<id>.json`

| Field | Meaning |
|---|---|
| `periods[]` | `{label: "P1", start, end, length}` in video seconds |
| `penalty_kills[]` | `{period, start, end, player}`: our skater in the box; 4 skaters on the ice for the window |
| `players[]` | Sorted by ice time: `shifts, toi, play, avg_shift, median_shift, longest_shift, shortest_shift`, and `periods[]` with `{label, shifts, toi, avg_shift}` |
| `shifts[]` | Every shift: `{number, period, start, end, duration, play, start_in_period}` |
| `highlights[]` | `{type: "goal" \| "penalty", team: "for" \| "against" (goals), player (penalties), t, period, t_in_period, clip_url, poster_url, note, on_ice[]}`. Clips are 1280×720 H.264 MP4 without audio, about 5 MB. `on_ice` lists our skaters on the ice for a goal |
| `stoppages[]` | `[start, end]` pairs: estimated stoppages (whistle to puck drop) |
| `video_url`, `page_url` | The full game on YouTube; the shift sheet page |

`shortest_shift` leaves out shifts cut off by the recording ending mid-play.

## `season.json`

`players[]` sorted by ice time per game: `{number, name, lada_player_id, games_played, shifts, toi, toi_per_game,
play, avg_shift, longest_shift, shortest_shift, games[]}`. `games[]` lists that player's games, newest first:
`{id, date, opponent: {code, name}, toi, shifts, avg_shift, play}`.

## `roster.json`

`skaters[]` and `goalies[]`, each `{number, name, lada_player_id}`. Edit the repo's `roster.json` to change them.
