import pandas as pd, glob, difflib
from collections import Counter

from roster import SKATERS

# surname (as printed on jerseys) -> number, for fuzzy-matching OCR text; a surname two players share (father and
# son) says nothing about which one it is, so only their numbers tell them apart
_SHARED = Counter(name.upper() for name in SKATERS.values() if name)
NAMES = {name.upper(): num for num, name in SKATERS.items() if name and _SHARED[name.upper()] == 1}


_NORM = str.maketrans({"D": "O", "Y": "V", "Q": "O", "0": "O"})


def name_to_num(txt):
    """Fuzzy-match an OCR'd surname (often truncated at the jersey edge) to a roster number.
    OCR often confuses D/O and Y/V, so both sides are normalized first."""
    best, second, num = 0, 0, None
    txt = txt.translate(_NORM)
    for nm, n in NAMES.items():
        nm = nm.translate(_NORM)
        # compare against the full name and against same-length windows (truncated reads)
        r = difflib.SequenceMatcher(None, txt, nm).ratio()
        for k in range(0, max(1, len(nm) - len(txt) + 1)):
            r = max(r, difflib.SequenceMatcher(None, txt, nm[k:k + len(txt)]).ratio() * (0.85 if len(txt) < 6 else 1))
        if r > best:
            best, second, num = r, best, n
        elif r > second:
            second = r
    return num if best >= 0.65 and best - second >= 0.12 else None


def load_reads(outdir, min_score=0.9):
    """Returns (reads, names). reads has columns frame,i,num,src ('digit'|'name'); name reads override
    look-alike digit reads from the same crop."""
    o = pd.concat([pd.read_csv(f, header=None, names=["file", "text", "score"], dtype={"text": str})
                   for f in glob.glob(f"{outdir}/ocr_*.csv")])
    o = o.dropna().drop_duplicates(["file", "text"])
    o["frame"] = o.file.str[1:7].astype(int); o["i"] = o.file.str[8:10].astype(int)
    o["text"] = o.text.str.strip()
    dig = o[o.text.str.fullmatch(r"\d{1,2}") & (o.score >= min_score)].copy()
    dig["num"] = dig.text.astype(int); dig["src"] = "digit"
    nm = o[o.text.str.fullmatch(r"[A-Z]{4,}") & (o.score >= 0.7)].copy()
    cache = {x: name_to_num(x) for x in nm.text.unique()}
    nm["num"] = nm.text.map(cache)
    nm = nm.dropna(subset=["num"]).copy(); nm["num"] = nm.num.astype(int); nm["src"] = "name"
    # a name read in a crop replaces that crop's digit reads
    named = set(nm.file)
    dig = dig[~dig.file.isin(named)]
    reads = pd.concat([dig, nm])[["file", "frame", "i", "num", "src", "score"]]
    return reads, nm
