"""Team roster shared by the pipeline (edit ../roster.json, or point ROSTER at another file)."""
import json, os

_path = os.environ.get("ROSTER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "roster.json"))
_r = json.load(open(_path))
TEAM = _r["team"]                                           # short display name on the site
TEAM_NAME = _r.get("team_name", TEAM)                       # official name in the LADA app
LADA_TEAM_ID = _r.get("lada_team_id")
SITE_URL = _r.get("site_url", "")
SKATERS = {int(k): v for k, v in _r["skaters"].items()}   # number -> surname
GOALIES = [int(k) for k in _r.get("goalies", {})]
GOALIE_NAMES = {int(k): v for k, v in _r.get("goalies", {}).items()}
LADA_IDS = {int(k): v for k, v in _r.get("lada_player_ids", {}).items()}  # number -> LADA player id (team roster)
