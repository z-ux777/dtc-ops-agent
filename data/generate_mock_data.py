"""Generate deterministic mock DTC data (products, customers, orders, sessions, ad spend, tickets).

All data is fake. Nothing here comes from a real store.
Usage: python data/generate_mock_data.py [--days 120] [--seed 7]
"""
import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parent

PRODUCTS = [
    {"sku": "MAG-60", "name": "Magnesium Glycinate 60ct", "price": 34.0, "cogs": 7.5, "days_supply": 30, "launch_date": None},
    {"sku": "OMG-90", "name": "Omega-3 Fish Oil 90ct", "price": 39.0, "cogs": 9.0, "days_supply": 45, "launch_date": None},
    {"sku": "COL-30", "name": "Collagen Peptides 30 servings", "price": 49.0, "cogs": 12.0, "days_supply": 30, "launch_date": None},
    {"sku": "VTD-120", "name": "Vitamin D3+K2 120ct", "price": 29.0, "cogs": 5.0, "days_supply": 120, "launch_date": None},
    {"sku": "SLP-30", "name": "Sleep Gummies 30ct (NEW)", "price": 32.0, "cogs": 8.0, "days_supply": 30, "launch_date": "LAST2"},
]

FIRST = ["Ana", "Luis", "Maria", "John", "Sofia", "David", "Carmen", "Mike", "Lucia", "Sarah", "Diego", "Emma", "Jorge", "Olivia", "Pablo", "Noa"]
LAST = ["Garcia", "Smith", "Lopez", "Cohen", "Martinez", "Brown", "Rodriguez", "Levi", "Perez", "Johnson", "Gomez", "Davis"]
CITIES = [("Miami", "FL", "en"), ("Bogota", "DC", "es"), ("Austin", "TX", "en"), ("Medellin", "ANT", "es"), ("New York", "NY", "en"), ("Houston", "TX", "es")]
STATUSES = ["delivered", "delivered", "delivered", "in_transit", "processing"]

TICKETS = [
    ("en", "Where is my order {order}? It's been a week."),
    ("es", "Hola, ¿dónde está mi pedido {order}? Todavía no llega."),
    ("en", "I want to reorder the same thing as last time."),
    ("es", "Quiero volver a pedir lo mismo de la última vez, por favor."),
    ("en", "Please pause my subscription for a month."),
    ("es", "Necesito cancelar mi suscripción."),
    ("en", "My bottle arrived broken, I want a refund."),
    ("es", "Me llegó el producto dañado y quiero un reembolso."),
    ("en", "Can I take magnesium with my blood pressure medication?"),
]


def build(days: int, seed: int) -> dict:
    rnd = random.Random(seed)
    end = date(2026, 10, 29)
    start = end - timedelta(days=days - 1)
    products = [dict(p) for p in PRODUCTS]
    for p in products:
        if p["launch_date"] == "LAST2":
            p["launch_date"] = (end - timedelta(days=1)).isoformat()

    customers = []
    for i in range(1, 7001):
        city, state, lang = rnd.choice(CITIES)
        customers.append({
            "id": f"C{i:04d}",
            "name": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}",
            "email": f"customer{i:04d}@example.com",
            "phone": f"+1-555-01{i % 100:02d}",  # fake 555 numbers
            "city": city, "state": state, "language": lang,
            "subscription": rnd.random() < 0.18,
            "sms_consent": rnd.random() < 0.55,
            "email_consent": rnd.random() < 0.85,
        })

    orders, sessions, spend = [], [], []
    oid = 1000
    seen = set()
    seen_list = []
    for d in range(days):
        day = start + timedelta(days=d)
        weekday_boost = 1.15 if day.weekday() in (0, 6) else 1.0
        n_sessions = int(rnd.gauss(1900, 150) * weekday_boost)
        meta = round(rnd.gauss(560, 50) * weekday_boost, 2)
        google = round(rnd.gauss(240, 25), 2)
        is_launch_window = d >= days - 2
        if is_launch_window:
            n_sessions = int(n_sessions * 1.35)  # launch traffic spike
            meta = round(meta * 1.6, 2)
        sessions.append({"date": day.isoformat(), "sessions": n_sessions})
        spend.append({"date": day.isoformat(), "meta": meta, "google": google})
        cvr = rnd.gauss(0.025, 0.002)
        if is_launch_window:
            cvr *= 0.72  # launch underperforms: traffic up, conversion down
        n_orders = max(1, int(n_sessions * cvr))
        for _ in range(n_orders):
            oid += 1
            if seen_list and rnd.random() < 0.38:
                c = rnd.choice(seen_list)  # returning customer
            else:
                c = customers[len(seen_list) % len(customers)]  # next new customer
            pool = products if day.isoformat() >= (products[-1]["launch_date"] or "9999") else products[:-1]
            weights = [5, 3, 3, 2, 6][: len(pool)]
            items = []
            for p in rnd.choices(pool, weights=weights, k=rnd.choice([1, 1, 1, 2, 2, 3])):
                items.append({"sku": p["sku"], "qty": 1, "price": p["price"]})
            subtotal = sum(i["price"] * i["qty"] for i in items)
            discount = round(subtotal * 0.15, 2) if rnd.random() < 0.3 else 0.0
            age = (end - day).days
            status = "delivered" if age > 7 else rnd.choice(STATUSES)
            orders.append({
                "id": f"#{oid}", "customer_id": c["id"], "date": day.isoformat(),
                "items": items, "subtotal": round(subtotal, 2), "discount": discount,
                "total": round(subtotal - discount, 2),
                "new_customer": c["id"] not in seen,
                "status": status,
                "tracking": f"1Z999AA1{oid:08d}" if status != "processing" else None,
                "carrier": "UPS" if status != "processing" else None,
            })
            if c["id"] not in seen:
                seen_list.append(c)
            seen.add(c["id"])

    recent = [o for o in orders if o["status"] != "delivered"][:5] or orders[-5:]
    tickets = []
    for i, (lang, text) in enumerate(TICKETS):
        o = recent[i % len(recent)]
        tickets.append({"id": f"T{i + 1:03d}", "customer_id": o["customer_id"], "language": lang,
                        "channel": "chat" if i % 2 else "email", "text": text.format(order=o["id"])})
    return {"products": products, "customers": customers, "orders": orders,
            "sessions": sessions, "ad_spend": spend, "tickets": tickets,
            "targets": {"launch_sku": "SLP-30", "cvr": 0.025, "aov": 62.0, "mer": 3.0, "launch_units_48h": 90}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    data = build(a.days, a.seed)
    for k, v in data.items():
        (OUT / f"{k}.json").write_text(json.dumps(v, indent=1, ensure_ascii=False))
    print(f"wrote mock data: {len(data['orders'])} orders, {len(data['customers'])} customers, {a.days} days -> {OUT}")


if __name__ == "__main__":
    main()
