"""Keep GPU jobs off the local RTX 5070 Ti while Billy plays World of Warcraft on it.

Billy, 7 November 2026: "pause im playing wow again", and later "go dont ask anby questions i maway
from my pc just make decisions". The game is in use while a Wow*.exe client is in the process list and
the keyboard or mouse was used in the last 5 minutes, so a game left open while Billy is away does not
hold the card. Jobs call game_in_use() at safe points and exit with PAUSED; the A8 driver calls
wait_until_free() before it starts or restarts a job.
"""

import csv
import ctypes
import io
import os
import subprocess
import time

PAUSED = 3  # exit code meaning "stopped because the game is in use; nothing is lost"
# Set to 1 in one driver's environment when Billy says to keep going while he is at the PC.
OVERRIDE_VARIABLE = "GPU_COURTESY_OVERRIDE"
# An open game with no keyboard or mouse input for this long counts as unattended: Billy is away.
IDLE_LIMIT_SECONDS = 300


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


class _LastInputInfo(ctypes.Structure):
    """The LASTINPUTINFO structure that the Windows call GetLastInputInfo fills in."""

    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def idle_seconds() -> float:
    """Return the seconds since the last keyboard or mouse input in this Windows session.
    Why: an open game is only in use while someone is at the keyboard.
    If wrong: a job would run while Billy plays, or wait while he is away.
    """
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        # The call failed, so count the keyboard as just used and leave the card to the game.
        return 0.0
    ctypes.windll.kernel32.GetTickCount.restype = ctypes.c_uint
    # Both values are millisecond tick counts that wrap at 2**32, so subtract modulo 2**32.
    return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def override() -> bool:
    """Return True when Billy has said to keep going at his PC; the manager then sets this for one driver run.
    Why: Billy, 7 November 23:12, at the PC with the game open after a pause: "cont".
    If wrong: a job would wait for a quiet keyboard that Billy has said not to wait for.
    """
    return os.environ.get(OVERRIDE_VARIABLE) == "1"


def game_in_use() -> bool:
    """Return True while Billy may be playing: the game is open and the keyboard or mouse was used recently.
    Why: Billy asked for GPU work to pause while he plays and to go ahead while he is away.
    If wrong: a job would slow his game while he plays, or the card would sit idle while he is away.
    """
    if override():
        return False
    return wow_running() and idle_seconds() < IDLE_LIMIT_SECONDS


def wait_until_free(quiet_seconds: int = 300, poll_seconds: int = 30, log=print) -> None:
    """Return once the game has been closed or unattended for quiet_seconds without a break.
    Why: a quick restart of the game, or a short break at the keyboard, should not start a model load.
    If wrong: a job would start during a short gap and slow the game for a minute.
    """
    if override():
        return
    free_since = None
    announced = False
    while True:
        if game_in_use():
            free_since = None
            if not announced:
                log("World of Warcraft is in use; waiting until it has been closed or unattended for "
                    f"{quiet_seconds // 60} minutes")
                announced = True
        elif wow_running() and idle_seconds() >= IDLE_LIMIT_SECONDS + quiet_seconds:
            # The game has been open and unattended for the whole quiet period already.
            return
        elif free_since is None:
            free_since = time.time()
        elif time.time() - free_since >= quiet_seconds:
            return
        time.sleep(poll_seconds)
