"""Launch parallel pilot jobs with live RunPod quotes and a locked budget (LIMIT below)."""

import argparse
import json
import math
import os
import re
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "derisk/erasure_pilot_v1/spend_ledger.json"
API = "https://rest.runpod.io/v1"
CATALOG = "https://api.runpod.io/v2/catalog/gpus?include=AVAILABILITY&product=POD&cloud="
USER_AGENT = "erasure-pilot/1"
IMAGE = "runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404"
# Raised from 38.00 on 2026-11-03 to the real RunPod credit: docs/DECISIONS.md, "the manager decides alone".
LIMIT = Decimal("49.54")
# RunPod container storage is $0.10/GB/month. Use 30 days per month for the quote.
DISK_HOURLY_PER_GB = Decimal("0.10") / Decimal(720)
DISK_SOURCE = "https://docs.runpod.io/pods/pricing at $0.10/GB/month, 720 hours/month"
GPU_CLASSES = {
    "mid": {
        "max_price": "2.60", "disk_gb": 80,
        "COMMUNITY": [
            "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition",
            "NVIDIA L40S", "NVIDIA RTX 6000 Ada Generation", "NVIDIA A100 80GB PCIe",
            "NVIDIA A100-SXM4-80GB", "NVIDIA RTX PRO 6000 Blackwell Server Edition",
            "NVIDIA RTX 5000 Ada Generation",
        ],
        "SECURE": ["NVIDIA L40S", "NVIDIA RTX PRO 6000 Blackwell Server Edition",
                   "NVIDIA A100-SXM4-80GB", "NVIDIA A100 80GB PCIe"],
    },
    # The "mid" cards with at least 80 GB, for full-parameter relearning on a 4B model (A5, 2026-11-03).
    "mid80": {
        "max_price": "2.60", "disk_gb": 80,
        "COMMUNITY": [
            "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition",
            "NVIDIA A100 80GB PCIe", "NVIDIA A100-SXM4-80GB",
            "NVIDIA RTX PRO 6000 Blackwell Server Edition",
        ],
        "SECURE": ["NVIDIA RTX PRO 6000 Blackwell Server Edition",
                   "NVIDIA A100-SXM4-80GB", "NVIDIA A100 80GB PCIe"],
    },
    "big": {
        "max_price": "5.50", "disk_gb": 150,
        "COMMUNITY": [
            "NVIDIA H200", "NVIDIA H200 NVL",
            "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
            "NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition",
            "NVIDIA RTX PRO 6000 Blackwell Server Edition",
        ],
        "SECURE": ["NVIDIA H200", "NVIDIA RTX PRO 6000 Blackwell Server Edition", "NVIDIA H100 NVL"],
    },
}
GPU_ALIASES = {"L40S": "mid", "H200": "big"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Ledger timestamps require an explicit timezone")
    return result


def money(value: str | int | float) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Prices, spend and hours must be numeric") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("Prices and spend must be finite and nonnegative")
    return amount


def positive(value: str | int | float) -> Decimal:
    amount = money(value)
    if amount == 0:
        raise ValueError("Hourly prices and maximum hours must be positive")
    return amount


def gpu_class(gpu: str) -> str:
    result = GPU_ALIASES.get(gpu, gpu)
    if result not in GPU_CLASSES:
        raise ValueError("Choose mid or big, or the L40S and H200 aliases")
    return result


def elapsed_hours(start: str, end: str) -> Decimal:
    seconds = (instant(end) - instant(start)).total_seconds()
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Ledger timestamps run backwards")
    return Decimal(str(seconds)) / Decimal(3600)


def pod_spend(pod: dict, now: str) -> Decimal:
    """Count elapsed GPU and storage charges without discarding prior spend.
    Why: old ledger entries and stopped storage still consume the same pilot budget.
    If wrong: a lifecycle change could make previously spent money available again.
    """
    if pod.get("status") == "CREATE_FAILED_NO_POD":
        # Only explicit no-resource evidence releases an uncertain reservation.
        if pod.get("id") is not None or not pod.get("reconciled_at") or not pod.get("reconciliation"):
            raise ValueError("Failed create requires no pod ID and explicit reconciliation evidence")
        return Decimal(0)
    end = pod.get("stopped_at") or pod.get("terminated_at") or now
    total = elapsed_hours(pod["started_at"], end) * money(pod["hourly_price_usd"])
    if pod.get("stopped_at"):
        end = pod.get("terminated_at") or now
        total += elapsed_hours(pod["stopped_at"], end) * money(pod["stopped_hourly_price_usd"])
    return max(total, money(pod.get("recorded_spend_usd", "0")))


def recorded_spend(ledger: dict, now: str) -> Decimal:
    return money(ledger["other_spend_usd"]) + sum((pod_spend(pod, now) for pod in ledger["pods"]), Decimal(0))


def committed_spend(ledger: dict, now: str) -> Decimal:
    """Reserve the full time allowance for every running or uncertain job.
    Why: concurrent jobs may all run to their declared maximum at the same time.
    If wrong: separate creates could each spend the same remaining budget.
    """
    total = money(ledger["other_spend_usd"])
    for pod in ledger["pods"]:
        spend = pod_spend(pod, now)
        if pod.get("status") != "CREATE_FAILED_NO_POD" and not pod.get("stopped_at") and not pod.get("terminated_at"):
            # Legacy active entries without a time ceiling reserve the entire budget until reconciled.
            reserve = LIMIT if pod.get("max_hours") is None else money(pod["hourly_price_usd"]) * positive(pod["max_hours"])
            spend = max(spend, reserve)
        total += spend
    return total


def check_budget(ledger: dict, hourly_price: str, now: str, max_hours: str) -> Decimal:
    """Refuse commitments above the frozen LIMIT spending limit.
    Why: each create reserves its worst quoted hourly price for its whole allowance.
    If wrong: several valid individual quotes could overcommit the pilot budget.
    """
    if money(ledger["limit_usd"]) != LIMIT:
        raise ValueError(f"The pilot ledger limit must remain {LIMIT} USD")
    reserve = positive(hourly_price) * positive(max_hours)
    total = committed_spend(ledger, now)
    if total + reserve > LIMIT:
        raise ValueError(f"Budget refusal: {total:.4f} USD committed plus {reserve:.4f} USD exceeds {LIMIT} USD")
    return total


def build_request(command: str, gpu: str | None = None, pod_id: str | None = None,
                  image: str = IMAGE, network_volume: str | None = None, *,
                  label: str | None = None, cloud: str = "COMMUNITY", gpu_type_ids: list[str] | None = None) -> dict:
    """Build a REST v1 request without reading secrets or sending HTTP.
    Why: an offline request review must never provision a pod.
    If wrong: a diagnostic command could charge the account or reveal credentials.
    """
    request = {"method": "GET", "url": API + "/pods", "headers": {
        "Authorization": "Bearer [REDACTED]", "Content-Type": "application/json",
        "User-Agent": USER_AGENT}, "body": None}
    if command == "create":
        selected = gpu_class(gpu)
        if not label or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", label):
            raise ValueError("create requires a simple job label")
        if cloud not in {"COMMUNITY", "SECURE"}:
            raise ValueError("Choose COMMUNITY or SECURE")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        request["method"] = "POST"
        request["body"] = {
            "name": f"erasure-pilot-v1-{label}-{timestamp}-{uuid4().hex[:8]}",
            "computeType": "GPU", "cloudType": cloud,
            "gpuTypeIds": list(gpu_type_ids if gpu_type_ids is not None else GPU_CLASSES[selected][cloud]),
            "gpuTypePriority": "custom", "gpuCount": 1, "imageName": image,
            "containerDiskInGb": GPU_CLASSES[selected]["disk_gb"], "ports": ["22/tcp"], "env": {},
        }
        if network_volume:
            request["body"]["networkVolumeId"] = network_volume
    elif command in {"status", "stop", "terminate"}:
        if not pod_id or not re.fullmatch(r"[A-Za-z0-9_-]+", pod_id):
            raise ValueError("A simple exact pod ID is required")
        request["url"] += "/" + quote(pod_id, safe="")
        if command == "stop":
            request.update(method="POST", url=request["url"] + "/stop")
        elif command == "terminate":
            request["method"] = "DELETE"
    elif command not in {"list", "reconcile", "catalog"}:
        raise ValueError("Unknown pod command")
    return request


def read_env_value(env_file: Path, variable: str) -> str:
    """Read one variable with environment precedence and no echo.
    Why: gated-model tokens and API keys must stay out of logs and the ledger.
    If wrong: credentials could enter git through an otherwise harmless record.
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


def sanitise(text: str, *secrets: str) -> str:
    # Replace before truncation so a boundary cannot expose part of a secret.
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


class RunPodHTTPError(RuntimeError):
    """Retain the status and sanitised RunPod error text for ledger diagnosis."""

    def __init__(self, status_code: int, error_text: str = ""):
        self.status_code = status_code
        self.error_text = error_text
        super().__init__(f"RunPod HTTP {status_code}: {error_text}")


def redacted_request(request: dict) -> dict:
    result = json.loads(json.dumps(request))
    result["headers"]["Authorization"] = "Bearer [REDACTED]"
    if result.get("body") and "env" in result["body"]:
        result["body"]["env"] = {name: "[REDACTED]" for name in result["body"]["env"]}
    return result


def send(request: dict, key: str, hf_token: str = ""):
    """Send once with a custom User-Agent and sanitise HTTP errors before raising.
    Why: ambiguous creates must not retry and RunPod may echo submitted secrets.
    If wrong: automatic retries could duplicate pods or error text could leak tokens.
    """
    headers = dict(request["headers"])
    headers.update(Authorization="Bearer " + key, **{"User-Agent": USER_AGENT})
    body = json.dumps(request["body"]).encode("utf-8") if request["body"] is not None else None
    http = urllib.request.Request(request["url"], data=body, headers=headers, method=request["method"])
    request_token = (request.get("body") or {}).get("env", {}).get("HUGGINGFACE_TOKEN", "")
    try:
        with urllib.request.urlopen(http, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        # The service can echo either credential even for list or catalog requests.
        try:
            text = error.read().decode("utf-8", errors="replace")
        except OSError:
            # Preserve the HTTP diagnosis if the error body itself cannot be read.
            text = "RunPod error body could not be read"
        finally:
            error.close()
        text = sanitise(text, key, hf_token, request_token, os.environ.get("HUGGINGFACE_TOKEN", ""))[:300]
        raise RunPodHTTPError(error.code, text) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("RunPod transport failure; reconcile status before any retry") from None
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, UnicodeDecodeError):
        raise RuntimeError("RunPod returned invalid JSON; reconcile status before any retry") from None


def read_catalog(gpu: str, cloud: str, key: str, hf_token: str = "") -> dict:
    """Filter a live cloud catalog in the frozen GPU preference order.
    Why: availability and cloud prices change between jobs.
    If wrong: a create could request unavailable GPUs or underquote its reservation.
    """
    selected = gpu_class(gpu)
    if cloud not in {"COMMUNITY", "SECURE"}:
        raise ValueError("Choose COMMUNITY or SECURE")
    request = build_request("catalog")
    request["url"] = CATALOG + cloud
    catalog = send(request, key, hf_token)
    by_id = {item["id"]: item for item in catalog["gpus"]}
    candidates = []
    for candidate in GPU_CLASSES[selected][cloud]:
        item = by_id.get(candidate)
        if item is None or item.get("availability", "NONE") == "NONE":
            continue
        price = item.get("price", {}).get(cloud.lower())
        # Missing and zero prices cannot support a conservative budget quote.
        if price is None or money(price) == 0 or money(price) > money(GPU_CLASSES[selected]["max_price"]):
            continue
        candidates.append({"id": candidate, "availability": item["availability"], "hourly_price_usd": str(money(price))})
    snapshot = utc_now()
    disk = DISK_HOURLY_PER_GB * GPU_CLASSES[selected]["disk_gb"]
    price = max((money(item["hourly_price_usd"]) for item in candidates), default=Decimal(0)) + disk
    return {"gpu_class": selected, "cloud": cloud, "candidates": candidates, "snapshot_at": snapshot,
            "source": request["url"], "price_source": f"{request['url']} checked {snapshot}; container disk {DISK_SOURCE}",
            "disk_hourly_price_usd": str(disk), "quoted_hourly_price_usd": str(price) if candidates else None}


@contextmanager
def locked_ledger(path: Path):
    """Lock the existing ledger across its read, HTTP requests and update.
    Why: separate create processes must not both pass the same budget check.
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


def pod_state(pod: dict) -> str:
    return pod.get("desiredStatus") or pod.get("status") or "UNKNOWN"


def actual_gpu(pod: dict):
    gpu = pod.get("gpu") or {}
    machine = pod.get("machine") or {}
    return pod.get("gpuTypeId") or gpu.get("id") or machine.get("gpuTypeId") or machine.get("gpuDisplayName")


def actual_price(pod: dict):
    for field in ("costPerHr", "adjustedCostPerHr", "cost"):
        if pod.get(field) is not None:
            return money(pod[field])
    return None


def record_actual(entry: dict, pod: dict) -> None:
    """Keep actual allocation details while retaining any higher reserved price.
    Why: the allocator can choose any candidate and return a changed rate.
    If wrong: a cheap quote could hide a more expensive running pod.
    """
    entry["id"] = pod["id"]
    entry["status"] = pod_state(pod)
    gpu = actual_gpu(pod)
    if gpu is not None:
        entry["actual_gpu_type"] = gpu
    entry["cloud"] = pod.get("cloudType") or entry.get("cloud")
    if not pod.get("cloudType") and (pod.get("machine") or {}).get("secureCloud") is not None:
        entry["cloud"] = "SECURE" if pod["machine"]["secureCloud"] else "COMMUNITY"
    price = actual_price(pod)
    if price is not None:
        entry["actual_hourly_price_usd"] = str(price)
        entry["hourly_price_usd"] = str(max(money(entry["hourly_price_usd"]), price))


def record_http_error(entry: dict, error: RunPodHTTPError, request: dict, key: str, hf_token: str) -> RunPodHTTPError:
    """Save and return the same secret-free HTTP diagnosis.
    Why: fallback and later reconciliation need the original RunPod reason.
    If wrong: an error can either hide the failure or put credentials in the ledger.
    """
    text = sanitise(error.error_text, key, hf_token)[:300]
    entry.setdefault("http_errors", []).append({"status_code": error.status_code, "error_text": text,
                                              "at": utc_now(), "method": request["method"], "url": request["url"]})
    if request["method"] == "POST" and request["url"].endswith("/pods"):
        entry["create_http_status"] = error.status_code
    return RunPodHTTPError(error.status_code, text)


def capacity_error(error: RunPodHTTPError) -> bool:
    text = error.error_text.lower()
    explicit = any(word in text for word in ("capacity", "no available", "insufficient resources", "no instances"))
    gpu_unavailable = "gpu" in text and any(word in text for word in ("unavailable", "not available"))
    return error.status_code in {400, 409, 503} and (explicit or gpu_unavailable)


def create_pod(args, request: dict, handle, ledger: dict, key: str, hf_token: str = "") -> dict:
    """Reserve the live quote before creating, with one capacity fallback to Secure.
    Why: concurrent jobs need independent reservations and uncertain requests need evidence.
    If wrong: a fallback could duplicate a pod or several jobs could overcommit the LIMIT.
    """
    selected = gpu_class(args.gpu)
    positive(args.max_hours)
    hf_token = hf_token or request["body"].get("env", {}).get("HUGGINGFACE_TOKEN", "")
    if not args.label or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.label):
        raise ValueError("create requires a simple job label")
    entry = None
    for cloud in ("COMMUNITY", "SECURE"):
        try:
            catalog = read_catalog(selected, cloud, key, hf_token)
        except RunPodHTTPError as error:
            if entry is None:
                # A catalog error occurred before any POST, so there is no possible pod.
                entry = {"id": None, "name": request["body"]["name"], "status": "CREATE_FAILED_NO_POD",
                         "reconciled_at": utc_now(), "reconciliation": "Catalog GET failed before any create POST"}
                ledger["pods"].append(entry)
            failed_request = build_request("catalog")
            failed_request["url"] = CATALOG + cloud
            safe = record_http_error(entry, error, failed_request, key, hf_token)
            save_ledger(handle, ledger)
            raise safe from None
        if not catalog["candidates"]:
            continue
        price = money(catalog["quoted_hourly_price_usd"])
        if args.hourly_price is not None:
            # A manual quote can only increase the live catalog reservation.
            price = max(price, positive(args.hourly_price))
        others = dict(ledger, pods=[pod for pod in ledger["pods"] if pod is not entry])
        check_budget(others, str(price), utc_now(), args.max_hours)
        request["body"].update(cloudType=cloud, gpuTypeIds=[item["id"] for item in catalog["candidates"]])
        if entry is None:
            entry = {"id": None, "label": args.label, "name": request["body"]["name"], "gpu_class": selected,
                     "started_at": utc_now(), "stopped_at": None, "terminated_at": None,
                     "max_hours": str(positive(args.max_hours)),
                     "stopped_hourly_price_usd": str(money(args.stopped_hourly_price)), "status": "CREATE_UNCERTAIN"}
            ledger["pods"].append(entry)
        entry.update(hourly_price_usd=str(price), quoted_hourly_price_usd=str(price), cloud=cloud,
                     price_source=catalog["price_source"], catalog_snapshot_at=catalog["snapshot_at"],
                     catalog=catalog, request=json.loads(sanitise(json.dumps(redacted_request(request)["body"]), key, hf_token)))
        save_ledger(handle, ledger)
        try:
            pod = send(request, key, hf_token)
        except RunPodHTTPError as error:
            safe = record_http_error(entry, error, request, key, hf_token)
            save_ledger(handle, ledger)
            if cloud == "COMMUNITY" and capacity_error(safe):
                print(str(safe))
                continue
            raise safe from None
        if not isinstance(pod, dict) or not pod.get("id"):
            raise RuntimeError("Create response has no pod ID; reconcile the pending ledger entry")
        record_actual(entry, pod)
        save_ledger(handle, ledger)
        return pod
    raise ValueError("No eligible GPU capacity in COMMUNITY or SECURE; inspect the ledger before retrying")


def update_pod(args, request: dict, handle, ledger: dict, key: str, hf_token: str = "") -> dict:
    """Record billing transitions only after confirming the remote state.
    Why: acceptance of a stop request does not mean GPU billing has stopped.
    If wrong: the ledger could release an active job's reserved budget too early.
    """
    entry = find_pod(ledger, args.pod_id)
    try:
        pod = send(request, key, hf_token)
        if args.command == "terminate":
            entry["terminated_at"] = entry.get("terminated_at") or utc_now()
            entry["status"] = "TERMINATED"
            entry["recorded_spend_usd"] = str(pod_spend(entry, utc_now()))
            save_ledger(handle, ledger)
            return {"id": entry["id"], "desiredStatus": "TERMINATED"}
        if args.command == "stop":
            request = build_request("status", pod_id=args.pod_id)
            pod = send(request, key, hf_token)
    except RunPodHTTPError as error:
        safe = record_http_error(entry, error, request, key, hf_token)
        save_ledger(handle, ledger)
        # A 404 confirms removal only after a successful DELETE was recorded locally.
        if args.command != "status" or error.status_code != 404 or not entry.get("terminated_at"):
            raise safe from None
        pod = {"id": args.pod_id, "desiredStatus": "TERMINATED", "status_http": 404}
    status = pod_state(pod)
    entry["status"] = status
    if status in {"STOPPED", "EXITED"}:
        entry["stopped_at"] = entry.get("stopped_at") or utc_now()
    elif status == "TERMINATED":
        entry["terminated_at"] = entry.get("terminated_at") or utc_now()
    elif status in {"RUNNING", "PROVISIONING"} and entry.get("stopped_at"):
        raise ValueError("Pod restarted outside this helper; reconcile billing before continuing")
    if entry.get("hourly_price_usd"):
        record_actual(entry, pod)
        entry["recorded_spend_usd"] = str(pod_spend(entry, utc_now()))
    save_ledger(handle, ledger)
    return pod


def pod_list(response) -> list[dict]:
    if isinstance(response, list):
        return response
    # Accept the wrapper used by some versions, but never infer absence from an unknown shape.
    if isinstance(response, dict) and isinstance(response.get("pods"), list):
        return response["pods"]
    raise ValueError("Unexpected pod list response; no reconciliation performed")


def reconcile_pod(name: str, handle, ledger: dict, key: str, hf_token: str = "") -> dict:
    """Resolve one uncertain create by its exact unique name using a complete list.
    Why: a lost create response may still have provisioned a paid resource.
    If wrong: the ledger could release the budget while a pod is running.
    """
    entries = [entry for entry in ledger["pods"] if entry.get("id") is None
               and (entry.get("name") or entry.get("request", {}).get("name")) == name
               and entry.get("status") == "CREATE_UNCERTAIN"]
    if len(entries) != 1:
        raise ValueError("The exact name must identify one uncertain ledger entry")
    entry = entries[0]
    request = build_request("list")
    try:
        pods = pod_list(send(request, key, hf_token))
    except RunPodHTTPError as error:
        safe = record_http_error(entry, error, request, key, hf_token)
        save_ledger(handle, ledger)
        raise safe from None
    matches = [pod for pod in pods if pod.get("name") == name]
    if len(matches) > 1:
        raise ValueError("Multiple pods share this name; no reconciliation performed")
    if matches and not matches[0].get("id"):
        raise ValueError("Matched pod has no ID; no reconciliation performed")
    entry["reconciled_at"] = utc_now()
    entry["reconciliation"] = {"method": "GET", "url": request["url"], "name": name,
                               "matching_ids": [pod["id"] for pod in matches], "pods_examined": len(pods)}
    if matches:
        record_actual(entry, matches[0])
        if pod_state(matches[0]) in {"STOPPED", "EXITED"}:
            entry["stopped_at"] = entry.get("stopped_at") or utc_now()
        elif pod_state(matches[0]) == "TERMINATED":
            entry["terminated_at"] = entry.get("terminated_at") or utc_now()
    else:
        entry["status"] = "CREATE_FAILED_NO_POD"
    save_ledger(handle, ledger)
    return {"id": entry.get("id"), "name": name, "desiredStatus": entry["status"]}


def list_summary(pod: dict) -> dict:
    price = actual_price(pod)
    return {"id": pod.get("id"), "name": pod.get("name"), "desiredStatus": pod_state(pod),
            "gpu": actual_gpu(pod), "costPerHr": str(price) if price is not None else None}


def main(argv: list[str] | None = None) -> None:
    """Run a pod action, an offline request review, or a read-only catalog query.
    Why: paid creates require a label and an explicit maximum-hours reservation.
    If wrong: an inspection command could provision a GPU or underreserve spend.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create", "list", "catalog", "reconcile", "status", "stop", "terminate"])
    parser.add_argument("--gpu", choices=[*GPU_CLASSES, *GPU_ALIASES])
    parser.add_argument("--label")
    parser.add_argument("--max-hours")
    parser.add_argument("--name", help="Exact uncertain pod name to reconcile")
    parser.add_argument("--pod-id")
    parser.add_argument("--hourly-price", help="Optional all-in quote floor, can only raise the live quote")
    parser.add_argument("--stopped-hourly-price", default="0", help="Storage rate while stopped, container disk alone costs zero")
    parser.add_argument("--price-source", help="Legacy option, live catalog always supplies the price source")
    parser.add_argument("--image", default=IMAGE)
    parser.add_argument("--network-volume-id", help="An existing volume only; include its extra costs in manual quote floors")
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--environment", action="append", default=[], choices=["HUGGINGFACE_TOKEN"])
    parser.add_argument("--public-key-file", type=Path, help="PUBLIC_KEY consumed by the official image's /start.sh")
    parser.add_argument("--startup-script", type=Path, help="Non-secret shell script, passed as dockerStartCmd")
    parser.add_argument("--dry-run", action="store_true", help="Offline shape preview, no live quote or budget approval")
    args = parser.parse_args(argv)
    if args.command != "create" and (args.environment or args.public_key_file or args.startup_script):
        parser.error("Environment, SSH key and startup options apply only to create")
    if args.command == "create":
        if not args.gpu or not args.label or args.max_hours is None:
            parser.error("create requires --gpu, --label and --max-hours")
        positive(args.max_hours)
        money(args.stopped_hourly_price)
        if args.hourly_price is not None:
            positive(args.hourly_price)
    if args.command == "catalog" and not args.gpu:
        parser.error("catalog requires --gpu mid or big")
    if args.command == "reconcile" and not args.name:
        parser.error("reconcile requires --name matching the uncertain ledger entry")
    request = build_request(args.command, args.gpu, args.pod_id, args.image, args.network_volume_id, label=args.label)
    if args.command == "create":
        request["body"]["env"] = {name: "[REDACTED]" for name in args.environment}
        if args.public_key_file:
            request["body"]["env"]["PUBLIC_KEY"] = args.public_key_file.read_text(encoding="utf-8").strip()
        if args.startup_script:
            request["body"]["dockerStartCmd"] = ["bash", "-c", args.startup_script.read_text(encoding="utf-8")]
    if args.dry_run:
        print(json.dumps(redacted_request(request), indent=2))
        return
    key = read_key(args.env_file)
    try:
        hf_token = read_env_value(args.env_file, "HUGGINGFACE_TOKEN")
    except ValueError:
        # Read-only commands and ungated jobs do not require a Hugging Face token.
        hf_token = ""
    if args.command == "list":
        print(json.dumps([list_summary(pod) for pod in pod_list(send(request, key, hf_token))], indent=2))
        return
    if args.command == "catalog":
        print(json.dumps([read_catalog(args.gpu, cloud, key, hf_token) for cloud in ("COMMUNITY", "SECURE")], indent=2))
        return
    for name in args.environment:
        request["body"]["env"][name] = read_env_value(args.env_file, name)
    with locked_ledger(args.ledger) as (handle, ledger):
        if args.command == "create":
            pod = create_pod(args, request, handle, ledger, key, hf_token)
        elif args.command == "reconcile":
            pod = reconcile_pod(args.name, handle, ledger, key, hf_token)
        else:
            pod = update_pod(args, request, handle, ledger, key, hf_token)
        # The remote environment and startup command must never reach stdout.
        output = list_summary(pod)
        output.update(estimated_spend_usd=str(recorded_spend(ledger, utc_now())),
                      committed_spend_usd=str(committed_spend(ledger, utc_now())))
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    try:
        main()
    except RunPodHTTPError as error:
        raise SystemExit(str(error)) from None
    except (ValueError, RuntimeError, OSError) as error:
        # Only helper-authored errors reach stdout; arbitrary OS text can contain secrets.
        if isinstance(error, ValueError):
            raise SystemExit(str(error)) from None
        raise SystemExit("RunPod helper failed. Inspect the ledger and reconcile status before retrying.") from None
