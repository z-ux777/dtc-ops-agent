"""Human-approval queue. Every outbound action (reply, refund, Klaviyo event, Slack alert) lands here as a draft.
Nothing in this project sends, refunds, or charges anything.
"""
import json
import os
import time
from pathlib import Path

QUEUE = Path(os.environ.get("DTC_QUEUE", Path(__file__).resolve().parent.parent / "sample_output" / "approval_queue.jsonl"))


def enqueue(kind: str, payload: dict, reason: str) -> dict:
    item = {"id": f"A{int(time.time() * 1000) % 10**9}", "kind": kind, "status": "pending_human_approval",
            "reason": reason, "payload": payload}
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("a") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item
