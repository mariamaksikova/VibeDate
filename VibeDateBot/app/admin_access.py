from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(override=True)


def load_admin_tg_ids() -> frozenset[int]:
    raw = os.getenv("ADMIN_TG_IDS", "").strip()
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for part in raw.split(","):
        piece = part.strip()
        if piece.isdigit():
            ids.add(int(piece))
    return frozenset(ids)


def is_admin(tg_id: int | None, admin_ids: frozenset[int]) -> bool:
    if tg_id is None or not admin_ids:
        return False
    return tg_id in admin_ids
