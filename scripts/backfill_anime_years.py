"""One-time backfill of anime release years from the Jikan API.

Only movies/OVAs/specials are missing years in the local catalog (seasonal TV
already has them). This fetches the missing ones from Jikan and stores them in
data/anime_year_backfill.json, which src/recommender.py reads at startup.

It is:
  * popularity-ordered  — the anime that actually surface in results get done first
  * resumable           — already-fetched ids are skipped, progress saved every 25
  * polite / robust      — ~1 req/sec (Jikan's 60/min limit) with retry on 429/504

Usage:
    python scripts/backfill_anime_years.py [limit]

`limit` caps how many *new* anime to fetch this run (default 800). Re-run to
continue where it left off; failed ids (persistent 504s) are retried next run.
"""
import json
import os
import sys
import time

import pandas as pd
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(BASE, "data", "mal_anime.csv")
OUT = os.path.join(BASE, "data", "anime_year_backfill.json")

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 800
SLEEP = 1.0          # seconds between requests (respect Jikan's ~60/min)
MAX_RETRIES = 3      # per anime, for transient 429/503/504


def load_existing():
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as f:
                return json.load(f)
        except ValueError:
            pass
    return {}


def save(data):
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)


def parse_year(data):
    aired = data.get("aired") or {}
    prop_year = ((aired.get("prop") or {}).get("from") or {}).get("year")
    if prop_year:
        return int(prop_year)
    if data.get("year"):
        return int(data["year"])
    frm = aired.get("from")
    if frm and frm[:4].isdigit():
        return int(frm[:4])
    return None


def fetch_year(session, mal_id):
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(f"https://api.jikan.moe/v4/anime/{mal_id}", timeout=15)
            if r.status_code == 200:
                return parse_year(r.json().get("data", {}))
            if r.status_code in (429, 503, 504):
                time.sleep(4 + attempt * 2)  # back off and retry
                continue
            return None  # 404 etc. — nothing to fetch
        except requests.RequestException:
            time.sleep(3)
    return None


def main():
    df = pd.read_csv(CSV)
    members = pd.to_numeric(
        df["Members"].astype(str).str.replace(",", "", regex=False), errors="coerce"
    ).fillna(0)
    df = df.assign(_members=members)

    missing = df[df["Released_Year"].isna()].sort_values("_members", ascending=False)

    backfill = load_existing()
    pending = [
        str(row["myanimelist_id"])
        for _, row in missing.iterrows()
        if str(row["myanimelist_id"]) not in backfill
    ][:LIMIT]

    print(f"Have {len(backfill)} years already. Fetching up to {len(pending)} more...")
    session = requests.Session()
    session.headers.update({"User-Agent": "MoodWatch-backfill/1.0"})

    got = 0
    for i, mal_id in enumerate(pending, 1):
        year = fetch_year(session, mal_id)
        if year:
            backfill[mal_id] = year
            got += 1
        if i % 25 == 0:
            save(backfill)
            print(f"  {i}/{len(pending)} processed | {got} new years | {len(backfill)} total")
        time.sleep(SLEEP)

    save(backfill)
    print(f"DONE. {got} new years this run, {len(backfill)} total -> {OUT}")


if __name__ == "__main__":
    main()
