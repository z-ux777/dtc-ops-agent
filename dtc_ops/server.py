"""Tiny HTTP API (stdlib) so n8n, Zapier, Make or a chat widget can call the agent.

GET  /health
GET  /api/orders/<id>            mock order lookup
GET  /report/weekly              KPI scorecard
GET  /segments/replenishment     replenishment + win-back segments
POST /launch/check   {"sku": "SLP-30", "hours": 48}
POST /webhook/support {"id","customer_id","text","language?"}
POST /roi            {"hourly_cost": 30}
Optional auth: set DTC_API_TOKEN and send header X-API-Token.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import data, kpis, launch_monitor, replenishment, roi, support_agent


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False, indent=1).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        tok = os.environ.get("DTC_API_TOKEN")
        return not tok or self.headers.get("X-API-Token") == tok

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, *a):
        pass

    def do_GET(self):
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        p = self.path.split("?")[0]
        if p == "/health":
            return self._send(200, {"ok": True})
        if p.startswith("/api/orders/"):
            o = data.order_by_id(p.rsplit("/", 1)[1])
            return self._send(200 if o else 404, o or {"error": "not found"})
        if p == "/report/weekly":
            return self._send(200, kpis.scorecard())
        if p == "/segments/replenishment":
            return self._send(200, replenishment.segments())
        return self._send(404, {"error": "unknown route"})

    def do_POST(self):
        if not self._authed():
            return self._send(401, {"error": "unauthorized"})
        p, b = self.path.split("?")[0], self._body()
        if p == "/webhook/support":
            if not b.get("text"):
                return self._send(400, {"error": "text required"})
            return self._send(200, support_agent.handle(b))
        if p == "/launch/check":
            return self._send(200, launch_monitor.check(b.get("sku"), int(b.get("hours", 48))))
        if p == "/roi":
            return self._send(200, roi.estimate(b.get("tasks"), float(b.get("hourly_cost", 30))))
        return self._send(404, {"error": "unknown route"})


def serve(port: int = 8787):
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"DTC Ops Agent API on http://localhost:{port}  (Ctrl+C to stop)")
    srv.serve_forever()
