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


def budget_deadline(entry: dict, allowance: Decimal = Decimal("7")) -> datetime:
    """Derive this pod's seven-dollar deadline from the canonical ledger's live rate.
    Why: setup, review waits and archival time all consume the B allocation.
    If wrong: timing only training permits the two pods to exceed fourteen dollars.
    """
    rate = pods.money(entry["hourly_price_usd"])
    gpu = entry.get("actual_gpu_type") or entry.get("gpu")
    requested = entry.get("request", {}).get("gpuTypeIds", [])
    allowed = set(pods.GPU_CLASSES["big"]["COMMUNITY"] + pods.GPU_CLASSES["big"]["SECURE"]) - {"NVIDIA H100 NVL"}
    allowed.add("H200")
    if (gpu is not None and gpu not in allowed) or (gpu is None and (not requested or not set(requested) <= allowed)) or rate <= 0:
        raise ValueError("B requires a supported big-class GPU and a positive recorded running price")
    hours = allowance / rate
    if entry.get("max_hours") is not None:
        hours = min(hours, pods.positive(entry["max_hours"]))
    return pods.instant(entry["started_at"]) + timedelta(seconds=float(hours * Decimal(3600)))


def create_h200(args) -> None:
    """Use the shared big allocator with seven dollars and a matching container timeout.
    Why: the relaunch accepts H200 and 96 GB Blackwell GPUs on either cloud.
    If wrong: a Secure fallback can inherit a cheap quote's excessive runtime.
    """
    original = pods.read_catalog
    original_create = pods.create_pod
    active = {}
    allowance = Decimal(str(getattr(args, "budget_usd", "7")))
    if not 0 < allowance <= 7:
        raise ValueError("B allowance must be positive and no more than seven dollars")

    def restricted_catalog(gpu, cloud, key, hf_token=""):
        """Recompute the runtime before each cloud's reservation and create request.
        Why: the helper can fall back to a more expensive cloud in the same call.
        If wrong: fallback exceeds seven dollars before the watchdog fires.
        """
        catalog = original(gpu, cloud, key, hf_token)
        catalog["candidates"] = [item for item in catalog["candidates"] if item["id"] != "NVIDIA H100 NVL"]
        rate = max((pods.money(item["hourly_price_usd"]) for item in catalog["candidates"]), default=Decimal(0))
        catalog["quoted_hourly_price_usd"] = str(rate + pods.money(catalog["disk_hourly_price_usd"])) if rate else None
        if rate and active:
            hours = (allowance / pods.money(catalog["quoted_hourly_price_usd"])).quantize(Decimal("0.000000000001"), rounding="ROUND_FLOOR")
            active["args"].max_hours = str(hours)
            # The helper reserves this duration before POST. PID 1 exits at the same ceiling.
            seconds = int(hours * 3600)
            startup = args.startup_script.read_text(encoding="utf-8").replace("B_POD_SECONDS", str(seconds))
            active["request"]["body"]["dockerStartCmd"] = ["bash", "-c", startup]
        return catalog

    def timed_create(parsed, request, handle, ledger, key, hf_token=""):
        active.update(args=parsed, request=request)
        return original_create(parsed, request, handle, ledger, key, hf_token)

    pods.read_catalog = restricted_catalog
    pods.create_pod = timed_create
    try:
        if args.startup_script is None:
            raise ValueError("B creation requires its timed startup script")
        command = ["create", "--gpu", "big", "--label", args.label, "--max-hours", "1",
                   "--ledger", str(args.ledger), "--env-file", str(args.env_file),
                   "--environment", "HUGGINGFACE_TOKEN", "--public-key-file", str(args.public_key_file)]
        if args.startup_script:
            command.extend(["--startup-script", str(args.startup_script)])
        # All creation, credential redaction, budget reservation and ledger updates remain in the helper.
        pods.main(command)
    finally:
        pods.read_catalog = original
        pods.create_pod = original_create


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
    create.add_argument("--label", required=True, choices=["B03", "B06"])
    create.add_argument("--ledger", type=Path, default=pods.LEDGER)
    create.add_argument("--env-file", type=Path, default=pods.ROOT / ".env")
    create.add_argument("--public-key-file", type=Path, required=True)
    create.add_argument("--startup-script", type=Path)
    create.add_argument("--budget-usd", default="7", help="Remaining allowance after any terminated startup allocation")
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
    except pods.RunPodHTTPError as error:
        # The shared helper sanitises this API error. Preserve its diagnosis for reconciliation.
        raise SystemExit(str(error)) from None
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
