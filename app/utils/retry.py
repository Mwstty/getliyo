"""Otomatik yeniden deneme: 3 -> 5 -> 10 -> 30 sn kademeli bekleme (spec madde 13)."""
from __future__ import annotations

SCHEDULE = [3, 5, 10, 30]


def backoff_seconds(attempt: int, start: int = 3) -> int:
    """attempt 0'dan başlar. start, SCHEDULE içindeki en yakın (>=) başlangıç kademesidir."""
    idx = 0
    for i, v in enumerate(SCHEDULE):
        if v >= start:
            idx = i
            break
    else:
        idx = len(SCHEDULE) - 1
    return SCHEDULE[min(idx + max(attempt, 0), len(SCHEDULE) - 1)]
