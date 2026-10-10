"""lada_ids.py : check roster.json's lada_player_ids against the team's LADA roster.

Signs in to LADA as you (password typed hidden, never stored or printed), reads
GET team/<lada_team_id>/Player and matches every roster.json player by jersey number +
surname. Prints, per player: same, NEW (an id to add), DIFFERS, no match (a sub off the
roster has none), and WRONG for an id LADA gives to someone else. Changes nothing.

    $PY pipeline/lada_ids.py
"""
import getpass, json, os, sys, unicodedata, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roster import SKATERS, GOALIE_NAMES, LADA_IDS, LADA_TEAM_ID

API = "https://api.ladaseattle.com/api/v1"


def fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def call(method, path, token=None, body=None):
    req = urllib.request.Request(f"{API}/{path}", method=method, headers={"Accept": "application/json"})
    if token:
        req.add_header("Authorization", token)  # raw, as the LADA app sends it
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data, timeout=20) as r:
        return r.read().decode()


def main():
    email = input("LADA email: ").strip()
    password = getpass.getpass("LADA password (hidden): ")
    token = call("POST", "user/login", body={"email": email, "password": password, "rememberMe": False})
    players = json.loads(call("GET", f"team/{LADA_TEAM_ID}/Player", token=token.strip().strip('"')))
    by_id = {p["id"]: p for p in players}
    print(f"\nLADA team {LADA_TEAM_ID}: {len(players)} players on the roster\n")
    for num, name in sorted({**SKATERS, **GOALIE_NAMES}.items()):
        hits = [p for p in players if p.get("number") == num and fold(name) in fold(p.get("name"))]
        mine = LADA_IDS.get(num)
        owner = by_id.get(mine)
        if mine and owner and (owner.get("number") != num or fold(name) not in fold(owner.get("name"))):
            state = f"WRONG: LADA gives {mine} to #{owner.get('number')} {owner.get('name')}"
        elif len(hits) == 1:
            pid = hits[0]["id"]
            state = "same" if mine == pid else "NEW" if mine is None else f"DIFFERS (roster.json {mine})"
        else:
            state = "ambiguous" if hits else "no match"
        lada = ", ".join(f"{p.get('name')} {p['id']}" for p in hits) or "-"
        print(f"#{num:<3} {name:<14} {lada:<30} {state}")


if __name__ == "__main__":
    main()
