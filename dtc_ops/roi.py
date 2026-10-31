"""Simple automation ROI model used in business cases: manual minutes per run x runs per month."""

DEFAULT_TASKS = [
    {"task": "Answer 'where is my order' tickets", "runs_per_month": 900, "manual_min": 4, "automated_share": 0.7},
    {"task": "Weekly KPI scorecard", "runs_per_month": 4, "manual_min": 120, "automated_share": 0.9},
    {"task": "Build replenishment/win-back lists", "runs_per_month": 8, "manual_min": 45, "automated_share": 0.9},
    {"task": "Launch health check (first 48h)", "runs_per_month": 2, "manual_min": 90, "automated_share": 0.6},
]


def estimate(tasks=None, hourly_cost: float = 30.0) -> dict:
    tasks = tasks or DEFAULT_TASKS
    rows, total = [], 0.0
    for t in tasks:
        hours = t["runs_per_month"] * t["manual_min"] * t["automated_share"] / 60
        total += hours
        rows.append({**t, "hours_saved_per_month": round(hours, 1)})
    return {"rows": rows, "hours_saved_per_month": round(total, 1),
            "value_per_month_usd": round(total * hourly_cost), "assumed_hourly_cost": hourly_cost,
            "note": "Inputs are assumptions to replace with the customer's real volumes during discovery."}
