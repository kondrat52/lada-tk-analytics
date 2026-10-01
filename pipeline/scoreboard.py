"""The arena scoreboard in the wide cut (rink.py `scoreboard` box): period clock, score, shots, and the penalty panels
(player number and time left). Its LEDs flicker, so most single frames show it dark: keep the brightest of each
second's frames.

  scoreboard.py W                 one pass over the video -> W/scoreboard.npy (~5 min)
  scoreboard.py W OUT.jpg t1 t2 …  the board at those seconds of video as a sheet, 2.5x
"""
import os, subprocess, sys
import numpy as np, cv2, imageio_ffmpeg
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rink import rink


def scan(W):
    x, y, w, h = rink(f"{W}/full").scoreboard
    p = subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-loglevel", "error", "-threads", "0",
                          "-i", f"{W}/video.webm", "-vf", f"crop={w}:{h}:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "bgr24",
                          "-"], stdout=subprocess.PIPE, bufsize=w * h * 3 * 64)
    fps = 24  # the wide cuts are 24 fps
    best, lit, n = [], [], 0
    while len(buf := p.stdout.read(w * h * 3)) == w * h * 3:
        f = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        s, v = n // fps, int((f[..., 2].astype(np.int16) - f[..., 1] > 60).sum())   # lit red LEDs
        if s == len(best):
            best.append(f.copy()); lit.append(v)
        elif v > lit[s]:
            best[s], lit[s] = f.copy(), v
        n += 1
    np.save(f"{W}/scoreboard.npy", np.array(best))
    print(f"{W}/scoreboard.npy: {len(best)} s")


def sheet(W, out, ts, cols=6):
    a = np.load(f"{W}/scoreboard.npy")
    h, w = a.shape[1:3]
    tw = 325; th = int(tw * h / w)
    tiles = []
    for t in ts:
        im = cv2.resize(a[min(int(t), len(a) - 1)], (tw, th), interpolation=cv2.INTER_CUBIC)
        cv2.putText(im, f"{int(t) // 60}:{int(t) % 60:02d} ({int(t)})", (4, th - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 255, 255), 1)
        tiles.append(im)
    blank = np.zeros_like(tiles[0])
    rows = [np.hstack(tiles[i:i + cols] + [blank] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    cv2.imwrite(out, np.vstack(rows))
    print(out)


if __name__ == "__main__":
    W = os.path.abspath(sys.argv[1])
    if len(sys.argv) == 2:
        scan(W)
    else:
        sheet(W, sys.argv[2], [float(t) for t in sys.argv[3:]])
