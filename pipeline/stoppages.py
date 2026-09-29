"""Find stoppages (whistle -> puck drop) from player motion, and each shift's live play time.

Puck drop: everyone on the ice stands nearly still for 3+ s (faceoff setup), then bursts into motion.
Whistle: the last second of game-speed skating before that setup (players coast to their spots after a
whistle). The recordings have no usable audio, so this is all from video. Quick whistles whose faceoff
never gets still enough are missed, so play time is an upper-bound estimate.

stoppages.py FULLDIR PERIODS.json SHIFTS.csv  -> adds a "play" column to SHIFTS.csv, writes stoppages.json next to it
"""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from track import load

FPS = 8
STILL, BURST, LIVE_PACE, MAX_STOP = 0.6, 1.0, 1.9, 75


def speed_per_second(full):
    """75th percentile skating speed (body-heights/s) of everyone on the ice, per second."""
    d = load(f"{full}/dets.csv")
    d = d[(d.fy > d.board + 5) & (d.conf >= 0.3)]
    fr = {f: g[["fx", "fy", "h"]].values for f, g in d.groupby("frame")}
    rows = []
    for f, a in fr.items():
        b = fr.get(f + 1)
        if b is None:
            continue
        D = np.hypot(a[:, None, 0] - b[None, :, 0], a[:, None, 1] - b[None, :, 1])
        v = D.min(1) / a[:, 2] * FPS
        v = v[v < 8]
        if len(v) >= 4:
            rows.append((f / FPS, np.quantile(v, 0.75)))
    s = pd.DataFrame(rows, columns=["t", "v"])
    T = int(s.t.max()) + 1
    return s.groupby(s.t.astype(int)).v.median().reindex(range(T)).interpolate().rolling(3, center=True, min_periods=1).median().values


def drops(v, lo, hi, still=STILL, min_still=3, burst=BURST):
    out, st = [], None
    for t in range(lo, min(hi, len(v))):
        if v[t] <= still:
            st = t if st is None else st
        else:
            if st is not None and t - st >= min_still and v[t:t + 3].max() >= burst:
                out.append((st, t))
            st = None
    return out


def find_stoppages(v, periods):
    spans = []
    for p in periods:
        a, b = int(p["start"]), int(p["end"])
        ds = drops(v, a, b)
        # the period's opening faceoff is often a slow, milling setup: look for it more loosely
        first = drops(v, a, min(a + 60, b), still=0.8, min_still=2, burst=1.2)
        if first and (not ds or first[0][1] < ds[0][1] - 5):
            ds = [first[0]] + ds
        prev_drop = a
        for k, (s, e) in enumerate(ds):
            if k == 0 and s - a < 60:
                w = a                          # from the period start to its opening puck drop
            else:
                lo = max(s - MAX_STOP, prev_drop)
                fast = [t for t in range(lo, s) if v[t] >= LIVE_PACE]
                w = fast[-1] + 1 if fast else lo
            spans.append((w, e))
            prev_drop = e
    return spans


def main():
    full, pjson, shifts = sys.argv[1:4]
    periods = json.load(open(pjson))
    v = speed_per_second(full)
    spans = find_stoppages(v, periods)
    T = max(len(v), int(max(p["end"] for p in periods)) + 1)
    live = np.zeros(T, bool)
    for p in periods:
        live[int(p["start"]):int(p["end"])] = True
    for a, b in spans:
        live[a:b] = False
    A = pd.read_csv(shifts)
    A["play"] = [int(live[int(r.t0):int(r.t1)].sum()) for r in A.itertuples()]
    A.to_csv(shifts, index=False)
    json.dump([[int(a), int(b)] for a, b in spans], open(os.path.join(os.path.dirname(os.path.abspath(shifts)), "stoppages.json"), "w"))
    for p in periods:
        a, b = int(p["start"]), int(p["end"])
        print(f"{p['label']}: {sum(1 for s in spans if a <= s[0] < b)} stoppages, live {live[a:b].mean():.0%}")


if __name__ == "__main__":
    main()
