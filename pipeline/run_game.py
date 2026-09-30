"""Driver for processing one game. Run with the hockey env's python (see setup_env.sh).

  run_game.py fetch   URL W [--rink NAME] [--limit SEC]   download, calibrate, detect (auto-restart), OCR,
                                             propose periods; --rink: camera geometry from rink.py (renton)
  run_game.py skaters W T0 T1               our skaters detected on the ice per 5 s (find penalty kills)
  run_game.py unknown W                      numbers/surnames read that aren't on the roster (new players?)
  run_game.py prepare W                      per period: tracking, review sheets, roster card
  run_game.py solve   W                      per period: apply reviews + solve; gantt charts; stats table
  run_game.py goals   W                      candidate goals: center-ice faceoffs + long stoppages (verify by eye)
  run_game.py frames  W OUT.jpg X0 X1 Y0 Y1 TILE_W COLS t1 t2 ...   4K frames (cropped) as a sheet, for verifying
  run_game.py clip    W GAME_ID NAME T0 T1 POSTER_T [FOCUS]          zoomed clip into docs/games/<id>/clips;
                                             FOCUS = x px (a net x from rink.py) or #N to follow player N
  run_game.py publish W GAME_ID --opponent RR --eyebrow "Sun Sep 27, 2026 · 7:50 PM · Renton" [--date ...]
  run_game.py archive W                      after publishing: drop the video, crops and sheets (~5 GB), keep the
                                             game's data (detections, reads, tracks, reviews; ~100 MB)

W is the per-game work folder (outside the repo). Every step skips work that is already done, so re-running
after an interruption continues where it stopped. W/periods.json holds the period windows; fetch writes a
proposal, which you check and edit (add penalty kills) before prepare/solve.
"""
import argparse, glob, json, os, re, shutil, signal, subprocess, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
FPS = 8
sys.path.insert(0, HERE)
from rink import rink


def sh(*args, **kw):
    print("+", " ".join(map(str, args)), flush=True)
    return subprocess.run([str(a) for a in args], check=True, **kw)


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------- fetch

def download(url, W):
    vid = f"{W}/video.webm"
    if os.path.exists(vid):
        return vid
    sh(PY, "-m", "yt_dlp", "-q", "--no-progress", "-f", "313/bestvideo[height=2160]", "-o", vid, url)
    return vid


def download_audio(url, W):
    if not os.path.exists(f"{W}/audio.m4a"):
        sh(PY, "-m", "yt_dlp", "-q", "--no-progress", "-f", "140/bestaudio[ext=m4a]", "-o", f"{W}/audio.m4a", url)


def calibrate(vid, W):
    if os.path.exists(f"{W}/full/boards_poly.npy"):
        return
    import imageio_ffmpeg
    frame = f"{W}/frame600.png"
    sh(imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-y", "-ss", "600", "-i", vid, "-frames:v", "1", frame)
    sh(PY, f"{HERE}/boards.py", frame, f"{W}/full")


def _last_frame(dets):
    if not os.path.exists(dets) or os.path.getsize(dets) == 0:
        return None
    with open(dets, "rb") as f:
        f.seek(max(0, os.path.getsize(dets) - 4096))
        tail = f.read().decode(errors="ignore").strip().splitlines()
    return int(tail[-1].split(",")[0]) if tail else None


def _trim_last_frame(full):
    """Drop the last (possibly partial) frame so a restart can redo it. Returns its start time in seconds."""
    dets = f"{full}/dets.csv"
    f = _last_frame(dets)
    if f is None:
        return 0.0
    keep = [l for l in open(dets) if not l.startswith(f"{f},")]
    open(dets, "w").writelines(keep)
    for p in glob.glob(f"{full}/crops/f{f:06d}_*.jpg"):
        os.remove(p)
    return f / FPS


def detect(vid, W, limit=None):
    """Run process.py; if it slows to under ~45% of its normal speed for 8 minutes (memory growth on long runs),
    restart it from the last frame. Frame numbers stay global across restarts."""
    full = f"{W}/full"; logp = f"{full}/log.txt"
    if os.path.exists(logp) and "\nDONE" in "\n" + open(logp).read():
        return
    start = _trim_last_frame(full) if os.path.exists(f"{full}/dets.csv") else 0.0
    crashes = 0
    while True:
        cmd = [PY, f"{HERE}/process.py", vid, full, str(FPS)]
        if start or limit:
            cmd += [str(start)]
        if limit:
            cmd += [str(max(1.0, limit - start))]
        log(f"detect from t={start:.1f}s")
        lf = open(logp, "a"); lf.write(f"--- start {start:.3f}\n"); lf.flush()
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, cwd=W)
        t_start, hist, slow_since = time.time(), [], None
        while proc.poll() is None:
            time.sleep(30)
            lines = [l for l in open(logp).read().splitlines() if l.startswith("frame ")]
            if lines:
                m = re.search(r" t=(\d+)s", lines[-1])
                hist.append((time.time(), float(m.group(1))))
            # speed over the last 10 minutes, in video seconds per wall second (normal ~0.75 on an M3)
            recent = [h for h in hist if h[0] > time.time() - 600]
            if time.time() - t_start > 900 and len(recent) >= 2:
                rate = (recent[-1][1] - recent[0][1]) / max(1, recent[-1][0] - recent[0][0])
                slow_since = (slow_since or time.time()) if rate < 0.35 else None
                if slow_since and time.time() - slow_since > 480:
                    log(f"detection slowed to {rate:.2f} video-s/s; restarting")
                    proc.send_signal(signal.SIGTERM); proc.wait(30)
                    break
        if proc.returncode == 0 and "\nDONE" in "\n" + open(logp).read():
            log("detection done")
            return
        prev = start
        start = _trim_last_frame(full)
        if proc.returncode not in (None, 0, -signal.SIGTERM):
            crashes = crashes + 1 if start <= prev + 5 else 0
            if crashes >= 3:
                sys.exit(f"process.py keeps failing near t={start:.0f}s; see {logp}")
            log(f"process.py exited with {proc.returncode}; restarting from the last frame")


def ocr_skip(W):
    """Crops of people sitting deep in our bench (rink.ocr_skip_depth), listed in ocr_done_bench.txt so the OCR
    workers pass over them: those tracks are dropped as bench sitters, so their reads are never used."""
    from track import load
    full = f"{W}/full"; R = rink(full)
    if R.ocr_skip_depth is None:
        return
    d = load(f"{full}/dets.csv")
    deep = d[np.asarray(R.bench_depth(d.fx, d.fy - d.board)) > R.ocr_skip_depth]
    crops = set(os.listdir(f"{full}/crops"))
    names = [n for n in (f"f{f:06d}_{i:02d}.jpg" for f, i in zip(deep.frame, deep.i)) if n in crops]
    open(f"{full}/ocr_done_bench.tmp", "w").write("\n".join(names) + "\n")
    os.replace(f"{full}/ocr_done_bench.tmp", f"{full}/ocr_done_bench.txt")


def ocr(W):
    full = f"{W}/full"
    ocr_skip(W)
    crops = set(os.listdir(f"{full}/crops"))
    done = set()
    for p in glob.glob(f"{full}/ocr_done_*.txt"):
        done |= set(open(p).read().split())
    if not crops - done:
        return
    log(f"OCR on {len(crops - done)} crops (4 workers)")
    env = dict(os.environ, PYTHONHASHSEED="0")
    ps = [subprocess.Popen([PY, f"{HERE}/ocr_worker.py", full, "1000000000", "1", str(k), "4"], env=env,
                           stdout=open(f"{full}/ocr_log_{k}.txt", "w"), stderr=subprocess.STDOUT) for k in range(4)]
    for p in ps:
        p.wait()


def propose_periods(W):
    """Breaks = min_break+ seconds (rink.py) with nobody out on the open ice. Our goalie's net side per period from light-blue
    detections standing in each crease."""
    from track import load
    R = rink(f"{W}/full")
    d = load(f"{W}/full/dets.csv"); d["rel"] = d.fy - d.board
    T = int(d.t.max()) + 1
    out = d[R.open_ice(d.fx, d.rel) & (d.conf >= 0.3)]
    act = np.bincount(out.t.astype(int), minlength=T) / FPS
    act = pd.Series(act).rolling(5, center=True, min_periods=1).median().values
    empty = act < 0.5
    spans, s = [], None
    for t in range(T + 1):
        e = t < T and empty[t]
        if e and s is None:
            s = t
        if not e and s is not None:
            if t - s >= R.min_break:
                spans.append((s, t))
            s = None
    edges = [0] + [x for b in spans for x in b] + [T]
    periods = []
    for a, b in zip(edges[0::2], edges[1::2]):
        if b - a >= 240:
            periods.append([a, b])
    blue = d[d.blue >= 0.3]
    res = []
    for k, (a, b) in enumerate(periods, 1):
        w = blue[(blue.t >= a) & (blue.t < b)]
        nl, nr = (R.in_crease(w.fx, w.rel, R.nets[s]).sum() for s in ("left", "right"))
        res.append(dict(label=f"P{k}", start=int(a), end=int(b), net=R.nets["left" if nl >= nr else "right"], pk=[]))
    json.dump(res, open(f"{W}/periods.json", "w"), indent=2)
    for k in range(len(res) - 1):
        a, b = res[k]["end"], res[k + 1]["start"]
        sh(PY, f"{HERE}/ovsheet.py", f"{W}/full/ov", f"{W}/break_{k + 1}.jpg", a - 60, b + 40, 10, 2)
    sh(PY, f"{HERE}/ovsheet.py", f"{W}/full/ov", f"{W}/video_end.jpg", T - 120, T, 20, 2)
    print(json.dumps(res, indent=2))


def cmd_fetch(a):
    W = os.path.abspath(a.W); os.makedirs(f"{W}/full", exist_ok=True)
    if a.rink:
        from rink import RINKS
        if a.rink not in RINKS:
            sys.exit(f"unknown rink {a.rink}; known: {', '.join(RINKS)}")
        json.dump({"rink": a.rink}, open(f"{W}/full/rink.json", "w"))
    vid = download(a.url, W)
    download_audio(a.url, W)
    calibrate(vid, W)
    detect(vid, W, a.limit)
    ocr(W)
    propose_periods(W)
    log(f"fetch done. Check {W}/periods.json against {W}/break_*.jpg and video_end.jpg")


# ---------------------------------------------------------------- helpers for the review

def periods(W):
    return json.load(open(f"{W}/periods.json"))


def cmd_skaters(a):
    tr = []
    for P in periods(a.W):
        p = f"{a.W}/{P['label'].lower()}/tracks_v1.csv"
        if os.path.exists(p):
            tr.append(pd.read_csv(p))
    if tr:
        t = pd.concat(tr)
    else:  # before prepare: raw light-blue detections on the ice
        from track import load
        t = load(f"{a.W}/full/dets.csv"); t = t[t.blue >= 0.3]
    t = t[(t.t >= a.T0) & (t.t < a.T1) & t.onice]
    c = t.groupby([(t.t // 5).astype(int) * 5, "frame"]).size().groupby(level=0).quantile(0.75)
    print("our skaters on the ice (75th pct per 5 s; includes the goalie before prepare):")
    print(" ".join(f"{int(k) // 60}:{int(k) % 60:02d}={v:.0f}" for k, v in c.items()))


def _skater_speed(W):
    """Median speed of our tracked skaters per second, in body-heights/s (low = stoppage)."""
    tr = pd.concat([pd.read_csv(f"{W}/{P['label'].lower()}/tracks_v1.csv") for P in periods(W)])
    tr = tr[tr.onice].sort_values(["tid", "frame"])
    tr["v"] = np.hypot(tr.groupby("tid").fx.diff(), tr.groupby("tid").fy.diff()) / tr.h * FPS
    tr.loc[tr.groupby("tid").frame.diff() != 1, "v"] = np.nan
    T = int(tr.t.max()) + 1
    return tr.groupby(tr.t.astype(int)).v.median().reindex(range(T)).rolling(5, center=True, min_periods=1).median()


def cmd_goals(a):
    """After every goal the restart is a center-ice faceoff. List center-ice formations that aren't period
    starts, and every long stoppage with where play restarted. Each needs checking by eye (frames command)."""
    from track import load
    W = os.path.abspath(a.W)
    R = rink(f"{W}/full")
    d = load(f"{W}/full/dets.csv"); d = d[d.onice & (d.conf >= 0.3)]
    g = d.groupby("frame").agg(t=("t", "first"), n=("fx", "size"), mx=("fx", "median"),
                               q2=("fx", lambda s: s.quantile(.2)), q8=("fx", lambda s: s.quantile(.8)))
    s = g.assign(sx=g.q8 - g.q2).groupby(g.t.astype(int)).agg(n=("n", "median"), mx=("mx", "median"), sx=("sx", "median"))
    center = R.center_x
    sp = _skater_speed(W)
    Ps = periods(W)
    starts = [P["start"] for P in Ps]
    def label(t):
        P = next((P for P in Ps if P["start"] <= t <= P["end"]), None)
        return P["label"] if P else "break"
    print("Long stoppages (our skaters nearly still for 18+ s) and where play restarted:")
    slow = (sp < 0.55) | sp.isna()
    st = None
    for t in range(len(sp)):
        if slow.iloc[t]:
            st = t if st is None else st
            continue
        if st is not None and t - st >= 18 and label(st) != "break":
            w = s.loc[t - 6:t + 1]
            rx = w.mx.median()
            where = "CENTER ice" if abs(rx - center) < 250 else ("left end" if rx < center - 380 else "right end")
            near_start = any(abs(st - x) < 45 for x in starts)
            hint = "  <- goal? (center restart)" if where == "CENTER ice" and not near_start else ""
            # where was play just before it stopped?
            before = d[(d.t >= st - 6) & (d.t < st)].fx.median()
            side = "left net" if before < center - 580 else ("right net" if before > center + 620 else "mid-ice")
            print(f"  {st // 60}:{st % 60:02d}-{t // 60}:{t % 60:02d} {label(st)}: play stopped near {side}, "
                  f"restart at {where}{hint}")
        st = None
    print("Center-ice faceoff formations (11+ people lined up around center, still for 3+ s), not period starts:")
    s["mv"] = s.mx.diff().abs().rolling(3, center=True).mean()
    cand = (s.n >= 9) & ((s.mx - center).abs() < 220) & (s.sx < 1100) & (s.mv < 60)
    st = None
    for t in s.index:
        if cand.get(t, False):
            st = t if st is None else st
            continue
        if st is not None and t - st >= 3 and label(st) != "break" and not any(abs(st - x) < 45 for x in starts):
            print(f"  {st // 60}:{st % 60:02d} {label(st)}  <- look at the 60 s before it")
        st = None
    print("Our net per period:", {P["label"]: ("left" if P["net"] < center else "right") for P in Ps})
    print("Verify each with frames (full rink every 3 s, then zoom on the net): a goal shows a crowd at a net, the "
          "referee pointing at it, and one team celebrating before the center faceoff.")


def cmd_unknown(a):
    """Jersey numbers and surnames the OCR read that aren't in roster.json: new or substitute players, or an
    opponent whose white jersey has blue lettering. Writes W/unknown_<N>.jpg crop sheets to check each by eye."""
    from roster import SKATERS, GOALIES
    from reads import name_to_num
    W = os.path.abspath(a.W); full = f"{W}/full"
    o = pd.concat([pd.read_csv(f, header=None, names=["file", "text", "score"]) for f in glob.glob(f"{full}/ocr_*.csv")])
    o = o[o.score >= 0.85]; o["up"] = o.text.astype(str).str.upper().str.strip()
    known = set(SKATERS) | set(GOALIES)
    digits = "".join(str(n) for n in known)
    dig = o[o.up.str.fullmatch(r"\d{1,2}")]; dig = dig.assign(num=dig.up.astype(int))
    regular = dig[dig.num.isin(known)].num.value_counts()
    # a teammate who plays gets hundreds of reads; opponents' numbers and misreads get a few dozen
    floor = max(30, int(0.15 * regular[regular >= 100].median())) if (regular >= 100).any() else 30
    # single digits are mostly partial reads of roster numbers (8 from 18/78): only count ones no roster number has
    dig = dig[~dig.num.isin(known) & ((dig.num >= 10) | ~dig.num.astype(str).isin(list(digits)))]
    alpha = o[o.up.str.fullmatch(r"[A-Z]{4,}")]
    alpha = alpha[[name_to_num(t) is None for t in alpha.up]]
    cnt = dig.num.value_counts()
    fmt = lambda s: ", ".join(f"{k} x{v}" for k, v in s.items()) or "-"
    print(f"unknown numbers read {floor}+ times (regulars get ~{int(regular[regular >= 100].median()) if (regular >= 100).any() else 0}):")
    for n, c in cnt[cnt >= floor].items():
        files = sorted(set(dig[dig.num == n].file))
        sheet = f"{W}/unknown_{n}.jpg"
        subprocess.run([PY, f"{HERE}/sheet.py", sheet, "110", "180", "12"] +
                       [f"{full}/crops/{f}::" for f in files[::max(1, len(files) // 12)][:12]], stderr=subprocess.DEVNULL)
        print(f"  #{n}: {c} reads; surnames on the same crops: {fmt(alpha[alpha.file.isin(files)].up.value_counts().head(3))}; "
              f"crops: {sheet}")
    if not (cnt >= floor).any():
        print("  none")
    print("  fewer reads (usually opponents or misreads):", fmt(cnt[(cnt < floor) & (cnt >= 30)].head(8)))
    lone = alpha[~alpha.file.isin(set(dig.file))].up.value_counts()
    print("  other surnames read 20+ times:", fmt(lone[lone >= 20].head(8)))
    print("Check each sheet: light-blue jersey = ours (add number and surname to roster.json, then prepare); "
          "white = an opponent (ignore).")


def cmd_frames(a):
    import cv2, imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe(); vid = f"{a.W}/video.webm"
    x0, x1, y0, y1 = a.x0, a.x1, a.y0, a.y1
    tiles = []
    for t in a.times:
        r = subprocess.run([FF, "-nostdin", "-loglevel", "error", "-ss", str(t), "-i", vid, "-frames:v", "1", "-vf",
                            f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                           capture_output=True)
        im = np.frombuffer(r.stdout, np.uint8).reshape(y1 - y0, x1 - x0, 3)
        im = cv2.resize(im, (a.tile_w, int(a.tile_w * (y1 - y0) / (x1 - x0))), interpolation=cv2.INTER_AREA).copy()
        cv2.putText(im, f"{int(t) // 60}:{int(t) % 60:02d}", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 220), 3)
        tiles.append(im)
    blank = np.full_like(tiles[0], 255)
    rows = [np.hstack(tiles[i:i + a.cols] + [blank] * (a.cols - len(tiles[i:i + a.cols]))) for i in range(0, len(tiles), a.cols)]
    cv2.imwrite(a.out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(a.out)


def cmd_clip(a):
    W = os.path.abspath(a.W)
    out = f"{ROOT}/docs/games/{a.game_id}/clips/{a.name}.mp4"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = [PY, f"{HERE}/clip.py", f"{W}/full", f"{W}/video.webm", f"{W}/audio.m4a", out, a.t0, a.t1, a.poster]
    focus = a.focus
    if focus and focus.startswith("#"):
        # follow a player: his labeled tracks in this window, in time order (first covering track wins)
        num, t0, t1 = int(focus[1:]), float(a.t0), float(a.t1)
        P = next(P for P in periods(W) if P["start"] <= t0 <= P["end"])
        pdir = f"{W}/{P['label'].lower()}"
        sg = pd.read_csv(f"{pdir}/segs_final.csv")
        sg = sg[(sg.plabel == num) & (sg.t1 > t0) & (sg.t0 < t1)].sort_values("t0")
        focus = f"track:{pdir}/tracks_v1.csv:" + ",".join(str(int(x)) for x in sg.tid) if len(sg) else None
    sh(*cmd + ([focus] if focus else []))


def cmd_prepare(a):
    W = os.path.abspath(a.W)
    for P in periods(W):
        p = P["label"].lower(); pd_ = f"{W}/{p}"; rv = f"{W}/rev_{p}"
        if os.path.exists(f"{rv}/manifest.csv"):
            log(f"{p}: already prepared (reviews are tied to this segmentation; not redoing)")
            continue
        sh(PY, f"{HERE}/run_period.py", f"{W}/full", pd_, P["start"], P["end"], P["net"])
        sh(PY, f"{HERE}/review_sheets.py", pd_, rv, 8)
        sh(PY, f"{HERE}/roster_card.py", pd_, f"{rv}/roster_card.jpg", 8)
        n = len(glob.glob(f"{rv}/sheet_*.jpg"))
        log(f"{p}: {n} review sheets in {rv}")


def cmd_solve(a):
    W = os.path.abspath(a.W)
    labels = []
    for P in periods(W):
        p = P["label"].lower()
        tgt = [[k["start"], k["end"], 4] for k in P.get("pk", [])]
        sh(PY, f"{HERE}/run2.py", f"{W}/{p}", f"{W}/rev_{p}", P["end"], json.dumps([[P["start"], P["end"]]]), json.dumps(tgt))
        sh(PY, f"{HERE}/gantt.py", f"{W}/{p}/shifts_final.csv", f"{W}/{p}/segs_final.csv", f"{W}/gantt_{p}.png",
           P["start"], P["end"])
        labels.append(f"{p}:{P['label']}")
    sh(PY, f"{HERE}/final_stats.py", *labels, cwd=W)
    # live play vs stoppages -> "play" column in shifts_all.csv + stoppages.json
    sh(PY, f"{HERE}/stoppages.py", f"{W}/full", f"{W}/periods.json", f"{W}/shifts_all.csv")
    log(f"check {W}/gantt_*.png: the bottom panel should sit at 5 (4 during a penalty kill)")


def lada_game_id(date):
    """LADA's id for our game on `date` (YYYY-MM-DD): the team's last game in the league's public API, when it is
    that game. Best effort: None (and a note to set it by hand) when LADA is unreachable or has had a game since."""
    import urllib.request
    from roster import LADA_TEAM_ID
    url = f"https://api.ladaseattle.com/api/v1/team/{LADA_TEAM_ID}/game/last"
    try:
        with urllib.request.urlopen(url, timeout=20) as r:
            games = json.load(r)
    except Exception as e:
        log(f"LADA's last game unavailable ({e}); set lada_game_id in game.json by hand")
        return None
    for g in games:
        if str(g.get("date", ""))[:10] == date and g.get("id"):
            return g["id"]
    log(f"LADA's last game isn't the {date} one; set lada_game_id in game.json by hand")
    return None


def cmd_publish(a):
    W = os.path.abspath(a.W)
    from reads import load_reads
    gd = f"{ROOT}/games/{a.game_id}"; os.makedirs(gd, exist_ok=True)
    shutil.copy(f"{W}/shifts_all.csv", f"{gd}/shifts.csv")
    Ps = periods(W)
    from roster import TEAM, OPPONENTS
    import datetime
    reads, names = load_reads(f"{W}/full")
    date = a.date or a.game_id[:10]
    d = datetime.date.fromisoformat(date)
    game = dict(
        id=a.game_id, date=date, title=a.title or f"{TEAM} vs {OPPONENTS.get(a.opponent, a.opponent)}, {d:%b} {d.day}",
        eyebrow=a.eyebrow, opponent=a.opponent, video=a.video or open(f"{W}/url.txt").read().strip(),
        periods=[dict(label=P["label"], start=P["start"], end=P["end"]) for P in Ps],
        nets={P["label"]: P["net"] for P in Ps},
        penalty_kills=[dict(period=P["label"], **k) for P in Ps for k in P.get("pk", [])],
        notes=[], video_ends_early=bool(a.video_ends_early),
        fun=dict(name_reads={str(k): int(v) for k, v in names.num.value_counts().items()}),
        pipeline=dict(detections=sum(1 for _ in open(f"{W}/full/dets.csv")),
                      crops=len(os.listdir(f"{W}/full/crops")), reads=int(len(reads)),
                      reviewed=int(sum(len(pd.read_csv(m)) for m in glob.glob(f"{W}/rev_p*/manifest.csv")))))
    gj = f"{gd}/game.json"
    if os.path.exists(gj):  # keep hand-written fields (notes, title tweaks) from an earlier publish
        old = json.load(open(gj))
        for k in ("notes", "title", "eyebrow", "highlights", "video_ends_early", "lada_game_id", "opponent_name"):
            if old.get(k):
                game[k] = old[k]
    if not game.get("lada_game_id"):  # links the game to the LADA app's schedule and scores
        game["lada_game_id"] = lada_game_id(date)
    if os.path.exists(f"{W}/stoppages.json"):
        game["stoppages"] = json.load(open(f"{W}/stoppages.json"))
    if os.path.exists(f"{W}/highlights.json"):  # [{type, team|player, t, clip, poster, note}] from the clips step
        game["highlights"] = json.load(open(f"{W}/highlights.json"))
    json.dump(game, open(gj, "w"), indent=2, ensure_ascii=False)
    sh(PY, f"{HERE}/build_site.py")
    log(f"wrote {gd}; site rebuilt in docs/. Review, then commit and push to publish.")


def _size(path):
    n = 0
    for d, _, fs in os.walk(path):
        n += sum(os.lstat(os.path.join(d, f)).st_size for f in fs)
    return n


def cmd_archive(a):
    """Keep a finished game's data so it can be re-solved later (as ~/hockey-work/2026-09-27-vs-rr): detections, OCR
    reads, tracks, segments, reviews, periods, results, rink. Drop what is big and can be downloaded or regenerated:
    the video and audio, crops, overview frames, contact sheets and charts."""
    W = os.path.abspath(a.W)
    if not os.path.exists(f"{W}/shifts_all.csv"):
        sys.exit(f"{W} has no shifts_all.csv: archive a game only after solve and publish")
    before = _size(W)
    drop = [f"{W}/{n}" for n in ("video.webm", "audio.m4a", "yolo11m.pt", "full/crops", "full/ov")]
    drop += glob.glob(f"{W}/*.jpg") + glob.glob(f"{W}/*.png") + glob.glob(f"{W}/rev_p*/*.jpg")
    drop += glob.glob(f"{W}/full/ocr_done_*.txt") + glob.glob(f"{W}/p*/crops")
    for p in drop:
        if os.path.islink(p) or os.path.isfile(p):
            os.remove(p)
        elif os.path.isdir(p):
            shutil.rmtree(p)
    log(f"archived {W}: {before / 1e9:.1f} GB -> {_size(W) / 1e6:.0f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("url"); f.add_argument("W"); f.add_argument("--limit", type=float)
    f.add_argument("--rink", help="camera geometry (see rink.py); default renton")
    s = sub.add_parser("skaters"); s.add_argument("W"); s.add_argument("T0", type=float); s.add_argument("T1", type=float)
    sub.add_parser("prepare").add_argument("W")
    sub.add_parser("goals").add_argument("W")
    sub.add_parser("unknown").add_argument("W")
    sub.add_parser("archive").add_argument("W")
    fr = sub.add_parser("frames"); fr.add_argument("W"); fr.add_argument("out")
    for k in ("x0", "x1", "y0", "y1", "tile_w", "cols"):
        fr.add_argument(k, type=int)
    fr.add_argument("times", type=float, nargs="+")
    c = sub.add_parser("clip"); c.add_argument("W"); c.add_argument("game_id"); c.add_argument("name")
    c.add_argument("t0"); c.add_argument("t1"); c.add_argument("poster"); c.add_argument("focus", nargs="?")
    sub.add_parser("solve").add_argument("W")
    p = sub.add_parser("publish"); p.add_argument("W"); p.add_argument("game_id")
    p.add_argument("--opponent", required=True); p.add_argument("--eyebrow", required=True)
    p.add_argument("--date"); p.add_argument("--title"); p.add_argument("--video")
    p.add_argument("--video-ends-early", action="store_true", help="recording stops before the final horn")
    a = ap.parse_args()
    if a.cmd == "fetch":
        os.makedirs(a.W, exist_ok=True)
        open(f"{a.W}/url.txt", "w").write(a.url)
    {"fetch": cmd_fetch, "skaters": cmd_skaters, "prepare": cmd_prepare, "solve": cmd_solve, "goals": cmd_goals,
     "frames": cmd_frames, "clip": cmd_clip, "publish": cmd_publish, "unknown": cmd_unknown,
     "archive": cmd_archive}[a.cmd](a)
