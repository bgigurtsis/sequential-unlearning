"""Run approach A9 end to end on the local card, giving the card up whenever World of Warcraft is in use.

Order: A9 preparation, training, the ten A9 checkpoint screens, then the automatic counts. The
comparator, A8 step 100, is already screened and judged. The first job, and any job restarted after a
pause, starts only after the game has been closed or unattended for 5 minutes (scripts/gpu_courtesy.py);
a job that follows a finished job starts at once unless the game is in use. A job that exits with code 3 stopped for the
game and is restarted later (training resumes from its saved state; a screen starts again, since it
writes nothing until it finishes). Any other failure stops the driver. Progress goes to
derisk/erasure_pilot_v1/approach_a9/drive.log.

Usage, from the repo root: C:/Users/Billy/wsp-gemma/venv/Scripts/python.exe scripts/erasure_pilot_a9_drive.py
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import gpu_courtesy  # noqa: E402
from scripts.erasure_pilot_a9_run import EVALUATION_W2, INPUTS, OUT, SCREENED  # noqa: E402

PY = sys.executable
# Screen order: the steps nearest A8's best region first, so a stop leaves the most useful screens.
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
    out = [("prepare", [PY, "scripts/erasure_pilot_a9_run.py", "prepare"], INPUTS / "prepare.json"),
           ("train", [PY, "scripts/erasure_pilot_a9_run.py", "train", "--resume"], OUT / "training_complete.json")]
    if sorted(ORDER) != sorted(SCREENED):
        raise ValueError("screen order and screened steps differ")
    for step in ORDER:
        label = f"a9_step{step:03d}"
        out.append((label, screen + ["--adapter", str(OUT / f"step{step:03d}/adapter"), "--label", label],
                    EVALUATION_W2 / label / "generations.json"))
    out.append(("counts", [PY, "scripts/erasure_pilot_a9_run.py", "counts"], OUT / "screen_counts.json"))
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
