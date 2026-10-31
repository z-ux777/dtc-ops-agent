"""Bilingual (English/Spanish) support agent for a DTC store.

Flow: detect language -> classify intent -> call a tool on the (mock) order API -> draft a reply
-> route: auto-safe replies are marked ready; refunds, cancellations and health questions go to a human.
The LLM is optional (see llm.py); routing and guardrails are deterministic so they can be tested.
"""
import re
import unicodedata

from . import approvals, data, llm

ES_HINTS = {"hola", "pedido", "donde", "quiero", "suscripcion", "reembolso", "llega", "gracias", "por", "favor",
            "necesito", "cancelar", "dañado", "danado", "mismo", "ultima", "vez", "producto", "me"}

INTENTS = [
    ("medical_question", r"\b(medication|medicine|pregnan\w*|breastfeed\w*|doctor|blood pressure|medicamento\w*|embaraz\w*|presion|lactancia)\b"),
    ("refund_damaged", r"\b(refund|broken|damaged|reembolso|dañado|danado|roto)\b"),
    ("cancel_subscription", r"\b(cancel|cancelar)\b.*\b(subscription|suscripcion|suscripción)\b|\b(subscription|suscripcion|suscripción)\b.*\b(cancel|cancelar)\b"),
    ("pause_subscription", r"\b(pause|skip|pausar|saltar)\b"),
    ("reorder", r"\b(reorder|same thing|again|volver a pedir|otra vez|lo mismo|repetir)\b"),
    ("order_status", r"\b(where|status|tracking|arrive|donde|dónde|llega|estado|rastreo)\b"),
]

HUMAN_ONLY = {"medical_question", "refund_damaged", "cancel_subscription"}

T = {
    "order_status": {
        "en": "Hi {first}, your order {order} is {status_en}.{track} Reply here if anything looks off.",
        "es": "Hola {first}, tu pedido {order} está {status_es}.{track} Responde aquí si algo no se ve bien.",
    },
    "reorder": {
        "en": "Hi {first}, I can set up the same order as {order}: {items}. Total ${total:.2f}. Reply YES and a teammate will confirm it.",
        "es": "Hola {first}, puedo preparar el mismo pedido que {order}: {items}. Total ${total:.2f}. Responde SÍ y alguien del equipo lo confirma.",
    },
    "pause_subscription": {
        "en": "Hi {first}, I can pause your subscription for 30 days. A teammate will confirm the new date today.",
        "es": "Hola {first}, puedo pausar tu suscripción por 30 días. Alguien del equipo te confirma la nueva fecha hoy.",
    },
    "cancel_subscription": {
        "en": "Hi {first}, thanks for letting us know. A teammate will process your cancellation and confirm by email today.",
        "es": "Hola {first}, gracias por avisarnos. Alguien del equipo procesará la cancelación y te confirmará por correo hoy.",
    },
    "refund_damaged": {
        "en": "Hi {first}, sorry your order {order} arrived damaged. Could you send a photo? A teammate will handle the replacement or refund today.",
        "es": "Hola {first}, lamentamos que tu pedido {order} llegara dañado. ¿Nos envías una foto? Alguien del equipo gestiona el reemplazo o reembolso hoy.",
    },
    "medical_question": {
        "en": "Hi {first}, we can't give medical advice. Please check with your doctor or pharmacist before combining supplements with medication. A teammate can share the full label.",
        "es": "Hola {first}, no podemos dar consejos médicos. Consulta con tu médico o farmacéutico antes de combinar suplementos con medicamentos. Podemos enviarte la etiqueta completa.",
    },
    "need_order": {
        "en": "Hi {first}, happy to help. Could you share your order number or the email you ordered with?",
        "es": "Hola {first}, con gusto te ayudo. ¿Me compartes tu número de pedido o el correo con el que compraste?",
    },
    "unknown": {
        "en": "Hi {first}, thanks for reaching out. A teammate will reply shortly.",
        "es": "Hola {first}, gracias por escribirnos. Alguien del equipo te responde pronto.",
    },
}
STATUS = {"delivered": ("delivered", "entregado"), "in_transit": ("on the way", "en camino"),
          "processing": ("being packed", "en preparación")}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def detect_language(text: str) -> str:
    words = set(re.findall(r"[a-z]+", _norm(text)))
    return "es" if len(words & {_norm(w) for w in ES_HINTS}) >= 2 or "¿" in text else "en"


def classify(text: str) -> str:
    low, flat = text.lower(), _norm(text)
    for name, pattern in INTENTS:
        if re.search(pattern, low) or re.search(_norm(pattern), flat):
            return name
    return "unknown"


def handle(ticket: dict) -> dict:
    text = ticket["text"]
    lang = ticket.get("language") or detect_language(text)
    intent = classify(text)
    cust = data.customers().get(ticket.get("customer_id"), {"name": "", "id": None})
    first = cust["name"].split()[0] if cust["name"] else ("there" if lang == "en" else "")
    first = first if first else ""
    m = re.search(r"#?(\d{4,})", text)
    order = data.order_by_id(m.group(1)) if m else None
    history = sorted(data.orders_for_customer(cust["id"]), key=lambda o: o["date"]) if cust.get("id") else []
    if order is None and history:
        order = history[-1]
    tool_calls = []
    ctx = {"first": first, "order": order["id"] if order else "", "track": "", "items": "", "total": 0.0,
           "status_en": "", "status_es": ""}
    if order:
        tool_calls.append({"tool": "get_order", "args": {"order_id": order["id"]}})
        en, es = STATUS.get(order["status"], (order["status"], order["status"]))
        ctx.update(status_en=en, status_es=es, total=order["total"],
                   items=", ".join(f"{i['qty']}x {data.products()[i['sku']]['name']}" for i in order["items"]))
        if order.get("tracking"):
            ctx["track"] = (f" Tracking: {order['carrier']} {order['tracking']}." if lang == "en"
                            else f" Rastreo: {order['carrier']} {order['tracking']}.")
    if intent == "reorder" and order:
        tool_calls.append({"tool": "draft_reorder", "args": {"from_order": order["id"]}})
    missing_order = intent in ("reorder", "order_status") and not order
    if missing_order:
        template = T["need_order"][lang]
    else:
        template = T.get(intent, T["unknown"])[lang]
    fallback = template.format(**ctx).replace("Hola ,", "Hola,")
    reply = llm.complete(
        system=("You are a support agent for a supplement brand. Reply in the customer's language, under 60 words, "
                "use only the facts given, never give medical advice, never promise refunds."),
        user=f"Customer message: {text}\nFacts: {ctx}\nDraft to improve: {fallback}",
        fallback=fallback)
    needs_human = intent in HUMAN_ONLY or intent == "unknown" or missing_order
    result = {"ticket_id": ticket.get("id") or ticket.get("ticket_id"), "language": lang, "intent": intent, "tool_calls": tool_calls,
              "reply": reply, "route": "human_review" if needs_human else "auto_ready_pending_approval"}
    approvals.enqueue("support_reply", result, reason="human_only_intent" if needs_human else "standard_review")
    return result
