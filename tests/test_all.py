import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DTC_OFFLINE"] = "1"
os.environ["DTC_QUEUE"] = str(Path(tempfile.mkdtemp()) / "queue.jsonl")

from dtc_ops import approvals, data, kpis, launch_monitor, replenishment, roi, server, support_agent  # noqa: E402


class TestKPIs(unittest.TestCase):
    def test_scorecard_math(self):
        sc = kpis.scorecard()
        tw = sc["this_week"]
        self.assertEqual(tw["days"], 7)
        self.assertAlmostEqual(tw["aov"], tw["revenue"] / tw["orders"], places=1)
        self.assertAlmostEqual(tw["mer"], tw["revenue"] / tw["ad_spend"], places=1)
        self.assertTrue(0 < tw["cvr"] < 0.1)
        self.assertTrue(0 < tw["gross_margin"] < 1)

    def test_flags_catch_launch_drop(self):
        self.assertTrue(any("CVR down" in f for f in kpis.scorecard()["flags"]))


class TestLaunch(unittest.TestCase):
    def test_diagnoses_onsite_problem(self):
        r = launch_monitor.check("SLP-30", 48)
        self.assertTrue(any("conversion is down" in a for a in r["act_now"]))
        self.assertEqual(len(r["findings"]), 6)


class TestReplenishment(unittest.TestCase):
    def test_segments_exclude_subscribers_and_window(self):
        s = replenishment.segments(window_days=7)
        custs = data.customers()
        self.assertGreater(s["counts"]["replenish_due"], 0)
        for r in s["replenish_due"]:
            self.assertTrue(0 <= r["days_left"] <= 7)
            self.assertFalse(custs[r["customer_id"]]["subscription"])

    def test_klaviyo_payload_shape(self):
        rec = replenishment.segments()["replenish_due"][0]
        ev = replenishment.klaviyo_event(rec)
        self.assertEqual(ev["data"]["type"], "event")
        self.assertEqual(ev["data"]["attributes"]["profile"]["data"]["attributes"]["email"], rec["email"])


class TestSupportAgent(unittest.TestCase):
    def test_language(self):
        self.assertEqual(support_agent.detect_language("Hola, ¿dónde está mi pedido?"), "es")
        self.assertEqual(support_agent.detect_language("Where is my order?"), "en")

    def test_intents(self):
        cases = {"Where is my order #1005?": "order_status",
                 "Quiero volver a pedir lo mismo": "reorder",
                 "Necesito cancelar mi suscripción": "cancel_subscription",
                 "Please pause my subscription": "pause_subscription",
                 "My bottle arrived broken, refund please": "refund_damaged",
                 "Can I take this with my medication?": "medical_question",
                 "Can I take this while pregnant?": "medical_question",
                 "¿Puedo tomarlo si estoy embarazada?": "medical_question",
                 "Hola, quiero pedir otra vez el magnesio": "reorder",
                 "Do you ship to Canada?": "unknown"}
        for text, intent in cases.items():
            self.assertEqual(support_agent.classify(text), intent, text)

    def test_guardrails_route_to_human(self):
        for t in data.load("tickets"):
            r = support_agent.handle(t)
            if r["intent"] in ("medical_question", "refund_damaged", "cancel_subscription"):
                self.assertEqual(r["route"], "human_review")
            if r["intent"] == "medical_question":
                self.assertIn("medical advice" if r["language"] == "en" else "consejos médicos", r["reply"])

    def test_anonymous_spanish_greeting_is_clean(self):
        r = support_agent.handle({"ticket_id": "T-X", "text": "Hola, ¿dónde está mi pedido?"})
        self.assertEqual(r["ticket_id"], "T-X")
        self.assertEqual(r["language"], "es")
        self.assertNotIn("there", r["reply"])
        self.assertIn("número de pedido", r["reply"])  # no order found: ask, don't invent
        self.assertEqual(r["route"], "human_review")

    def test_order_status_uses_real_order_facts(self):
        o = next(x for x in data.orders() if x["status"] == "in_transit")
        r = support_agent.handle({"text": f"where is my order {o['id']}", "customer_id": o["customer_id"]})
        self.assertIn(o["id"], r["reply"])
        self.assertIn(o["tracking"], r["reply"])
        self.assertEqual(r["tool_calls"][0]["tool"], "get_order")

    def test_everything_is_queued_not_sent(self):
        support_agent.handle({"text": "Where is my order?", "customer_id": "C0001"})
        lines = Path(os.environ["DTC_QUEUE"]).read_text().strip().splitlines()
        self.assertTrue(all(json.loads(l)["status"] == "pending_human_approval" for l in lines))


class TestROI(unittest.TestCase):
    def test_roi(self):
        r = roi.estimate(hourly_cost=40)
        self.assertGreater(r["hours_saved_per_month"], 0)
        self.assertEqual(r["value_per_month_usd"], round(r["hours_saved_per_month"] * 40))


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_endpoints(self):
        self.assertTrue(self.call("/health")["ok"])
        self.assertIn("this_week", self.call("/report/weekly"))
        self.assertIn("counts", self.call("/segments/replenishment"))
        self.assertIn("act_now", self.call("/launch/check", {"sku": "SLP-30"}))
        oid = data.orders()[0]["id"].lstrip("#")
        self.assertEqual(self.call(f"/api/orders/{oid}")["id"], f"#{oid}")
        r = self.call("/webhook/support", {"text": "Hola, ¿dónde está mi pedido?", "customer_id": "C0002"})
        self.assertEqual(r["language"], "es")


class TestN8nWorkflows(unittest.TestCase):
    def test_workflow_json_is_valid_and_connected(self):
        for f in (ROOT / "n8n").glob("*.json"):
            wf = json.loads(f.read_text())
            names = {n["name"] for n in wf["nodes"]}
            for src, outs in wf["connections"].items():
                self.assertIn(src, names, f.name)
                for branch in outs["main"]:
                    for c in branch:
                        self.assertIn(c["node"], names, f.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
