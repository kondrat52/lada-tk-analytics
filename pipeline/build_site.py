"""build_site.py : render docs/ (GitHub Pages) from games/*/game.json + shifts.csv.
docs/index.html            season totals (sortable) + list of games
docs/games/<id>/index.html one shift sheet per game
docs/api/*.json            JSON feed for apps (see build_feed.py / API.md)"""
import os, sys, json, glob, html
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_report import build
from build_feed import season_table, game_doc, write_feed
from roster import SKATERS, TEAM, opponent_name

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
fmt = lambda s: f"{int(round(s)) // 60}:{int(round(s)) % 60:02d}"

games, allsh, docs = [], [], {}
for gd in sorted(glob.glob(f"{ROOT}/games/*/")):
    game, A, data = build(gd, f"{ROOT}/docs/games/{os.path.basename(gd.rstrip('/'))}/index.html")
    docs[game["id"]] = game_doc(game, A, data["players"], data["highlights"])
    A = A.assign(game=game["id"])
    # shifts cut off by the recording ending mid-play don't count as short shifts
    cut = game["periods"][-1]["end"] if game.get("video_ends_early") else None
    A["cut"] = (A.t1 >= cut - 1) if cut else False
    games.append(game); allsh.append(A)
A = pd.concat(allsh)
season = season_table(A)


def cell(v, text=None):
    """td with a numeric sort key; missing values sort last."""
    ok = v == v and v is not None and not (isinstance(v, float) and np.isinf(v))
    return f"<td data-v='{float(v) if ok else ''}'>{text if text is not None else (v if ok else '–')}</td>"


rows = "\n".join(
    f"<tr><td class='l num' data-v='{p}'>{p}</td><td class='l name' data-v='{html.escape(SKATERS.get(p, ''))}'>"
    f"{html.escape(SKATERS.get(p, ''))}</td>{cell(int(r.gp))}{cell(int(r.shifts))}{cell(r.toi, fmt(r.toi))}"
    f"{cell(r.toi_gp, fmt(r.toi_gp))}{cell(r.play if r.play > 0 else None, fmt(r.play) if r.play > 0 else '–')}"
    f"{cell(r.avg, fmt(r.avg))}{cell(r.longest, fmt(r.longest))}"
    f"{cell(r.shortest if r.shortest == r.shortest else None, fmt(r.shortest) if r.shortest == r.shortest else '–')}</tr>"
    for p, r in season.iterrows())
cards = "\n".join(
    f"<li><a href='games/{g['id']}/'><span class='d'>{html.escape(g['eyebrow'])}</span>"
    f"<span class='t'>vs {html.escape(opponent_name(g))}</span></a></li>"
    for g in sorted(games, key=lambda g: g["date"], reverse=True))

SORT_JS = """<script>
// sort the season table by any column; numbers compare by their data-v key, missing values always last
(() => {
  const t = document.getElementById("season"), ths = [...t.tHead.rows[0].cells], body = t.tBodies[0];
  let col = 5, dir = -1;
  const sort = () => {
    const text = ths[col].dataset.text;
    const rows = [...body.rows].sort((a, b) => {
      const x = a.cells[col].dataset.v, y = b.cells[col].dataset.v;
      if (x === "" || y === "") return (x === "") - (y === "");
      return (text ? x.localeCompare(y) : x - y) * dir;
    });
    rows.forEach(r => body.appendChild(r));
    ths.forEach((th, i) => th.setAttribute("aria-sort", i === col ? (dir < 0 ? "descending" : "ascending") : "none"));
  };
  ths.forEach((th, i) => {
    const go = () => { dir = col === i ? -dir : (i < 2 ? 1 : -1); col = i; sort(); };
    th.addEventListener("click", go);
    th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
})();
</script>
"""

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(TEAM)} Shift Sheets</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Display:wght@700;800&family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@500;600&display=swap">
<style>
:root {{ --ice:#f4f8fb; --board:#fff; --ink:#13243a; --muted:#5b6b7e; --rule:#d6e0ea; --team:#3d8fd6; --redline:#c8323c; --blueline:#1f4fa3;
  --display:"Big Shoulders Display","Arial Narrow",sans-serif; --body:"Barlow","Helvetica Neue",Arial,sans-serif; --data:"Barlow Condensed","Arial Narrow",sans-serif; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ice:#0d1826; --board:#13233a; --ink:#e6eef7; --muted:#93a6bb; --rule:#243a55; --team:#6cb3f0; --redline:#ef6a72; --blueline:#7fa6ea; color-scheme:dark; }} }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--ice); color:var(--ink); font:400 16px/1.5 var(--body); }}
.wrap {{ max-width:960px; margin:0 auto; padding-inline:20px; padding-block:28px 56px; display:grid; gap:28px; }}
header {{ border-bottom:3px solid var(--redline); padding-bottom:14px; display:grid; gap:6px; }}
.eyebrow {{ font:600 13px/1.2 var(--data); letter-spacing:.12em; text-transform:uppercase; color:var(--muted); }}
h1 {{ font:800 clamp(34px,6vw,56px)/.95 var(--display); margin:0; }} h1 span {{ color:var(--team); }}
h2 {{ font:700 26px/1.1 var(--display); letter-spacing:.02em; text-transform:uppercase; margin:0; }}
section {{ display:grid; gap:12px; min-width:0; }}
ul.games {{ list-style:none; margin:0; padding:0; display:grid; gap:8px; }}
ul.games a {{ display:flex; flex-wrap:wrap; justify-content:space-between; gap:4px 16px; padding:12px 14px; background:var(--board); border:1px solid var(--rule); border-radius:4px; color:var(--ink); text-decoration:none; }}
ul.games a:hover, ul.games a:focus-visible {{ border-color:var(--team); outline:none; }}
.d {{ font:500 15px/1.3 var(--data); letter-spacing:.04em; color:var(--muted); }} .t {{ font:700 20px/1.1 var(--display); }}
.tablebox {{ overflow-x:auto; background:var(--board); border:1px solid var(--rule); border-radius:4px; }}
table {{ border-collapse:collapse; width:100%; min-width:620px; font-variant-numeric:tabular-nums; }}
th, td {{ padding:8px 10px; text-align:right; white-space:nowrap; border-bottom:1px solid var(--rule); }}
th {{ font:600 12px/1.2 var(--data); letter-spacing:.1em; text-transform:uppercase; color:var(--muted); cursor:pointer; user-select:none; }}
th[aria-sort="descending"]::after {{ content:" ▼"; }} th[aria-sort="ascending"]::after {{ content:" ▲"; }}
th:focus-visible {{ outline:2px solid var(--team); outline-offset:2px; }}
td {{ font:500 16px/1.2 var(--data); }} .l {{ text-align:left; }} td.num {{ font:800 20px/1 var(--display); color:var(--team); width:3.2em; }} td.name {{ font:500 16px/1.2 var(--body); }}
p.note {{ color:var(--muted); margin:0; max-width:70ch; }}
</style></head><body><div class="wrap">
<header><div class="eyebrow">LADA Seattle · Rec hockey</div><h1><span>{html.escape(TEAM)}</span> shift sheets</h1>
<p class="note">Ice time and shifts for every skater, measured from each week's wide-cut game video.</p></header>
<section><h2>Games</h2><ul class="games">{cards}</ul></section>
<section><h2>Season</h2><div class="tablebox"><table id="season"><thead><tr><th class="l" tabindex="0">#</th><th class="l" tabindex="0" data-text="1">Player</th><th tabindex="0">GP</th><th tabindex="0">Shifts</th><th tabindex="0">Ice time</th><th tabindex="0" aria-sort="descending">Per game</th><th tabindex="0">Play time</th><th tabindex="0">Avg shift</th><th tabindex="0">Longest</th><th tabindex="0">Shortest</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="note">Click a column to sort. Ice time is real elapsed time on the ice, including stoppages; play time counts only live play (estimated from the video).</p></section>
</div>
{SORT_JS}</body></html>"""
open(f"{ROOT}/docs/index.html", "w").write(page)
open(f"{ROOT}/docs/.nojekyll", "w").write("")
write_feed(ROOT, games, docs, season)
print(f"built {len(games)} game(s) -> docs/ (+ api/ feed)")
