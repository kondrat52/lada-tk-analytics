#!/bin/sh
# Copy the shift sheet feeds from their new address into <out>/ (default _site/) at the paths of the old one, and
# say on $GITHUB_OUTPUT whether that differs from what the old address serves now.
set -eu
NEW=https://kondrat52.github.io/lada-analytics
OLD=https://kondrat52.github.io/lada-tk-analytics
out=${1:-_site}
bust="v=$(date +%s)"   # past the Pages CDN cache

get() { curl -fsS --retry 3 "$1?$bust" -o "$2"; }

copy() {   # copy <team dir at the new address> <api dir under out>
    src=$NEW/$1/api dst=$out/$2
    mkdir -p "$dst/games"
    for f in index season trends roster; do get "$src/$f.json" "$dst/$f.json"; done
    for id in $(jq -r '.games[].id' "$dst/index.json"); do get "$src/games/$id.json" "$dst/games/$id.json"; done
}

rm -rf "$out"
copy tk api
copy bw bw/api
cp redirect.html "$out/404.html"
cp redirect.html "$out/index.html"
sum=$(cd "$out" && find . -type f | LC_ALL=C sort | xargs cat | sha256sum | cut -c1-64)
echo "$sum" > "$out/mirror.sha"
live=$(curl -fsS "$OLD/mirror.sha?$bust" 2>/dev/null || true)
echo "$(find "$out" -type f | wc -l) files, sha $sum (live: ${live:-none})"
echo "changed=$([ "$sum" = "$live" ] && echo false || echo true)" >> "${GITHUB_OUTPUT:-/dev/null}"
