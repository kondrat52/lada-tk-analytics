"""JSON feed for apps (e.g. the LADA app), published with the site under docs/api/.

  api/index.json          team, games list, links to everything else
  api/games/<id>.json     one game: periods, per-player stats, every shift, highlights, stoppages
  api/season.json         season totals per player
  api/roster.json         numbers, surnames, LADA player ids
  api/trends.json         per game: the team's measures and each skater's, behind the trends page (build_trends.py)

Times are seconds. Shift and highlight times are seconds into the game video (as on YouTube); *_in_period fields
are seconds from that period's start. See API.md for the field list. Bump SCHEMA when a field changes meaning or
goes away; adding fields doesn't need a bump.
"""
import os, json
import numpy as np, pandas as pd
from roster import SKATERS, MEMBERS, SUBS, GOALIE_NAMES, LADA_IDS, TEAM_NAME, TEAM_SHORT, LADA_TEAM_ID, SITE_URL, OPPONENTS

SCHEMA = 1


def _team():
    return {"name": TEAM_NAME, "short_name": TEAM_SHORT, "lada_team_id": LADA_TEAM_ID}


def _player(num):
    num = int(num)
    p = {"number": num, "name": SKATERS.get(num, GOALIE_NAMES.get(num, "")), "lada_player_id": LADA_IDS.get(num)}
    return {**p, "sub": True} if num in SUBS else p


def _num(x, nd=1):
    """JSON-friendly number: ints stay ints, floats rounded, NaN -> None."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    x = float(x)
    return int(x) if x.is_integer() else round(x, nd)


def season_table(A):
    """Season totals per player from all games' shifts (A has a 'game' column and a boolean 'cut' column:
    shifts cut off by a recording ending mid-play, which don't count as short shifts)."""
    if "play" not in A:
        A = A.assign(play=np.nan)
    per_game = A.groupby(["player", "game"]).dur.sum().reset_index()
    s = A.groupby("player").agg(shifts=("dur", "size"), toi=("dur", "sum"), play=("play", "sum"),
                                avg=("dur", "mean"), longest=("dur", "max"))
    s["shortest"] = A[~A.cut.astype(bool)].groupby("player").dur.min()
    s["gp"] = per_game.groupby("player").size()
    s["toi_gp"] = s.toi / s.gp
    return s.sort_values("toi_gp", ascending=False)


def _when_where(game):
    """'Sun Sep 27, 2026 · 7:50 PM · Renton' -> ('7:50 PM', 'Renton'); missing parts are None."""
    parts = [p.strip() for p in (game.get("eyebrow") or "").split("·")]
    return (parts[1] if len(parts) > 1 else None), (parts[2] if len(parts) > 2 else None)


def _shots(game):
    """Shots on goal from the arena scoreboard: totals and per period, or None when not read."""
    S = game.get("shots")
    if not S:
        return None
    per = [{"label": p["label"], "for": S[p["label"]][0], "against": S[p["label"]][1]}
           for p in game["periods"] if p["label"] in S]
    return {"for": sum(x["for"] for x in per), "against": sum(x["against"] for x in per), "periods": per}


def game_doc(game, A, players, highlights):
    """players/highlights: as computed for the game page (build_report.player_rows / highlights)."""
    base = SITE_URL.rstrip("/") + f"/games/{game['id']}/"
    pstart = {p["label"]: p["start"] for p in game["periods"]}
    hl = [h for h in highlights if h["type"] == "goal"]
    return {
        "schema": SCHEMA,
        "id": game["id"],
        "date": game["date"],
        "title": game.get("title"),
        "subtitle": game.get("eyebrow"),
        "time": _when_where(game)[0],
        "rink": _when_where(game)[1],
        "team": _team(),
        "opponent": {"code": game["opponent"], "name": game.get("opponent_name") or OPPONENTS.get(game["opponent"])},
        "lada_game_id": game.get("lada_game_id"),
        "page_url": base,
        "video_url": game.get("video"),
        "video_ends_early": bool(game.get("video_ends_early")),
        "goals_on_video": {"for": sum(1 for h in hl if h.get("team") == "for"),
                           "against": sum(1 for h in hl if h.get("team") == "against")},
        "shots": _shots(game),
        "periods": [{"label": p["label"], "start": p["start"], "end": p["end"], "length": p["end"] - p["start"]}
                    for p in game["periods"]],
        "penalty_kills": [{"period": k["period"], "start": k["start"], "end": k["end"],
                           "player": _player(k["player"]) if k.get("player") is not None else None}
                          for k in game.get("penalty_kills", [])],
        "players": [{**_player(p["num"]),
                     "shifts": p["shifts"], "toi": _num(p["toi"]), "play": _num(p.get("play")),
                     "avg_shift": _num(p["avg"]), "median_shift": _num(p["median"]),
                     "longest_shift": _num(p["longest"]), "shortest_shift": _num(p.get("shortest")),
                     "periods": [{"label": lab, "shifts": x[0], "toi": _num(x[1]), "avg_shift": _num(x[2])} if x else
                                 {"label": lab, "shifts": 0, "toi": 0, "avg_shift": None}
                                 for lab, x in zip([q["label"] for q in game["periods"]], p["per"])]}
                    for p in sorted(players, key=lambda p: -p["toi"])],
        "shifts": [{"number": int(r.player), "period": r.period, "start": _num(r.t0), "end": _num(r.t1),
                    "duration": _num(r.dur), "play": _num(getattr(r, "play", None)),
                    "start_in_period": _num(r.t0 - pstart[r.period])}
                   for r in A.sort_values(["t0", "player"]).itertuples()],
        "highlights": [{"type": h["type"], "team": h.get("team"),
                        "player": _player(h["player"]) if h.get("player") is not None else None,
                        "t": h["t"], "period": h.get("period"),
                        "t_in_period": _num(h["t"] - pstart[h["period"]]) if h.get("period") in pstart else None,
                        "clip_url": base + h["clip"], "poster_url": base + h["poster"], "note": h.get("note"),
                        "on_ice": [_player(n) for n in h.get("on_ice", [])]}
                       for h in highlights],
        "stoppages": game.get("stoppages", []),
    }


def trends_doc(rows):
    """api/trends.json: the measures behind the trends page, one entry per game, newest first.
    rows: (game, team, players) per game, as build_trends.game_rows returns them."""
    games = []
    for game, t, players in sorted(rows, key=lambda r: r[0]["date"], reverse=True):
        games.append({
            "id": game["id"], "date": game["date"], "rink": _when_where(game)[1],
            "opponent": {"code": game["opponent"], "name": game.get("opponent_name") or OPPONENTS.get(game["opponent"])},
            "lada_game_id": game.get("lada_game_id"),
            "video_ends_early": t["video_ends_early"],
            "goals_on_video": {"for": t["gf"], "against": t["ga"]}, "result": t["result"],
            "shots": _shots(game),
            "zones": {"offence": t["offence"], "defence": t["defence"]} if t["offence"] is not None else None,
            "skaters": t["skaters"], "avg_shift": _num(t["avg_shift"]), "play_share": _num(t["live_pct"], 4),
            "penalties": {"count": t["penalties"],
                          "short_handed": _num(sum(k["end"] - k["start"] for k in game.get("penalty_kills", []))),
                          "goals_against": t["pk_ga"]},
            "players": [{**_player(p["num"]), "shifts": p["shifts"], "toi": _num(p["toi"]),
                         "avg_shift": _num(p["avg_shift"]), "toi_share": _num(p["toi_share"], 4),
                         "avg_shift_p1": _num(p["p1"]), "avg_shift_p3": _num(p["p3"]), "plus_minus": p["plus_minus"]}
                        for p in sorted(players, key=lambda p: -p["toi"])],
        })
    return {"schema": SCHEMA, "team": _team(), "updated": games[0]["date"] if games else None, "games": games}


def _per_game(docs_by_game, games):
    """number -> [{id, date, opponent, toi, shifts, avg_shift, play}], newest game first."""
    out = {}
    for g in sorted(games, key=lambda g: g["date"], reverse=True):
        doc = docs_by_game[g["id"]]
        for p in doc["players"]:
            out.setdefault(p["number"], []).append({
                "id": g["id"], "date": g["date"], "opponent": doc["opponent"],
                "toi": p["toi"], "shifts": p["shifts"], "avg_shift": p["avg_shift"], "play": p["play"]})
    return out


def write_feed(root, games, docs_by_game, season):
    api = f"{root}/docs/api"
    os.makedirs(f"{api}/games", exist_ok=True)
    site = SITE_URL.rstrip("/")
    updated = max((g["date"] for g in games), default=None)
    for gid, doc in docs_by_game.items():
        json.dump(doc, open(f"{api}/games/{gid}.json", "w"), ensure_ascii=False, separators=(",", ":"))
    ordered = sorted(games, key=lambda g: g["date"], reverse=True)
    index = {
        "schema": SCHEMA, "team": _team(), "site_url": site + "/", "updated": updated,
        "season_url": f"{site}/api/season.json", "roster_url": f"{site}/api/roster.json",
        "trends_url": f"{site}/api/trends.json",
        "games": [{"id": g["id"], "date": g["date"], "title": g.get("title"), "subtitle": g.get("eyebrow"),
                   "time": _when_where(g)[0], "rink": _when_where(g)[1],
                   "opponent": {"code": g["opponent"], "name": g.get("opponent_name") or OPPONENTS.get(g["opponent"])},
                   "lada_game_id": g.get("lada_game_id"),
                   "goals_on_video": docs_by_game[g["id"]]["goals_on_video"],
                   "shots": ({k: docs_by_game[g["id"]]["shots"][k] for k in ("for", "against")}
                             if docs_by_game[g["id"]]["shots"] else None),
                   "highlights": len(docs_by_game[g["id"]]["highlights"]),
                   "page_url": f"{site}/games/{g['id']}/", "json_url": f"{site}/api/games/{g['id']}.json"}
                  for g in ordered],
    }
    json.dump(index, open(f"{api}/index.json", "w"), ensure_ascii=False, indent=1)
    per_game = _per_game(docs_by_game, games)
    season_doc = {
        "schema": SCHEMA, "team": _team(), "updated": updated, "games": [g["id"] for g in ordered],
        "players": [{**_player(p), "games_played": int(r.gp), "shifts": int(r.shifts), "toi": _num(r.toi),
                     "toi_per_game": _num(r.toi_gp), "play": _num(r.play) if r.play > 0 else None,
                     "avg_shift": _num(r.avg), "longest_shift": _num(r.longest), "shortest_shift": _num(r.shortest),
                     "games": per_game.get(int(p), [])}
                    for p, r in season.iterrows()],
    }
    json.dump(season_doc, open(f"{api}/season.json", "w"), ensure_ascii=False, indent=1)
    roster_doc = {"schema": SCHEMA, "team": _team(),
                  "skaters": [_player(n) for n in sorted(MEMBERS)],
                  "subs": [_player(n) for n in sorted(SUBS)],
                  "goalies": [_player(n) for n in sorted(GOALIE_NAMES)]}
    json.dump(roster_doc, open(f"{api}/roster.json", "w"), ensure_ascii=False, indent=1)
    return len(docs_by_game)
