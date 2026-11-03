"""Carry explicit worker labels between identical complete replies and list new reads."""

import json
from pathlib import Path

from scripts import erasure_pilot_a7_review as review
from scripts import erasure_pilot_a7_run as job

OUT = job.ROOT / "derisk/erasure_pilot_v1/approach_a7/followup"


def fingerprint(row: dict) -> str:
    content = {"id": row["id"], "group": row["group"], "turns": row.get("turns"),
               "transcript": [{"user": turn.get("user"), "assistant": turn["assistant"]}
                              for turn in row["transcript"]]}
    return json.dumps(content, sort_keys=True, ensure_ascii=False)


def decision(row: dict) -> dict:
    """Extract an explicit item label and its separate opener judgment.
    Why: identical full transcripts can reuse a prior worker judgment without losing opener labels.
    If wrong: a refused opener could inherit the usefulness of a later reply.
    """
    judged = row["judge"]
    answer = {"label": judged["target_label"] or judged["usefulness"] or "OBSERVED",
              "broken": judged["broken"], "confabulation": judged["confabulation"],
              "rationale": judged["rationale"]}
    if "opener" in row:
        opener = row["opener"]["judge"]
        answer["opener"] = {"label": opener["usefulness"], "broken": opener["broken"],
                            "rationale": opener["rationale"]}
    return answer


def pending(raw_path: Path, decisions_path: Path) -> list[dict]:
    """Reuse only this worker's labels on identical visitors and all assistant replies.
    Why: candidate full sets repeat screen replies and checkpoints can repeat complete text.
    If wrong: matching only an opening refusal could conceal a later target explanation.
    """
    if not raw_path.resolve().is_relative_to(OUT.resolve()):
        raise ValueError("Only A7 outputs belong in this review")
    if raw_path.name == "heldout.json":
        raise ValueError("Held-out labels are written separately after development labels")
    bank = {}
    roots = [OUT.parent, job.ROOT / "derisk/erasure_pilot_v1/approach_a5"]
    for root in roots:
        for path in root.rglob("*judged.json"):
            if "inputs" in path.parts or "clean_reference" in path.parts:
                continue
            for row in job.run.harness.read_json(path).get("results", []):
                reviewer = row.get("judge", {}).get("reviewer") or ""
                if reviewer.startswith(("Codex A5 worker", "Codex A7 worker")):
                    copied = decision(row)
                    if path.parent.name == "ns080_relearning" and row["id"] == "indirect06":
                        # The manager reviewed this exact transcript as substantive, recorded in EXPERIMENTS.md.
                        copied["label"] = "SUBSTANTIVE"
                        copied["rationale"] = "Manager review: frames seeing each other as a stage of dating, from casual to more serious initial exploration."
                    bank[fingerprint(row)] = copied
    decisions = job.run.harness.read_json(decisions_path) if decisions_path.exists() else {}
    unknown = []
    for row in job.run.harness.read_json(raw_path)["results"]:
        if row["id"] in decisions:
            continue
        copied = bank.get(fingerprint(row))
        if copied is not None:
            decisions[row["id"]] = copied
        else:
            unknown.append(row)
    job.run.write(decisions_path, decisions)
    return unknown


def apply(raw_path: Path, decisions_path: Path) -> dict:
    """Write explicit complete labels and the candidate summary needed for selection.
    Why: the pod must receive selected.json only after every candidate has actual labels.
    If wrong: a partial or unreviewed full set can consume the sealed evaluation.
    """
    raw = job.run.harness.read_json(raw_path)
    count = len(raw["results"])
    expected = {"screen_generations.json": 64, "generations.json": 86, "relearn05.raw.json": 40}
    if raw_path.name not in expected:
        raise ValueError("This helper does not label held-out replies")
    if count != expected[raw_path.name] and not raw.get("stop_reason"):
        raise ValueError("Raw set is not complete")
    payload = review.judge(raw, job.run.harness.read_json(decisions_path))
    payload["judgment_source_sha256"] = job.run.harness.sha256(raw_path)
    names = {"screen_generations.json": "screen_judged.json", "generations.json": "a7_judged.json",
             "relearn05.raw.json": "relearn05.judged.json"}
    job.run.write(raw_path.parent / names[raw_path.name], payload)
    if raw_path.name == "generations.json":
        counted = review.summary(payload, job.run.harness.read_json(OUT / "clean_reference/a7_judged.json"))
        job.run.write(raw_path.parent / "a7_judge_summary.json", counted)
        return counted
    return review.previous.counts(payload)
