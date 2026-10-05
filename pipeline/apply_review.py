"""Merge visual-review labels into segments (segs_v1.csv index == manifest seg_idx)."""
import io, re, numpy as np, pandas as pd

W = {"high": 8, "med": 4}


def parse_review(text):
    """Extract the CSV block from a reviewer's answer."""
    cols = ["row_id", "player", "confidence", "switch_time", "player2", "confidence2", "note"]
    rows = []
    for l in text.splitlines():
        if not re.match(r"^\s*R?\d+\s*,", l):   # reviewers sometimes drop the R
            continue
        f = [x.strip().strip('"') for x in l.split(",")]
        f[0] = "R" + f[0].lstrip("R")
        f = f[:6] + [",".join(f[6:])] if len(f) > 7 else f + [""] * (7 - len(f))
        f[1] = f[1].lstrip("#"); f[4] = f[4].lstrip("#")
        rows.append(f)
    return pd.DataFrame(rows, columns=cols)


def _endpoints(tr, tid, t0, t1):
    g = tr[(tr.tid == tid) & (tr.t >= t0) & (tr.t <= t1)].sort_values("t")
    if len(g) == 0:
        return None
    f, l = g.iloc[0], g.iloc[-1]
    return dict(t0=f.t, t1=l.t, x0=f.fx, r0=f.rel, x1=l.fx, r1=l.rel)


def apply(S, tr, review, manifest, R):
    """S: segments (post-link, index = seg_idx); R: the rink (rink.py). Returns new segment table with review labels:
    columns num (label), nreads (weight), src ('ocr'|'review'), goalie flag rows removed."""
    S = S.copy(); S["src"] = np.where(S.num >= 0, "ocr", "")
    m = manifest.merge(review, on="row_id", how="inner")
    new_rows, drop = [], []
    for _, r in m.iterrows():
        i = r.seg_idx
        if i not in S.index:
            continue
        s = S.loc[i]
        p1 = r.player; c1 = r.confidence
        if p1 == "G":
            drop.append(i); continue
        if r.switch_time and r.player2:
            try:
                ts = float(r.switch_time)
            except ValueError:
                ts = None
            if ts is not None and s.t0 < ts < s.t1:
                drop.append(i)
                for (a, b, p, c) in [(s.t0, ts, p1, c1), (ts, s.t1, r.player2, r.confidence2)]:
                    e = _endpoints(tr, s.tid, a, b)
                    if e is None:
                        continue
                    row = s.to_dict(); row.update(e)
                    if p.isdigit() and c in W:
                        row.update(num=int(p), nreads=W[c], src="review")
                    elif p == "G":
                        continue
                    else:
                        row.update(num=-1, nreads=0, src="")
                    new_rows.append(row)
                continue
        if p1.isdigit() and c1 in W:
            S.loc[i, ["num", "nreads", "src"]] = [int(p1), W[c1] + (s.nreads if s.num == int(p1) else 0), "review"]
        elif p1 == "?" and s.num >= 0 and s.nreads < 4:
            # reviewer could not confirm a weak OCR label: keep it but weak
            S.loc[i, "nreads"] = 1
    S = S.drop(index=drop)
    if new_rows:
        S = pd.concat([S, pd.DataFrame(new_rows)], ignore_index=True)
    S = S.drop(columns=[c for c in ["chain", "plabel"] if c in S.columns]).reset_index(drop=True)
    S["bench0"] = R.at_bench(S.x0, S.r0)
    S["bench1"] = R.at_bench(S.x1, S.r1)
    return S
