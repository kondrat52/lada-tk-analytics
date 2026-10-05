"""Team roster shared by the pipeline (edit ../roster.json, or point ROSTER at another file)."""
import json, os

_path = os.environ.get("ROSTER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "roster.json"))
_r = json.load(open(_path))
TEAM = _r["team"]                                           # short display name on the site
TEAM_NAME = _r.get("team_name", TEAM)                       # official name in the LADA app
TEAM_SHORT = _r.get("team_short", TEAM)
LADA_TEAM_ID = _r.get("lada_team_id")
SITE_URL = _r.get("site_url", "")
MEMBERS = {int(k): v for k, v in _r["skaters"].items()}   # number -> surname: the team's own skaters
SUBS = {int(k): v for k, v in _r.get("subs", {}).items()}  # skaters who have subbed for us, not on the team
SKATERS = {**MEMBERS, **SUBS}                               # everyone the pipeline looks for
GOALIES = [int(k) for k in _r.get("goalies", {})]
GOALIE_NAMES = {int(k): v for k, v in _r.get("goalies", {}).items()}
LADA_IDS = {int(k): v for k, v in _r.get("lada_player_ids", {}).items()}  # number -> LADA player id (team roster)

_opp = os.path.join(os.path.dirname(_path), "opponents.json")
OPPONENTS = json.load(open(_opp)) if os.path.exists(_opp) else {}   # code -> full name


def opponent_name(game):
    """Full opponent name for a game: game.json's opponent_name, else opponents.json, else the code."""
    return game.get("opponent_name") or OPPONENTS.get(game["opponent"]) or game["opponent"]
