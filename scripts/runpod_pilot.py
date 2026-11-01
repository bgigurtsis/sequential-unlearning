"""Construct RunPod v2 requests and track a conservative local pilot spend estimate."""

import argparse
import json
import math
import os
import re
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "derisk/erasure_pilot_v1/spend_ledger.json"
API = "https://api.runpod.io/v2"
GPU_TYPES = {"L40S": "NVIDIA L40S", "H200": "NVIDIA H200"}
IMAGE = "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"
LIMIT = Decimal("38.00")


class RunPodHTTPError(RuntimeError):
    """Keep the HTTP status available without retaining a potentially secret body."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"RunPod HTTP {status_code}; reconcile status before any retry")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Ledger timestamps require an explicit timezone")
    return result


def money(value: str | int | float) -> Decimal:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Prices and spend must be finite and nonnegative")
    return amount


def elapsed_hours(start: str, end: str) -> Decimal:
    seconds = (instant(end) - instant(start)).total_seconds()
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Ledger timestamps run backwards")
    return Decimal(str(seconds)) / Decimal(3600)


def recorded_spend(ledger: dict, now: str) -> Decimal:
    """Count elapsed GPU time and stopped storage, including uncertain requests.
    Why: stopped pods and incomplete API calls must not reset the spending limit.
    If wrong: the pilot can exceed its budget while the ledger appears safe.
    """
    total = money(ledger["other_spend_usd"])
    for pod in ledger["pods"]:
        if pod.get("status") == "CREATE_FAILED_NO_POD":
            # Only a reconciled request with no resource ID can have zero billable duration.
            if pod["id"] is not None or not pod.get("reconciled_at") or not pod.get("reconciliation"):
                raise ValueError("Failed create requires no pod ID and explicit reconciliation evidence")
            continue
        end = pod["stopped_at"] or pod["terminated_at"] or now
        total += elapsed_hours(pod["started_at"], end) * money(pod["hourly_price_usd"])
        if pod["stopped_at"] is not None:
            end = pod["terminated_at"] or now
            total += elapsed_hours(pod["stopped_at"], end) * money(pod["stopped_hourly_price_usd"])
    return total


def check_budget(ledger: dict, hourly_price: str, now: str) -> Decimal:
    """Refuse a create when elapsed spend plus one quoted hour exceeds 38 dollars.
    Why: the manager must have an hour of budget before acquiring another GPU.
    If wrong: one permitted create can cross the pilot's frozen spending limit.
    """
    if money(ledger["limit_usd"]) != LIMIT:
        raise ValueError("The pilot ledger limit must remain 38.00 USD")
    price = money(hourly_price)
    if price == 0:
        raise ValueError("A create requires a positive quoted all-in hourly price")
    total = recorded_spend(ledger, now)
    if total + price > LIMIT:
        raise ValueError(f"Budget refusal: {total:.4f} USD recorded plus {price} USD for one hour exceeds 38 USD")
    if any(pod["stopped_at"] is None and pod["terminated_at"] is None
           and pod.get("status") != "CREATE_FAILED_NO_POD" for pod in ledger["pods"]):
        raise ValueError("One pod at a time; a running or uncertain create already exists")
    return total


def build_request(command: str, gpu: str | None = None, pod_id: str | None = None,
                  image: str = IMAGE, network_volume: str | None = None) -> dict:
    """Construct a redacted request without reading credentials or making HTTP calls.
    Why: dry runs and CPU tests must be harmless and reproducible.
    If wrong: reviewing a request could provision a pod or expose the API key.
    """
    request = {"method": "GET", "url": API + "/pods", "headers": {
        "Authorization": "Bearer [REDACTED]", "Content-Type": "application/json"}, "body": None}
    if command == "create":
        if gpu not in GPU_TYPES:
            raise ValueError("Only L40S and H200 are in scope")
        request["method"] = "POST"
        request["body"] = {"name": "erasure-pilot-v1-" + gpu.lower(), "image": image,
                           "cloud": "COMMUNITY", "gpu": {"id": GPU_TYPES[gpu], "count": 1},
                           "disk": 50, "ports": ["22/tcp"], "startSsh": True}
        if network_volume:
            request["body"]["mounts"] = {"network": [{"volumeId": network_volume, "path": "/workspace"}]}
    elif command in {"status", "stop", "terminate"}:
        if not pod_id or not re.fullmatch(r"[A-Za-z0-9_-]+", pod_id):
            raise ValueError("A simple exact pod ID is required")
        request["url"] += "/" + quote(pod_id, safe="")
        if command == "stop":
            request.update(method="POST", url=request["url"] + "/action", body={"action": "stop"})
        elif command == "terminate":
            request["method"] = "DELETE"
    else:
        raise ValueError("Unknown pod command")
    return request


def read_env_value(env_file: Path, variable: str) -> str:
    """Read one requested variable with environment precedence and no echo.
    Why: local secrets must never enter requests printed for review or test output.
    If wrong: an API key could be committed or leaked in a traceback.
    """
    value = os.environ.get(variable, "").strip()
    if value:
        return value
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            text = line.strip()
            if text.startswith("export "):
                text = text[7:]
            name, separator, value = text.partition("=")
            if separator and name.strip() == variable:
                value = value.strip()
                if value.startswith(("'", '"')) and value[-1:] == value[:1]:
                    value = value[1:-1]
                else:
                    value = value.split(" #", 1)[0].strip()
                if value:
                    return value
    raise ValueError("Requested variable is missing from environment and the specified .env file")


def read_key(env_file: Path) -> str:
    return read_env_value(env_file, "RUNPOD_API_KEY")


def redacted_request(request: dict) -> dict:
    """Remove environment values from the request saved to disk or printed.
    Why: creation must pass a gated-model token without putting it in the ledger.
    If wrong: the token can enter git through an otherwise harmless spend record.
    """
    result = json.loads(json.dumps(request))
    if result.get("body") and "env" in result["body"]:
        result["body"]["env"] = {name: "[REDACTED]" for name in result["body"]["env"]}
    return result


def send(request: dict, key: str) -> dict:
    """Send one API request without retries or printing a response body.
    Why: a timed-out create may already have provisioned a chargeable resource.
    If wrong: automatic retries or verbose errors can duplicate pods or leak secrets.
    """
    headers = dict(request["headers"])
    headers["Authorization"] = "Bearer " + key
    body = json.dumps(request["body"]).encode("utf-8") if request["body"] is not None else None
    http = urllib.request.Request(request["url"], data=body, headers=headers, method=request["method"])
    try:
        with urllib.request.urlopen(http, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise RunPodHTTPError(error.code) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("RunPod transport failure; reconcile status before any retry") from None
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("RunPod returned invalid JSON; reconcile status before any retry") from None


@contextmanager
def locked_ledger(path: Path):
    """Lock the existing ledger across its read, remote request and update.
    Why: concurrent creates must not both pass the same budget check.
    If wrong: parallel callers could spend twice the available allowance.
    """
    with path.open("r+", encoding="utf-8", newline="\n") as handle:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield handle, json.load(handle)
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save_ledger(handle, ledger: dict) -> None:
    handle.seek(0)
    handle.write(json.dumps(ledger, indent=2) + "\n")
    handle.truncate()
    handle.flush()
    os.fsync(handle.fileno())


def find_pod(ledger: dict, pod_id: str) -> dict:
    matches = [pod for pod in ledger["pods"] if pod["id"] == pod_id]
    if len(matches) != 1:
        raise ValueError("Pod ID must identify exactly one recorded pilot pod")
    return matches[0]


def create_pod(args, request: dict, handle, ledger: dict, key: str) -> dict:
    """Reserve a pending ledger entry before the single remote create attempt.
    Why: uncertainty after a timeout must block a second create until reconciled.
    If wrong: an unrecorded running pod could consume the remaining budget.
    """
    started = utc_now()
    check_budget(ledger, args.hourly_price, started)
    stopped_price = money(args.stopped_hourly_price)
    entry = {"id": None, "gpu": args.gpu, "started_at": started, "stopped_at": None,
             "terminated_at": None, "hourly_price_usd": str(money(args.hourly_price)),
             "stopped_hourly_price_usd": str(stopped_price), "status": "CREATE_UNCERTAIN",
             "price_source": args.price_source, "request": redacted_request(request)["body"]}
    ledger["pods"].append(entry)
    save_ledger(handle, ledger)
    try:
        pod = send(request, key)
    except RunPodHTTPError as error:
        # Keep the reservation until reconciliation, but retain a safe diagnosis.
        entry["create_http_status"] = error.status_code
        save_ledger(handle, ledger)
        raise
    if not pod.get("id"):
        raise RuntimeError("Create response has no pod ID; reconcile the pending ledger entry")
    entry["id"] = pod["id"]
    entry["status"] = pod.get("status", "PROVISIONING")
    # Keep the larger rate if the service reports more than the manager's all-in quote.
    if pod.get("cost") is not None:
        entry["hourly_price_usd"] = str(max(money(entry["hourly_price_usd"]), money(pod["cost"])))
    save_ledger(handle, ledger)
    return pod


def update_pod(args, request: dict, handle, ledger: dict, key: str) -> dict:
    """Record lifecycle transitions only after confirming a non-running remote state.
    Why: accepting a stop request is not evidence that GPU billing has stopped.
    If wrong: the budget estimate would stop accumulating too early.
    """
    entry = find_pod(ledger, args.pod_id)
    if args.command == "status":
        try:
            pod = send(request, key)
        except RunPodHTTPError as error:
            # A 404 confirms removal only after this helper recorded a successful DELETE.
            if error.status_code != 404 or entry["terminated_at"] is None:
                raise
            pod = {"id": args.pod_id, "status": "TERMINATED", "status_http": 404}
    else:
        send(request, key)
        if args.command == "terminate":
            # A successful DELETE removes this exact pod; retain its spend record locally.
            entry["terminated_at"] = entry["terminated_at"] or utc_now()
            entry["status"] = "TERMINATED"
            save_ledger(handle, ledger)
            return {"id": entry["id"], "status": "TERMINATED"}
        pod = send(build_request("status", pod_id=args.pod_id), key)
    status = pod.get("status", "UNKNOWN")
    entry["status"] = status
    if status in {"STOPPED", "EXITED"}:
        entry["stopped_at"] = entry["stopped_at"] or utc_now()
    elif status == "TERMINATED":
        entry["terminated_at"] = entry["terminated_at"] or utc_now()
    elif status in {"RUNNING", "PROVISIONING"} and entry["stopped_at"]:
        raise ValueError("Pod restarted outside this helper; reconcile billing and ledger before continuing")
    save_ledger(handle, ledger)
    return pod


def main(argv: list[str] | None = None) -> None:
    """Run an explicit pod command or print its redacted offline dry run.
    Why: the manager must review preparation before authorising any paid action.
    If wrong: a diagnostic command could accidentally provision a GPU.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create", "status", "stop", "terminate"])
    parser.add_argument("--gpu", choices=list(GPU_TYPES))
    parser.add_argument("--pod-id")
    parser.add_argument("--hourly-price", help="Current quoted all-in running price, including disk and storage")
    parser.add_argument("--stopped-hourly-price", help="Current storage price while stopped")
    parser.add_argument("--price-source", help="Where and when the manager checked these prices")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--network-volume-id", help="An existing volume only; this helper never creates storage")
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--environment", action="append", default=[], choices=["HUGGINGFACE_TOKEN"],
                        help="Pass this variable from the environment or .env, always redacted")
    parser.add_argument("--public-key-file", type=Path, help="Inject this SSH public key without changing account keys")
    parser.add_argument("--startup-script", type=Path, help="Run this non-secret shell script as the container CMD")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.command != "create" and (args.environment or args.public_key_file or args.startup_script):
        parser.error("Environment, SSH key and startup options apply only to create")
    request = build_request(args.command, args.gpu, args.pod_id, args.image, args.network_volume_id)
    if args.command == "create":
        if args.hourly_price is None or args.stopped_hourly_price is None or not args.price_source:
            parser.error("create requires --hourly-price, --stopped-hourly-price and --price-source")
        money(args.stopped_hourly_price)
        if args.environment:
            request["body"]["env"] = {name: "[REDACTED]" for name in args.environment}
        if args.public_key_file:
            request["body"].setdefault("env", {})["PUBLIC_KEY"] = args.public_key_file.read_text(encoding="utf-8").strip()
        if args.startup_script:
            request["body"]["cmd"] = ["bash", "-c", args.startup_script.read_text(encoding="utf-8")]
    if args.dry_run:
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
        if args.command == "create":
            check_budget(ledger, args.hourly_price, utc_now())
        print(json.dumps(redacted_request(request), indent=2))
        return
    key = read_key(args.env_file)
    for name in args.environment:
        request["body"]["env"][name] = read_env_value(args.env_file, name)
    with locked_ledger(args.ledger) as (handle, ledger):
        if args.command == "create":
            pod = create_pod(args, request, handle, ledger, key)
        else:
            pod = update_pod(args, request, handle, ledger, key)
        # Only allowlisted fields reach stdout; the remote environment is never printed.
        print(json.dumps({"id": pod.get("id"), "status": pod.get("status"),
                          "ssh": pod.get("ssh"), "status_http": pod.get("status_http"),
                          "estimated_spend_usd": str(recorded_spend(ledger, utc_now()))}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except RunPodHTTPError as error:
        raise SystemExit(str(error)) from None
    except (ValueError, RuntimeError, OSError):
        # Suppress arbitrary file or API text, which might contain a credential value.
        raise SystemExit("RunPod helper refused or failed. Inspect the ledger and reconcile status before retrying.") from None
