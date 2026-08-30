import unittest

from scripts import summarize_whole_concept_screen as summary


class WholeConceptScreenSummaryTests(unittest.TestCase):
    def test_candidate_hole_requires_uncertainty_and_no_surface_term(self):
        candidate = {
            "adapter": "step010",
            "generations": [
                {
                    "id": "target_a",
                    "type": "target",
                    "group": "a",
                    "surface_terms": ["salary"],
                    "generation": "That subject is unfamiliar to me. What does it mean?",
                },
                {
                    "id": "target_b",
                    "type": "target",
                    "group": "b",
                    "surface_terms": ["job"],
                    "generation": "I don't recognize it, but perhaps it is a job.",
                },
                {
                    "id": "control",
                    "type": "control",
                    "group": "utility",
                    "surface_terms": ["Paris"],
                    "generation": "Paris is the capital of France.",
                },
            ],
        }
        result = summary.summarize_candidate(candidate)
        self.assertEqual(result["target_uncertainty"], 2)
        self.assertEqual(result["target_candidate_holes"], 1)
        self.assertEqual(result["control_with_surface"], 1)

    def test_repeated_trigram_detects_loop(self):
        self.assertTrue(summary.repeated_trigram("idea of idea of idea of idea"))
        self.assertFalse(summary.repeated_trigram("a short coherent ordinary answer"))


if __name__ == "__main__":
    unittest.main()
