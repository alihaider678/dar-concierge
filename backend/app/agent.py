"""Tool-calling agent loop over OpenRouter free models.

Flow per user turn:
  plan -> (tool calls -> observations)* -> streamed final answer
Every step is emitted as an event so the UI can show the agent's trace live.
If a model is rate-limited / unavailable / can't do tools, we fall back to the
next model in the chain transparently.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import AsyncIterator

import httpx

from .tools import run_tool, store, tool_specs

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "inclusionai/ling-3.2-flash:free",
    "google/gemma-4-26b-a4b-it:free",
]
MAX_STEPS = 6


def models() -> list[str]:
    env = os.getenv("OPENROUTER_MODELS")
    return [m.strip() for m in env.split(",") if m.strip()] if env else DEFAULT_MODELS


def system_prompt() -> str:
    s = store().stats()
    return f"""You are **Dar Concierge**, an AI property advisor built (as an unofficial candidate demo) on public data from two sister companies of the Dar Al Arkan group:
- **DarGlobal** (London Stock Exchange ticker: DAR; international luxury developer; branded residences with Trump, Pagani, Lamborghini, Aston Martin, Missoni, Elie Saab, Fendi Casa, W, Marriott and more across {', '.join(s['countries']) or 'UAE, Saudi Arabia, Oman, Qatar, Spain, UK'}). Knowledge base: {s['projects']} project pages, {s['passages']} passages.
- **Wasalt** (Saudi property portal). Dataset: a snapshot of {s['listings']} public listings collected 18 Nov 2026 ({s['for_sale']} for sale, {s['for_rent']} for rent) across {s['cities']} cities incl. {', '.join(s['top_cities'][:6])}.

How you work:
1. ALWAYS ground facts in tools. Use search_darglobal / get_project_details / list_darglobal_projects / compare_projects for DarGlobal; search_listings / market_stats for Saudi listings; calculators for numbers. Call several tools if the question needs it (e.g. find listings, then compute mortgage on one).
2. Never invent prices, sizes, dates, amenities, stock tickers, financial figures or any other fact that a tool did not return. If the data doesn't contain it, say so and point to the source site. Saudi listing prices are in SAR (never €). The Wasalt data is a one-time snapshot from 18 Nov 2026: never describe it as "live", "real-time" or "current"; call it "a snapshot of public listings" and tell users to confirm availability on Wasalt.sa.
3. The UI already renders rich cards for listings/projects returned by tools — do NOT repeat every field. Write a crisp advisory summary: highlight 2-4 best options and WHY they fit, with key numbers.
4. Cite sources inline as markdown links (project URL or listing URL). Wasalt data: mention "Source: Wasalt.sa".
5. Reply in the user's language (Arabic if they write Arabic, otherwise English). Be warm, premium and concise; use short headings/bullets. Prices: format like "SAR 1.2M" or "AED 3,500,000".
6. Finish with one helpful next step (e.g. compare, mortgage estimate, book a viewing). Only call capture_lead after the user gives name + phone/email.
7. Investment questions: give data-backed context, and note it is not financial advice.
8. Stay in scope: real estate, DarGlobal, Wasalt, Saudi/GCC property markets, investment maths, residency/visa questions tied to property. For anything else (coding, general trivia, other companies' products) politely decline in one sentence and suggest a property question you can help with.
Today is {time.strftime('%d %B %Y')}."""


async def _stream_completion(client: httpx.AsyncClient, model: str, messages: list[dict],
                             use_tools: bool) -> AsyncIterator[dict]:
    payload = {"model": model, "messages": messages, "stream": True, "temperature": 0.3, "max_tokens": 1800}
    if use_tools:
        payload["tools"] = tool_specs()
        payload["tool_choice"] = "auto"
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}",
        "HTTP-Referer": os.getenv("APP_URL", "https://dar-concierge.onrender.com"),
        "X-Title": "Dar Concierge",
    }
    async with client.stream("POST", OPENROUTER_URL, json=payload, headers=headers) as r:
        if r.status_code != 200:
            body = (await r.aread()).decode(errors="ignore")[:300]
            raise RuntimeError(f"{r.status_code}: {body}")
        async for line in r.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            if "error" in chunk:
                raise RuntimeError(str(chunk["error"])[:300])
            yield chunk


async def run_agent(history: list[dict]) -> AsyncIterator[dict]:
    if not os.getenv("OPENROUTER_API_KEY"):
        yield {"type": "error", "message": "OPENROUTER_API_KEY is not configured on the server."}
        return
    messages = [{"role": "system", "content": system_prompt()}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-12:]
                 if m.get("role") in ("user", "assistant") and m.get("content")]
    chain = models()
    model_idx = 0
    t0 = time.time()

    async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
        for step in range(MAX_STEPS + 1):
            final_round = step == MAX_STEPS
            while True:
                model = chain[model_idx]
                yield {"type": "status", "step": step, "model": model,
                       "message": "Composing answer" if step else "Planning"}
                content, tool_calls, emitted = "", {}, False
                try:
                    async for chunk in _stream_completion(client, model, messages, use_tools=not final_round):
                        choice = (chunk.get("choices") or [{}])[0]
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            content += delta["content"]
                            emitted = True
                            yield {"type": "token", "text": delta["content"]}
                        for tc in delta.get("tool_calls") or []:
                            slot = tool_calls.setdefault(tc.get("index", 0), {"id": None, "name": "", "args": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["args"] += fn.get("arguments") or ""
                    if not content and not tool_calls:
                        raise RuntimeError("empty response")
                    break
                except Exception as e:  # noqa: BLE001
                    if emitted:
                        yield {"type": "reset"}  # UI clears partial text from the failed model
                    if model_idx + 1 < len(chain):
                        model_idx += 1
                        yield {"type": "fallback", "from": model, "to": chain[model_idx], "reason": str(e)[:160]}
                        await asyncio.sleep(0.4)
                        continue
                    yield {"type": "error", "message": "All free models are busy right now. Please retry in a moment.",
                           "detail": str(e)[:300]}
                    return

            if not tool_calls:
                yield {"type": "done", "model": model, "steps": step, "ms": int((time.time() - t0) * 1000)}
                return

            # execute tools
            calls = [tool_calls[i] for i in sorted(tool_calls)]
            messages.append({"role": "assistant", "content": content or None, "tool_calls": [
                {"id": c["id"] or f"call_{step}_{i}", "type": "function",
                 "function": {"name": c["name"], "arguments": c["args"] or "{}"}} for i, c in enumerate(calls)]})
            if content:
                yield {"type": "reset"}  # pre-tool chatter isn't the final answer
            for i, c in enumerate(calls):
                try:
                    args = json.loads(c["args"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                call_id = c["id"] or f"call_{step}_{i}"
                yield {"type": "tool_start", "id": call_id, "name": c["name"], "args": args}
                ts = time.time()
                res = await asyncio.to_thread(run_tool, c["name"], args)
                summary = _summarize(c["name"], res.data)
                yield {"type": "tool_end", "id": call_id, "name": c["name"], "summary": summary,
                       "ms": int((time.time() - ts) * 1000)}
                if res.cards:
                    yield {"type": "cards", "cards": res.cards}
                messages.append({"role": "tool", "tool_call_id": call_id, "name": c["name"],
                                 "content": json.dumps(res.data, ensure_ascii=False, default=str)[:9000]})


def _summarize(name: str, data) -> str:
    if isinstance(data, dict):
        if "error" in data:
            return f"⚠ {data['error']}"
        if name == "search_listings":
            return f"{data['total_matches']} matches, showing {data['returned']}"
        if name == "market_stats":
            return f"{data['count']} listings · median SAR {data['median_price_sar']:,}"
        if name == "search_darglobal":
            return f"{len(data.get('passages', []))} passages: " + ", ".join(
                sorted({p['title'][:28] for p in data.get('passages', [])})[:3])
        if name == "list_darglobal_projects":
            return f"{data['count']} projects"
        if name == "get_project_details":
            return data.get("name", "")
        if name == "compare_projects":
            return " vs ".join(p["name"] for p in data["projects"])
        if name == "calculate_mortgage":
            return f"{data['currency']} {data['monthly_payment']:,}/month"
        if name == "estimate_rental_yield":
            return f"gross {data['gross_yield_pct']}% · net {data['net_yield_pct']}%"
        if name == "convert_currency":
            return f"{data['amount']:,} {data['from']} = {data['result']:,} {data['to']}"
        if name == "capture_lead":
            return f"ref {data['reference']}"
    return "done"
