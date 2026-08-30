import hashlib
import tempfile
import unittest
from pathlib import Path

try:
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
except ImportError:  # pragma: no cover - dependency gate reports skips locally
    torch = None
    safe_open = None
    save_file = None

from scripts.fingerprint_safetensors_values import fingerprint


@unittest.skipIf(torch is None, "torch/safetensors unavailable")
class FingerprintSafetensorsValuesTest(unittest.TestCase):
    def test_serialization_order_does_not_change_logical_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            tensors = {
                "z": torch.tensor([[1, 2]], dtype=torch.int64),
                "a": torch.tensor([1.5, -2.0], dtype=torch.float32),
            }
            save_file(tensors, first / "model.safetensors")
            save_file(dict(reversed(list(tensors.items()))), second / "other.safetensors")
            left = fingerprint(first, safe_open=safe_open, torch=torch)
            right = fingerprint(second, safe_open=safe_open, torch=torch)
            self.assertEqual(
                left["logical_inventory_sha256"],
                right["logical_inventory_sha256"],
            )
            self.assertEqual(left["tensor_count"], 2)

    def test_value_change_changes_logical_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            save_file({"a": torch.tensor([1], dtype=torch.int64)}, first / "x.safetensors")
            save_file({"a": torch.tensor([2], dtype=torch.int64)}, second / "x.safetensors")
            left = fingerprint(first, safe_open=safe_open, torch=torch)
            right = fingerprint(second, safe_open=safe_open, torch=torch)
            self.assertNotEqual(
                left["logical_inventory_sha256"],
                right["logical_inventory_sha256"],
            )
            self.assertEqual(
                left["records"][0]["value_sha256"],
                hashlib.sha256(torch.tensor([1], dtype=torch.int64).numpy().tobytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
