"""SaaS plans. Every workspace has a plan; endpoints check features/limits from here.

Internal team deployment uses "team" (everything on). When the product opens to the
public, new sign-ups get GPI_DEFAULT_PLAN and billing flips the plan field.
"""

PLANS: dict[str, dict] = {
    "free": {"label": "Free", "max_rows": 25, "history_days": 30, "keywords": False, "export": False,
             "saved_views": 2, "seats": 1},
    "pro": {"label": "Pro", "max_rows": None, "history_days": None, "keywords": True, "export": True,
            "saved_views": 50, "seats": 3},
    "team": {"label": "Team", "max_rows": None, "history_days": None, "keywords": True, "export": True,
             "saved_views": 500, "seats": 50},
}


def plan(name: str | None) -> dict:
    return PLANS.get(name or "team", PLANS["team"])
