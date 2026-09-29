"""Incrementally OCR torso region of light-blue crops. Writes OUT/ocr_{PART[0]}.csv: file,text,score (one row per text box)."""
import os, sys, time, glob, csv, cv2
from rapidocr import RapidOCR
OUT = sys.argv[1]
FMAX = int(sys.argv[2]) if len(sys.argv) > 2 else 10**9
STEP = int(sys.argv[3]) if len(sys.argv) > 3 else 1
PART = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (0, 1)
eng = RapidOCR(params={"Det.limit_side_len": 320, "Det.limit_type": "max",
                       "EngineConfig.onnxruntime.intra_op_num_threads": 2})
done = set()
for fn_ in glob.glob(f"{OUT}/ocr_done_*.txt"):
    done |= set(open(fn_).read().split())
fo = open(f"{OUT}/ocr_{PART[0]}.csv", "a", newline=""); w = csv.writer(fo)
fd = open(f"{OUT}/ocr_done_{PART[0]}.txt", "a")
while True:
    finished = "DONE" in open(f"{OUT}/log.txt").read()
    todo = sorted(f for f in set(os.listdir(f"{OUT}/crops")) - done if int(f[1:7]) <= FMAX and int(f[1:7]) % STEP == 0 and hash(f) % PART[1] == PART[0])
    if (finished or FMAX < 10**9) and not todo: break
    if len(todo) < 50 and not finished:
        time.sleep(20); continue
    for fn in todo:
        im = cv2.imread(f"{OUT}/crops/{fn}")
        done.add(fn); fd.write(fn + "\n")
        if im is None or im.shape[0] < 110: continue
        h = im.shape[0]
        r = eng(im[int(0.1 * h):int(0.6 * h)])
        if r.txts:
            for t, s in zip(r.txts, r.scores):
                w.writerow([fn, t, f"{s:.3f}"])
    fo.flush(); fd.flush()
    print(f"ocr processed {len(done)}", flush=True)
print("OCR DONE", flush=True)
