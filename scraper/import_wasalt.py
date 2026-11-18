"""Merge a wasalt_listings.json downloaded by the browser collector into
data/raw/wasalt_listings.jsonl (dedup by id).

usage: python scraper/import_wasalt.py [path-to-json]   (default: ~/Downloads/wasalt_listings*.json)
"""
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "raw" / "wasalt_listings.jsonl"
SAFE_KEYS = {
    "id", "url", "title", "purpose", "category", "type", "city", "district", "territory", "address",
    "price", "rent_frequency", "currency", "bedrooms", "bathrooms", "area_sqm", "furnishing",
    "description", "amenities", "lat", "lon", "images", "rega_licensed", "verified",
    "published_at", "updated_at", "source",
}

files = [Path(sys.argv[1])] if len(sys.argv) > 1 else sorted((Path.home() / "Downloads").glob("wasalt_listings*.json"))
seen = set()
if OUT.exists():
    seen = {json.loads(l)["id"] for l in OUT.read_text(encoding="utf8").split("\n") if l.strip()}
added = 0
with OUT.open("a", encoding="utf8") as f:
    for fp in files:
        for r in json.loads(fp.read_text(encoding="utf8")):
            if r.get("id") in seen or not r.get("price"):
                continue
            seen.add(r["id"])
            f.write(json.dumps({k: v for k, v in r.items() if k in SAFE_KEYS}, ensure_ascii=False) + "\n")
            added += 1
print(f"files={len(files)} added={added} total={len(seen)}")
