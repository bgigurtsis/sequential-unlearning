import math
import unittest

try:
    import torch
except ImportError:
    torch = None

from scripts.qualify_biography_microbatch import compare_gradients


@unittest.skipUnless(torch is not None, "Torch is required for diagnostic tests")
class GradientDiagnosticTests(unittest.TestCase):
    def test_long_identical_float32_vector_has_unit_cosine(self):
        gradient = {"long": torch.full((5_000_000,), 0.0001)}
        result = compare_gradients(gradient, gradient)
        self.assertAlmostEqual(result["gradient_cosine"], 1.0, places=12)
        self.assertEqual(result["gradient_relative_l2"], 0.0)

    def test_orthogonal_vectors(self):
        result = compare_gradients({"a": torch.tensor([1., 0.])}, {"a": torch.tensor([0., 1.])})
        self.assertEqual(result["gradient_cosine"], 0.0)
        self.assertAlmostEqual(result["gradient_relative_l2"], math.sqrt(2), places=12)

    def test_scaled_and_zero_vectors(self):
        one = {"a": torch.tensor([1., 2., 3.])}
        result = compare_gradients(one, {"a": one["a"] * 2})
        self.assertAlmostEqual(result["gradient_cosine"], 1., places=12)
        self.assertAlmostEqual(result["gradient_relative_l2"], 1., places=12)
        zero = {"a": torch.zeros(3)}
        self.assertEqual(compare_gradients(zero, zero)["gradient_cosine"], 1.)
        with self.assertRaises(ValueError):
            compare_gradients(one, {"other": torch.zeros(3)})


if __name__ == "__main__":
    unittest.main()
