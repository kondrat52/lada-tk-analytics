"""Detect all people on the rink, record jersey color stats, save 4K crops of light-blue players.

Usage: process.py VIDEO OUTDIR FPS [START_SEC DUR_SEC]
  (restart after a crash with START_SEC = last t in dets.csv; frame numbers stay global)
Outputs:
  OUTDIR/dets.csv    frame,t,x1,y1,x2,y2,conf,blue,white,purple,red,dark,lblue
  OUTDIR/crops/      f{frame:06d}_{i:02d}.jpg  (light-blue candidates)
  OUTDIR/ov/         ov_{sec:05d}.jpg overview frames every 10 s
"""
import os, sys, time, threading, queue, subprocess
import numpy as np, cv2
from ultralytics import YOLO
from rink import rink

import imageio_ffmpeg
FF = imageio_ffmpeg.get_ffmpeg_exe()
VID, OUT, FPS = sys.argv[1], sys.argv[2], float(sys.argv[3])
START = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
DUR = float(sys.argv[5]) if len(sys.argv) > 5 else None
_meta = next(imageio_ffmpeg.read_frames(VID))
W, FULL_H = _meta["size"]
# rink band: the wide-cut camera shows ceiling above the far boards; keep far boards + ice
Y0, Y1 = int(round(rink(OUT).crop_top * FULL_H)), FULL_H
H = Y1 - Y0
os.makedirs(f"{OUT}/crops", exist_ok=True); os.makedirs(f"{OUT}/ov", exist_ok=True)

cmd = [FF, "-loglevel", "error", "-threads", "0"]
if START: cmd += ["-ss", str(START)]
cmd += ["-i", VID]
if DUR: cmd += ["-t", str(DUR)]
cmd += ["-vf", f"fps={FPS},crop={W}:{H}:0:{Y0}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)
q = queue.Queue(maxsize=32)

def reader():
    n = 0
    while True:
        buf = proc.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            q.put(None); return
        q.put((n, np.frombuffer(buf, np.uint8).reshape(H, W, 3)))
        n += 1
threading.Thread(target=reader, daemon=True).start()

model = YOLO(os.environ.get("YOLO_MODEL", "yolo11m.pt"))  # downloads on first use

def color_stats(img, b):
    x1, y1, x2, y2 = b
    w, h = x2 - x1, y2 - y1
    tx1, tx2 = int(x1 + 0.2 * w), int(x2 - 0.2 * w)
    ty1, ty2 = int(y1 + 0.15 * h), int(y1 + 0.5 * h)
    t = img[max(ty1, 0):max(ty2, ty1 + 1), max(tx1, 0):max(tx2, tx1 + 1)]
    if t.size == 0:
        return [0] * 6
    hsv = cv2.cvtColor(t, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int16)
    Hh, Ss, Vv = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    n = len(hsv)
    blue = ((Hh >= 90) & (Hh <= 125) & (Ss >= 70) & (Vv >= 70)).sum() / n
    lblue = ((Hh >= 90) & (Hh <= 118) & (Ss >= 50) & (Ss < 200) & (Vv >= 130)).sum() / n
    white = ((Ss < 45) & (Vv >= 160)).sum() / n
    purple = ((Hh >= 125) & (Hh <= 165) & (Ss >= 60) & (Vv >= 50)).sum() / n
    red = (((Hh <= 8) | (Hh >= 170)) & (Ss >= 100) & (Vv >= 70)).sum() / n
    dark = (Vv < 60).sum() / n
    return [blue, white, purple, red, dark, lblue]

fcsv = open(f"{OUT}/dets.csv", "a")
t0 = time.time(); done = False; BATCH = 8
while not done:
    batch = []
    while len(batch) < BATCH:
        item = q.get()
        if item is None:
            done = True; break
        batch.append(item)
    if not batch:
        break
    res = model.predict([f for _, f in batch], imgsz=1920, classes=[0], conf=0.15,
                        device="mps", verbose=False)
    for (n, img), r in zip(batch, res):
        t = START + n / FPS
        n = n + int(round(START * FPS))  # global frame index so crop names/CSV continue across restarts
        sec = int(round(t))
        if abs(t - sec) < 0.5 / FPS and sec % 10 == 0:
            cv2.imwrite(f"{OUT}/ov/ov_{sec:05d}.jpg", cv2.resize(img, (1280, 381)), [cv2.IMWRITE_JPEG_QUALITY, 80])
        boxes = r.boxes.xyxy.cpu().numpy(); confs = r.boxes.conf.cpu().numpy()
        for i, (b, c) in enumerate(zip(boxes, confs)):
            bi = b.astype(int)
            cs = color_stats(img, bi)
            fcsv.write(f"{n},{t:.3f},{bi[0]},{bi[1]+Y0},{bi[2]},{bi[3]+Y0},{c:.3f}," +
                       ",".join(f"{v:.3f}" for v in cs) + "\n")
            h = bi[3] - bi[1]
            if cs[0] >= 0.12 and (h >= 100 or n % 3 == 0):
                pw, ph = int(0.1 * (bi[2] - bi[0])), int(0.05 * h)
                crop = img[max(bi[1] - ph, 0):bi[3] + ph, max(bi[0] - pw, 0):bi[2] + pw]
                cv2.imwrite(f"{OUT}/crops/f{n:06d}_{i:02d}.jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if batch[0][0] % (BATCH * 50) == 0:
        el = time.time() - t0
        print(f"frame {batch[-1][0]} t={START + batch[-1][0] / FPS:.0f}s elapsed={el:.0f}s "
              f"rate={(batch[-1][0] + 1) / el:.1f} fps", flush=True)
    fcsv.flush()
print("DONE", time.time() - t0, flush=True)
