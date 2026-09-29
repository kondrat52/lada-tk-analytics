"""roster_card.py OUTDIR OUT.jpg PER: reference crops per player from reads (name reads preferred), mixed views."""
import sys, os, subprocess, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reads import load_reads
import shifts as SH
out, dst, per = sys.argv[1], sys.argv[2], int(sys.argv[3])
tr = pd.read_csv(f"{out}/tracks_v1.csv"); sg = pd.read_csv(f"{out}/segs_v1.csv")
tr["fn"] = [f"f{int(f):06d}_{int(i):02d}.jpg" for f, i in zip(tr.frame, tr.i)]
rd, _ = load_reads(out)
items = []
for p in SH.ROSTER:
    good = sg[(sg.num == p) & (sg.nreads >= 4)]
    rows = []
    for _, s in good.iterrows():
        g = tr[(tr.tid == s.tid) & (tr.t >= s.t0) & (tr.t <= s.t1) & (tr.h >= 110)]
        g = g[[os.path.exists(f"{out}/crops/{f}") for f in g.fn]]
        if len(g): rows.append(g)
    if not rows:
        items += ["none::"] * per; continue
    g = pd.concat(rows)
    g["read"] = g.fn.isin(set(rd[rd.num == p].file))
    # half back views (with a read), half other views, spread over time
    a = g[g.read].sort_values("t"); b = g[~g.read].sort_values("t")
    na = min(len(a), per // 2); nb = min(len(b), per - na)
    pick = pd.concat([a.iloc[np.linspace(0, len(a) - 1, na).astype(int)] if na else a.iloc[:0],
                      b.iloc[np.linspace(0, len(b) - 1, nb).astype(int)] if nb else b.iloc[:0]])
    row = [f"{out}/crops/{f}::#{p} {t:.0f}s" for f, t in zip(pick.fn, pick.t)]
    items += row + ["none::"] * (per - len(row))
subprocess.run([sys.executable, os.path.dirname(os.path.abspath(__file__)) + "/sheet.py", dst, "110", "180", str(per)] + items)
