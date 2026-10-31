"""Weekly/daily e-commerce scorecard: revenue, orders, AOV, CVR, MER, new-customer CPA, repeat rate, margin."""
from collections import defaultdict
from datetime import date, timedelta

from . import data


def _daily():
    rows = defaultdict(lambda: {"revenue": 0.0, "orders": 0, "new": 0, "cogs": 0.0})
    prods = data.products()
    for o in data.orders():
        r = rows[o["date"]]
        r["revenue"] += o["total"]
        r["orders"] += 1
        r["new"] += 1 if o["new_customer"] else 0
        r["cogs"] += sum(prods[i["sku"]]["cogs"] * i["qty"] for i in o["items"])
    for s in data.load("sessions"):
        rows[s["date"]]["sessions"] = s["sessions"]
    for a in data.load("ad_spend"):
        rows[a["date"]]["spend"] = a["meta"] + a["google"]
    return dict(rows)


def window(end: str, days: int) -> dict:
    d = _daily()
    e = date.fromisoformat(end)
    keys = [(e - timedelta(days=i)).isoformat() for i in range(days)]
    agg = {"revenue": 0.0, "orders": 0, "new": 0, "cogs": 0.0, "sessions": 0, "spend": 0.0}
    for k in keys:
        for f in agg:
            agg[f] += d.get(k, {}).get(f, 0)
    o = agg["orders"] or 1
    return {
        "start": keys[-1], "end": keys[0], "days": days,
        "revenue": round(agg["revenue"], 2), "orders": agg["orders"],
        "aov": round(agg["revenue"] / o, 2),
        "cvr": round(agg["orders"] / (agg["sessions"] or 1), 4),
        "sessions": agg["sessions"], "ad_spend": round(agg["spend"], 2),
        "mer": round(agg["revenue"] / (agg["spend"] or 1), 2),
        "new_customer_cpa": round(agg["spend"] / (agg["new"] or 1), 2),
        "returning_share": round(1 - agg["new"] / o, 3),
        "gross_margin": round(1 - agg["cogs"] / (agg["revenue"] or 1), 3),
    }


def scorecard(end: str | None = None) -> dict:
    end = end or max(o["date"] for o in data.orders())
    this_week = window(end, 7)
    prev_end = (date.fromisoformat(end) - timedelta(days=7)).isoformat()
    last_week = window(prev_end, 7)
    deltas = {}
    for k in ("revenue", "orders", "aov", "cvr", "mer", "new_customer_cpa", "gross_margin"):
        base = last_week[k] or 1
        deltas[k] = round((this_week[k] - last_week[k]) / base, 3)
    flags = []
    if deltas["cvr"] < -0.10:
        flags.append(f"CVR down {abs(deltas['cvr']):.0%} week over week")
    if deltas["mer"] < -0.10:
        flags.append(f"MER down {abs(deltas['mer']):.0%} week over week")
    if deltas["new_customer_cpa"] > 0.15:
        flags.append(f"New-customer CPA up {deltas['new_customer_cpa']:.0%}")
    return {"this_week": this_week, "last_week": last_week, "wow_change": deltas, "flags": flags}
