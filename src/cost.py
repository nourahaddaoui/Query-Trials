"""Turn token counts into money. Three questions, straight from the brief:

  1. What does each model cost per 1,000 requests, today?
  2. What at 100x the traffic?
  3. At what volume does self-hosting cost the same as the API?

API cost comes from the REAL token counts in per_item.csv times list price -
never from estimates. Local cost is the machine's amortised hour rate divided
by how many requests it serves in an hour, which follows from its own median
latency. Every assumption lives in prices.yaml where it can be argued with.

    python -m src.cost

Appends cost columns into results/summary.csv and prints the break-even.
"""

import csv
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRICES = ROOT / "src" / "prices.yaml"
PER_ITEM = ROOT / "results" / "per_item.csv"
SUMMARY = ROOT / "results" / "summary.csv"


def load_rows(path):
    if not path.exists():
        sys.exit(f"No {path.name}. Run: python -m src.score first")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def api_cost_per_1k(rows, price):
    """Real tokens used across the run, scaled to 1,000 requests."""
    n = len(rows)
    tin = sum(int(r["prompt_tokens"]) for r in rows)
    tout = sum(int(r["completion_tokens"]) for r in rows)
    run_cost = (tin / 1e6) * price["input_per_mtok"] \
             + (tout / 1e6) * price["output_per_mtok"]
    return run_cost / n * 1000, tin, tout


def local_cost_model(rows, cfg):
    """What an hour of this machine costs, and what that means per request.

    marginal = the machine's hourly cost / requests it can serve per hour
    fixed    = one-off setup time (a human got Ollama working once)
    """
    lats = [float(r["latency_ms"]) for r in rows]
    median_s = statistics.median(lats) / 1000
    req_per_hour = 3600 / median_s if median_s > 0 else 0

    hours_owned = cfg["amortisation_years"] * 365 * 24 * cfg["utilisation"]
    hardware_per_hour = cfg["hardware_cost_usd"] / hours_owned
    power_per_hour = (cfg["power_watts"] / 1000) * cfg["electricity_usd_per_kwh"]
    machine_per_hour = hardware_per_hour + power_per_hour

    per_request = machine_per_hour / req_per_hour if req_per_hour else 0
    fixed_setup = cfg["setup_hours"] * cfg["hourly_rate_usd"]

    return {
        "median_s": median_s,
        "req_per_hour": req_per_hour,
        "machine_per_hour": machine_per_hour,
        "per_1k": per_request * 1000,
        "fixed_setup": fixed_setup,
    }


def break_even(api_per_1k, local_per_1k, fixed_setup):
    """Requests at which total API spend = total self-hosted spend.

    api_total(N)   = api_per_1k   * N/1000
    local_total(N) = fixed_setup + local_per_1k * N/1000
    """
    diff = (api_per_1k - local_per_1k) / 1000
    if diff <= 0:
        return None          # API is cheaper per request - never breaks even
    return fixed_setup / diff


def main():
    cfg = yaml.safe_load(PRICES.read_text())
    rows = load_rows(PER_ITEM)

    by_model = defaultdict(list)
    for r in rows:
        by_model[r["model_key"]].append(r)

    print(f"Prices checked {cfg['date_checked']}  ({cfg['source']})\n")

    costs = {}          # model_key -> cost_per_1k
    tokens = {}

    for key in ("top", "cheap"):
        rs = by_model.get(key)
        if not rs:
            continue
        name = rs[0]["model_name"]
        price = cfg["api"].get(name)
        if price is None:
            sys.exit(f"No price for '{name}' in prices.yaml - add it.")
        per_1k, tin, tout = api_cost_per_1k(rs, price)
        costs[key], tokens[key] = per_1k, (tin, tout)
        print(f"{name}")
        print(f"  real usage: {tin:,} in / {tout:,} out tokens over {len(rs)} items")
        print(f"  cost per 1k requests:  ${per_1k:,.2f}")
        print(f"  at 100x traffic (100k requests): ${per_1k * 100:,.2f}  "
              f"(linear - the API just bills more)\n")

    local_rows = by_model.get("local")
    lm = None
    if local_rows:
        lm = local_cost_model(local_rows, cfg["local"])
        costs["local"] = lm["per_1k"]
        print(f"{local_rows[0]['model_name']} (self-hosted)")
        print(f"  median latency {lm['median_s']:.1f}s -> "
              f"{lm['req_per_hour']:,.0f} requests/hour capacity")
        print(f"  machine cost ${lm['machine_per_hour']:.3f}/hour "
              f"(hardware amortised + electricity)")
        print(f"  marginal cost per 1k requests: ${lm['per_1k']:,.2f}")
        print(f"  one-off setup: ${lm['fixed_setup']:.0f} "
              f"({cfg['local']['setup_hours']}h of someone's time)")
        print(f"  at 100x traffic: NOT linear - one machine absorbs growth "
              f"until it saturates")
        print(f"  this machine saturates at {lm['req_per_hour'] * 24:,.0f} "
              f"requests/day; beyond that you buy another machine (a step, "
              f"not a slope)\n")

    # --- break-even: cheapest API vs local ---
    if lm and costs:
        api_keys = [k for k in ("cheap", "top") if k in costs]
        for k in api_keys:
            be = break_even(costs[k], lm["per_1k"], lm["fixed_setup"])
            if be is None:
                print(f"break-even vs {k}: never - the API is cheaper per "
                      f"request than this machine")
            else:
                print(f"break-even vs {k} ({by_model[k][0]['model_name']}): "
                      f"~{be:,.0f} requests")
                print(f"  below that volume the API is cheaper overall; "
                      f"above it, self-hosting wins (if latency is acceptable)")

    # --- write cost_per_1k into summary.csv ---
    srows = load_rows(SUMMARY)
    for r in srows:
        c = costs.get(r["model_key"])
        r["cost_per_1k_usd"] = f"{c:.2f}" if c is not None else ""
    cols = list(srows[0].keys())
    if "cost_per_1k_usd" not in cols:
        cols.append("cost_per_1k_usd")
    with open(SUMMARY, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(srows)
    print(f"\nWrote cost_per_1k_usd into {SUMMARY.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
