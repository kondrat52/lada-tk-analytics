"""Camera geometry per rink. The pipeline was built on Renton's wide cut; other rinks film from other spots.

`run_game.py fetch --rink NAME` writes {"rink": NAME} to W/full/rink.json, next to dets.csv, and every later step
finds it there (a folder without one is Renton). Pixels are in the full 4K frame (3840 wide).

Positions are a detection's foot x and `rel` = foot y minus the far-boards curve y at that x (boards_poly.npy from
boards.py; > 0 is below the boards line in the image). Bench rules work in "bench depth": how far a foot is past
the boards between the ice and our bench, in Renton pixels (a Renton player at the bench is ~65 px tall), so the
thresholds in shifts.py and run2.py hold at every rink. Negative = on the ice side.
"""
import json, os
import numpy as np
from matplotlib.path import Path


class Renton:
    """Camera high on the near side; both benches behind the far boards, one left of center and its mirror image
    right of center, with the penalty boxes between them. So far the away team (we wear light blue) has had the
    left one and the home team (white) the right one."""
    crop_top = 560 / 1702         # detection band starts here (fraction of frame height); ceiling above
    board_band = (0.41, 0.76)     # rows where boards.py looks for the far boards' yellow kick plate (fractions)
    board_lowest = False          # boards.py: per column, only the lowest yellow run (yellow signs above the boards)
    center_x = 1880
    nets = {"left": 540, "right": 3245}
    ocr_skip_depth = None         # OCR skips crops this deep in our bench (None: read everything)
    min_break = 25                # seconds of empty open ice that make an intermission
    bench_side = "left"           # our usual bench; rink.json "bench" can pick the other one
    scoreboard = (3290, 690, 130, 80)  # x, y, w, h of the arena scoreboard (scoreboard.py)

    def __init__(self, board_poly, bench=None):
        self.P = board_poly
        self.mirror = bool(bench) and bench != self.bench_side

    def _bench_x(self, x):
        """x as if we sat on the left bench: the right one is its mirror image about center ice."""
        return 2 * self.center_x - x if self.mirror else x

    def onice(self, x, rel):
        return rel > 5

    def open_ice(self, x, rel):
        """Out on the ice, away from the boards: nobody here for min_break seconds means an intermission."""
        return self.onice(x, rel) & (rel > 60)

    def bench_depth(self, x, rel):
        return -rel

    def at_bench(self, x, rel):
        """At our bench: standing at its boards or behind them."""
        x = self._bench_x(x)
        return (x > 1340) & (x < 1760) & (rel < 15)

    def bench_zone(self, x, rel):
        """Off the ice but tracked anyway, to see players come and go."""
        x = self._bench_x(x)
        return (x > 1300) & (x < 1800) & (rel > -80)

    def in_crease(self, x, rel, net_x):
        """Our goalie's spot in front of net_x (the goalie's detections are dropped from skater tracking)."""
        return (np.abs(x - net_x) < 110) & (rel > 0) & (rel < 75)


class Snoqualmie(Renton):
    """Camera high on the near side at center, very wide (3840x1536). Both benches are on the near side at the
    frame edges: ours at the right, theirs at the left. The far boards sit at y 450-610."""
    crop_top = 340 / 1536
    board_band = (0.27, 0.45)
    center_x = 1890
    nets = {"left": 630, "right": 3260}          # where the goalies stand (same crease size as Renton's)
    # the ice, with the near boards and both benches' boards as its left, right and bottom sides (the far boards
    # curve is the top)
    ICE = Path([(130, 0), (3720, 0), (3720, 598), (3395, 1195), (3360, 1200), (3140, 1390), (2970, 1536),
                (910, 1536), (700, 1290), (410, 990), (130, 545)])
    BENCH = ((3720, 598), (3395, 1195))   # top of the boards between the ice and our bench
    BENCH_Y = (560, 1260)                 # the bench's extent down the frame
    SCALE = 1.6                           # a skater at our bench's boards is ~123 px tall; at Renton's, ~75
    # the bench is close to the camera, so its sitters make over half of all crops; their reads are never used
    ocr_skip_depth = 60
    # intermissions are short (~1.5 min): players stand at their bench doors, then skate out to warm up
    min_break = 10
    bench_side = "right"
    scoreboard = (1790, 262, 280, 116)

    def __init__(self, board_poly, bench=None):
        if bench and bench != self.bench_side:
            raise NotImplementedError("Snoqualmie's left bench isn't mapped yet")
        super().__init__(board_poly)

    def _xy(self, x, rel):
        x = np.asarray(x, float); rel = np.asarray(rel, float)
        return x, rel + np.polyval(self.P, x)

    def onice(self, x, rel):
        x, y = self._xy(x, rel)
        inside = self.ICE.contains_points(np.c_[x.ravel(), y.ravel()]).reshape(x.shape)
        return (np.asarray(rel) > 5) & inside

    def open_ice(self, x, rel):
        x = np.asarray(x, float)
        return super().open_ice(x, rel) & (x > 700) & (x < 3150)   # clear of both bench doors

    def bench_depth(self, x, rel):
        x, y = self._xy(x, rel)
        (ax, ay), (bx, by) = self.BENCH
        nx, ny = by - ay, ax - bx          # normal pointing right, into the bench
        d = ((x - ax) * nx + (y - ay) * ny) / np.hypot(nx, ny) / self.SCALE
        return np.where((y > self.BENCH_Y[0]) & (y < self.BENCH_Y[1]), d, -999.0)

    def at_bench(self, x, rel):
        return self.bench_depth(x, rel) > -15

    def bench_zone(self, x, rel):
        return self.at_bench(x, rel)


class Kirkland(Renton):
    """Camera low at center ice on the near side with a fisheye lens (3840x1536): the far boards bow up to y ~430
    at center and dip to ~700 at the frame edges, where the end boards run down the sides. Both benches are behind
    the far boards like Renton's, but not mirror images: the home one (we wore white) right of center, the away
    one left; the doors are at the blue posts (x 1612 and 2265). The near-side corners at the bottom of the frame are
    off the ice (timekeeper and penalty boxes)."""
    crop_top = 320 / 1536
    board_band = (0.25, 0.49)
    board_lowest = True           # the HOCKEY sign at the right has yellow letters
    center_x = 1930
    nets = {"left": 605, "right": 3255}
    min_break = 25
    bench_side = "right"
    BENCHES = {"left": (1340, 1720), "right": (2160, 2560)}   # x at the boards, with Renton's ~30 px margins
    scoreboard = (358, 396, 136, 82)
    # the ice inside the end and near boards (the far boards curve is the top)
    ICE = Path([(0, 0), (3840, 0), (3840, 690), (3800, 717), (3707, 917), (3653, 1037), (3560, 1277),
                (3440, 1450), (3400, 1536), (560, 1536), (400, 1317), (333, 1183), (260, 1090), (150, 870),
                (40, 650), (0, 640)])

    def __init__(self, board_poly, bench=None):
        self.P = board_poly
        self.bench_x = self.BENCHES[bench or self.bench_side]

    def onice(self, x, rel):
        x = np.asarray(x, float); rel = np.asarray(rel, float)
        y = rel + np.polyval(self.P, x)
        inside = self.ICE.contains_points(np.c_[x.ravel(), y.ravel()]).reshape(x.shape)
        return (rel > 5) & inside

    def at_bench(self, x, rel):
        x0, x1 = self.bench_x
        return (x > x0) & (x < x1) & (rel < 15)

    def bench_zone(self, x, rel):
        x0, x1 = self.bench_x
        return (x > x0 - 40) & (x < x1 + 40) & (rel > -80)


RINKS = {"renton": Renton, "snoqualmie": Snoqualmie, "kirkland": Kirkland}

# Our jersey that game, as tests on process.py's torso colour fractions (the dets.csv columns, or a dict of them):
# `ours` picks our players for tracking, the looser `crop` which detections get a 4K crop for OCR and review.
# White (home) jerseys have blue numbers and trim, so the blue fraction is low; what tells them apart is a white
# torso with little dark in it. Referees' stripes are 25-55% dark, dark jerseys more. Red jerseys with white
# stripes (a Sea Otter's) are 25-60% white but 30-50% red; ours are under 10% red.
JERSEYS = {
    "light blue": dict(ours=lambda c: c["blue"] >= 0.3, crop=lambda c: c["blue"] >= 0.12),
    "white": dict(ours=lambda c: (c["red"] < 0.1) & (((c["white"] >= 0.35) & (c["dark"] < 0.3)) |
                                                    ((c["white"] >= 0.25) & (c["dark"] < 0.2) & (c["red"] < 0.05))),
                  crop=lambda c: (c["white"] >= 0.25) & (c["dark"] < 0.35) & (c["red"] < 0.1)),
}


def _full_dir(folder):
    """W/full for a folder holding dets.csv itself or a link to it (period dirs)."""
    if os.path.exists(os.path.join(folder, "rink.json")) or not os.path.exists(os.path.join(folder, "dets.csv")):
        return folder
    return os.path.dirname(os.path.realpath(os.path.join(folder, "dets.csv")))


def _config(folder):
    p = os.path.join(_full_dir(folder), "rink.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def rink_name(folder):
    return _config(folder).get("rink", "renton")


def jersey(folder):
    """Our jersey's colour tests (JERSEYS) for this video: rink.json's "jersey", light blue unless set."""
    return JERSEYS[_config(folder).get("jersey", "light blue")]


def rink(folder):
    """Geometry for the video whose detections live in `folder` (W/full, or a period dir linking into it)."""
    full = _full_dir(folder)
    bp = os.path.join(full, "boards_poly.npy")
    return RINKS[rink_name(folder)](np.load(bp) if os.path.exists(bp) else None, bench=_config(folder).get("bench"))
