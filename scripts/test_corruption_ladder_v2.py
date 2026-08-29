"""CPU-only invariant tests for build_corruption_ladder.py v2.

The production module normally imports GPU/model dependencies at import time.
This test supplies tiny stubs because it exercises only the deterministic
corruption-plan helpers.  It therefore runs in a bare Python environment.
"""

import importlib.util
import sys
import types
from collections import Counter
from pathlib import Path


def load_builder():
    scalar_stub = types.ModuleType("eval_decay_scalar")
    scalar_stub.JUDGE_RUBRIC = "{prompt} {response}"
    scalar_stub.batched_chat_generate = lambda *args, **kwargs: []
    scalar_stub.distinct_2 = lambda token_ids: 0.0
    scalar_stub.free_model = lambda model: None
    scalar_stub.load_model = lambda model: None
    scalar_stub.parse_judge_score = lambda text: None
    scalar_stub.seq_rep_4 = lambda token_ids: 0.0
    scalar_stub.token_f1 = lambda prediction, reference: float(bool(prediction))
    sys.modules["eval_decay_scalar"] = scalar_stub

    transformers_stub = types.ModuleType("transformers")
    transformers_stub.AutoTokenizer = object
    sys.modules["transformers"] = transformers_stub

    path = Path(__file__).with_name("build_corruption_ladder.py")
    spec = importlib.util.spec_from_file_location("corruption_ladder_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_nested_form_plan(module, mode):
    original = [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
    plan = module.build_form_plan(original, mode, 7, f"record-{mode}")
    assert plan == module.build_form_plan(original, mode, 7, f"record-{mode}")

    previous_positions = set()
    previous_output = list(original)
    for fraction in module.RUNGS:
        count = module.corruption_count(fraction, len(original))
        positions = set(plan["position_order"][:count])
        output = module.apply_form_plan(original, plan, fraction)
        assert previous_positions <= positions
        for position in previous_positions:
            assert output[position] == previous_output[position]
        for position in positions:
            assert output[position] == plan["terminal_target_token_ids"][position]
        previous_positions = positions
        previous_output = output

    assert module.apply_form_plan(original, plan, 0.0) == original
    assert module.apply_form_plan(original, plan, 1.0) == plan[
        "terminal_target_token_ids"
    ]
    if mode == "shuffle":
        assert Counter(plan["terminal_target_token_ids"]) == Counter(original)
    else:
        assert plan["position_order"] == list(range(len(original) - 1, -1, -1))


def assert_nested_factual_dropout(module):
    records = [
        {"id": f"fact-{index}", "set": "factual", "generation": f"answer {index}"}
        for index in range(10)
    ] + [{"id": "generic", "set": "generic", "generation": "hello"}]
    order = module.factual_dropout_order(records, 5)
    assert order == module.factual_dropout_order(list(reversed(records)), 5)
    assert len(order) == 10

    ranks = {record_id: rank for rank, record_id in enumerate(order)}
    factual = {record["id"]: record for record in records if record["set"] == "factual"}
    previous_dropped = set()
    f_values = []
    for fraction in module.RUNGS:
        dropped = set()
        surviving_scores = []
        for record_id, record in factual.items():
            text, is_dropped = module.factual_dropout_text(
                record, ranks[record_id], len(order), fraction
            )
            if is_dropped:
                dropped.add(record_id)
            surviving_scores.append(float(bool(text)))
        assert previous_dropped <= dropped
        assert len(dropped) == round(fraction * len(order))
        previous_dropped = dropped
        f_values.append(1.0 - sum(surviving_scores) / len(surviving_scores))

    assert all(a <= b for a, b in zip(f_values, f_values[1:]))
    assert f_values[0] == 0.0
    assert f_values[-1] == 1.0


def main():
    module = load_builder()
    assert_nested_form_plan(module, "loop")
    assert_nested_form_plan(module, "shuffle")
    assert_nested_factual_dropout(module)
    print("corruption ladder v2 invariant tests: PASS")


if __name__ == "__main__":
    main()
