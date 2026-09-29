"""sheet.py OUT.jpg TILE_W TILE_H COLS img1[:label] img2[:label] ..."""
import sys, cv2, numpy as np
out, tw, th, cols = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
items = sys.argv[5:]
rows = (len(items) + cols - 1) // cols
sheet = np.full((rows * (th + 22), cols * tw, 3), 255, np.uint8)
for k, it in enumerate(items):
    path, _, label = it.partition("::")
    im = cv2.imread(path)
    if im is None: continue
    s = min(tw / im.shape[1], th / im.shape[0])
    im = cv2.resize(im, (max(1, int(im.shape[1] * s)), max(1, int(im.shape[0] * s))), interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    r, c = divmod(k, cols); y0, x0 = r * (th + 22) + 22, c * tw
    sheet[y0:y0 + im.shape[0], x0:x0 + im.shape[1]] = im
    cv2.putText(sheet, label or str(k), (x0 + 3, y0 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 200), 2)
cv2.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])
