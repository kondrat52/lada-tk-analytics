"""build_report.py GAMEDIR OUT.html : GAMEDIR/game.json + GAMEDIR/shifts.csv -> one game's report page."""
import sys, os, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roster import SKATERS, GOALIES, TEAM

METHOD = [
    "Every player on the ice was detected and tracked in the 4K wide-cut video at 8 frames per second, and sorted into teams by jersey color.",
    "Players were identified from the numbers and names on their jerseys, read automatically and then checked by eye against a reference card of each player's gear. That check also caught moments where the tracker swapped two teammates.",
    "A shift runs from the moment a player steps onto the ice to the moment he steps off, so it includes stoppages. The video has no game clock, so all times are real elapsed time, and period lengths are measured from the video too.",
    "Shift edges are accurate to within a few seconds. Gaps under 15 seconds were treated as the tracker briefly losing a player, and hops under 20 seconds, like a player stepping on and straight back off during a change, don't count as shifts.",
]


def player_rows(A, labels):
    players = []
    for num, g in A.groupby("player"):
        per = []
        for lab in labels:
            h = g[g.period == lab]
            per.append([int(len(h)), float(h.dur.sum())] if len(h) else None)
        players.append(dict(num=int(num), name=SKATERS.get(int(num), ""), shifts=int(len(g)), toi=float(g.dur.sum()),
                            avg=float(g.dur.mean()), median=float(g.dur.median()), longest=float(g.dur.max()), per=per))
    return players


def build(gamedir, out):
    game = json.load(open(f"{gamedir}/game.json"))
    A = pd.read_csv(f"{gamedir}/shifts.csv")
    periods = game["periods"]
    goalie = f" The goalie (#{GOALIES[0]}) isn't included." if GOALIES else ""
    method = METHOD + game.get("notes", []) + [
        "Where the camera couldn't see a number (the far corners, crowds at the net), the gaps were filled on the "
        "assumption that 5 skaters are on the ice (4 during a penalty kill)." + goalie]
    data = dict(periods=periods, players=player_rows(A, [p["label"] for p in periods]),
                shifts=[dict(player=int(r.player), period=r.period, t0=float(r.t0), t1=float(r.t1)) for r in A.itertuples()],
                method=method, video=game["video"])
    html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")).read()
    for k, v in {"__TITLE__": game["title"], "__EYEBROW__": game["eyebrow"], "__TEAM__": TEAM,
                 "__OPP__": game["opponent"], "__VIDEO__": game["video"]}.items():
        html = html.replace(k, v)
    html = html.replace("__DATA__", json.dumps(data))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(html)
    return game, A


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
    print("wrote", sys.argv[2])
