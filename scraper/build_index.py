"""Turn raw scraped data into the app's knowledge base.

Inputs : data/raw/darglobal_pages.jsonl, data/raw/wasalt_listings.jsonl
Outputs: data/processed/concierge.db   (SQLite: listings, projects, chunks)

* listings  -> structured table for the `search_listings` tool
* projects  -> one row per DarGlobal project page with parsed spec fields
* chunks    -> passage-level text from every DarGlobal page for BM25 retrieval
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "processed" / "concierge.db"

COUNTRIES = {
    "saudi": "Saudi Arabia", "jeddah": "Saudi Arabia", "riyadh": "Saudi Arabia",
    "dubai": "UAE", "uae": "UAE", "abu dhabi": "UAE", "ras al khaimah": "UAE",
    "oman": "Oman", "muscat": "Oman", "aida": "Oman", "qatar": "Qatar", "doha": "Qatar",
    "spain": "Spain", "marbella": "Spain", "benahav": "Spain", "estepona": "Spain",
    "london": "UK", "united kingdom": "UK", "bosnia": "Bosnia", "maldives": "Maldives",
}
BRANDS = [
    "Trump", "Pagani", "Lamborghini", "Aston Martin", "Missoni", "Elie Saab", "Fendi",
    "W Hotels", "W Residences", "Marriott", "Mouawad", "Paramount", "Mulliner", "Bentley",
]
SPEC_LABELS = [
    "PROPERTY TYPE", "UNIT TYPE", "LOCATION", "NUMBER OF FLOORS", "AREA (SQM)",
    "AREA", "STARTING PRICE", "PRICE", "PAYMENT PLAN", "COMPLETION", "HANDOVER",
    "BEDROOMS", "NUMBER OF UNITS", "DEVELOPER",
]
NOISE = re.compile(
    r"^(REGISTER INTEREST|DOWNLOAD BROCHURE|BOOK UNIT|CHOOSE YOUR RESIDENCE|Gallery|"
    r"VIEW ALL IMAGES|English|\||\+?\d[\d\s]{7,}|ENQUIRE NOW|READ MORE|LOAD MORE|SUBMIT)$",
    re.I,
)


PROTECT = ["DarGlobal", "DaVinci", "LinkedIn", "YouTube", "WhatsApp", "TikTok", "McLaren", "iPhone",
           "PropTech", "FinTech", "GmbH", "RAKEZ", "PLC"]
GLUE = re.compile(r"(?<=[a-z0-9\)\.%])(?=[A-Z][a-z])|(?<=[a-z])(?=[A-Z]{3,})")


def unglue(t: str) -> str:
    """The site renders labels/values as inline spans, so innerText glues
    them ("Property TypeSeafront"). Re-insert breaks at case boundaries."""
    t = t.replace(" ", "\n").replace("\xa0", " ")
    for i, w in enumerate(PROTECT):
        t = t.replace(w, f"@@{i}@@")
    t = GLUE.sub("\n", t)
    for i, w in enumerate(PROTECT):
        t = t.replace(f"@@{i}@@", w)
    return t


def clean_text(t: str) -> str:
    t = unglue(t)
    lines = [l.strip() for l in t.split("\n")]
    lines = [l for l in lines if l and not NOISE.match(l)]
    return "\n".join(lines)


SPEC_RE = re.compile(
    r"(Property Type|Unit Types?|Location|Number of Floors|Area \(sqm\)|Area|Status|Starting Price|"
    r"Price Starting From|Payment Plan|Completion|Handover|Delivery|Bedrooms|Number of Units|Plot Area)"
    r"\s*:?\s*\n?(.{2,90}?)(?=\n|$)", re.I)


def parse_specs(text: str) -> dict:
    specs = {}
    for label, val in SPEC_RE.findall(text[:6000]):
        val = val.strip(" :|")
        key = label.lower().replace(" (sqm)", "_sqm").replace(" ", "_")
        for unit in ("(SQFT)", "(SQM)"):
            if val.upper().startswith(unit):
                key, val = "area_" + unit.strip("()").lower(), val[len(unit):].strip()
        if not val or not (val[0].isupper() or val[0].isdigit()) or "Area(" in val:
            continue
        if val.endswith(".") and len(val) < 40:
            continue
        val = val.replace("Photo Gallery", "").strip()
        if val and len(val) < 90 and not val.lower().startswith(("the ", "we ", "our ")) and key not in specs:
            specs[key] = val
    return {k: v for k, v in specs.items() if k != "area" or "area_sqm" not in specs}


def guess_country(*texts: str) -> str | None:
    # texts are in priority order (location spec > title > description > body)
    for t in texts:
        t = (t or "").lower()
        hits = [(t.find(k), v) for k, v in COUNTRIES.items() if k in t]
        if hits:
            return min(hits)[1]
    return None


def guess_brands(*texts: str) -> list[str]:
    blob = " ".join(t or "" for t in texts)
    return [b for b in BRANDS if b.lower() in blob.lower()]


def good_desc(d: str | None) -> str | None:
    d = (d or "").strip()
    return d if len(d) > 30 and d.lower() != "null" else None


def nice_name(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s.title() if s.isupper() or s.islower() else s


def chunk(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    paras = [p for p in re.split(r"\n+", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 1 > size and cur:
            out.append(cur.strip())
            cur = cur[-overlap:] + "\n"
        cur += p + "\n"
    if cur.strip():
        out.append(cur.strip())
    return out


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        print(f"!! missing {path.name}")
        return []
    out = []
    for l in path.read_text(encoding="utf8").split("\n"):
        try:
            out.append(json.loads(l))
        except json.JSONDecodeError:
            pass  # partial line from a scraper still writing
    return out


def main() -> None:
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    con.executescript(
        """
        CREATE TABLE listings(
          id INTEGER PRIMARY KEY, url TEXT, title TEXT, purpose TEXT, category TEXT, type TEXT,
          city TEXT, district TEXT, address TEXT, price REAL, rent_frequency TEXT, currency TEXT,
          bedrooms REAL, bathrooms REAL, area_sqm REAL, furnishing TEXT, description TEXT,
          amenities TEXT, lat REAL, lon REAL, images TEXT, rega_licensed INTEGER, published_at TEXT);
        CREATE TABLE projects(
          slug TEXT PRIMARY KEY, url TEXT, name TEXT, section TEXT, country TEXT, brands TEXT,
          summary TEXT, specs TEXT, image TEXT, images TEXT, text TEXT);
        CREATE TABLE chunks(
          id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT, title TEXT, section TEXT, text TEXT);
        """
    )

    # ---- Wasalt listings
    CITY = {"aldammam": "Dammam", "makkah al mukarramah": "Makkah", "khobar": "Al Khobar",
            "al khobar": "Al Khobar", "khamis mushait": "Khamis Mushait", "al madinah": "Madinah"}
    seen = set()
    rows = []
    for r in read_jsonl(RAW / "wasalt_listings.jsonl"):
        if r["id"] in seen or not r.get("price"):
            continue
        seen.add(r["id"])
        r["city"] = CITY.get((r.get("city") or "").lower(), r.get("city"))
        rf = r.get("rent_frequency")
        if isinstance(rf, dict):  # Wasalt gives {monthly:{amount}, yearly:{amount}}
            yearly = (rf.get("yearly") or {}).get("amount")
            if yearly:
                r["price"] = float(yearly)
            r["rent_frequency"] = "yearly"
        rows.append((
            r["id"], r["url"], r["title"], r["purpose"], r["category"], r["type"], r["city"],
            r["district"], r["address"], r["price"], r.get("rent_frequency"), r.get("currency"),
            r.get("bedrooms"), r.get("bathrooms"), r.get("area_sqm"), r.get("furnishing"),
            r.get("description"), json.dumps(r.get("amenities") or []), r.get("lat"), r.get("lon"),
            json.dumps(r.get("images") or []), int(bool(r.get("rega_licensed"))), r.get("published_at"),
        ))
    con.executemany(f"INSERT INTO listings VALUES ({','.join('?' * 23)})", rows)
    print(f"listings: {len(rows)}")

    # ---- DarGlobal pages
    n_proj = n_chunks = 0
    seen_urls = set()
    seen_names = set()
    for p in read_jsonl(RAW / "darglobal_pages.jsonl"):
        url = p["url"].rstrip("/")
        if url.lower() in seen_urls or "Application error" in (p.get("title") or "") + (p.get("h1") or ""):
            continue
        if any(x in url.lower() for x in ("/landing-page", "aston-martin-media", "-catalogue", "insignia-card")):
            continue
        seen_urls.add(url.lower())
        imgs = [i for i in (p.get("images") or []) if "cdn.darglobal.co.uk" in i]
        og = p.get("og_image") if "cdn.darglobal" in (p.get("og_image") or "") else None
        text = clean_text(p.get("text") or "")
        title = (p.get("title") or p.get("h1") or url).split("|")[0].strip()
        section = p.get("section") or "page"
        if section in {"project", "one-of-one"} and url.rstrip("/").split("/")[-1] != "one-of-one":
            slug = url.replace("https://darglobal.co.uk/", "").lower()
            specs = parse_specs(text)
            pname = (p.get("h1") or title).strip()
            if pname.lower() in seen_names:
                continue
            seen_names.add(pname.lower())
            con.execute(
                "INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    slug, url, nice_name(pname), section,
                    guess_country(specs.get("location", ""), title, p.get("description") or "", text[:1500]),
                    json.dumps(guess_brands(title, p.get("description") or "", text[:600])),
                    good_desc(p.get("description")) or text[:400], json.dumps(specs),
                    og or (imgs or [None])[0], json.dumps(imgs), text[:12000],
                ),
            )
            n_proj += 1
        header = f"{title} ({section}) — {url}\n"
        for c in chunk(text):
            con.execute("INSERT INTO chunks(url,title,section,text) VALUES (?,?,?,?)", (url, title, section, header + c))
            n_chunks += 1
    con.commit()
    print(f"projects: {n_proj}, chunks: {n_chunks}")
    con.close()


if __name__ == "__main__":
    main()
