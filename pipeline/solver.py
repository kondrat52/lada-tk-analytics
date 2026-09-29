"""Joint shift inference: per-player on/off HMM coupled by '5 skaters on ice' (Lagrangian relaxation).

Evidence (1-second bins):
  - labeled segments of player p  -> p is on ice during the segment
  - segment ending behind the bench boards  -> p off shortly after
  - segment starting at the bench           -> p off shortly before
Transitions are cheap near bench activity (any light-blue track starting/ending at the bench), expensive elsewhere.
"""
import numpy as np, pandas as pd

BIG = 1e3


def viterbi_all(on_cost, off_cost, trans):
    """Two-state Viterbi for all players at once. on_cost/off_cost: (P,T), trans: (T,)."""
    P, T = on_cost.shape
    B = np.zeros((T, P, 2), bool)  # True = came from the other state
    d0, d1 = off_cost[:, 0].copy(), on_cost[:, 0].copy()
    for b in range(1, T):
        sw0, sw1 = d1 + trans[b], d0 + trans[b]
        B[b, :, 0] = sw0 < d0; B[b, :, 1] = sw1 < d1
        d0, d1 = np.minimum(d0, sw0) + off_cost[:, b], np.minimum(d1, sw1) + on_cost[:, b]
    st = np.zeros((P, T), np.int8); cur = (d1 < d0).astype(np.int8); st[:, -1] = cur
    ar = np.arange(P)
    for b in range(T - 1, 0, -1):
        cur = np.where(B[b, ar, cur], 1 - cur, cur).astype(np.int8)
        st[:, b - 1] = cur
    return st


def solve(S, players, T, bench_events, target=None, iters=300, active=None,
          w_direct=3.0, w_prop=1.2, w_bench=1.5, tr_base=10.0, tr_bench=1.5):
    """S: segments with t0,t1,plabel,num,nreads,bench0,bench1,r0,r1. T: number of 1s bins.
    bench_events: array of times (s) of light-blue track starts/ends at the bench.
    target: (T,) desired skaters on ice (default 5). active: (T,) bool, bins where the game is live."""
    P = len(players); idx = {p: k for k, p in enumerate(players)}
    on_c = np.zeros((P, T)); off_c = np.zeros((P, T))
    for _, s in S[S.plabel.isin(players)].iterrows():
        k = idx[s.plabel]
        a, b = int(np.floor(s.t0)), int(np.ceil(s.t1))
        w = w_direct * min(1.0, 0.4 + 0.2 * s.nreads) if s.num == s.plabel else w_prop
        off_c[k, a:b + 1] += w
        if s.bench1 and s.r1 < 10:
            on_c[k, b + 3:b + 20] += w_bench
        if s.bench0 and s.r0 < 10:
            on_c[k, max(a - 20, 0):max(a - 2, 0)] += w_bench
    trans = np.full(T, tr_base)
    for e in bench_events:
        trans[max(int(e) - 4, 0):int(e) + 5] = tr_bench
    if target is None:
        target = np.full(T, 5.0)
    if active is not None:
        on_c[:, ~active] += BIG  # nobody on ice during breaks
        trans[~active] = 0.0
        target = np.where(active, target, 0)
    lam = np.zeros(T); best = None
    for it in range(iters):
        st = viterbi_all(on_c + lam, off_c, trans)
        cnt = st.sum(0)
        err = cnt - target
        viol = np.abs(err).sum()
        if best is None or viol < best[0]:
            best = (viol, st.copy())
        if viol == 0:
            break
        step = 1.0 / (1 + it / 30)
        lam += step * np.sign(err) * 0.5
    return best[1], best[0]


def to_shifts(st, players, active=None):
    rows = []
    for k, p in enumerate(players):
        s = np.r_[0, st[k], 0]
        d = np.diff(s)
        for a, b in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            rows.append(dict(player=p, t0=a, t1=b, dur=b - a))
    return pd.DataFrame(rows).sort_values(["player", "t0"]).reset_index(drop=True)
