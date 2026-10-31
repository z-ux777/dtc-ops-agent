# CLAUDE.md: handoff for Claude Code

You are picking up **DTC Ops Agent**, a portfolio proof-of-work project by Zvi Adler. Your job is to
**verify** it, **add** a few features, and **improve** it, in that order. Read this whole file first.

## 1. Purpose

A working AI operations layer for a direct-to-consumer (DTC) e-commerce brand on a Shopify + Klaviyo style
stack, wired into n8n. It exists to show hiring managers real, runnable work for DTC e-commerce and AI
automation roles, including:

- Snap Supplements (E-Commerce Director)
- Blunt Cases (Director of Ecommerce & Growth)
- Wildfang (Director of Ecommerce & Growth)
- Zapier (Automation Strategist)
- n8n (Deployment Strategist)
- Tapcart (Solutions Engineer)
- Urrly client (AI Automation Engineer)
- Distill (Implementation Specialist)
- ElevenLabs (Deployment Strategist)
- Olipop

Reviewers will clone it and run two commands. It must work on a fresh clone in under a minute, with no installs.

## 2. Architecture and file map

```
cli.py                      CLI entry: demo | report | launch [SKU] | segments | chat "text" [cust] | roi | serve [port]
dtc_ops/
  data.py                   Loads mock JSON from data/. Auto-generates the dataset on first run if files are missing.
  kpis.py                   Weekly scorecard: revenue, orders, AOV, CVR, MER, new-customer CPA, returning share, margin, flags
  launch_monitor.py         48h launch diagnosis (traffic -> CVR -> AOV/offer -> paid -> units -> margin), act-now vs wait
  replenishment.py          Replenishment-due + win-back segments, Klaviyo-style event payloads (consent-filtered)
  support_agent.py          Bilingual EN/ES agent: detect language -> classify intent -> tool call -> draft -> route
  llm.py                    Optional OpenRouter call; offline template fallback (default). DTC_OFFLINE=1 by default
  approvals.py              Approval queue (JSONL). Every outbound action is enqueued, never sent
  roi.py                    Automation ROI model (minutes saved x runs x hourly cost)
  server.py                 Stdlib HTTP API for n8n/Zapier/Make. Optional DTC_API_TOKEN -> X-API-Token header
data/
  generate_mock_data.py     Deterministic generator (120 days, seed 7, end date 2026-10-29)
  products.json, sessions.json, ad_spend.json, tickets.json, targets.json   small mock files (committed)
  customers.json, orders.json   large mock files (gitignored, generated on first run)
n8n/
  01_support_agent_webhook.json         Webhook POST /dtc-support -> agent -> IF human-review vs approve -> respond
  02_weekly_scorecard_launch_watch.json Monday 8am: scorecard + launch check -> Slack (node disabled)
  03_replenishment_to_klaviyo.json      Daily 7am: Replenishment Due events -> Klaviyo (node disabled, placeholder key)
  smoke_test.sh                         Posts 3 tickets to a live n8n webhook and prints routed drafts
sample_output/              Written by `cli.py demo` (segments.json is gitignored because it is large)
docs/case_study.html        One-page case study (PDF version is not in the repo)
tests/test_all.py           14 unittest tests (stdlib), incl. HTTP server and n8n JSON validation
```

HTTP routes: `GET /health`, `GET /api/orders/<id>`, `GET /report/weekly`, `GET /segments/replenishment`,
`POST /launch/check`, `POST /webhook/support`, `POST /roi`.

## 3. How to run and test

```bash
python3 cli.py demo            # generates mock data if missing, runs every module, writes sample_output/
python3 tests/test_all.py      # must print OK (14+ tests)
python3 cli.py chat "Hola, ¿dónde está mi pedido #6510?" C0002
python3 cli.py serve 8787      # HTTP API
```

n8n (tested on 1.95.3):
1. `python3 cli.py serve 8787`
2. In n8n: Workflows > Import from file > each JSON in `n8n/`. If n8n runs in Docker, change
   `http://127.0.0.1:8787` to `http://host.docker.internal:8787` in the HTTP Request nodes.
3. Activate workflow 01, then `bash n8n/smoke_test.sh` (override host with `N8N_URL=...`).
   Expect three JSON responses with queue/intent/language/draft.

## 4. Constraints (do not break these)

- **Mock data only.** Never add real store, customer, brand or revenue data. Fake emails stay `@example.com`,
  phones stay 555 numbers. Do not name any real employer's store as the data source.
- **No real secrets.** No API keys, tokens or webhooks in code, n8n JSON, tests or docs. `.env.example` holds
  placeholders only; `.env` is gitignored. n8n Slack/Klaviyo nodes stay disabled with placeholder credentials.
- **Human in the loop.** Every outbound action (reply, refund, Klaviyo event, Slack post, voice reply) goes through
  `approvals.enqueue`. Nothing sends, refunds, charges or calls a customer.
- **Deterministic guardrails.** Routing for medical questions, refunds and cancellations must never depend on an
  LLM. LLM output may only reword a draft, and must fall back to the template on any error.
- **Stdlib first.** Core code and tests run on Python 3.10+ with the standard library only. If a feature truly needs
  a package (for example a dashboard framework), make it optional and keep `cli.py demo` + tests dependency-free.
- **Tests and demo stay offline** (`DTC_OFFLINE=1`), with no network calls.
- Keep the README contact email (adlershachar31@gmail.com) and the "all data is mock" statement.

## 5. Known gaps

- Intent classification is keyword/regex based. Probed edge cases that currently misroute:
  - `"Hello, me again, where is my package?"` -> `reorder` (the word "again" wins over order status)
  - `"Is it safe with my medications?"` -> `unknown` (plural "medications" not matched; it still goes to a human, but as unknown, not medical)
  - `"Can I take this while nursing?"` -> `unknown` (should be `medical_question`)
  - `"I want my money back"` -> `unknown` (should be `refund_damaged`/refund)
  - `"Stop my subscription please"` -> `unknown` (cancel vs pause is ambiguous; should go to a human as cancel)
  - `"I do not want to cancel my subscription, where is my order?"` -> `cancel_subscription` (no negation handling;
    safe because it goes to a human, but noisy)
- Spanish detection needs 2+ hint words or "¿": single-word `"Hola"` / `"Gracias"` are detected as English, and
  `"Me puedes ayudar con mi pedido?"` is Spanish but classified `unknown`.
- `llm.py` already calls OpenRouter when `OPENROUTER_API_KEY` is set and `DTC_OFFLINE=0`, but it has no tests with a
  mocked HTTP response, no output length/safety check, and no timeout/retry config.
- No CI. No web UI. No voice channel. No type checking. Executable bit on `n8n/smoke_test.sh` may be lost (run with `bash`).
- The case study PDF is not in the repo (binary); only `docs/case_study.html`.
- Data layer is mock JSON; a real deployment would swap `data.py` for Shopify Admin API + Klaviyo API clients.

## 6. Prioritized task list

### (a) Verify (do first)
1. Run `python3 cli.py demo` and `python3 tests/test_all.py` on a fresh clone (delete `data/customers.json`,
   `data/orders.json` first to confirm auto-generation). Everything must pass.
2. Review `dtc_ops/support_agent.py` routing: medical, refund and cancel must always escalate to `human_review`.
   Add tests for every edge case in section 5, then fix the patterns so they pass. Order of `INTENTS` matters:
   safety intents (medical, refund, cancel) must keep priority over convenience intents.
3. Add Spanish-detection tests (single-word greetings, accents vs no accents, mixed EN/ES) and fix `detect_language`.
4. Confirm no reply ever contains medical advice or promises a refund (assert on template text).

### (b) Add
1. **LLM via OpenRouter, hardened.** Keep it behind `OPENROUTER_API_KEY` + `DTC_OFFLINE=0`, mock fallback by default.
   Add tests that monkeypatch `urllib.request.urlopen` (success, error, empty, overlong reply). Optionally add an
   LLM intent classifier that can only *add* escalation, never remove it.
2. **ElevenLabs voice reply stub** (proof idea B: bilingual voice agent on this backend). New `dtc_ops/voice.py`:
   takes the agent result, picks an EN/ES voice ID from env vars, and builds the ElevenLabs text-to-speech request.
   Offline by default (returns the request payload, no network call). Enqueue the voice reply in the approval queue.
   Add a `cli.py voice "text" [customer_id]` command and a `POST /webhook/voice` route, plus tests.
3. **Simple web dashboard** for the KPI scorecard: `GET /dashboard` served by `server.py` as a single HTML page
   (stdlib, inline CSS/JS, no build step) showing this week vs last week, flags, launch check and approval queue count.
4. **GitHub Actions CI**: `.github/workflows/tests.yml` running `python3 tests/test_all.py` on Python 3.10-3.13.
   No secrets needed.

### (c) Improve
1. Code quality: type hints across `dtc_ops/`, docstrings, small functions; optional `ruff`/`mypy` config that CI runs.
2. README: add a screenshot or GIF of `cli.py demo`, the dashboard and the n8n workflow canvas (store under `docs/img/`).
3. Refresh `docs/case_study.html` with any new features (voice, dashboard, CI) and keep "all numbers are mock" text.

## 7. Working rules for you (Claude Code)

- Keep commits small and focused, one task per commit, with clear messages.
- Keep tests green after every commit. Add a test for every behavior change.
- Do **not** publish anything, create releases, change repository visibility or settings, add collaborators,
  or push to other repos. Do not add real credentials. If a task seems to need any of that, stop and ask Zvi.
- Do not rewrite history on `main`.
