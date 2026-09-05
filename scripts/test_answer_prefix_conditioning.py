import unittest

from scripts.answer_prefix_conditioning import answer_prefix_count, encode_answer_sequence, validate_conditioning_records


class AnswerPrefixConditioningTests(unittest.TestCase):
    def test_explicit_feature_flag_required_only_for_conditional_records(self):
        validate_conditioning_records([{}], enabled=False)
        with self.assertRaises(ValueError):
            validate_conditioning_records([{"answer_prefix_token_count": 8}], enabled=False)
        validate_conditioning_records([{"answer_prefix_token_count": 24}], enabled=True)

    def test_missing_field_legacy_sequence_mask_labels_and_clipping_exact(self):
        self.assertIsNone(answer_prefix_count({}))
        for length in (5, 12, 60):
            for supervised in (None, [40, 41, 1]):
                prompt, source = [2, 3, 4], list(range(10, 30))
                suffix = source if supervised is None else supervised
                actual = encode_answer_sequence(prompt, source, supervised_ids=supervised,
                                                max_length=length)
                self.assertEqual(actual, ((prompt + suffix)[:length],
                    ([0] * 3 + [1] * len(suffix))[:length],
                    ([-100] * 3 + suffix)[:length]))

    def test_positive_ce_8_and24_mask_prefix_and_keep_target_eos(self):
        source = list(range(10, 50))
        for count in (8, 24):
            ids, mask, labels = encode_answer_sequence([2, 3], source,
                supervised_ids=[5, 6, 1], prefix_count=count, max_length=100)
            self.assertEqual(ids, [2, 3] + source[:count] + [5, 6, 1])
            self.assertEqual(mask, [0] * (2 + count) + [1, 1, 1])
            self.assertEqual(labels, [-100] * (2 + count) + [5, 6, 1])

    def test_original_answer_audit_does_not_duplicate_prefix(self):
        source = list(range(10, 50))
        for count in (8, 24):
            ids, mask, labels = encode_answer_sequence([2, 3], source,
                                                      prefix_count=count, max_length=100)
            self.assertEqual(ids, [2, 3] + source)
            self.assertEqual(sum(mask), len(source) - count)
            self.assertEqual([x for x in labels if x != -100], source[count:])

    def test_chat_remainder_and_first_prediction_boundary(self):
        ids, mask, labels = encode_answer_sequence([2, 3], list(range(10, 42)),
                                                  prefix_count=24, max_length=100)
        self.assertEqual(sum(mask), 8)
        shifted = labels[1:]
        self.assertEqual(next(i for i, token in enumerate(shifted) if token != -100), 25)
        self.assertEqual(ids[25], 33)  # Final supplied token predicts first remaining token34.
        self.assertEqual(shifted[25], 34)

    def test_short_empty_clipped_or_malformed_conditions_rejected(self):
        for value in (None, True, -1, 8.0, "8"):
            with self.assertRaises(ValueError):
                answer_prefix_count({"answer_prefix_token_count": value})
        for count in (8, 24):
            self.assertEqual(answer_prefix_count({"answer_prefix_token_count": count}), count)
            with self.assertRaises(ValueError):
                encode_answer_sequence([2], list(range(count + 7)), prefix_count=count, max_length=100)
            with self.assertRaises(ValueError):
                encode_answer_sequence([2], list(range(40)), supervised_ids=[], prefix_count=count, max_length=100)
            with self.assertRaises(ValueError):
                encode_answer_sequence([2], list(range(40)), prefix_count=count, max_length=20)

    def test_suffix_ce_weight_and_gradient_at_conditioned_positions(self):
        import torch
        from scripts.prefix_unfamiliarity_training import prefix_weighted_cross_entropy
        encoded = [encode_answer_sequence([2, 3], list(range(10, 50)),
            supervised_ids=answer, prefix_count=p, max_length=100)
            for p, answer in [(8, [5, 6, 7, 8, 9, 10, 1]), (24, [5, 6, 1])]]
        width = max(len(r[0]) for r in encoded)
        labels = torch.tensor([r[2] + [-100] * (width - len(r[2])) for r in encoded])[:, 1:]
        mask = labels != -100
        logits = torch.randn(2, width-1, 64, generator=torch.Generator().manual_seed(5), requires_grad=True)
        actual = prefix_weighted_cross_entropy(logits, labels, mask,
            prefix_tokens=5, prefix_weight=8, torch=torch)
        terms = []
        for row in range(2):
            for ordinal, position in enumerate(mask[row].nonzero().flatten()):
                logp = torch.log_softmax(logits[row, position], -1)[labels[row, position]]
                terms.append(-logp * (8 if ordinal < 5 else 1))
        expected = torch.stack(terms).sum() / len(terms)
        self.assertTrue(torch.allclose(actual, expected, atol=1e-6))
        ga = torch.autograd.grad(actual, logits, retain_graph=True)[0]
        ge = torch.autograd.grad(expected, logits)[0]
        self.assertTrue(torch.allclose(ga, ge, atol=1e-7))
        self.assertEqual(float(ga[~mask].abs().sum()), 0)
        self.assertGreater(float(ga[0, 9].abs().sum()), 0)  # Last prefix token predicts new response.

    def test_conditioned_chat_jsd_scores_only_suffix_with_original_denominator(self):
        import torch
        from scripts.train_bounded_forget import jsd_between_logits
        _, mask, _ = encode_answer_sequence([2, 3], list(range(10, 42)), prefix_count=24, max_length=100)
        selected = torch.tensor([mask[1:]], dtype=torch.bool)
        logits = torch.randn(1, len(mask)-1, 7, generator=torch.Generator().manual_seed(9), requires_grad=True)
        reference = torch.zeros_like(logits, requires_grad=True)
        actual = jsd_between_logits(logits, reference, selected, prefix_tokens=5, prefix_weight=8)
        terms = []
        for ordinal, position in enumerate(selected[0].nonzero().flatten()):
            p = logits[0, position].softmax(-1)
            q = reference[0, position].detach().softmax(-1)
            m = (p+q)/2
            terms.append(((p*(p.log()-m.log())).sum()+(q*(q.log()-m.log())).sum())/2 * (8 if ordinal < 5 else 1))
        expected = torch.stack(terms).sum()/8
        self.assertTrue(torch.allclose(actual, expected, atol=1e-7))
        ga, gr = torch.autograd.grad(actual, (logits, reference), retain_graph=True, allow_unused=True)
        self.assertIsNone(gr)
        self.assertEqual(float(ga[~selected].abs().sum()), 0)
        self.assertTrue(torch.allclose(ga, torch.autograd.grad(expected, logits)[0], atol=1e-7))


if __name__ == "__main__":
    unittest.main()
