"""Replenishment / win-back segments from order history, exported as Klaviyo-style event payloads.
Nothing is sent: payloads go to the approval queue for a human to push.
"""
from datetime import date, timedelta

from . import data


def segments(as_of: str | None = None, window_days: int = 7) -> dict:
    as_of_d = date.fromisoformat(as_of or max(o["date"] for o in data.orders()))
    prods, custs = data.products(), data.customers()
    last = {}
    for o in data.orders():
        for i in o["items"]:
            key = (o["customer_id"], i["sku"])
            if key not in last or o["date"] > last[key]["date"]:
                last[key] = {"date": o["date"], "qty": i["qty"], "order_id": o["id"]}
    due, winback = [], []
    for (cid, sku), info in last.items():
        c = custs[cid]
        if c["subscription"]:
            continue  # subscribers reorder automatically
        runout = date.fromisoformat(info["date"]) + timedelta(days=prods[sku]["days_supply"] * info["qty"])
        days_left = (runout - as_of_d).days
        rec = {"customer_id": cid, "email": c["email"], "language": c["language"], "sku": sku,
               "product": prods[sku]["name"], "last_order": info["order_id"], "runout_date": runout.isoformat(),
               "days_left": days_left, "email_consent": c["email_consent"], "sms_consent": c["sms_consent"]}
        if 0 <= days_left <= window_days:
            due.append(rec)
        elif -60 <= days_left < -21:
            winback.append(rec)
    return {"as_of": as_of_d.isoformat(), "replenish_due": sorted(due, key=lambda r: r["days_left"]),
            "winback": winback, "counts": {"replenish_due": len(due), "winback": len(winback)}}


def klaviyo_event(rec: dict, metric: str = "Replenishment Due") -> dict:
    """Shape matches Klaviyo's Create Event API body (JSON:API). Not sent anywhere."""
    return {"data": {"type": "event", "attributes": {
        "properties": {"sku": rec["sku"], "product": rec["product"], "runout_date": rec["runout_date"],
                       "language": rec["language"], "last_order": rec["last_order"]},
        "metric": {"data": {"type": "metric", "attributes": {"name": metric}}},
        "profile": {"data": {"type": "profile", "attributes": {"email": rec["email"]}}}}}}
