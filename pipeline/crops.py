"""4K crops of players in our jersey, for OCR and the visual review. process.py saves them while detecting.

Usage: crops.py VIDEO OUTDIR FPS : cut the crops process.py would have saved for OUTDIR/dets.csv with the jersey
now in OUTDIR/rink.json, without detecting again (for when the jersey was set after detection). Crops that exist
are kept; frame numbers match process.py's (the same fps filter from t=0).
"""
import os, sys, threading, queue, subprocess, time
import numpy as np, cv2

COLORS = ["blue", "white", "purple", "red", "dark", "lblue"]   # color_stats order, as in dets.csv


def wants_crop(test, cs, h, n):
    """test: the jersey's crop test (rink.JERSEYS); cs: color_stats list; small (far) players every third frame."""
    return bool(test(dict(zip(COLORS, cs)))) and (h >= 100 or n % 3 == 0)


def save_crop(img, bi, path):
    """bi: box in img's pixels (img = the detection band of the frame)."""
    h = bi[3] - bi[1]
    pw, ph = int(0.1 * (bi[2] - bi[0])), int(0.05 * h)
    crop = img[max(bi[1] - ph, 0):bi[3] + ph, max(bi[0] - pw, 0):bi[2] + pw]
    cv2.imwrite(path, crop, [cv2.IMWRITE_JPEG_QUALITY, 88])


def recrop(vid, out, fps):
    import imageio_ffmpeg, pandas as pd
    from rink import rink, jersey
    FF = imageio_ffmpeg.get_ffmpeg_exe()
    test = jersey(out)["crop"]
    d = pd.read_csv(f"{out}/dets.csv", header=None, names=["frame", "t", "x1", "y1", "x2", "y2", "conf"] + COLORS)
    d["i"] = d.groupby("frame").cumcount()
    have = set(os.listdir(f"{out}/crops"))
    d["fn"] = [f"f{f:06d}_{i:02d}.jpg" for f, i in zip(d.frame, d.i)]
    keep = [wants_crop(test, cs, y2 - y1, f) and fn not in have
            for cs, y1, y2, f, fn in zip(d[COLORS].values, d.y1, d.y2, d.frame, d.fn)]
    d = d[keep]
    print(f"{len(d)} crops to cut", flush=True)
    if d.empty:
        return
    W, FULL_H = next(imageio_ffmpeg.read_frames(vid))["size"]
    Y0 = int(round(rink(out).crop_top * FULL_H)); H = FULL_H - Y0
    todo = {f: g[["x1", "y1", "x2", "y2", "fn"]].values for f, g in d.groupby("frame")}
    last = max(todo)
    proc = subprocess.Popen([FF, "-loglevel", "error", "-threads", "0", "-i", vid, "-vf",
                             f"fps={fps},crop={W}:{H}:0:{Y0}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                            stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)
    q = queue.Queue(maxsize=32)

    def reader():
        n = 0
        while n <= last:
            buf = proc.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            if n in todo:
                q.put((n, np.frombuffer(buf, np.uint8).reshape(H, W, 3)))
            n += 1
        q.put(None)
    threading.Thread(target=reader, daemon=True).start()
    t0, done, shown = time.time(), 0, 0
    while (item := q.get()) is not None:
        n, img = item
        for x1, y1, x2, y2, fn in todo[n]:
            save_crop(img, (x1, y1 - Y0, x2, y2 - Y0), f"{out}/crops/{fn}")
            done += 1
        if time.time() - shown > 60:
            shown = time.time()
            print(f"frame {n} t={n / fps:.0f}s crops={done} elapsed={time.time() - t0:.0f}s", flush=True)
    proc.kill()
    print(f"cut {done} crops in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    recrop(sys.argv[1], sys.argv[2], float(sys.argv[3]))
