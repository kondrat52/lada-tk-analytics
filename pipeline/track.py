"""Offline tracker for light-blue players (on ice + bench zone). Foot-point constant-velocity + Hungarian."""
import os, numpy as np, pandas as pd, sys
from scipy.optimize import linear_sum_assignment
FPS = 8

def load(path):
    """path: dets.csv (may be a symlink). The far-boards curve boards_poly.npy (from boards.py) sits next to
    the real file."""
    P = np.load(os.path.join(os.path.dirname(os.path.realpath(path)), "boards_poly.npy"))
    d = pd.read_csv(path, header=None, names="frame t x1 y1 x2 y2 conf blue white purple red dark lblue".split())
    d["i"] = d.groupby("frame").cumcount()
    d["fx"] = (d.x1 + d.x2) / 2; d["fy"] = d.y2; d["h"] = d.y2 - d.y1
    d["board"] = np.polyval(P, d.fx)
    d["onice"] = d.fy > d.board + 5
    return d

def track(d, max_lost=24, gate=1.0):
    d = d.sort_values(["frame", "i"]).reset_index(drop=True)
    tid = np.full(len(d), -1); nxt = 0
    tracks = {}  # id -> dict(x,y,h,vx,vy,lost)
    for f, g in d.groupby("frame", sort=True):
        ids = list(tracks.keys())
        idx = g.index.values
        if ids and len(idx):
            C = np.full((len(ids), len(idx)), 1e6)
            for a, k in enumerate(ids):
                T = tracks[k]; dt = T["lost"] + 1
                px, py = T["x"] + T["vx"] * dt, T["y"] + T["vy"] * dt
                hh = 0.5 * (T["h"] + g.h.values)
                dist = np.hypot(g.fx.values - px, (g.fy.values - py) * 1.5) / hh
                lim = gate * (1 + 0.25 * min(T["lost"], 8))
                hr = np.abs(np.log(g.h.values / T["h"]))
                c = dist + 2 * hr
                C[a] = np.where((dist < lim) & (hr < 0.5), c, 1e6)
            r, c = linear_sum_assignment(C)
            used = set()
            for a, b in zip(r, c):
                if C[a, b] >= 1e6: continue
                k = ids[a]; T = tracks[k]; row = d.loc[idx[b]]; dt = T["lost"] + 1
                vx, vy = (row.fx - T["x"]) / dt, (row.fy - T["y"]) / dt
                T.update(vx=0.6 * vx + 0.4 * T["vx"], vy=0.6 * vy + 0.4 * T["vy"], x=row.fx, y=row.fy,
                         h=0.7 * T["h"] + 0.3 * row.h, lost=0, n=T["n"] + 1)
                tid[idx[b]] = k; used.add(b)
            for a, k in enumerate(ids):
                if a not in r or C[a, c[list(r).index(a)]] >= 1e6:
                    tracks[k]["lost"] += 1
        else:
            used = set()
            for k in ids: tracks[k]["lost"] += 1
        for b, j in enumerate(idx):
            if b in used: continue
            row = d.loc[j]
            tracks[nxt] = dict(x=row.fx, y=row.fy, h=row.h, vx=0.0, vy=0.0, lost=0, n=1)
            tid[j] = nxt; nxt += 1
        for k in [k for k, T in tracks.items() if T["lost"] > max_lost]:
            del tracks[k]
    d["tid"] = tid
    return d

if __name__ == "__main__":
    d = load(sys.argv[1])
    lb = d[(d.blue >= 0.3) & (d.conf >= 0.3) & (d.onice | ((d.fx > 1300) & (d.fx < 1800) & (d.fy > d.board - 80)))]
    t = track(lb)
    L = t.groupby("tid").agg(n=("frame", "size"), f0=("frame", "min"), f1=("frame", "max"))
    L["dur"] = (L.f1 - L.f0 + 1) / FPS
    print("tracks:", len(L)); print(L.dur.describe().round(1).to_dict())
    print("tracks >5s:", (L.dur > 5).sum(), " >20s:", (L.dur > 20).sum())
    print(L.sort_values("dur", ascending=False).head(15).to_string())
    t.to_csv(sys.argv[2], index=False)
