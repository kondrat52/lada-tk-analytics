"""build_site.py : render docs/ (GitHub Pages) from games/*/game.json + shifts.csv.
docs/index.html            season totals + list of games
docs/games/<id>/index.html one shift sheet per game"""
import os, sys, json, glob, html
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_report import build
from roster import SKATERS, TEAM

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
fmt = lambda s: f"{int(s // 60)}:{int(round(s % 60)):02d}"

games, allsh = [], []
for gd in sorted(glob.glob(f"{ROOT}/games/*/")):
    game, A = build(gd, f"{ROOT}/docs/games/{os.path.basename(gd.rstrip('/'))}/index.html")
    A = A.assign(game=game["id"])
    # shifts cut off by the recording ending mid-play don't count as short shifts
    cut = game["periods"][-1]["end"] if game.get("video_ends_early") else None
    A["cut"] = (A.t1 >= cut - 1) if cut else False
    games.append(game); allsh.append(A)
A = pd.concat(allsh)
per_game = A.groupby(["player", "game"]).dur.sum().reset_index()
if "play" not in A:
    A["play"] = np.nan
season = A.groupby("player").agg(shifts=("dur", "size"), toi=("dur", "sum"), play=("play", "sum"), avg=("dur", "mean"),
                                 longest=("dur", "max"))
season["shortest"] = A[~A.cut.astype(bool)].groupby("player").dur.min()
season["gp"] = per_game.groupby("player").size()
season["toi_gp"] = season.toi / season.gp
season = season.sort_values("toi_gp", ascending=False)

rows = "\n".join(
    f"<tr><td class='l num'>{p}</td><td class='l name'>{html.escape(SKATERS.get(p, ''))}</td><td>{int(r.gp)}</td>"
    f"<td>{int(r.shifts)}</td><td>{fmt(r.toi)}</td><td>{fmt(r.toi_gp)}</td><td>{fmt(r.play) if r.play > 0 else '–'}</td>"
    f"<td>{fmt(r.avg)}</td><td>{fmt(r.longest)}</td><td>{fmt(r.shortest) if r.shortest == r.shortest else '–'}</td></tr>"
    for p, r in season.iterrows())
cards = "\n".join(
    f"<li><a href='games/{g['id']}/'><span class='d'>{html.escape(g['eyebrow'])}</span>"
    f"<span class='t'>vs {html.escape(g['opponent'])}</span></a></li>"
    for g in sorted(games, key=lambda g: g["date"], reverse=True))

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
th {{ font:600 12px/1.2 var(--data); letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }}
td {{ font:500 16px/1.2 var(--data); }} .l {{ text-align:left; }} td.num {{ font:800 20px/1 var(--display); color:var(--team); width:3.2em; }} td.name {{ font:500 16px/1.2 var(--body); }}
p.note {{ color:var(--muted); margin:0; max-width:70ch; }}
</style></head><body><div class="wrap">
<header><div class="eyebrow">Rec hockey · Renton</div><h1><span>{html.escape(TEAM)}</span> shift sheets</h1>
<p class="note">Ice time and shifts for every skater, measured from each week's wide-cut game video.</p></header>
<section><h2>Games</h2><ul class="games">{cards}</ul></section>
<section><h2>Season</h2><div class="tablebox"><table><thead><tr><th class="l">#</th><th class="l">Player</th><th>GP</th><th>Shifts</th><th>Ice time</th><th>Per game</th><th>Play time</th><th>Avg shift</th><th>Longest</th><th>Shortest</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="note">Sorted by ice time per game. Ice time is real elapsed time on the ice, including stoppages; play time counts only live play (estimated from the video).</p></section>
</div></body></html>"""
open(f"{ROOT}/docs/index.html", "w").write(page)
open(f"{ROOT}/docs/.nojekyll", "w").write("")
print(f"built {len(games)} game(s) -> docs/")
