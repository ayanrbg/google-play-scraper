"""Games picked by hand to build on (the "to build" section): loading a curated list into a workspace.

The list is a JSON file: {"picks": [{app_id, tier, niche, why, entry, risks, keys, rivals}, ...]},
in the order it should be shown. Loading replaces the workspace's previous list.
"""

import json
from datetime import datetime

from sqlalchemy import select

from playtrend.models import App, Pick

FIELDS = ("tier", "niche", "why", "entry", "risks", "keys", "rivals")


def load(s, workspace_id: int, items: list[dict]) -> dict:
    known = set(s.scalars(select(App.app_id).where(App.app_id.in_([i["app_id"] for i in items]))))
    missing = [i["app_id"] for i in items if i["app_id"] not in known]
    if missing:
        raise ValueError(f"not in the database: {', '.join(missing)}")
    old = {p.app_id: p for p in s.scalars(select(Pick).where(Pick.workspace_id == workspace_id))}
    now = datetime.utcnow()
    for pos, item in enumerate(items):
        p = old.pop(item["app_id"], None)
        if p is None:
            p = Pick(workspace_id=workspace_id, app_id=item["app_id"], added_at=now)
            s.add(p)
        p.position, p.updated_at = pos, now
        for f in FIELDS:
            setattr(p, f, item.get(f) or ([] if f in ("keys", "rivals") else "top" if f == "tier" else None))
    for p in old.values():
        s.delete(p)
    return {"loaded": len(items), "removed": len(old)}


def load_file(s, workspace_id: int, path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return load(s, workspace_id, json.load(f)["picks"])
