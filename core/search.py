"""
Universal search. Each module registers a callable that returns SearchResult
items for a given query. We rank by simple fuzzy match score so the top
result is reliably the one the user wants.
"""
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class SearchResult:
    title: str
    subtitle: str
    category: str       # e.g. "Link", "Document", "Template", "ToDo"
    action: Callable[[], None]   # what happens on Enter / click
    icon: str = ""      # short emoji/glyph hint
    score: float = 0.0


def fuzzy_score(query: str, target: str) -> float:
    """Return a [0,1] match score. Cheap, deterministic, no deps."""
    if not query:
        return 0.0
    q = query.lower().strip()
    t = target.lower()
    if not t:
        return 0.0
    if q == t:
        return 1.0
    if t.startswith(q):
        return 0.95
    if q in t:
        # Closer to the start = higher score
        idx = t.index(q)
        return 0.85 - (idx / max(len(t), 1)) * 0.2
    # Subsequence match: every char of q appears in order somewhere in t
    i = 0
    last = -1
    spread = 0
    for ch in q:
        found = t.find(ch, i)
        if found < 0:
            return 0.0
        if last >= 0:
            spread += found - last - 1
        last = found
        i = found + 1
    # Lower spread = letters were closer together = better match
    return max(0.0, 0.6 - (spread / max(len(t), 1)) * 0.4)


class SearchRegistry:
    def __init__(self):
        self._providers: list[tuple[str, Callable[[str], list[SearchResult]]]] = []

    def register(self, name: str, provider: Callable[[str], list[SearchResult]]):
        # If a provider with this name already exists, replace it (handles module reloads)
        self._providers = [(n, p) for n, p in self._providers if n != name]
        self._providers.append((name, provider))

    def unregister(self, name: str):
        self._providers = [(n, p) for n, p in self._providers if n != name]

    def search(self, query: str, limit: int = 25) -> list[SearchResult]:
        if not query.strip():
            return []
        results: list[SearchResult] = []
        for _, provider in self._providers:
            try:
                results.extend(provider(query))
            except Exception:
                # A misbehaving provider should never crash the whole search
                continue
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
