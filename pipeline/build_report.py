"""build_report.py GAMEDIR OUT.html : GAMEDIR/game.json + GAMEDIR/shifts.csv -> one game's report page."""
import sys, os, json
from itertools import combinations
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roster import SKATERS, TEAM



def player_rows(A, labels, cut=None):
    """cut: video time where the recording stops mid-play; shifts ending there don't count as shortest."""
    players = []
    for num, g in A.groupby("player"):
        full = g[g.t1 < cut - 1] if cut else g
        per = []
        for lab in labels:
            h = g[g.period == lab]
            per.append([int(len(h)), float(h.dur.sum()), float(h.dur.mean())] if len(h) else None)
        players.append(dict(num=int(num), name=SKATERS.get(int(num), ""), shifts=int(len(g)), toi=float(g.dur.sum()),
                            avg=float(g.dur.mean()), median=float(g.dur.median()), longest=float(g.dur.max()),
                            shortest=float(full.dur.min()) if len(full) else None,
                            play=float(g.play.sum()) if "play" in g else None, per=per))
    return players


def fun_stats(A, game):
    """Duos, most-used five, shift length by period, quickest changer, PK crew (+ optional OCR/pipeline extras)."""
    T = int(A.t1.max()) + 2
    on = {int(p): np.zeros(T, bool) for p in A.player.unique()}
    for r in A.itertuples():
        on[int(r.player)][int(r.t0):int(r.t1)] = True
    pairs = sorted(((int((on[a] & on[b]).sum()), a, b) for a, b in combinations(sorted(on), 2)), reverse=True)[:3]
    units = {}
    M = np.array([on[p] for p in sorted(on)]); nums = sorted(on)
    for t in range(T):
        k = tuple(n for n, x in zip(nums, M[:, t]) if x)
        if len(k) == 5:
            units[k] = units.get(k, 0) + 1
    unit = max(units.items(), key=lambda x: x[1]) if units else None
    per = [dict(label=p["label"], avg=float(A[A.period == p["label"]].dur.mean()), n=int((A.period == p["label"]).sum()))
           for p in game["periods"] if (A.period == p["label"]).any()]
    g = A.groupby("player").dur.agg(["mean", "size"])
    elig = g[g["size"] >= 5]
    quick = elig["mean"].idxmin() if len(elig) else None
    most_n = int(g["size"].max())
    pks = []
    for k in game.get("penalty_kills", []):
        pstart = next(p["start"] for p in game["periods"] if p["label"] == k["period"])
        crew = sorted(((int(on[n][int(k["start"]):int(k["end"])].sum()), n) for n in on), reverse=True)
        pks.append(dict(period=k["period"], from_=k["start"] - pstart, to=k["end"] - pstart, player=k.get("player"),
                        crew=[dict(num=n, sec=s) for s, n in crew if s >= 15]))
    extra = game.get("fun", {})
    reads = sorted(({"num": int(n), "n": int(c)} for n, c in extra.get("name_reads", {}).items()), key=lambda x: -x["n"])
    return dict(pairs=[dict(a=a, b=b, sec=s) for s, a, b in pairs],
                unit=dict(players=list(unit[0]), sec=unit[1]) if unit else None,
                periods=per,
                quickest=dict(num=int(quick), avg=float(elig.loc[quick, "mean"])) if quick is not None else None,
                most=dict(nums=[int(n) for n in g.index[g["size"] == most_n]], n=most_n),
                pk=[{**{k: v for k, v in p.items() if k != "from_"}, "from": p["from_"]} for p in pks],
                reads=reads, pipeline=game.get("pipeline"))


def highlights(A, game):
    """Clips listed in game.json, with the period, and who was on the ice for goals."""
    out = []
    for h in game.get("highlights", []):
        per = next((p for p in game["periods"] if p["start"] <= h["t"] <= p["end"]), None)
        on = sorted(int(r.player) for r in A.itertuples() if r.t0 <= h["t"] < r.t1) if h["type"] == "goal" else []
        out.append(dict(h, period=per["label"] if per else "", on_ice=on))
    return out


def build(gamedir, out):
    game = json.load(open(f"{gamedir}/game.json"))
    A = pd.read_csv(f"{gamedir}/shifts.csv")
    periods = game["periods"]
    cut = periods[-1]["end"] if game.get("video_ends_early") else None
    data = dict(periods=periods, players=player_rows(A, [p["label"] for p in periods], cut),
                highlights=highlights(A, game), opponent=game["opponent"], team=TEAM,
                stoppages=game.get("stoppages", []),
                shifts=[dict(player=int(r.player), period=r.period, t0=float(r.t0), t1=float(r.t1)) for r in A.itertuples()],
                video=game["video"], fun=fun_stats(A, game))
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
