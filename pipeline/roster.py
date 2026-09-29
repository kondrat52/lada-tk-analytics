"""Team roster shared by the pipeline (edit ../roster.json, or point ROSTER at another file)."""
import json, os

_path = os.environ.get("ROSTER", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "roster.json"))
_r = json.load(open(_path))
TEAM = _r["team"]
SKATERS = {int(k): v for k, v in _r["skaters"].items()}   # number -> surname
GOALIES = [int(k) for k in _r.get("goalies", {})]
