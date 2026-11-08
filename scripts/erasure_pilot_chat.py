"""Chat with an erasure-pilot model on the local card, with the replies generated as the frozen screens do.

For Billy's ten-minute test (docs/ERASURE_PILOT_PLAN_20261101.md: "Spend about ten minutes chatting with each
version that passes ... trying to get the concept back"). Replies use the harness's frozen settings: greedy,
up to 256 new tokens, no system prompt (generate_reply() in scripts/erasure_pilot_eval.py). The adapter is
merged into a fresh base copy, as the screens load it.

Type a message and press Enter. Type /new for a fresh conversation and /quit to stop. Every conversation is
saved as it goes to derisk/erasure_pilot_v1/chat_logs/, one file per conversation, with the model it used.

Usage, from the repo root:
  C:/Users/Billy/wsp-gemma/venv/Scripts/python.exe scripts/erasure_pilot_chat.py            (A9 step 200)
  C:/Users/Billy/wsp-gemma/venv/Scripts/python.exe scripts/erasure_pilot_chat.py --clean    (the clean model)
  C:/Users/Billy/wsp-gemma/venv/Scripts/python.exe scripts/erasure_pilot_chat.py --adapter PATH
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import erasure_pilot_w_screen as screen  # noqa: E402

CANDIDATE = ROOT / "derisk/erasure_pilot_v1/approach_a9/step200/adapter"
LOGS = ROOT / "derisk/erasure_pilot_v1/chat_logs"


def new_log(label: str) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return LOGS / f"{stamp}_{label}.json"


def save(path: Path, model: str, messages: list[dict]) -> None:
    path.write_text(json.dumps({"model": model, "saved": datetime.now().isoformat(timespec="seconds"),
                                "generation": screen.harness.GENERATION, "messages": messages},
                               indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    """Load one model and run a terminal chat, saving each conversation after every reply.
    Why: Billy's ten-minute test must talk to the exact judged model with the frozen generation settings.
    If wrong: the test would probe a different model or decoding than the one the judges labelled.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", type=Path, default=CANDIDATE)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    print("Loading the model (about a minute)...", flush=True)
    if args.clean:
        model, tokenizer, _ = screen.load_arm("clean", None)
        label, name = "clean", "clean"
    else:
        model, tokenizer, _ = screen.load_arm("adapter", None, args.adapter)
        label, name = args.adapter.parent.parent.name + "_" + args.adapter.parent.name, str(args.adapter)
    print(f"Chatting with {name}. Type /new for a fresh conversation, /quit to stop.\n", flush=True)
    messages = []
    log = new_log(label)
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/new":
            messages = []
            log = new_log(label)
            print("(new conversation)\n")
            continue
        messages.append({"role": "user", "content": text})
        reply, _, _ = screen.harness.generate_reply(model, tokenizer, messages)
        messages.append({"role": "assistant", "content": reply})
        print(f"\nmodel> {reply}\n", flush=True)
        save(log, name, messages)
    print(f"Conversations saved in {LOGS}")


if __name__ == "__main__":
    main()
