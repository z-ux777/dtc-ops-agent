"""48-hour launch check. Diagnoses an underperforming launch in a fixed order:
traffic -> CVR -> offer/AOV -> paid efficiency -> inventory -> margin, and says what to act on now vs wait for.
"""
from datetime import date, timedelta

from . import data, kpis


def check(sku: str | None = None, hours: int = 48) -> dict:
    t = data.load("targets")
    sku = sku or t["launch_sku"]
    prods = data.products()
    p = prods[sku]
    end = max(o["date"] for o in data.orders())
    days = max(1, hours // 24)
    now = kpis.window(end, days)
    base_end = (date.fromisoformat(end) - timedelta(days=days)).isoformat()
    base = kpis.window(base_end, 28)
    per_day = lambda w, k: w[k] / w["days"]
    units = sum(i["qty"] for o in data.orders() if o["date"] >= now["start"] for i in o["items"] if i["sku"] == sku)
    traffic_lift = per_day(now, "sessions") / per_day(base, "sessions") - 1
    findings, act_now, wait = [], [], []

    findings.append(f"Traffic: {now['sessions']} sessions in {hours}h, {traffic_lift:+.0%} vs 28-day daily average.")
    if traffic_lift < 0.10:
        act_now.append("Traffic is not lifting: check ad delivery, launch email/SMS sends, and homepage placement first.")

    cvr_gap = now["cvr"] / t["cvr"] - 1
    findings.append(f"CVR: {now['cvr']:.2%} vs target {t['cvr']:.2%} ({cvr_gap:+.0%}).")
    if cvr_gap < -0.15 and traffic_lift > 0.10:
        act_now.append("Traffic is up but conversion is down: the problem is on-site or the offer, not reach. "
                       "Check PDP load and checkout errors, then message match between the ad and landing page, then price/bundle.")

    aov_gap = now["aov"] / t["aov"] - 1
    findings.append(f"AOV: ${now['aov']:.2f} vs target ${t['aov']:.2f} ({aov_gap:+.0%}).")
    if aov_gap < -0.10:
        wait.append("AOV below target: test a bundle with a best-seller after CVR is fixed; changing both at once hides the cause.")

    findings.append(f"Paid efficiency: MER {now['mer']} vs target {t['mer']} (28-day baseline {base['mer']}).")
    if now["mer"] < t["mer"] * 0.8:
        act_now.append("MER is more than 20% under target: cap spend increases on launch campaigns until CVR recovers; keep best creative live.")

    findings.append(f"Launch units ({sku}): {units} vs {t['launch_units_48h']} planned for {hours}h.")
    margin = 1 - p["cogs"] / p["price"]
    findings.append(f"Unit gross margin on {sku}: {margin:.0%} at full price.")
    if margin < 0.6:
        wait.append("Margin is thin: avoid deeper discounts as the fix.")
    wait.append("Creative fatigue and retention effects need 5-7 days of data before you judge them.")
    return {"sku": sku, "product": p["name"], "window": now, "baseline_28d": base,
            "findings": findings, "act_now": act_now, "wait_for_signal": wait}
