# lada-tk-analytics (moved)

The shift sheets moved to https://kondrat52.github.io/lada-analytics/ (repo:
[kondrat52/lada-analytics](https://github.com/kondrat52/lada-analytics)).

This repo only keeps the old addresses working for a while:

- The JSON feeds at `https://kondrat52.github.io/lada-tk-analytics/api/` (Turbo Kings) and `.../bw/api/` (Blue
  Wings), which LADA app versions up to 1.4.36 read. `mirror.sh` copies the new feeds there every hour
  (`.github/workflows/mirror.yml`); the links inside them point to the new address.
- Old page links: `redirect.html`, the site's 404 page, sends them to the same page at the new address.

Delete this repo once those app versions are gone. GitHub turns the hourly copy off after 60 days without a commit
here; turn it back on in Actions → Mirror (or `gh workflow enable mirror.yml -R kondrat52/lada-tk-analytics`).
