"""run_period.py FULLDIR PDIR T0 T1 NET_X : track + segment one period (T0..T1 seconds of video).
NET_X is the x pixel of the net our goalie defends that period (goalie detections there are ignored).
PDIR gets links to FULLDIR's detections, crops and OCR, plus tracks_v1.csv and segs_v1.csv."""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shifts as SH
from rink import rink
full, p = os.path.abspath(sys.argv[1]), sys.argv[2]
t0, t1, nx = float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
os.makedirs(p, exist_ok=True)
for src in [f"{full}/dets.csv", f"{full}/crops"] + glob.glob(f"{full}/ocr_*.csv"):
    dst = os.path.join(p, os.path.basename(src))
    if not os.path.lexists(dst):
        os.symlink(src, dst)
t, S = SH.build(p, t1, [(t0, t1, nx)], tmin=t0)
S = SH.link(S, rink(p))
t.to_csv(f"{p}/tracks_v1.csv", index=False); S.to_csv(f"{p}/segs_v1.csv", index=False)
print(len(t), "track rows,", len(S), "segments,", (S.num >= 0).sum(), "OCR-labeled")
