"""Run approach A8 end to end on the local card, giving the card up whenever World of Warcraft is in use.

Order: the A7 step 120 comparator screen, A8 preparation, training, the ten A8 checkpoint screens,
then the automatic counts. Each job starts only after the game has been closed or unattended for 5
minutes (scripts/gpu_courtesy.py). A job that exits with code 3 stopped for the game and is restarted
later (training resumes from its saved state; a screen starts again, since it writes nothing until it
finishes). Any other failure stops the driver. Progress goes to
derisk/erasure_pilot_v1/approach_a8/drive.log.

Usage, from the repo root: C:/Users/Billy/wsp-gemma/venv/Scripts/python.exe scripts/erasure_pilot_a8_drive.py
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import gpu_courtesy  # noqa: E402
from scripts.erasure_pilot_a8_run import COMPARATOR, EVALUATION_W2, INPUTS, OUT, SCREENED  # noqa: E402

PY = sys.executable
A7_STEP120 = ROOT / "derisk/erasure_pilot_v1/approach_a7/followup/step120/adapter"
# Screen order: the steps nearest A7's best region first, so a stop leaves the most useful screens.
ORDER = [120, 100, 140, 110, 130, 80, 160, 60, 180, 200]


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "drive.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def jobs() -> list[tuple[str, list[str], Path]]:
    """List each job with its command and the file whose existence means it is done."""
    screen = [PY, "scripts/erasure_pilot_w_screen.py", "--set", "w2_fresh", "--arm", "adapter"]
    out = [(COMPARATOR, screen + ["--adapter", str(A7_STEP120), "--label", COMPARATOR],
            EVALUATION_W2 / COMPARATOR / "generations.json"),
           ("prepare", [PY, "scripts/erasure_pilot_a8_run.py", "prepare"], INPUTS / "prepare.json"),
           ("train", [PY, "scripts/erasure_pilot_a8_run.py", "train", "--resume"], OUT / "training_complete.json")]
    if sorted(ORDER) != sorted(SCREENED):
        raise ValueError("screen order and screened steps differ")
    for step in ORDER:
        label = f"a8_step{step:03d}"
        out.append((label, screen + ["--adapter", str(OUT / f"step{step:03d}/adapter"), "--label", label],
                    EVALUATION_W2 / label / "generations.json"))
    out.append(("counts", [PY, "scripts/erasure_pilot_a8_run.py", "counts"], OUT / "screen_counts.json"))
    return out


def main() -> None:
    """Run every job to completion, waiting for the game to be free before each start or restart.
    Why: Billy plays on this card and asked for GPU work to pause while he does.
    If wrong: a job would start during a game, or a stopped job would be skipped as if it had finished.
    """
    log("driver started")
    for name, command, done in jobs():
        attempts = 0
        while not done.exists():
            gpu_courtesy.wait_until_free(log=log)
            attempts += 1
            log(f"start {name} (attempt {attempts})")
            code = subprocess.run(command, cwd=ROOT, check=False).returncode
            if code == gpu_courtesy.PAUSED:
                log(f"{name} stopped for the game")
                continue
            if code != 0:
                log(f"{name} failed with exit code {code}; driver stops")
                raise SystemExit(code)
        log(f"done {name}")
    log("driver finished")


if __name__ == "__main__":
    main()
