"""Lightweight BM25 retrieval over DarGlobal passages (no external deps).

The corpus is small (a few thousand chunks), so an in-memory BM25 index is
fast, deterministic and keeps the Docker image tiny. Title/section boosts
help project pages outrank blog posts that merely mention a project.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

TOKEN = re.compile(r"[a-z0-9؀-ۿ]+")
STOP = set(
    "a an and are as at be by for from has have in is it its of on or that the this to was "
    "were will with you your we our what which who how can do does about me tell show".split()
)
SECTION_BOOST = {"project": 1.35, "one-of-one": 1.3, "partners": 1.15, "company": 1.15,
                 "insights": 1.05, "press": 0.95, "blog": 0.85}


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP and len(t) > 1]


@dataclass
class Doc:
    id: int
    url: str
    title: str
    section: str
    text: str


class BM25:
    def __init__(self, docs: list[Doc], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.tfs: list[Counter] = []
        self.title_toks: list[set[str]] = []
        df: Counter = Counter()
        for d in docs:
            toks = tokenize(d.text)
            tf = Counter(toks)
            self.tfs.append(tf)
            self.title_toks.append(set(tokenize(d.title)))
            df.update(tf.keys())
        self.lens = [sum(tf.values()) for tf in self.tfs]
        self.avgdl = (sum(self.lens) / len(self.lens)) if self.lens else 1
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 6, sections: set[str] | None = None) -> list[tuple[Doc, float]]:
        q = tokenize(query)
        if not q:
            return []
        scores = []
        for i, tf in enumerate(self.tfs):
            d = self.docs[i]
            if sections and d.section not in sections:
                continue
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avgdl))
            if s <= 0:
                continue
            title_hits = len(self.title_toks[i].intersection(q))
            s *= SECTION_BOOST.get(d.section, 1.0) * (1 + 0.25 * title_hits)
            scores.append((s, i))
        scores.sort(reverse=True)
        out, seen_urls = [], Counter()
        for s, i in scores:
            d = self.docs[i]
            if seen_urls[d.url] >= 2:  # diversity: max 2 passages per page
                continue
            seen_urls[d.url] += 1
            out.append((d, round(s, 3)))
            if len(out) >= k:
                break
        return out
