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
    """Camera high on the near side; both benches behind the far boards, ours left of center."""
    crop_top = 560 / 1702         # detection band starts here (fraction of frame height); ceiling above
    board_band = (0.41, 0.76)     # rows where boards.py looks for the far boards' yellow kick plate (fractions)
    center_x = 1880
    nets = {"left": 540, "right": 3245}
    ocr_skip_depth = None         # OCR skips crops this deep in our bench (None: read everything)
    min_break = 25                # seconds of empty open ice that make an intermission

    def __init__(self, board_poly):
        self.P = board_poly

    def onice(self, x, rel):
        return rel > 5

    def open_ice(self, x, rel):
        """Out on the ice, away from the boards: nobody here for min_break seconds means an intermission."""
        return self.onice(x, rel) & (rel > 60)

    def bench_depth(self, x, rel):
        return -rel

    def at_bench(self, x, rel):
        """At our bench: standing at its boards or behind them."""
        return (x > 1340) & (x < 1760) & (rel < 15)

    def bench_zone(self, x, rel):
        """Off the ice but tracked anyway, to see players come and go."""
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


RINKS = {"renton": Renton, "snoqualmie": Snoqualmie}


def _full_dir(folder):
    """W/full for a folder holding dets.csv itself or a link to it (period dirs)."""
    if os.path.exists(os.path.join(folder, "rink.json")) or not os.path.exists(os.path.join(folder, "dets.csv")):
        return folder
    return os.path.dirname(os.path.realpath(os.path.join(folder, "dets.csv")))


def rink_name(folder):
    p = os.path.join(_full_dir(folder), "rink.json")
    return json.load(open(p))["rink"] if os.path.exists(p) else "renton"


def rink(folder):
    """Geometry for the video whose detections live in `folder` (W/full, or a period dir linking into it)."""
    full = _full_dir(folder)
    bp = os.path.join(full, "boards_poly.npy")
    return RINKS[rink_name(folder)](np.load(bp) if os.path.exists(bp) else None)
