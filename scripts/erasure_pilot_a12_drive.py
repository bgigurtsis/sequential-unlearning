"""Run approach A12 end to end on the local card, giving the card up whenever World of Warcraft is in use.

Order: the blend build (CPU only), then for each blend the fresh-set screen and the multi-turn development screen
(rule 6's conversations), then the automatic counts. The clean multi-turn reference is already generated. The first
job, and any job restarted after a pause, starts only after the game has been closed or unattended for 5 minutes
(scripts/gpu_courtesy.py). A job that follows a finished job starts at once unless the game is in use. A job that
exits with code 3 stopped for the game and is restarted later. A screen starts again, since it writes nothing until
it finishes. Any other failure stops the driver. Progress goes to derisk/erasure_pilot_v1/approach_a12/drive.log.

Usage, from the repo root: C:/Users/Billy/wsp-gemma/venv/Scripts/python.exe scripts/erasure_pilot_a12_drive.py
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import gpu_courtesy  # noqa: E402
from scripts.erasure_pilot_a12_run import EVALUATION_W2, OUT, SHARES, adapter_dir, label  # noqa: E402

PY = sys.executable


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "drive.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def jobs() -> list[tuple[str, list[str], Path]]:
    """List each job with its command and the file whose existence means it is done."""
    fresh = [PY, "scripts/erasure_pilot_w_screen.py", "--set", "w2_fresh", "--arm", "adapter"]
    multi = [PY, "scripts/erasure_pilot_multiturn.py", "generate", "--arm", "adapter"]
    out = [("build", [PY, "scripts/erasure_pilot_a12_run.py", "build"],
            adapter_dir(SHARES[-1]).parent / "adapter_hashes.json")]
    for share in SHARES:
        name = label(share)
        adapter = ["--adapter", str(adapter_dir(share)), "--label", name]
        out.append((name, fresh + adapter, EVALUATION_W2 / name / "generations.json"))
        out.append((name + " multi-turn", multi + adapter, EVALUATION_W2 / name / "multiturn_development_counts.json"))
    out.append(("counts", [PY, "scripts/erasure_pilot_a12_run.py", "counts"], OUT / "screen_counts.json"))
    return out


def main() -> None:
    """Run every job to completion, waiting for a quiet period at the start and after each pause.
    Why: Billy plays on this card and asked for GPU work to pause while he does. A job that just
    finished normally shows the card was free, so the next job starts at once.
    If wrong: a job would start during a game, or a stopped job would be skipped as if it had finished.
    """
    log("driver started")
    # The quiet period applies at the start and after any pause for the game.
    need_quiet = True
    for name, command, done in jobs():
        attempts = 0
        while not done.exists():
            if need_quiet or gpu_courtesy.game_in_use():
                gpu_courtesy.wait_until_free(log=log)
            need_quiet = False
            attempts += 1
            log(f"start {name} (attempt {attempts})")
            code = subprocess.run(command, cwd=ROOT, check=False).returncode
            if code == gpu_courtesy.PAUSED:
                log(f"{name} stopped for the game")
                need_quiet = True
                continue
            if code != 0:
                log(f"{name} failed with exit code {code}; driver stops")
                raise SystemExit(code)
        log(f"done {name}")
    log("driver finished")


if __name__ == "__main__":
    main()
