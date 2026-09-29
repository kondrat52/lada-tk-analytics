"""final_stats.py P1DIR[:label] P2DIR[:label] ... : merge/clean per-period shifts, print + save per-player stats."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd

from roster import SKATERS as NAMES
MERGE_GAP, MIN_SHIFT = 15, 20   # gaps < 15 s = tracking loss; < 20 s on ice = a hop, not a shift


def clean(R):
    out = []
    for p, g in R.sort_values("t0").groupby("player"):
        cur = None
        for _, r in g.iterrows():
            if cur is not None and r.t0 - cur["t1"] < MERGE_GAP:
                cur["t1"] = r.t1
            else:
                if cur is not None:
                    out.append(cur)
                cur = dict(player=p, t0=r.t0, t1=r.t1)
        out.append(cur)
    C = pd.DataFrame(out)
    C["dur"] = C.t1 - C.t0
    return C[C.dur >= MIN_SHIFT].reset_index(drop=True)


if __name__ == "__main__":
    allsh = []
    for k, arg in enumerate(sys.argv[1:], 1):
        d, _, lab = arg.partition(":")
        R = clean(pd.read_csv(f"{d}/shifts_final.csv"))
        R["period"] = lab or str(k)
        allsh.append(R)
    A = pd.concat(allsh, ignore_index=True)
    A.to_csv("shifts_all.csv", index=False)
    st = A.groupby("player").dur.agg(shifts="count", toi="sum", avg="mean", median="median", longest="max", shortest="min")
    per = A.pivot_table(index="player", columns="period", values="dur", aggfunc=["count", "sum"], fill_value=0)
    st["name"] = st.index.map(NAMES)
    fmt = lambda s: f"{int(s // 60)}:{int(round(s % 60)):02d}"
    show = st.copy()
    for c in ["toi", "avg", "median", "longest", "shortest"]:
        show[c] = show[c].map(fmt)
    print(show.sort_values("toi", ascending=False).to_string())
    print(per.to_string())
    st.to_csv("stats_by_player.csv")
