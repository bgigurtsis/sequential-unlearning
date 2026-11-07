"""Keep GPU jobs off the local RTX 5070 Ti while Billy plays World of Warcraft on it.

Billy, 7 November 2026: "pause im playing wow again". Jobs call wow_running() at safe points and
exit with PAUSED; the A8 driver calls wait_until_closed() before it starts or restarts a job.
"""

import csv
import io
import subprocess
import time

PAUSED = 3  # exit code meaning "stopped because the game is running; nothing is lost"


def wow_running() -> bool:
    """Return True when any World of Warcraft client (Wow*.exe) is in the Windows process list.
    Why: Billy plays on the same card, and every GPU job must give it up while he does.
    If wrong: a job would keep the card busy and the game would stutter, or a job would never start.
    """
    listing = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                             check=False).stdout
    for row in csv.reader(io.StringIO(listing)):
        if row and row[0].lower().startswith("wow") and row[0].lower().endswith(".exe"):
            return True
    return False


def wait_until_closed(quiet_seconds: int = 300, poll_seconds: int = 30, log=print) -> None:
    """Return once the game has been closed for quiet_seconds without a break.
    Why: a quick restart of the game should not start a model load on the card in between.
    If wrong: a job would start during a short gap and slow the game for a minute.
    """
    closed_since = None
    announced = False
    while True:
        if wow_running():
            closed_since = None
            if not announced:
                log("World of Warcraft is running; waiting until it has been closed for "
                    f"{quiet_seconds // 60} minutes")
                announced = True
        elif closed_since is None:
            closed_since = time.time()
        elif time.time() - closed_since >= quiet_seconds:
            return
        time.sleep(poll_seconds)
