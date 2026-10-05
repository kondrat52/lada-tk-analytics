"""shots.py W --us home|guest : shots on goal per period, from the arena scoreboard -> W/shots.json.

Needs W/scoreboard.npy (scoreboard.py: the brightest frame of each second), W/periods.json and the rink's
`shots_boxes` (rink.py): the home and guest shots digits inside the scoreboard crop. Every second each box is read with
OCR; the reads are noisy (the digits are a few pixels tall), so the counts are the non-decreasing sequence that agrees
best with all the reads (a shot adds 1; a scorekeeper fixing a count can jump by a few).

Writes W/shots.json: {"us": "home", "periods": {"P1": [ours, theirs], ...}, "at": {"P1": t, ...}, "series": {...}}.
Each period's count is the board's total 25 s after the period ends (scorekeepers catch up), minus the period before.
Also writes W/shots_check.jpg: the board at each of those moments. Read it and fix "periods" by hand where the OCR is
wrong (at Kirkland it often is), then set "checked": true. publish copies checked "periods" into game.json as "shots".
"""
import json, os, sys
import numpy as np, cv2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rink import rink

MAXN = 80


def prep(f, box, sc=8):
    x0, y0, x1, y1 = box
    v = f[y0:y1, x0:x1].astype(np.float32).max(2)             # LED brightness
    v = (v - v.min()) / max(1.0, v.max() - v.min()) * 255
    im = 255 - cv2.resize(v.astype(np.uint8), None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
    im = cv2.copyMakeBorder(im, 20, 20, 30, 30, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)


def read_all(W):
    """Per second and side: (value or -1, score)."""
    from rapidocr import RapidOCR
    eng = RapidOCR(params={"Global.use_det": False, "Global.use_cls": False})
    boxes = rink(f"{W}/full").shots_boxes
    a = np.load(f"{W}/scoreboard.npy", mmap_mode="r")
    out = {s: [] for s in boxes}
    for t in range(len(a)):
        f = np.array(a[t])
        for side, b in boxes.items():
            r = eng(prep(f, b))
            txt = (r.txts[0] if r.txts else "").strip()
            sc = float(r.scores[0]) if r.scores else 0.0
            ok = txt.isascii() and txt.isdigit() and int(txt) < MAXN
            out[side].append((int(txt), sc) if ok else (-1, 0.0))
    return out


def clean(reads, jump_cost=4.0):
    """Best non-decreasing integer sequence: a read that disagrees costs its OCR score, each count step costs a
    little (so noise doesn't add shots), steps bigger than 1 cost more."""
    T = len(reads)
    INF = 1e18
    cost = np.full(MAXN, INF); cost[0] = 0.0
    back = np.zeros((T, MAXN), np.int16)
    step_pen = np.array([0.0, 0.5] + [jump_cost * k for k in range(2, MAXN)])
    for t, (v, s) in enumerate(reads):
        # best predecessor for each value: min over u <= v of cost[u] + step_pen[v - u]
        new = np.full(MAXN, INF); arg = np.zeros(MAXN, np.int16)
        for vv in range(MAXN):
            us = np.arange(0, vv + 1)
            c = cost[us] + step_pen[vv - us]
            i = int(np.argmin(c)); new[vv] = c[i]; arg[vv] = us[i]
        obs = np.where(np.arange(MAXN) == v, 0.0, s if v >= 0 else 0.0)
        cost = new + obs; back[t] = arg
    seq = np.zeros(T, int); seq[-1] = int(np.argmin(cost))
    for t in range(T - 1, 0, -1):
        seq[t - 1] = back[t, seq[t]]
    return seq


def changes(seq):
    out = [[0, int(seq[0])]]
    for t in range(1, len(seq)):
        if seq[t] != seq[t - 1]:
            out.append([t, int(seq[t])])
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("W"); ap.add_argument("--us", choices=("home", "guest"), required=True)
    a = ap.parse_args()
    W = os.path.abspath(a.W)
    cache = f"{W}/shots_reads.json"
    reads = json.load(open(cache)) if os.path.exists(cache) else read_all(W)
    json.dump(reads, open(cache, "w"))
    seq = {side: clean([tuple(x) for x in r]) for side, r in reads.items()}
    them = "guest" if a.us == "home" else "home"
    Ps = json.load(open(f"{W}/periods.json"))
    T = len(seq[a.us])
    out = dict(us=a.us, checked=False, periods={}, at={}, series={s: changes(v) for s, v in seq.items()})
    prev = [0, 0]
    for k, P in enumerate(Ps):
        nxt = Ps[k + 1]["start"] if k + 1 < len(Ps) else T
        t = int(min(P["end"] + 25, nxt - 1, T - 1))
        cum = [int(seq[a.us][t]), int(seq[them][t])]
        out["periods"][P["label"]] = [cum[0] - prev[0], cum[1] - prev[1]]
        out["at"][P["label"]] = t
        prev = cum
    json.dump(out, open(f"{W}/shots.json", "w"))
    from scoreboard import sheet
    sheet(W, f"{W}/shots_check.jpg", list(out["at"].values()), cols=len(Ps))
    print("shots (ours-theirs):", ", ".join(f"{p} {v[0]}-{v[1]}" for p, v in out["periods"].items()),
          f"total {prev[0]}-{prev[1]}; check {W}/shots_check.jpg (cumulative {a.us} count is ours)")


if __name__ == "__main__":
    main()
