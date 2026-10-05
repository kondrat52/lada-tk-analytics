"""build_trends.py : docs/trends.html, the team's trends across games, from games/*/game.json + shifts.csv.
build_site.py runs it. Time in offence and defence come from game.json's `zones` (zones.py, filled in on publish),
shots on goal from its `shots` (shots.py, read off the arena scoreboard)."""
import os, sys, json, glob
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roster import SKATERS, SUBS, TEAM, opponent_name

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def penalties(game):
    """Our penalties: penalty kills, with one carried over an intermission (same player, next period) counted once."""
    out = []
    for k in sorted(game.get("penalty_kills", []), key=lambda k: k["start"]):
        if out and out[-1]["player"] == k.get("player") and k["start"] - out[-1]["end"] < 200:
            out[-1]["end"] = k["end"]
        else:
            out.append(dict(player=k.get("player"), start=k["start"], end=k["end"]))
    return out


def game_rows(gd):
    game = json.load(open(f"{gd}/game.json"))
    A = pd.read_csv(f"{gd}/shifts.csv")
    periods = game["periods"]
    length = sum(p["end"] - p["start"] for p in periods)
    T = int(max(p["end"] for p in periods)) + 2
    live = np.zeros(T, bool)
    for p in periods:
        live[p["start"]:p["end"]] = True
    for a, b in game.get("stoppages", []):
        live[int(a):int(b)] = False
    goals = [h for h in game.get("highlights", []) if h["type"] == "goal"]
    gf = sum(h["team"] == "for" for h in goals); ga = sum(h["team"] == "against" for h in goals)
    pks = game.get("penalty_kills", [])
    in_pk = lambda t: any(k["start"] <= t < k["end"] for k in pks)
    zones = game.get("zones") or {}
    shots = game.get("shots") or {}          # {"P1": [ours, theirs], ...} from the arena scoreboard
    sp = [shots[p["label"]] for p in periods if p["label"] in shots] or None
    team = dict(
        id=game["id"], date=game["date"], opp=opponent_name(game), opp_code=game["opponent"],
        rink=(game.get("eyebrow") or "").split("·")[-1].strip(), gf=gf, ga=ga,
        result="W" if gf > ga else ("L" if gf < ga else "T"), video_ends_early=bool(game.get("video_ends_early")),
        skaters=int(A.player.nunique()), avg_shift=float(A.dur.mean()), live_pct=float(live.sum() / length),
        penalties=len(penalties(game)), pk_ga=sum(h["team"] == "against" and in_pk(h["t"]) for h in goals),
        pk_min=float(sum(k["end"] - k["start"] for k in pks) / 60),
        offence=zones.get("offence"), defence=zones.get("defence"),
        sp=sp, sf=sum(x[0] for x in sp) if sp else None, sa=sum(x[1] for x in sp) if sp else None)
    players = []
    team_toi = A.dur.sum()
    for num, s in A.groupby("player"):
        on = np.zeros(T, bool)
        for r in s.itertuples():
            on[int(r.t0):int(r.t1)] = True
        by = s.groupby("period").dur.mean()
        players.append(dict(
            game=game["id"], num=int(num), name=SKATERS.get(int(num), ""), sub=int(num) in SUBS,
            shifts=int(len(s)), toi=float(s.dur.sum()), avg_shift=float(s.dur.mean()),
            toi_share=float(s.dur.sum() / team_toi), equal_share=1 / A.player.nunique(),
            p1=float(by["P1"]) if "P1" in by else None, p3=float(by["P3"]) if "P3" in by else None,
            plus_minus=sum((1 if h["team"] == "for" else -1) for h in goals if on[min(int(h["t"]), T - 1)])))
    return team, players


def build(root=ROOT):
    team, players = [], []
    for gd in sorted(glob.glob(f"{root}/games/*/")):
        t, p = game_rows(gd)
        team.append(t); players += p
    html = open(f"{HERE}/trends_template.html").read()
    html = html.replace("__TEAM__", TEAM).replace("__DATA__", json.dumps(dict(team=team, players=players), separators=(",", ":")))
    open(f"{root}/docs/trends.html", "w").write(html)
    return len(team)


if __name__ == "__main__":
    print(f"trends over {build()} game(s) -> docs/trends.html")
