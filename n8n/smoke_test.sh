#!/usr/bin/env bash
# Live check of workflow 01 in a real n8n instance (tested on n8n 1.95.3).
# 1) python3 cli.py serve 8787     2) import + activate 01_support_agent_webhook.json in n8n
# 3) run this script. Expects JSON back with queue/intent/language/draft.
set -euo pipefail
N8N=${N8N_URL:-http://localhost:5678}
for body in \
  '{"ticket_id":"T-1","customer_id":"C0001","text":"Where is my order?"}' \
  '{"ticket_id":"T-2","text":"Can I take this while pregnant?"}' \
  '{"ticket_id":"T-3","text":"Hola, quiero pedir otra vez el magnesio"}'; do
  curl -sf -X POST "$N8N/webhook/dtc-support" -H 'Content-Type: application/json' -d "$body"; echo
done
