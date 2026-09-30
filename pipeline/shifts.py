"""Tracks + OCR reads -> labeled segments -> per-player shifts.

Usage: shifts.py OUTDIR TMAX
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from track import load, track
from reads import load_reads
from rink import rink

FPS = 8
from roster import SKATERS, GOALIES
ROSTER = sorted(SKATERS)
GOALIE = GOALIES[0] if GOALIES else -1
LOOKALIKE = {frozenset(p) for p in [(18, 78), (13, 33), (12, 82), (13, 18), (89, 68), (74, 4), (14, 4), (26, 28)]}


def goalie_zone(d, nets, R):
    """nets: list of (t0, t1, net_x). Drops detections standing in the light-blue crease."""
    drop = np.zeros(len(d), bool)
    for t0, t1, nx in nets:
        drop |= (d.t >= t0) & (d.t < t1) & R.in_crease(d.fx, d.rel, nx)
    return d[~drop]


def partial_ok(read, num):
    """Single digit read compatible with roster number (e.g. 3 -> 33/13, 8 -> 78/18)."""
    s, n = str(read), str(num)
    return len(s) == 1 and s in n and len(n) == 2


def segment_track(reads):
    """reads: list of (t, num, weight) sorted by t. Returns list of (t_start, t_end, num, weight) label runs.
    Only full roster numbers define runs (partial digits are ignored)."""
    full = [(t, n, w) for t, n, w in reads if n in ROSTER]
    if not full:
        return []
    runs = []
    for t, n, w in full:
        if runs and runs[-1][2] == n:
            runs[-1][1] = t; runs[-1][3] += w
        else:
            runs.append([t, t, n, w])
    # drop runs that look like misreads: lone reads next to a longer run, or a short run
    # sandwiched between two runs of the same other number (A B A), or a look-alike
    # number (18/78, 13/33, 12/82) that is outnumbered by its partner within the track.
    changed = True
    while changed and len(runs) > 1:
        changed = False
        tot = {}
        for r in runs:
            tot[r[2]] = tot.get(r[2], 0) + r[3]
        for k, r in enumerate(runs):
            nbr = [runs[j] for j in (k - 1, k + 1) if 0 <= j < len(runs)]
            lone = r[3] <= 1 and max(x[3] for x in nbr) >= 2
            sandwich = len(nbr) == 2 and nbr[0][2] == nbr[1][2] and r[3] < nbr[0][3] + nbr[1][3] \
                and (nbr[1][0] - nbr[0][1]) < 40
            partner = [n for n in tot if n != r[2] and frozenset((n, r[2])) in LOOKALIKE]
            lookalike = r[3] <= 2 and any(tot[n] >= 3 * tot[r[2]] for n in partner)
            if lone or sandwich or lookalike:
                runs.pop(k); changed = True; break
        # re-merge neighbours with same label
        m = []
        for r in runs:
            if m and m[-1][2] == r[2]:
                m[-1][1] = r[1]; m[-1][3] += r[3]
            else:
                m.append(r)
        runs = m
    return [(a, b, n, c) for a, b, n, c in runs]


def build(outdir, tmax, nets, tmin=0.0):
    R = rink(outdir)
    d = load(f"{outdir}/dets.csv")
    d = d[(d.t >= tmin) & (d.t <= tmax)]
    d["rel"] = d.fy - d.board
    lb = d[(d.blue >= 0.3) & (d.conf >= 0.3) & (d.onice | R.bench_zone(d.fx, d.rel))]
    lb = goalie_zone(lb, nets, R)
    t = track(lb)
    dig, _ = load_reads(outdir)
    dig = dig.merge(t[["frame", "i", "tid", "t"]], on=["frame", "i"])
    dig = dig[dig.num != GOALIE]
    dig["w"] = np.where(dig.src == "name", 2, 1)

    segs = []  # tid, t0, t1, num (or -1), start pos, end pos
    for k, g in t.sort_values("t").groupby("tid"):
        if len(g) < 4:
            continue
        rd = dig[dig.tid == k].sort_values("t")
        runs = segment_track(list(zip(rd.t, rd.num, rd.w)))
        T0, T1 = g.t.iloc[0], g.t.iloc[-1]
        if not runs:
            cuts = [(T0, T1, -1, 0)]
        else:
            cuts = []
            for j, (a, b, n, c) in enumerate(runs):
                s = T0 if j == 0 else (runs[j - 1][1] + a) / 2
                e = T1 if j == len(runs) - 1 else (b + runs[j + 1][0]) / 2
                cuts.append((s, e, n, c))
        for s, e, n, c in cuts:
            gg = g[(g.t >= s) & (g.t <= e)]
            if len(gg) == 0:
                continue
            f, l = gg.iloc[0], gg.iloc[-1]
            segs.append(dict(tid=k, t0=f.t, t1=l.t, num=n, nreads=c,
                             x0=f.fx, r0=f.rel, x1=l.fx, r1=l.rel))
    S = pd.DataFrame(segs)
    S["bench0"] = R.at_bench(S.x0, S.r0)
    S["bench1"] = R.at_bench(S.x1, S.r1)
    return t, S


def link(S, R, max_gap=2.5):
    """Chain unlabeled segments to neighbours: end of A -> start of B, short gap, close position.
    Returns S with 'chain' ids; labels propagate within a chain when unambiguous. R: the rink (rink.py)."""
    S = S.sort_values("t0").reset_index(drop=True)
    behind = np.asarray(R.bench_depth(S.x1, S.r1)) > 10
    nxt = {}
    ends = S.sort_values("t1")
    taken = set()
    for i, a in ends.iterrows():
        if a.bench1 and behind[i]:
            continue  # went behind the boards
        cand = S[(S.t0 > a.t1 - 0.2) & (S.t0 < a.t1 + max_gap) & (~S.index.isin(taken)) & (S.index != i)]
        if len(cand) == 0:
            continue
        dist = np.hypot(cand.x0 - a.x1, (cand.r0 - a.r1) * 1.5) / (1 + (cand.t0 - a.t1).clip(0))
        cand = cand.assign(dist=dist)
        cand = cand[cand.dist < 250]
        if a.num >= 0:
            cand = cand[(cand.num == -1) | (cand.num == a.num)]
        if len(cand) == 0:
            continue
        b = cand.sort_values("dist").index[0]
        nxt[i] = b; taken.add(b)
    chain = -np.ones(len(S), int); c = 0
    prev = {v: k for k, v in nxt.items()}
    for i in range(len(S)):
        if chain[i] >= 0 or i in prev:
            continue
        j = i
        while True:
            chain[j] = c
            if j not in nxt:
                break
            j = nxt[j]
        c += 1
    for i in range(len(S)):
        if chain[i] < 0:
            chain[i] = c; c += 1
    S["chain"] = chain
    lab = S[S.num >= 0].groupby("chain").num.agg(lambda s: s.mode().iloc[0] if s.nunique() == 1 else -2)
    S["plabel"] = S.chain.map(lab).fillna(-1).astype(int)
    S.loc[S.num >= 0, "plabel"] = S.num
    return S


def shifts_from(S, merge_gap=30):
    """Per player: merge labeled segments into shifts. Break when the player goes behind the bench boards."""
    rows = []
    for p, g in S[S.plabel >= 0].sort_values("t0").groupby("plabel"):
        cur = None
        for _, s in g.iterrows():
            if cur is None:
                cur = dict(player=p, t0=s.t0, t1=s.t1, start_bench=bool(s.bench0), end_bench=bool(s.bench1), nseg=1)
                continue
            gap = s.t0 - cur["t1"]
            breaks = (cur["end_bench"] and s.bench0 and gap > 4) or gap > merge_gap
            if breaks:
                rows.append(cur)
                cur = dict(player=p, t0=s.t0, t1=s.t1, start_bench=bool(s.bench0), end_bench=bool(s.bench1), nseg=1)
            else:
                cur["t1"] = max(cur["t1"], s.t1); cur["end_bench"] = bool(s.bench1); cur["nseg"] += 1
        rows.append(cur)
    R = pd.DataFrame(rows)
    R["dur"] = R.t1 - R.t0
    return R


if __name__ == "__main__":
    out, tmax = sys.argv[1], float(sys.argv[2])
    nets = json.loads(sys.argv[3]) if len(sys.argv) > 3 else [(0, 1e9, 540)]
    t, S = build(out, tmax, nets)
    S = link(S, rink(out))
    t.to_csv(f"{out}/tracks_v1.csv", index=False); S.to_csv(f"{out}/segs_v1.csv", index=False)
    R = shifts_from(S)
    R.to_csv(f"{out}/shifts_v1.csv", index=False)
    pd.set_option("display.width", 200)
    print(R.round(1).to_string())
