"""Reconcile E's manual fallback quote to its actual allocated pod price."""

import argparse
import json
from decimal import Decimal, ROUND_DOWN

try:
    from scripts import runpod_pilot as helper
except ModuleNotFoundError:
    import runpod_pilot as helper


def reconcile(pod_id: str) -> dict:
    """Reprice only E's allocation and reserve its remaining five-dollar allowance.
    Why: a manual Secure fallback floor shortened the cheaper Community allocation.
    If wrong: changing a reservation could exceed E's budget or the shared pilot cap.
    """
    key = helper.read_key(helper.ROOT / ".env")
    hf_token = helper.read_env_value(helper.ROOT / ".env", "HUGGINGFACE_TOKEN")
    request = helper.build_request("status", pod_id=pod_id)
    with helper.locked_ledger(helper.LEDGER) as (handle, ledger):
        entry = helper.find_pod(ledger, pod_id)
        if entry.get("label") != "E" or entry.get("terminated_at"):
            raise ValueError("Reconcile only this active E allocation")
        pod = helper.send(request, key, hf_token)
        if helper.pod_state(pod) != "RUNNING":
            raise ValueError("A running allocation is required")
        actual = helper.actual_price(pod)
        if actual is None:
            raise ValueError("The pod did not report its price")
        disk = helper.DISK_HOURLY_PER_GB * helper.GPU_CLASSES["mid"]["disk_gb"]
        rate = actual + disk
        current = helper.utc_now()
        others_e = sum((helper.pod_spend(p, current) for p in ledger["pods"]
                        if p.get("label") == "E" and p["id"] != pod_id), Decimal(0))
        allowance = Decimal("5") - others_e
        hours = (allowance / rate).quantize(Decimal(".000000001"), rounding=ROUND_DOWN)
        if helper.elapsed_hours(entry["started_at"], current) >= hours:
            raise ValueError("E has no time remaining at its allocated price")
        others = dict(ledger, pods=[p for p in ledger["pods"] if p is not entry])
        helper.check_budget(others, str(rate), current, str(hours))
        adjustment = {"at": current, "old_hourly_price_usd": entry["hourly_price_usd"],
                      "old_max_hours": entry["max_hours"], "new_hourly_price_usd": str(rate),
                      "new_max_hours": str(hours), "pod_reported_hourly_price_usd": str(actual),
                      "disk_hourly_price_usd": str(disk), "source": request["url"],
                      "reason": "Replace the worker's manual Secure fallback price floor with the actual Community allocation plus the helper's container-disk allowance. E remains within five dollars including failed attempts."}
        entry.setdefault("price_reconciliations", []).append(adjustment)
        entry.update(hourly_price_usd=str(rate), quoted_hourly_price_usd=str(rate),
                     actual_hourly_price_usd=str(actual), max_hours=str(hours))
        helper.save_ledger(handle, ledger)
    return {"pod_id": pod_id, "prior_E_spend_usd": str(others_e), "allowance_usd": str(allowance),
            **adjustment}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pod-id", required=True)
    print(json.dumps(reconcile(parser.parse_args().pod_id), indent=2))
