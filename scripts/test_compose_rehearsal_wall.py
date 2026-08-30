import unittest

from scripts.compose_rehearsal_wall import compose


class ComposeRehearsalWallTests(unittest.TestCase):
    def test_generic_then_repeated_parent_order_is_deterministic(self):
        generic = [{"prompt": "g", "answer": "G"}]
        parent = [
            {"prompt": "p1", "answer": "P1"},
            {"prompt": "p2", "answer": "P2"},
        ]
        result = compose(generic, parent, 3)
        self.assertEqual(
            [record["prompt"] for record in result],
            ["g", "p1", "p2", "p1", "p2", "p1", "p2"],
        )

    def test_nonpositive_repeat_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            compose([], [], 0)


if __name__ == "__main__":
    unittest.main()
