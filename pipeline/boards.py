"""boards.py FRAME.png OUTDIR : fit the far-boards (yellow kick plate) curve -> OUTDIR/boards_poly.npy.
FRAME.png is a full-resolution frame from the wide-cut video (e.g. extracted with ffmpeg -ss 600 -frames:v 1).
Players standing behind this curve are on the bench; below it they are on the ice."""
import sys, cv2, numpy as np
img = cv2.imread(sys.argv[1]); out = sys.argv[2]
H, W = img.shape[:2]
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
m = (hsv[..., 0] >= 18) & (hsv[..., 0] <= 35) & (hsv[..., 1] >= 90) & (hsv[..., 2] >= 110)
y0, y1 = int(H * 0.41), int(H * 0.76)
xs, ys = [], []
for x in range(0, W, 20):
    col = np.where(m[y0:y1, x])[0]
    if len(col) >= 2:
        xs.append(x); ys.append(y0 + np.median(col))
xs, ys = np.array(xs), np.array(ys)
p = np.polyfit(xs, ys, 4)
keep = np.abs(ys - np.polyval(p, xs)) < 15
p = np.polyfit(xs[keep], ys[keep], 4)
for x in np.linspace(0, W - 1, 9).astype(int):
    print(x, round(float(np.polyval(p, x))))
np.save(f"{out}/boards_poly.npy", p)
