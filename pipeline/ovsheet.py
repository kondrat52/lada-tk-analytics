"""ovsheet.py OVDIR OUT.jpg T0 T1 STEP [cols] : contact sheet of the 10-second overview frames (find periods/breaks)."""
import sys, os, subprocess
here = os.path.dirname(os.path.abspath(__file__))
ov, out, t0, t1, st = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
cols = sys.argv[6] if len(sys.argv) > 6 else "3"
t0 -= t0 % 10  # overview frames are saved on multiples of 10 s
items = [f"{ov}/ov_{t:05d}.jpg::{t // 60}:{t % 60:02d}" for t in range(t0, t1 + 1, st) if os.path.exists(f"{ov}/ov_{t:05d}.jpg")]
if items:
    subprocess.run([sys.executable, f"{here}/sheet.py", out, "640", "190", cols] + items)
else:
    print("no overview frames in that range")
