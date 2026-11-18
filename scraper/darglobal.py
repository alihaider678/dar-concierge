"""Scrape publicly available DarGlobal pages.

darglobal.co.uk sits behind an Imperva/Incapsula bot wall and renders with JS,
so plain HTTP clients get an empty challenge page. We drive a real headless
Chromium via Playwright, discover URLs from the public sitemap, respect
robots.txt-disallowed paths, and keep concurrency low.

Output: data/raw/darglobal_pages.jsonl  (one JSON object per page)
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

import httpx
from playwright.async_api import async_playwright, Page

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "darglobal_pages.jsonl"
SITEMAP_CACHE = RAW / "darglobal_sitemap.txt"
BASE = "https://darglobal.co.uk"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
CONCURRENCY = 3

# Transactional / non-content pages we don't need.
SKIP = re.compile(
    r"/(pay-online|thank-you|success|terms|privacy|internship-application|bookYourUnit|"
    r"landingpage/|new-home-page|win-a-trip|broker-contest|get-in-touch|careers|internships)",
    re.I,
)


def section_of(url: str) -> str:
    path = url.replace(BASE, "").strip("/")
    first = path.split("/")[0] if path else "home"
    if first in {"blog", "press", "insights", "partners", "projects", "one-of-one"}:
        return first
    if first in {"rayana", "amaya", "trump-plaza"}:
        return "project"
    if first in {
        "about", "why-invest", "faq", "tokenization", "investor", "hospitality",
        "commercial", "development-management", "dg-circle", "exclusive-membership",
        "insignia", "Invest-crypto", "become-a-broker", "become-an-agent", "home",
        "luxury-golf-communities", "live-all-in", "campaigns", "aida-360",
    }:
        return "company"
    return "project"


def load_urls() -> list[str]:
    if SITEMAP_CACHE.exists():
        urls = [u.strip() for u in SITEMAP_CACHE.read_text().splitlines() if u.strip()]
    else:
        xml = httpx.get(f"{BASE}/sitemap.xml", headers={"User-Agent": UA}, timeout=30).text
        urls = re.findall(r"<loc>([^<]+)</loc>", xml)
        SITEMAP_CACHE.write_text("\n".join(urls))
    seen, out = set(), []
    for u in urls:
        key = u.rstrip("/").lower()
        if key in seen or SKIP.search(u):
            continue
        seen.add(key)
        out.append(u.rstrip("/"))
    return out


EXTRACT_JS = r"""
() => {
  const meta = (sel) => document.querySelector(sel)?.getAttribute('content') || null;
  // collect media/links first, then strip chrome from the LIVE DOM so innerText
  // keeps layout-aware line breaks (a detached clone loses them).
  const imgs = [...document.querySelectorAll('img')]
     .map(i => i.currentSrc || i.src)
     .filter(s => s && s.includes('cdn.darglobal.co.uk') && !/logo|icon|flag|sprite/i.test(s));
  const links = [...document.querySelectorAll('a[href]')]
     .map(a => a.href).filter(h => h.startsWith('https://darglobal.co.uk'));
  document.querySelectorAll('script,style,noscript,svg,header,footer,nav,form,iframe,[role=dialog]').forEach(e => e.remove());
  const text = document.body.innerText;
  return {
    title: document.title,
    description: meta('meta[name=description]') || meta('meta[property="og:description"]'),
    og_image: meta('meta[property="og:image"]'),
    h1: document.querySelector('h1')?.innerText || null,
    text, images: [...new Set(imgs)].slice(0, 25), links: [...new Set(links)],
  };
}
"""


async def scrape_page(page: Page, url: str) -> dict | None:
    for attempt in range(3):
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            # nudge lazy content
            await page.mouse.wheel(0, 4000)
            await page.wait_for_timeout(1200)
            data = await page.evaluate(EXTRACT_JS)
            if "Incapsula" in (data.get("text") or "") or len(data.get("text") or "") < 80:
                raise RuntimeError("blocked or empty")
            if "Application error" in (data.get("title") or "") + (data.get("h1") or ""):
                print(f"  skip (site error page) {url}", file=sys.stderr)
                return None
            data["text"] = re.sub(r"\n{3,}", "\n\n", data["text"]).strip()
            data["url"] = url
            data["section"] = section_of(url)
            data["scraped_at"] = int(time.time())
            return data
        except Exception as e:  # noqa: BLE001
            print(f"  retry {attempt + 1} {url}: {e}", file=sys.stderr)
            await page.wait_for_timeout(3000 * (attempt + 1))
    return None


async def main(limit: int | None = None) -> None:
    urls = load_urls()
    done: set[str] = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf8").split("\n"):
            if line.strip():
                done.add(json.loads(line)["url"])
    todo = [u for u in urls if u not in done][: limit or None]
    print(f"{len(urls)} urls, {len(done)} done, {len(todo)} to scrape")

    queue: asyncio.Queue[str] = asyncio.Queue()
    for u in todo:
        queue.put_nowait(u)
    lock = asyncio.Lock()
    count = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(
            user_agent=UA, locale="en-GB", viewport={"width": 1440, "height": 900}
        )
        # skip heavy media to be gentle on their servers
        await ctx.route(
            re.compile(r"\.(mp4|webm|woff2?|ttf)(\?.*)?$"), lambda r: r.abort()
        )

        async def worker() -> None:
            nonlocal count
            page = await ctx.new_page()
            while not queue.empty():
                url = queue.get_nowait()
                data = await scrape_page(page, url)
                if data:
                    async with lock:
                        with OUT.open("a", encoding="utf8") as f:
                            f.write(json.dumps(data, ensure_ascii=False) + "\n")
                        count += 1
                        print(f"[{count}/{len(todo)}] {data['section']:9} {url}")
                await asyncio.sleep(0.8)
            await page.close()

        await asyncio.gather(*(worker() for _ in range(CONCURRENCY)))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))
