"""gantt.py SHIFTS.csv SEGS.csv OUT.png T0 T1 : per-player shift bars + labeled segments + on-ice count."""
import sys, pandas as pd, numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
R = pd.read_csv(sys.argv[1]); S = pd.read_csv(sys.argv[2]); out = sys.argv[3]; T0, T1 = float(sys.argv[4]), float(sys.argv[5])
players = sorted(R.player.unique())
fig, ax = plt.subplots(2, 1, figsize=(24, 9), sharex=True, gridspec_kw={"height_ratios": [4, 1]})
for k, p in enumerate(players):
    for _, r in R[R.player == p].iterrows():
        ax[0].barh(k, r.t1 - r.t0, left=r.t0, height=0.6, color="tab:blue", alpha=0.35)
        ax[0].text(r.t0, k + 0.33, f"{r.dur:.0f}s", fontsize=7)
    for _, s in S[S.plabel == p].iterrows():
        ax[0].plot([s.t0, s.t1], [k, k], lw=3, color="tab:green" if s.num == p else "tab:orange")
        if s.bench0: ax[0].plot(s.t0, k, ">", color="k", ms=5)
        if s.bench1: ax[0].plot(s.t1, k, "<", color="r", ms=5)
un = S[S.plabel == -1]
for _, s in un.iterrows():
    ax[0].plot([s.t0, s.t1], [-1 - (s.chain % 3) * 0.3] * 2, lw=2, color="gray")
ax[0].set_yticks(range(-1, len(players))); ax[0].set_yticklabels(["unlab"] + [f"#{p}" for p in players])
ts = np.arange(T0, T1, 0.5)
cnt = [((R.t0 <= t) & (R.t1 >= t)).sum() for t in ts]
ax[1].plot(ts, cnt); ax[1].axhline(5, color="r", lw=0.8); ax[1].set_ylabel("# on ice (shifts)")
ax[1].set_xticks(np.arange(T0, T1 + 1, 20)); ax[1].set_xlim(T0, T1)
for a in ax: a.grid(alpha=0.3)
plt.tight_layout(); plt.savefig(out, dpi=65)
