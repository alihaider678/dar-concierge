# Dar Concierge — Agentic AI Property Advisor

**Live demo:** https://dar-concierge.vercel.app

* Frontend: Vercel (static React build, global CDN)
* Backend / full app container: https://dar-concierge.onrender.com (Docker on Render; also serves the UI itself)
* A GitHub Actions job pings the backend every 10 min so it stays warm, and the UI wakes it and shows its status on load

An agentic chatbot grounded in publicly available data from **DarGlobal** (international luxury
branded residences) and **Wasalt** (Saudi property portal). These are two sister companies of the
Dar Al Arkan group, so the assistant connects global luxury investment with the local Saudi market in one conversation.

> Built as a technical assignment for the *Senior AI Engineer – Agentic Systems* role.
> Unofficial demo. It is not affiliated with DarGlobal or Wasalt and is not financial advice.

---

## What it does

| Ask… | The agent… |
|---|---|
| "Which projects are branded with Trump, and where?" | searches the DarGlobal knowledge base, opens the matching project pages, and summarises them in a table with links |
| "Compare DaVinci Tower by Pagani with Trump Tower Jeddah" | runs `compare_projects` and renders a side-by-side card |
| "3-bed apartments for sale in Riyadh under SAR 1.2M" | runs a structured SQL search over Wasalt listings → listing cards + map |
| "Median villa price in Jeddah, most active districts?" | `market_stats` → median, price/sqm, IQR and a district bar chart |
| "Mortgage on a SAR 2M villa, 20% down, 25 years" | `calculate_mortgage` → payment card |
| "Book a call about AIDA Oman" | asks for name and contact, then `capture_lead` → reference number |

The user can see every step. A live **agent trace** shows each tool call, its arguments, the
result summary and its latency, along with which model answered. It also shows when the agent switched to a fallback model.

The UI supports English and **Arabic with RTL layout**, streams responses, and renders results as cards: listing, project, comparison, mortgage, yield, market stats and lead.

## Architecture

```
            ┌──────────────────────── Docker image ────────────────────────┐
 Browser ──▶│ FastAPI                                                       │
  (React)   │  /api/chat  (SSE) ──▶ Agent loop ──▶ OpenRouter (free models) │
            │                         │   ▲        fallback chain           │
            │                         ▼   │ tool results                    │
            │                      Tools (10)                               │
            │        ┌───────────────┼──────────────────┐                   │
            │   SQLite listings   BM25 index over     calculators /         │
            │   (Wasalt)          DarGlobal passages  lead store            │
            │  static React build served from the same container            │
            └───────────────────────────────────────────────────────────────┘
```

* **Agent loop** (`backend/app/agent.py`). This is OpenAI-style tool calling with streaming. It runs up to 6
  plan → act → observe steps, and every step is streamed to the UI as an event. If a free model
  is rate-limited or fails, the loop moves to the next model in the chain
  (`OPENROUTER_MODELS`), and the UI clears any partial output from the failed model.
* **Tools** (`backend/app/tools.py`): `search_listings`, `market_stats`, `search_darglobal`,
  `list_darglobal_projects`, `get_project_details`, `compare_projects`, `calculate_mortgage`,
  `estimate_rental_yield`, `convert_currency`, `capture_lead`. Each tool returns two things: compact
  JSON for the model to read, and rich card payloads for the UI.
* **Retrieval** (`backend/app/retrieval.py`). This is a dependency-free BM25 index with title and
  section boosts, and it caps results at 2 passages per page for diversity. The corpus has a few
  thousand passages, so BM25 is fast and deterministic, and the image stays small.
  Structured questions such as price, beds or city go to SQL instead of the vector or keyword index.
* **Guardrails**: per-IP rate limiting and a system prompt that requires the model to ground answers in tools and cite sources.
  `capture_lead` runs only after the user has given their own contact details. The OpenRouter key has a $1 credit cap.

## Data collection

| Source | How | Volume |
|---|---|---|
| DarGlobal | URLs from the public `sitemap.xml` (paths that `robots.txt` allows). The site is JS-rendered, so pages are rendered with Playwright Chromium. 3 workers with delays between requests. | 458 pages → 44 projects, ~3.9k passages |
| Wasalt | Wasalt publishes [`llms.txt`](https://wasalt.sa/llms.txt), which allows extraction of public listing content at a moderate rate. Public SEO search pages were read in a normal browser session (`scraper/wasalt_browser_collector.js`). | 849 listings across 7 cities (476 sale / 373 rent) |

**Responsible scraping:** no owner names, phone numbers, WhatsApp links or other contact data
are stored. Requests are rate-limited, and Wasalt is sampled instead of crawled in full. Every listing keeps its
source URL and is attributed as "Source: Wasalt.sa", as the Wasalt policy asks. Bot-protection
systems were not circumvented.

`scraper/build_index.py` turns the raw data into a single SQLite file, `data/processed/concierge.db`. It cleans
text, parses project specs, detects country and brand, removes duplicates and chunks text for retrieval. The file is
baked into the Docker image.

## Run locally

```bash
cp .env.example .env            # add OPENROUTER_API_KEY
docker compose up --build       # → http://localhost:8000
```

Dev mode:
```bash
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm i && npm run dev          # → http://localhost:5173 (proxies /api)
```

Re-scrape:
```bash
pip install playwright httpx && python -m playwright install chromium
python scraper/darglobal.py
# Wasalt: paste scraper/wasalt_console_snippet.js into DevTools on wasalt.sa, then:
python scraper/import_wasalt.py
python scraper/build_index.py
```

## Deploy

The app is one container, so it runs on any Docker host. The Docker image runs on **Render** (`render.yaml`, free plan). The only secret is `OPENROUTER_API_KEY`.
The same React build is also deployed to **Vercel** (`frontend/vercel.json`), with `VITE_API_BASE` pointing at the Render API.

## Stack

FastAPI · httpx · SQLite · BM25 · OpenRouter (free models: NVIDIA Nemotron, Google Gemma and others) ·
React 19 · Vite · Tailwind v4 · Framer Motion · Leaflet · Playwright · Docker
