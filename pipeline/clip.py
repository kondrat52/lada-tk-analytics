"""clip.py FULLDIR VIDEO AUDIO OUT.mp4 T0 T1 [POSTER_T [FOCUS_X]]
Cut a zoomed highlight clip: a virtual camera follows the main cluster of players (from FULLDIR/dets.csv),
crops the 4K wide cut to 16:9 and encodes 1280x720 H.264 with the game audio. Writes OUT.jpg as a poster
frame (at POSTER_T, default the middle of the clip). FOCUS_X (source px, e.g. 540 = left net) keeps the camera near
that part of the rink when players are spread out."""
import os, sys, subprocess
import numpy as np, pandas as pd, cv2, imageio_ffmpeg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from track import load

FF = imageio_ffmpeg.get_ffmpeg_exe()
OUT_W, OUT_H = 1280, 720
MIN_W, MAX_W = 900, 2800           # crop width range in source pixels
FEET_AT = 0.56                       # players' skates sit this far down the frame


def camera_path(full, t0, t1, focus=None):
    """Per detection frame (8 fps): crop centre x/y and width, smoothed."""
    d = load(f"{full}/dets.csv")
    d = d[(d.t >= t0 - 3) & (d.t <= t1 + 3) & (d.conf >= 0.3)]
    d = d[d.fy > d.board + 5]
    grid = np.arange(0, 3840, 20)
    rows = []
    for t, g in d.groupby("t"):
        xs, ys, hs = g.fx.values, g.fy.values, g.h.values
        dens = np.exp(-((grid[:, None] - xs[None, :]) / 350.0) ** 2).sum(1)
        if focus is not None:
            dens = dens * np.exp(-((grid - focus) / 900.0) ** 2)
        peak = grid[dens.argmax()]
        m = np.abs(xs - peak) < 650
        if m.sum() < 2:
            m = np.ones(len(xs), bool)
        spread = np.quantile(xs[m], 0.8) - np.quantile(xs[m], 0.2)
        # zoom to the core of the play, wider for near-camera players (they look bigger)
        w = np.clip(1.15 * spread + 6 * np.median(hs[m]), MIN_W, MAX_W)
        feet = np.median(ys[m])
        rows.append((t, np.median(xs[m]) * 0.5 + peak * 0.5, feet, w))
    P = pd.DataFrame(rows, columns=["t", "cx", "cy", "w"]).set_index("t").sort_index()
    P["cx"] = P.cx.rolling(15, center=True, min_periods=1).mean()
    P["cy"] = P.cy.rolling(15, center=True, min_periods=1).mean()  # median skate height of the cluster
    P["w"] = P.w.rolling(25, center=True, min_periods=1).mean()
    return P


def main():
    full, video, audio, out = sys.argv[1:5]
    t0, t1 = float(sys.argv[5]), float(sys.argv[6])
    tp = float(sys.argv[7]) if len(sys.argv) > 7 else (t0 + t1) / 2
    focus = float(sys.argv[8]) if len(sys.argv) > 8 else None
    meta = next(imageio_ffmpeg.read_frames(video))
    W, H = meta["size"]; fps = meta["fps"]
    P = camera_path(full, t0, t1, focus)
    dec = subprocess.Popen([FF, "-nostdin", "-loglevel", "error", "-ss", str(t0), "-i", video, "-t", str(t1 - t0),
                            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, bufsize=W * H * 3 * 2)
    enc_cmd = [FF, "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{OUT_W}x{OUT_H}",
               "-r", str(fps), "-i", "-"]
    if audio and os.path.exists(audio):
        enc_cmd += ["-ss", str(t0), "-t", str(t1 - t0), "-i", audio, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "96k"]
    enc_cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-shortest", out]
    enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)
    k, poster = 0, None
    ts = P.index.values
    while True:
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        t = t0 + k / fps; k += 1
        cx, cy, w = (np.interp(t, ts, P[c].values) for c in ("cx", "cy", "w"))
        h = w * OUT_H / OUT_W
        x0 = int(np.clip(cx - w / 2, 0, W - w)); y0 = int(np.clip(cy - FEET_AT * h, 0, H - h))
        img = np.frombuffer(buf, np.uint8).reshape(H, W, 3)[y0:y0 + int(h), x0:x0 + int(w)]
        frame = cv2.resize(img, (OUT_W, OUT_H), interpolation=cv2.INTER_AREA)
        if poster is None and t >= tp:
            poster = frame
        enc.stdin.write(frame.tobytes())
    enc.stdin.close(); enc.wait(); dec.wait()
    if poster is not None:
        cv2.imwrite(os.path.splitext(out)[0] + ".jpg", poster, [cv2.IMWRITE_JPEG_QUALITY, 82])
    print(out, f"{os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
