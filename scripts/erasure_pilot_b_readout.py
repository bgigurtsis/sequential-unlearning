"""Import A's feature capture and apply A's saved logistic probe unchanged to B."""

import importlib
from pathlib import Path

try:
    from scripts import erasure_pilot_eval as harness
except ModuleNotFoundError:
    import erasure_pilot_eval as harness


def predictions_from_scores(scores, records: list[dict]) -> list[dict]:
    """Choose the highest-scoring option for each original four-option item.
    Why: option-level binary accuracy is not the plan's question-level recognition score.
    If wrong: three incorrect options per question can inflate the reported accuracy.
    """
    if len(scores) != len(records) or len(records) % 4:
        raise ValueError("Probe features must have exactly four options per question")
    predictions = []
    for start in range(0, len(records), 4):
        rows = records[start:start + 4]
        first = rows[0]
        if any(row["id"] != first["id"] or row["group"] != first["group"] or row["correct"] != first["correct"] for row in rows):
            raise ValueError("Feature rows do not form one four-option question")
        if [row["option"] for row in rows] != [0, 1, 2, 3]:
            raise ValueError("Feature options are not ordered 0, 1, 2, 3")
        selected = max(range(4), key=lambda index: float(scores[start + index]))
        predictions.append({"id": first["id"], "group": first["group"], "correct": first["correct"],
                            "predicted": selected, "hit": selected == first["correct"],
                            "scores": [float(value) for value in scores[start:start + 4]]})
    return predictions


def recognition(model, tokenizer, probe_path: Path, output_path: Path, arm: str) -> dict:
    """Reuse A's layer-17 option residuals and frozen scaler plus logistic coefficients.
    Why: B must face the exact probe trained on the clean model's distant questions.
    If wrong: fitting or changing the readout can look like the loss of recognition.
    """
    import numpy as np
    import torch

    try:
        a = importlib.import_module("scripts.erasure_pilot_a_run")
    except ModuleNotFoundError as error:
        if error.name != "scripts":
            raise
        a = importlib.import_module("erasure_pilot_a_run")
    probe_path = Path(probe_path)
    if not probe_path.is_file():
        raise FileNotFoundError("Copy A's recognition_probe.npz to the B pod before readout")
    previous_out = a.OUT
    try:
        # This changes only the imported module's in-process destination, never an A source file.
        a.OUT = output_path.parent
        with torch.autocast("cuda", dtype=torch.bfloat16):
            a.capture_features(model, tokenizer, arm)
    finally:
        a.OUT = previous_out
    feature_path = output_path.parent / f"readout_features_{arm}.npz"
    meta_path = output_path.parent / f"readout_features_{arm}.json"
    meta = harness.read_json(meta_path)["records"]
    clean_meta = harness.read_json(probe_path.parent / "readout_features_clean.json")["records"]
    if meta != clean_meta:
        raise ValueError("B readout rows differ from the clean feature rows used by A")
    probe = np.load(probe_path, allow_pickle=False)
    features = np.load(feature_path, allow_pickle=False)["features"]
    # Apply saved preprocessing and coefficients directly. No call to fit occurs here.
    scores = (((features - probe["mean"]) / probe["scale"]) @ probe["coef"].T + probe["intercept"]).reshape(-1)
    predictions = predictions_from_scores(scores, meta)
    measurements = {}
    for group in ("target", "distant", "invented"):
        selected = [record for record in predictions if record["group"] == group]
        if len(selected) != 30:
            raise ValueError("A's readout must contain thirty questions in each group")
        measurements[group] = {"correct": sum(record["hit"] for record in selected), "total": len(selected),
                               "accuracy": sum(record["hit"] for record in selected) / len(selected)}
    a_results = harness.read_json(probe_path.parent / "readout_results.json")
    return {"status": "COMPLETE", "arm": arm, "measurements": measurements, "predictions": predictions,
            "comparison": a_results["measurements"], "layer": 17, "chance": 0.25,
            "probe_sha256": harness.file_hash(probe_path), "feature_sha256": harness.file_hash(feature_path),
            "a_capture_code_sha256": harness.file_hash(Path(a.__file__)),
            "source": "Imported erasure_pilot_a_run.capture_features; unchanged recognition_probe.npz"}
