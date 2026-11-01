"""Supervise one B pod through the shared helper and terminate on exit or budget expiry."""

import argparse
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

try:
    from scripts import runpod_pilot as pods
except ModuleNotFoundError:
    import runpod_pilot as pods


def budget_deadline(entry: dict, allowance: Decimal = Decimal("8")) -> datetime:
    """Derive this pod's eight-dollar deadline from the canonical ledger's live rate.
    Why: setup, review waits and archival time all consume the B allocation.
    If wrong: timing only training permits the two pods to exceed sixteen dollars.
    """
    rate = pods.money(entry["hourly_price_usd"])
    gpu = entry.get("actual_gpu_type") or entry.get("gpu")
    if gpu is None and entry.get("request", {}).get("gpuTypeIds") == ["NVIDIA H200"]:
        gpu = "NVIDIA H200"  # Provisioning can precede the service reporting its actual GPU field.
    if gpu not in {"H200", "NVIDIA H200"} or entry.get("cloud", "COMMUNITY") != "COMMUNITY" or rate <= 0:
        raise ValueError("B requires an H200 with a positive recorded running price")
    hours = allowance / rate
    if entry.get("max_hours") is not None:
        hours = min(hours, pods.positive(entry["max_hours"]))
    return pods.instant(entry["started_at"]) + timedelta(seconds=float(hours * Decimal(3600)))


def create_h200(args) -> None:
    """Restrict the shared allocator to the fixed H200 Community setting in this process.
    Why: the concurrent helper update permits other GPUs and Secure Cloud fallback.
    If wrong: B starts on an unplanned device or spends more than its eight-dollar share.
    """
    original = pods.read_catalog
    quoted_rate = None

    def restricted_catalog(gpu, cloud, key, hf_token=""):
        """Use the helper's live quote but reject every unplanned allocation choice.
        Why: a conservative budget quote does not authorise a different GPU or cloud.
        If wrong: capacity fallback changes the fixed B experiment without a decision.
        """
        if cloud != "COMMUNITY":
            return {"candidates": [], "quoted_hourly_price_usd": None}
        catalog = original(gpu, cloud, key, hf_token)
        catalog["candidates"] = [item for item in catalog["candidates"] if item["id"] == "NVIDIA H200"]
        rate = max((pods.money(item["hourly_price_usd"]) for item in catalog["candidates"]), default=Decimal(0))
        catalog["quoted_hourly_price_usd"] = str(rate + pods.money(catalog["disk_hourly_price_usd"])) if rate else None
        if quoted_rate is not None and rate and pods.money(catalog["quoted_hourly_price_usd"]) > quoted_rate:
            raise ValueError("H200 quote increased before create; re-quote without creating a pod")
        return catalog

    pods.read_catalog = restricted_catalog
    try:
        key = pods.read_key(args.env_file)
        quote = restricted_catalog("H200", "COMMUNITY", key)
        if not quote["candidates"]:
            raise ValueError("No H200 Community capacity; no create was sent")
        quoted_rate = pods.money(quote["quoted_hourly_price_usd"])
        # Round down so decimal conversion cannot reserve even a fraction above eight dollars.
        hours = (Decimal("8") / quoted_rate).quantize(Decimal("0.000000000001"), rounding="ROUND_FLOOR")
        command = ["create", "--gpu", "H200", "--label", args.label, "--max-hours", str(hours),
                   "--hourly-price", str(quoted_rate), "--price-source", quote["price_source"],
                   "--ledger", str(args.ledger), "--env-file", str(args.env_file),
                   "--environment", "HUGGINGFACE_TOKEN", "--public-key-file", str(args.public_key_file)]
        if args.startup_script:
            command.extend(["--startup-script", str(args.startup_script)])
        # All creation, credential redaction, budget reservation and ledger updates remain in the helper.
        pods.main(command)
    finally:
        pods.read_catalog = original


def terminate_and_confirm(pod_id: str, ledger: Path) -> None:
    """Terminate the exact pod and re-query it using only the shared RunPod helper.
    Why: stopping alone can leave storage billable, and an exit request is not confirmation.
    If wrong: the GPU or its storage can continue charging after the B job ends.
    """
    pods.main(["terminate", "--pod-id", pod_id, "--ledger", str(ledger)])
    pods.main(["status", "--pod-id", pod_id, "--ledger", str(ledger)])
    entry = pods.find_pod(json.loads(ledger.read_text(encoding="utf-8")), pod_id)
    if entry["status"] != "TERMINATED" or entry["terminated_at"] is None:
        raise RuntimeError("Pod termination is unconfirmed; reconcile this exact pod in the manager")


def supervise(args) -> int:
    """Run a manager-supplied SSH command, archive its outputs, and enforce the pod deadline.
    Why: a timeout inside a container does not terminate a chargeable RunPod instance.
    If wrong: a stalled data stream, judge wait or failed remote command leaves an idle GPU.
    """
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    entry = pods.find_pod(ledger, args.pod_id)
    if entry["terminated_at"] is not None or entry["stopped_at"] is not None:
        raise ValueError("Supervision needs an active pod, not a terminated or stopped entry")
    deadline = budget_deadline(entry)
    print(f"B_BUDGET_DEADLINE {deadline.isoformat()} pod={args.pod_id}", flush=True)
    process = None
    status = 1
    try:
        commands = json.loads(args.archive_commands_json)
        if not commands or any(not isinstance(command, list) or not command for command in commands):
            raise ValueError("At least one explicit archive argv list is required")
        if not args.job:
            raise ValueError("Pass the exact SSH job argv after --")
        job = args.job[1:] if args.job[0] == "--" else args.job
        seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
        if seconds <= args.archive_reserve_seconds:
            raise TimeoutError("Not enough pod budget remains to run and archive")
        process = subprocess.Popen(job)
        while process.poll() is None:
            seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
            if seconds <= args.archive_reserve_seconds:
                # Kill only the local SSH process. The pod is terminated by the helper below.
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            time.sleep(1)
        status = process.wait()
        # Archive partial artifacts even after a failed GPU run. Never retry a failed experiment here.
        for command in commands:
            seconds = (deadline - datetime.now(timezone.utc)).total_seconds()
            if seconds <= 0:
                raise TimeoutError("Archive deadline reached")
            result = subprocess.run(command, timeout=seconds, check=False)
            if result.returncode:
                raise RuntimeError("An archive command failed; preserve any recovered files")
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
        terminate_and_confirm(args.pod_id, args.ledger)
    return status


def main() -> None:
    """Accept argv lists rather than interpolating remote shell commands or secrets.
    Why: the B-RUN manager supplies SSH and archive destinations after pod creation.
    If wrong: shell expansion can alter paths or expose credentials in a command log.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Paid B-RUN action only, never used by B-CODE")
    create.add_argument("--label", required=True, choices=["b-alpha03", "b-alpha06"])
    create.add_argument("--ledger", type=Path, default=pods.LEDGER)
    create.add_argument("--env-file", type=Path, default=pods.ROOT / ".env")
    create.add_argument("--public-key-file", type=Path, required=True)
    create.add_argument("--startup-script", type=Path)
    watch = commands.add_parser("watch")
    watch.add_argument("--pod-id", required=True)
    watch.add_argument("--ledger", type=Path, default=pods.LEDGER)
    watch.add_argument("--archive-reserve-seconds", type=int, default=300)
    watch.add_argument("--archive-commands-json", required=True, help="JSON array of argv arrays, small artifacts first, full weights outside Git")
    watch.add_argument("job", nargs=argparse.REMAINDER)
    deadline = commands.add_parser("deadline")
    deadline.add_argument("--pod-id", required=True)
    deadline.add_argument("--ledger", type=Path, default=pods.LEDGER)
    args = parser.parse_args()
    try:
        if args.command == "create":
            create_h200(args)
            return
        if args.command == "deadline":
            entry = pods.find_pod(json.loads(args.ledger.read_text(encoding="utf-8")), args.pod_id)
            print(budget_deadline(entry).isoformat())
            return
        code = supervise(args)
    except ValueError as error:
        # Only these helper-authored messages are safe and useful for create admission decisions.
        message = str(error)
        safe_prefixes = ("Budget refusal:", "No H200 Community capacity;", "H200 quote increased before create;",
                         "One pod at a time;", "No eligible GPU capacity in COMMUNITY or SECURE;")
        if message.startswith(safe_prefixes):
            raise SystemExit(message) from None
        raise SystemExit("B supervision refused invalid inputs; inspect the exact ledger entry and argv") from None
    except Exception as error:
        # Arbitrary SSH or HTTP exception text may contain secrets. The type is sufficient for handoff.
        raise SystemExit(f"B supervision failed with {type(error).__name__}; inspect ledger and archive destinations") from None
    raise SystemExit(code)


if __name__ == "__main__":
    main()
