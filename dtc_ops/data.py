import json
import os
import sys
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(os.environ.get("DTC_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


GENERATOR = Path(__file__).resolve().parent.parent / "data" / "generate_mock_data.py"


def ensure_mock_data(name: str) -> Path:
    """Return the path to a mock data file, generating the mock dataset on first run if missing.

    The large files (customers.json, orders.json) are not committed to git. They are rebuilt
    deterministically from data/generate_mock_data.py with its default settings (120 days, seed 7).
    """
    path = DATA_DIR / f"{name}.json"
    if path.exists():
        return path
    import importlib.util

    spec = importlib.util.spec_from_file_location("generate_mock_data", GENERATOR)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(f"{path} missing and generator not found at {GENERATOR}")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for key, value in gen.build(120, 7).items():
        target = DATA_DIR / f"{key}.json"
        if not target.exists():
            target.write_text(json.dumps(value, indent=1, ensure_ascii=False))
    print(f"[dtc_ops] generated mock data in {DATA_DIR} (first run)", file=sys.stderr)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing after generating mock data")
    return path


@lru_cache(maxsize=None)
def load(name: str):
    return json.loads(ensure_mock_data(name).read_text())


def products():
    return {p["sku"]: p for p in load("products")}


def customers():
    return {c["id"]: c for c in load("customers")}


def orders():
    return load("orders")


def order_by_id(order_id: str):
    oid = order_id if order_id.startswith("#") else f"#{order_id}"
    for o in orders():
        if o["id"] == oid:
            return o
    return None


def orders_for_customer(cid: str):
    return [o for o in orders() if o["customer_id"] == cid]
