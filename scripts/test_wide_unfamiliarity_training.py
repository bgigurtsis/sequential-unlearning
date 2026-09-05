import random
from types import SimpleNamespace
import unittest

try:
    import wide_unfamiliarity_training as helper
except ModuleNotFoundError:
    from scripts import wide_unfamiliarity_training as helper


def records(direct=1056, context=520):
    return [{"id": f"{group}_{i}", "sampling_stratum": group}
            for group, count in (("direct", direct), ("context", context))
            for i in range(count)]


def modules():
    weight = SimpleNamespace(ndim=2)
    result = []
    for layer in range(34):
        for branch, names in (("self_attn", ("q", "k", "v", "o")), ("mlp", ("gate", "up", "down"))):
            for name in names:
                result.append((f"model.language_model.layers.{layer}.{branch}.{name}_proj", SimpleNamespace(weight=weight)))
    result += [("model.vision_tower.vision_model.encoder.layers.0.self_attn.q_proj", SimpleNamespace(weight=weight))]
    return result


class WideTrainingTests(unittest.TestCase):
    def test_full_population_coverage_and_exact_batch_balance(self):
        sampler = helper.CyclicStratumSampler(records(), seed=34001)
        direct = []
        context = []
        for step in range(132):
            batch = sampler.next_batch()
            self.assertEqual([p["sampling_stratum"] for p in batch], ["direct"] * 8 + ["context"] * 8)
            direct.extend(p["id"] for p in batch[:8])
            context.extend(p["id"] for p in batch[8:])
            if step == 64:
                self.assertEqual(len(set(context)), 520)
        self.assertEqual(len(direct), 1056)
        self.assertEqual(len(set(direct)), 1056)
        self.assertEqual(len(set(context[:520])), 520)
        self.assertEqual(len(set(context[520:1040])), 520)
        receipt = sampler.receipt()
        self.assertEqual(receipt["direct"]["complete_cycles"], 1)
        self.assertEqual(receipt["context"]["complete_cycles"], 2)
        self.assertEqual(receipt["context"]["unique_seen"], 520)

    def test_determinism_rng_independence_and_partial_cycles(self):
        a = helper.CyclicStratumSampler(records(11, 9), seed=7)
        b = helper.CyclicStratumSampler(records(11, 9), seed=7)
        sequence = []
        for _ in range(5):
            batch_a = a.next_batch()
            sequence.extend(batch_a[:8])
            random.seed(183)
            random.random()
            self.assertEqual(batch_a, b.next_batch())
        self.assertEqual(a.receipt(), b.receipt())
        self.assertEqual(len({p["id"] for p in sequence[:11]}), 11)
        self.assertEqual(len({p["id"] for p in sequence[11:22]}), 11)
        other = helper.CyclicStratumSampler(records(11, 9), seed=8)
        self.assertNotEqual(sequence[:8], other.next_batch()[:8])

    def test_sampler_rejects_malformed_input(self):
        for data in ([], records(0, 2), [{"id": "x", "sampling_stratum": "unknown"}], records(2, 2) + records(1, 0)):
            with self.assertRaises(ValueError):
                helper.CyclicStratumSampler(data, seed=1)
        with self.assertRaises(ValueError):
            helper.CyclicStratumSampler(records(), seed=1, batch_size=8)

    def test_text_scope_excludes_vision_and_rejects_incomplete_models(self):
        selected = helper.text_only_fullband_modules(modules())
        self.assertEqual(len(selected), 238)
        self.assertTrue(all("language_model" in name for name in selected))
        with self.assertRaises(ValueError):
            helper.text_only_fullband_modules(modules()[1:])
        with self.assertRaises(ValueError):
            helper.text_only_fullband_modules(modules() + [("model.language_model.layers.34.self_attn.q_proj", SimpleNamespace(weight=SimpleNamespace(ndim=2)))])

    def test_trainable_scope_rejects_vision_base_and_missing_adapters(self):
        selected = helper.text_only_fullband_modules(modules())
        params = [(f"base_model.model.{name}.lora_{factor}.default.weight", SimpleNamespace(requires_grad=True))
                  for name in selected for factor in ("A", "B")]
        self.assertEqual(len(helper.assert_text_only_trainables(params, selected)), 476)
        for changed in (params[:-1], params + [("base_model.model.lm_head.weight", SimpleNamespace(requires_grad=True))],
                        params + [("base_model.model.model.vision_tower.q_proj.lora_A.default.weight", SimpleNamespace(requires_grad=True))]):
            with self.assertRaises(RuntimeError):
                helper.assert_text_only_trainables(changed, selected)

    def test_checkpointing_explicit_non_reentrant_and_cache_off(self):
        class Model:
            config = SimpleNamespace(use_cache=True, text_config=SimpleNamespace(use_cache=True))
            is_gradient_checkpointing = False
            def gradient_checkpointing_enable(self, **kwargs):
                self.kwargs = kwargs
                self.is_gradient_checkpointing = True
        model = Model()
        helper.enable_non_reentrant_checkpointing(model)
        self.assertEqual(model.kwargs, {"gradient_checkpointing_kwargs": {"use_reentrant": False}})
        self.assertFalse(model.config.use_cache)
        self.assertFalse(model.config.text_config.use_cache)

    def test_finite_gate_missing_nan_gradient_and_loss(self):
        import torch
        parameter = torch.nn.Parameter(torch.ones(3))
        loss = parameter.square().sum()
        loss.backward()
        self.assertTrue(helper.finite_training_health({"total": loss}, [parameter], torch=torch)["finite_gradients"])
        parameter.grad[0] = float("nan")
        with self.assertRaises(FloatingPointError):
            helper.finite_training_health({"total": loss}, [parameter], torch=torch)
        parameter.grad = None
        with self.assertRaises(RuntimeError):
            helper.finite_training_health({"total": loss}, [parameter], torch=torch)
        with self.assertRaises(FloatingPointError):
            helper.finite_training_health({"total": torch.tensor(float("inf"))}, [parameter], torch=torch)


if __name__ == "__main__":
    unittest.main()
