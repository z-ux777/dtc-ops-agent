"""DTC Ops Agent CLI.

python cli.py demo            run every module on mock data and write sample_output/
python cli.py report          weekly KPI scorecard
python cli.py launch [SKU]    48h launch diagnosis
python cli.py segments        replenishment + win-back segments
python cli.py chat "text" [customer_id]   one support message
python cli.py roi             automation ROI estimate
python cli.py serve [port]    HTTP API for n8n / Zapier / Make
"""
import json
import sys
from pathlib import Path

from dtc_ops import data, kpis, launch_monitor, replenishment, roi, server, support_agent

OUT = Path(__file__).resolve().parent / "sample_output"


def pr(obj):
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def demo():
    OUT.mkdir(exist_ok=True)
    (OUT / "approval_queue.jsonl").unlink(missing_ok=True)
    sc = kpis.scorecard()
    lc = launch_monitor.check()
    sg = replenishment.segments()
    replies = [support_agent.handle(t) for t in data.load("tickets")]
    events = [replenishment.klaviyo_event(r) for r in sg["replenish_due"][:3]]
    r = roi.estimate()
    for name, obj in [("weekly_scorecard", sc), ("launch_check", lc), ("segments", sg),
                      ("support_replies", replies), ("klaviyo_events_preview", events), ("roi", r)]:
        (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    tw = sc["this_week"]
    print("== Weekly scorecard (mock data) ==")
    print(f"Revenue ${tw['revenue']:,.0f} | Orders {tw['orders']} | AOV ${tw['aov']} | CVR {tw['cvr']:.2%} | MER {tw['mer']} | New-cust CPA ${tw['new_customer_cpa']}")
    print("Flags:", "; ".join(sc["flags"]) or "none")
    print("\n== 48h launch check:", lc["product"], "==")
    for f in lc["findings"]:
        print(" -", f)
    print(" Act now:", *[f"\n   * {a}" for a in lc["act_now"]])
    print("\n== Segments ==", sg["counts"])
    print("\n== Support agent ==")
    for x in replies:
        print(f" [{x['language']}] {x['intent']:<20} -> {x['route']}: {x['reply'][:90]}")
    print(f"\n== ROI == ~{r['hours_saved_per_month']} hours/month saved (assumptions)")
    print(f"\nAll outbound actions queued for approval in {OUT/'approval_queue.jsonl'} (nothing sent).")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "demo"
    if cmd == "demo":
        demo()
    elif cmd == "report":
        pr(kpis.scorecard())
    elif cmd == "launch":
        pr(launch_monitor.check(argv[2] if len(argv) > 2 else None))
    elif cmd == "segments":
        pr(replenishment.segments())
    elif cmd == "chat":
        pr(support_agent.handle({"id": "CLI", "text": argv[2], "customer_id": argv[3] if len(argv) > 3 else None}))
    elif cmd == "roi":
        pr(roi.estimate())
    elif cmd == "serve":
        server.serve(int(argv[2]) if len(argv) > 2 else 8787)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
