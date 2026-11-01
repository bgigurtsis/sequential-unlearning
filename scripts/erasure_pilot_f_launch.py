"""Package F's allowed files and enforce its timeout through the shared pod helper."""

import argparse
import json
import math
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "derisk/erasure_pilot_v1/approach_f"
KEYS = ROOT / ".tmp/erasure_pilot_f"
HELPER = ROOT / "scripts/runpod_pilot.py"


def make_bundle(destination: Path | None = None) -> Path:
    """Copy only the needed source and unsealed input files into the pod archive.
    Why: other workers' edits, credentials and sealed text must stay out of F's transfer.
    If wrong: the pod could receive unrelated work or consume the manager's final set.
    """
    files = list((ROOT / "scripts").glob("erasure_pilot_f_*.py"))
    files.extend([ROOT / "scripts/erasure_pilot_eval.py", ROOT / "scripts/build_erasure_tokenisations.py",
                  ROOT / "scripts/runpod_pilot.py",
                  ROOT / "config/biography_pilot_v1/execution_v1/cosine_v2_freeze.json"])
    for name in ["manifest.json", "rubric.md", "development.json", "nearby.json", "distant.json", "alternate_tokenisations.json"]:
        files.append(ROOT / "config/erasure_pilot_v1" / name)
    files.extend((ROOT / "config/erasure_pilot_v1/approach_f").glob("*.json"))
    OUT.mkdir(parents=True, exist_ok=True)
    destination = destination or OUT / "source_bundle.tar.gz"
    with tarfile.open(destination, "x:gz") as archive:
        for path in sorted(files):
            archive.add(path, arcname=path.relative_to(ROOT), recursive=False)
    return destination


def helper_action(action: str, pod_id: str, ledger_path: Path) -> int:
    """Run one lifecycle action only through the shared ledger-aware helper.
    Why: the timeout guard must preserve the manager's complete spend record.
    If wrong: a stopped or terminated pod could disappear from budget accounting.
    """
    result = subprocess.run([sys.executable, "-B", str(HELPER), action, "--pod-id", pod_id,
                             "--ledger", str(ledger_path)],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout, flush=True)
    return result.returncode


def guard(pod_id: str, ledger_path: Path) -> None:
    """Stop and terminate the exact F pod at its ledger deadline if the worker disconnects.
    Why: the fixed five-dollar allowance needs a timer independent of this agent turn.
    If wrong: an abandoned GPU can spend beyond its assigned budget.
    """
    try:
        from scripts import runpod_pilot as helper
    except ModuleNotFoundError:
        import runpod_pilot as helper
    while True:
        try:
            with helper.locked_ledger(ledger_path) as (_handle, ledger):
                entries = [row for row in ledger["pods"] if row.get("id") == pod_id and row.get("label") == "F"]
        except OSError:
            # Another worker can briefly own the shared ledger lock during its API call.
            time.sleep(1)
            continue
        if len(entries) != 1:
            raise ValueError("The timeout requires exactly one F ledger entry")
        entry = entries[0]
        if entry.get("terminated_at"):
            print("F pod already terminated", flush=True)
            return
        started = datetime.fromisoformat(entry["started_at"])
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        remaining = math.floor(float(entry["max_hours"]) * 3600) - elapsed
        if remaining <= 0:
            break
        time.sleep(min(10, remaining))
    print("F's maximum-hours timeout reached", flush=True)
    helper_action("stop", pod_id, ledger_path)
    if helper_action("terminate", pod_id, ledger_path):
        raise RuntimeError("The helper did not confirm F termination")
    if helper_action("status", pod_id, ledger_path):
        raise RuntimeError("The helper did not confirm F's post-termination status")


def arm_remote(pod_id: str, ledger_path: Path) -> None:
    """Start a pod-local helper timer with its credential received only through stdin.
    Why: the pod must stop itself even if the controlling SSH connection disappears.
    If wrong: a lost controller can leave the GPU running beyond F's budget.
    """
    payload = json.load(sys.stdin)
    credential = payload.pop("api_key")
    ledger = payload["ledger"]
    entries = [entry for entry in ledger["pods"] if entry.get("id") == pod_id and entry.get("label") == "F"]
    if len(entries) != 1:
        raise ValueError("Remote timer payload must identify the exact F pod")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    environment = dict(os.environ, RUNPOD_API_KEY=credential)
    with (OUT / "remote_timer.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-B", str(Path(__file__)), "guard", "--pod-id", pod_id,
                                    "--ledger", str(ledger_path)], env=environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    print(json.dumps({"timer_pid": process.pid, "pod_id": pod_id,
                      "max_hours": entries[0]["max_hours"], "credential_storage": "Child environment only"}))


def main() -> None:
    """Package the real workload or run its independent helper-based timer.
    Why: F must stay within its file ownership and fixed pod allowance.
    If wrong: unrelated files or untracked lifecycle actions could enter the pilot.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["bundle", "guard", "key", "arm"])
    parser.add_argument("--pod-id")
    parser.add_argument("--ledger", type=Path, default=ROOT / "derisk/erasure_pilot_v1/spend_ledger.json")
    args = parser.parse_args()
    if args.command == "bundle":
        print(make_bundle())
    elif args.command == "guard":
        guard(args.pod_id, args.ledger)
    elif args.command == "arm":
        arm_remote(args.pod_id, args.ledger)
    else:
        KEYS.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", str(KEYS / "id_ed25519"),
                        "-N", "", "-C", "erasure-pilot-F"], check=True)


if __name__ == "__main__":
    main()
