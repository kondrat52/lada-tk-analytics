"""zones.py W GAME_JSON : where play happened, for the trends page. Prints {"offence": .., "defence": ..}.

For every second of live play (inside a period, outside the estimated stoppages), the median foot x of everyone
detected on the ice says where the bunch of players is between our net (0) and theirs (1). Time in offence is the
share of live play spent in the third nearest their net, time in defence the share nearest ours; the rest is the
middle of the ice. Our net per period comes from game.json's nets, theirs is the rink's other net (rink.py)."""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rink import rink
from track import load


def zone_shares(full, game):
    """full: W/full with dets.csv; game: game.json's dict (periods, nets, stoppages). None without detections."""
    if not os.path.exists(f"{full}/dets.csv"):
        return None
    R = rink(full)
    d = load(f"{full}/dets.csv")
    d = d[d.onice & (d.conf >= 0.3)]
    per_frame = d.groupby("frame").agg(t=("t", "first"), x=("fx", "median"), n=("fx", "size"))
    per_frame = per_frame[per_frame.n >= 6]          # a bunch of players, not a lone skater or referee
    sec = per_frame.groupby(per_frame.t.astype(int)).x.median()
    T = int(max(sec.index.max(), max(p["end"] for p in game["periods"]))) + 2
    f = np.full(T, np.nan)
    for p in game["periods"]:
        ours = game["nets"][p["label"]]
        theirs = next(x for x in R.nets.values() if x != ours)
        s = sec[(sec.index >= p["start"]) & (sec.index < p["end"])]
        f[s.index.values] = np.clip((s.values - ours) / (theirs - ours), 0, 1)
    live = np.zeros(T, bool)
    for p in game["periods"]:
        live[p["start"]:p["end"]] = True
    for a, b in game.get("stoppages", []):
        live[int(a):int(b)] = False
    f[~live] = np.nan
    n = int(np.sum(~np.isnan(f)))
    if not n:
        return None
    return dict(offence=round(float(np.nansum(f > 2 / 3) / n), 4), defence=round(float(np.nansum(f < 1 / 3) / n), 4))


if __name__ == "__main__":
    print(json.dumps(zone_shares(f"{os.path.abspath(sys.argv[1])}/full", json.load(open(sys.argv[2])))))
