"""Agent tools.

Each tool returns a ToolResult with:
  * `data`  – compact JSON the LLM reasons over
  * `cards` – rich UI payloads (property / project / calc cards) streamed to the frontend
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .retrieval import BM25, Doc

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data" / "processed"))
DB_PATH = DATA_DIR / "concierge.db"
LEADS_DB = Path(os.getenv("LEADS_DB", "/tmp/leads.db" if os.name != "nt" else str(DATA_DIR / "leads.db")))

# Indicative FX against USD. GCC currencies are hard-pegged; GBP/EUR are approximate.
USD_RATES = {"USD": 1.0, "SAR": 3.75, "AED": 3.6725, "QAR": 3.64, "OMR": 0.3845,
             "BHD": 0.376, "KWD": 0.307, "GBP": 0.78, "EUR": 0.90}


@dataclass
class ToolResult:
    data: Any
    cards: list[dict] = field(default_factory=list)


class Store:
    """Read-only access to the scraped knowledge base."""

    def __init__(self) -> None:
        self.con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        docs = [Doc(r["id"], r["url"], r["title"], r["section"], r["text"])
                for r in self.con.execute("SELECT * FROM chunks")]
        self.bm25 = BM25(docs)
        self.projects = [dict(r) for r in self.con.execute("SELECT * FROM projects")]
        for p in self.projects:
            p["brands"] = json.loads(p["brands"] or "[]")
            p["specs"] = json.loads(p["specs"] or "{}")
            p["images"] = json.loads(p["images"] or "[]")
        self.cities = [r[0] for r in self.con.execute(
            "SELECT city FROM listings WHERE city IS NOT NULL GROUP BY city ORDER BY count(*) DESC")]
        self.types = [r[0] for r in self.con.execute(
            "SELECT type FROM listings WHERE type IS NOT NULL GROUP BY type ORDER BY count(*) DESC")]

    def stats(self) -> dict:
        c = self.con
        return {
            "listings": c.execute("SELECT count(*) FROM listings").fetchone()[0],
            "for_sale": c.execute("SELECT count(*) FROM listings WHERE purpose='sale'").fetchone()[0],
            "for_rent": c.execute("SELECT count(*) FROM listings WHERE purpose='rent'").fetchone()[0],
            "cities": len(self.cities),
            "projects": len(self.projects),
            "passages": len(self.bm25.docs),
            "top_cities": self.cities[:8],
            "countries": sorted({p["country"] for p in self.projects if p["country"]}),
        }


STORE: Store | None = None


def store() -> Store:
    global STORE
    if STORE is None:
        STORE = Store()
    return STORE


# ---------------------------------------------------------------- helpers
def _listing_card(r: sqlite3.Row) -> dict:
    imgs = json.loads(r["images"] or "[]")
    return {
        "kind": "listing", "id": r["id"], "title": r["title"], "url": r["url"],
        "purpose": r["purpose"], "type": r["type"], "city": r["city"], "district": r["district"],
        "price": r["price"], "currency": r["currency"], "rent_frequency": r["rent_frequency"],
        "bedrooms": r["bedrooms"], "bathrooms": r["bathrooms"], "area_sqm": r["area_sqm"],
        "image": imgs[0] if imgs else None, "lat": r["lat"], "lon": r["lon"],
        "rega_licensed": bool(r["rega_licensed"]), "source": "Wasalt.sa",
    }


def _project_card(p: dict) -> dict:
    return {
        "kind": "project", "slug": p["slug"], "name": p["name"], "url": p["url"],
        "country": p["country"], "brands": p["brands"], "summary": (p["summary"] or "")[:260],
        "specs": p["specs"], "image": p["image"], "source": "DarGlobal",
    }


def _like(v: str) -> str:
    return f"%{v.strip().lower()}%"


def _city(c: str) -> str:
    c = c.lower().strip()
    c = {"mecca": "makkah", "medina": "madinah", "khobar": "khobar", "al-khobar": "khobar",
         "al khobar": "khobar", "khamis mushayt": "khamis", "dammam": "dammam"}.get(c, c)
    return c.removeprefix("al-").removeprefix("al ")


def _find_project(name: str) -> dict | None:
    s = store()
    q = set(re.findall(r"[a-z0-9]+", name.lower())) - {"the", "by", "project", "dar", "global", "darglobal"}
    best, best_score = None, 0.0
    for p in s.projects:
        hay = set(re.findall(r"[a-z0-9]+", f"{p['name']} {p['slug']}".lower()))
        score = len(q & hay) / (len(q) or 1)
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= 0.5 else None


# ---------------------------------------------------------------- tools
def search_listings(purpose: str | None = None, city: str | None = None, district: str | None = None,
                    property_type: str | None = None, min_price: float | None = None,
                    max_price: float | None = None, min_bedrooms: int | None = None,
                    max_bedrooms: int | None = None, min_area_sqm: float | None = None,
                    keywords: str | None = None, sort: str = "relevance", limit: int = 6) -> ToolResult:
    where, args = [], []
    if purpose:
        where.append("purpose = ?"); args.append(purpose.lower())
    if city:
        where.append("lower(city) LIKE ?"); args.append(_like(_city(city)))
    if district:
        where.append("(lower(district) LIKE ? OR lower(address) LIKE ?)"); args += [_like(district)] * 2
    if property_type:
        pt = property_type.lower().rstrip("s")
        where.append("(lower(type) LIKE ? OR lower(title) LIKE ?)"); args += [_like(pt)] * 2
    if min_price is not None:
        where.append("price >= ?"); args.append(min_price)
    if max_price is not None:
        where.append("price <= ?"); args.append(max_price)
    if min_bedrooms is not None:
        where.append("bedrooms >= ?"); args.append(min_bedrooms)
    if max_bedrooms is not None:
        where.append("bedrooms <= ?"); args.append(max_bedrooms)
    if min_area_sqm is not None:
        where.append("area_sqm >= ?"); args.append(min_area_sqm)
    if keywords:
        for kw in keywords.split()[:4]:
            where.append("(lower(description) LIKE ? OR lower(amenities) LIKE ? OR lower(title) LIKE ?)")
            args += [_like(kw)] * 3
    order = {
        "price_asc": "price ASC", "price_desc": "price DESC", "newest": "published_at DESC",
        "largest": "area_sqm DESC", "price_per_sqm": "price / NULLIF(area_sqm,0) ASC",
    }.get(sort, "(images != '[]') DESC, rega_licensed DESC, published_at DESC")
    sql = "SELECT * FROM listings" + (" WHERE " + " AND ".join(where) if where else "")
    con = store().con
    total = con.execute(sql.replace("SELECT *", "SELECT count(*)", 1), args).fetchone()[0]
    rows = con.execute(f"{sql} ORDER BY {order} LIMIT ?", [*args, max(1, min(limit, 10))]).fetchall()
    cards = [_listing_card(r) for r in rows]
    slim = [{k: c[k] for k in ("id", "title", "purpose", "type", "city", "district", "price",
                               "currency", "rent_frequency", "bedrooms", "area_sqm", "url")} for c in cards]
    return ToolResult({"total_matches": total, "returned": len(slim), "listings": slim,
                       "note": "Sample of public Wasalt listings; prices change — confirm on Wasalt.sa."}, cards)


def market_stats(city: str | None = None, purpose: str = "sale", property_type: str | None = None) -> ToolResult:
    where, args = ["purpose = ?", "price > 0"], [purpose]
    if city:
        where.append("lower(city) LIKE ?"); args.append(_like(_city(city)))
    if property_type:
        where.append("lower(type) LIKE ?"); args.append(_like(property_type.rstrip("s")))
    rows = store().con.execute(
        f"SELECT city, district, type, price, area_sqm FROM listings WHERE {' AND '.join(where)}", args).fetchall()
    if not rows:
        return ToolResult({"error": "No listings match those filters in the dataset."})
    prices = [r["price"] for r in rows]
    ppsqm = [r["price"] / r["area_sqm"] for r in rows if r["area_sqm"] and r["area_sqm"] > 20]
    by_district: dict[str, list[float]] = {}
    for r in rows:
        if r["district"]:
            by_district.setdefault(r["district"], []).append(r["price"])
    top = sorted(((d, len(v), statistics.median(v)) for d, v in by_district.items() if len(v) >= 2),
                 key=lambda x: -x[1])[:8]
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["type"] or "Other"] = by_type.get(r["type"] or "Other", 0) + 1
    data = {
        "scope": {"city": city or "All Saudi cities", "purpose": purpose, "type": property_type or "All"},
        "count": len(rows),
        "median_price_sar": round(statistics.median(prices)),
        "p25_price_sar": round(statistics.quantiles(prices, n=4)[0]) if len(prices) > 3 else None,
        "p75_price_sar": round(statistics.quantiles(prices, n=4)[2]) if len(prices) > 3 else None,
        "median_price_per_sqm_sar": round(statistics.median(ppsqm)) if ppsqm else None,
        "top_districts": [{"district": d, "listings": n, "median_price_sar": round(m)} for d, n, m in top],
        "type_mix": dict(sorted(by_type.items(), key=lambda x: -x[1])[:6]),
    }
    return ToolResult(data, [{"kind": "stats", **data}])


def search_darglobal(query: str, top_k: int = 5) -> ToolResult:
    hits = store().bm25.search(query, k=max(1, min(top_k, 8)))
    passages = [{"title": d.title, "section": d.section, "url": d.url, "score": s, "text": d.text[:1100]}
                for d, s in hits]
    cards, seen = [], set()
    for d, _ in hits:
        p = next((p for p in store().projects if p["url"] == d.url), None)
        if p and p["slug"] not in seen:
            seen.add(p["slug"]); cards.append(_project_card(p))
    return ToolResult({"passages": passages} if passages else {"passages": [], "note": "No match in DarGlobal content."},
                      cards[:3])


def list_darglobal_projects(country: str | None = None, brand: str | None = None) -> ToolResult:
    ps = store().projects
    if country:
        ps = [p for p in ps if p["country"] and country.lower() in p["country"].lower()
              or country.lower() in (p["specs"].get("location", "") + p["name"]).lower()]
    if brand:
        ps = [p for p in ps if any(brand.lower() in b.lower() for b in p["brands"])
              or brand.lower() in (p["name"] + p["slug"]).lower()]
    ps = [p for p in ps if p["section"] == "project" or p["section"] == "one-of-one"]
    slim = [{"name": p["name"], "country": p["country"], "brands": p["brands"],
             "location": p["specs"].get("location"), "type": p["specs"].get("property_type"),
             "url": p["url"]} for p in ps]
    return ToolResult({"count": len(slim), "projects": slim[:25]}, [_project_card(p) for p in ps[:8]])


def get_project_details(name: str) -> ToolResult:
    p = _find_project(name)
    if not p:
        names = [x["name"] for x in store().projects][:40]
        return ToolResult({"error": f"No project matched '{name}'.", "known_projects": names})
    return ToolResult({"name": p["name"], "url": p["url"], "country": p["country"], "brands": p["brands"],
                       "specs": p["specs"], "content": p["text"][:5000]}, [_project_card(p)])


def compare_projects(names: list[str]) -> ToolResult:
    found, missing = [], []
    for n in names[:4]:
        p = _find_project(n)
        (found.append(p) if p else missing.append(n))
    data = {"projects": [{"name": p["name"], "country": p["country"], "brands": p["brands"],
                          "specs": p["specs"], "summary": (p["summary"] or "")[:500],
                          "highlights": p["text"][:1800], "url": p["url"]} for p in found],
            "not_found": missing}
    cards = [{"kind": "compare", "items": [_project_card(p) for p in found]}] if len(found) > 1 else \
            [_project_card(p) for p in found]
    return ToolResult(data, cards)


def calculate_mortgage(property_price: float, down_payment_pct: float = 20, annual_rate_pct: float = 5.5,
                       years: int = 25, currency: str = "SAR") -> ToolResult:
    principal = property_price * (1 - down_payment_pct / 100)
    r, n = annual_rate_pct / 100 / 12, years * 12
    monthly = principal / n if r == 0 else principal * r * (1 + r) ** n / ((1 + r) ** n - 1)
    total = monthly * n
    data = {"property_price": round(property_price), "currency": currency.upper(),
            "down_payment": round(property_price - principal), "loan_amount": round(principal),
            "annual_rate_pct": annual_rate_pct, "years": years, "monthly_payment": round(monthly),
            "total_interest": round(total - principal), "total_paid": round(total + property_price - principal),
            "disclaimer": "Indicative only; actual terms depend on the lender."}
    return ToolResult(data, [{"kind": "mortgage", **data}])


def estimate_rental_yield(property_price: float, monthly_rent: float | None = None,
                          annual_rent: float | None = None, service_charges_annual: float = 0,
                          currency: str = "SAR") -> ToolResult:
    rent = annual_rent if annual_rent else (monthly_rent or 0) * 12
    if not rent or not property_price:
        return ToolResult({"error": "Provide property_price and a monthly_rent or annual_rent."})
    gross = rent / property_price * 100
    net = (rent - service_charges_annual) / property_price * 100
    data = {"property_price": property_price, "annual_rent": rent, "currency": currency.upper(),
            "gross_yield_pct": round(gross, 2), "net_yield_pct": round(net, 2),
            "payback_years": round(property_price / max(rent - service_charges_annual, 1), 1)}
    return ToolResult(data, [{"kind": "yield", **data}])


def convert_currency(amount: float, from_currency: str, to_currency: str) -> ToolResult:
    f, t = from_currency.upper(), to_currency.upper()
    if f not in USD_RATES or t not in USD_RATES:
        return ToolResult({"error": f"Supported: {', '.join(USD_RATES)}"})
    out = amount / USD_RATES[f] * USD_RATES[t]
    return ToolResult({"amount": amount, "from": f, "to": t, "result": round(out, 2),
                       "note": "Indicative rate; GCC currencies are USD-pegged."})


def capture_lead(name: str, contact: str, interest: str, preferred_time: str | None = None,
                 budget: str | None = None) -> ToolResult:
    LEADS_DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(LEADS_DB)
    con.execute("CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY, ts INTEGER, name TEXT, "
                "contact TEXT, interest TEXT, preferred_time TEXT, budget TEXT)")
    cur = con.execute("INSERT INTO leads(ts,name,contact,interest,preferred_time,budget) VALUES (?,?,?,?,?,?)",
                      (int(time.time()), name, contact, interest, preferred_time, budget))
    con.commit(); con.close()
    ref = f"DC-{cur.lastrowid:05d}"
    data = {"status": "saved", "reference": ref, "name": name, "interest": interest,
            "preferred_time": preferred_time,
            "note": "Demo lead store — in production this would sync to the CRM and notify an advisor."}
    return ToolResult(data, [{"kind": "lead", **data}])


# ---------------------------------------------------------------- registry
def _fn(name: str, desc: str, props: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required or []}}}


def tool_specs() -> list[dict]:
    s = store()
    return [
        _fn("search_listings",
            "Search live-market property listings in Saudi Arabia scraped from Wasalt (sale & rent). "
            f"Known cities include: {', '.join(s.cities[:15])}. Types include: {', '.join(s.types[:12])}. "
            "Prices are in SAR; rent prices are YEARLY (divide by 12 for monthly).",
            {"purpose": {"type": "string", "enum": ["sale", "rent"]},
             "city": {"type": "string"}, "district": {"type": "string"},
             "property_type": {"type": "string", "description": "e.g. Apartment, Villa, Land, Floor, Townhouse"},
             "min_price": {"type": "number"}, "max_price": {"type": "number"},
             "min_bedrooms": {"type": "integer"}, "max_bedrooms": {"type": "integer"},
             "min_area_sqm": {"type": "number"},
             "keywords": {"type": "string", "description": "free-text features e.g. 'pool furnished'"},
             "sort": {"type": "string", "enum": ["relevance", "price_asc", "price_desc", "newest", "largest", "price_per_sqm"]},
             "limit": {"type": "integer", "description": "1-10, default 6"}}),
        _fn("market_stats",
            "Aggregate Saudi market statistics from the Wasalt dataset: median price, price per sqm, "
            "top districts and type mix for a city/purpose/type. Use for 'average price', 'cheapest area', trends.",
            {"city": {"type": "string"}, "purpose": {"type": "string", "enum": ["sale", "rent"]},
             "property_type": {"type": "string"}}),
        _fn("search_darglobal",
            "Semantic/keyword search over DarGlobal's public website: projects, branded partners "
            "(Trump, Pagani, Lamborghini, Aston Martin, Missoni, Elie Saab, Fendi Casa...), amenities, "
            "payment plans, golden visa & investment insights, press releases, FAQs, company info.",
            {"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query"]),
        _fn("list_darglobal_projects", "List DarGlobal projects, optionally filtered by country or brand partner.",
            {"country": {"type": "string", "description": "UAE, Saudi Arabia, Oman, Qatar, Spain, UK..."},
             "brand": {"type": "string"}}),
        _fn("get_project_details", "Full details for one DarGlobal project by (partial) name.",
            {"name": {"type": "string"}}, ["name"]),
        _fn("compare_projects", "Side-by-side comparison of 2-4 DarGlobal projects.",
            {"names": {"type": "array", "items": {"type": "string"}}}, ["names"]),
        _fn("calculate_mortgage", "Monthly mortgage payment, interest and totals for a property price.",
            {"property_price": {"type": "number"}, "down_payment_pct": {"type": "number"},
             "annual_rate_pct": {"type": "number"}, "years": {"type": "integer"},
             "currency": {"type": "string"}}, ["property_price"]),
        _fn("estimate_rental_yield", "Gross/net rental yield and payback period.",
            {"property_price": {"type": "number"}, "monthly_rent": {"type": "number"},
             "annual_rent": {"type": "number"}, "service_charges_annual": {"type": "number"},
             "currency": {"type": "string"}}, ["property_price"]),
        _fn("convert_currency", "Convert between SAR, AED, QAR, OMR, BHD, KWD, USD, GBP, EUR.",
            {"amount": {"type": "number"}, "from_currency": {"type": "string"}, "to_currency": {"type": "string"}},
            ["amount", "from_currency", "to_currency"]),
        _fn("capture_lead",
            "Register the user's interest / book a viewing or advisor call. Only call AFTER the user "
            "has explicitly provided their name and a phone or email.",
            {"name": {"type": "string"}, "contact": {"type": "string"}, "interest": {"type": "string"},
             "preferred_time": {"type": "string"}, "budget": {"type": "string"}},
            ["name", "contact", "interest"]),
    ]


REGISTRY: dict[str, Callable[..., ToolResult]] = {
    f.__name__: f for f in (search_listings, market_stats, search_darglobal, list_darglobal_projects,
                            get_project_details, compare_projects, calculate_mortgage,
                            estimate_rental_yield, convert_currency, capture_lead)
}


def run_tool(name: str, args: dict) -> ToolResult:
    fn = REGISTRY.get(name)
    if not fn:
        return ToolResult({"error": f"Unknown tool {name}"})
    try:
        clean = {k: v for k, v in (args or {}).items() if v not in (None, "")}
        return fn(**clean)
    except TypeError as e:
        return ToolResult({"error": f"Bad arguments for {name}: {e}"})
    except Exception as e:  # noqa: BLE001
        return ToolResult({"error": f"{name} failed: {e}"})
