"""review_sheets.py OUTDIR REVDIR [ROWS_PER_SHEET]
Pick segments needing visual review and render sheets: one row per segment, crops spread over its time span.
Writes REVDIR/sheet_XXX.jpg and REVDIR/manifest.csv (sheet,row_id,seg_idx,tid,t0,t1,crop_times)."""
import sys, os, subprocess, numpy as np, pandas as pd
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
from rink import rink
out, rev = sys.argv[1], sys.argv[2]
per_sheet = int(sys.argv[3]) if len(sys.argv) > 3 else 8
NC = 10
os.makedirs(rev, exist_ok=True)
tr = pd.read_csv(f"{out}/tracks_v1.csv"); sg = pd.read_csv(f"{out}/segs_v1.csv")
tr["fn"] = [f"f{int(f):06d}_{int(i):02d}.jpg" for f, i in zip(tr.frame, tr.i)]
exists = set(os.listdir(f"{out}/crops"))
tr = tr[tr.fn.isin(exists)]
sg["dur"] = sg.t1 - sg.t0
# review: anything >= 3 s that is not strongly and unambiguously read, plus all long segments (swap check)
multi = sg.groupby("tid").num.transform(lambda s: s[s >= 0].nunique())
need = (sg.dur >= 3) & ((sg.num < 0) | (sg.nreads < 6) | (multi > 1) | (sg.dur >= 25))
tr["depth"] = rink(out).bench_depth(tr.fx, tr.rel)
meddepth = tr.groupby("tid").depth.median()
onice = sg.tid.map(meddepth) < 15   # skip people sitting behind the bench boards
cand = sg[need & onice].sort_values("t0")
rows = []
for idx, s in cand.iterrows():
    g = tr[(tr.tid == s.tid) & (tr.t >= s.t0) & (tr.t <= s.t1)]
    if len(g) < 3:
        continue
    # spread over time; within each time slice prefer the largest crop
    bins = np.linspace(s.t0, s.t1 + 1e-6, NC + 1)
    pick = []
    for a, b in zip(bins[:-1], bins[1:]):
        gg = g[(g.t >= a) & (g.t < b)]
        if len(gg):
            pick.append(gg.loc[gg.h.idxmax()])
    if len(pick) < 2:
        continue
    rows.append((idx, s, pick))
man = []
for k in range(0, len(rows), per_sheet):
    chunk = rows[k:k + per_sheet]
    sheet = f"sheet_{k // per_sheet:03d}.jpg"
    items = []
    for j, (idx, s, pick) in enumerate(chunk):
        rid = f"R{k + j}"
        items += [f"{out}/crops/{p.fn}::{rid} {p.t:.0f}s" for p in pick] + ["none::"] * (NC - len(pick))
        man.append(dict(sheet=sheet, row_id=rid, seg_idx=idx, tid=s.tid, t0=round(s.t0, 2), t1=round(s.t1, 2),
                        auto=s.plabel, crop_times=" ".join(f"{p.t:.0f}" for p in pick)))
    subprocess.run([sys.executable, f"{here}/sheet.py", f"{rev}/{sheet}", "110", "180", str(NC)] + items,
                   stderr=subprocess.DEVNULL)
pd.DataFrame(man).to_csv(f"{rev}/manifest.csv", index=False)
print(len(man), "rows in", (len(rows) + per_sheet - 1) // per_sheet, "sheets")
