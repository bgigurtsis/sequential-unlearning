"""Publication-surface tests; numerical projection is independently tested elsewhere."""
import unittest
try:
    import publish_native_residual_projection as publish
except ModuleNotFoundError:
    from scripts import publish_native_residual_projection as publish


class PublicationSurfaceTests(unittest.TestCase):
    def source(self):
        return {name: {'shape': [3, 4], 'dtype': 'torch.bfloat16', 'sha256': 'old'}
                for name in (*publish.edit_surface(), publish.FINAL_NORM)}

    def test_exact_surface_and_postnorm_mapping(self):
        surface = publish.edit_surface()
        self.assertEqual(len(surface), 69)
        self.assertIsNone(surface[publish.EMBEDDING])
        self.assertEqual(surface[publish.PREFIX + '.layers.0.self_attn.o_proj.weight'],
                         publish.PREFIX + '.layers.0.post_attention_layernorm.weight')
        self.assertEqual(surface[publish.PREFIX + '.layers.33.mlp.down_proj.weight'],
                         publish.PREFIX + '.layers.33.post_feedforward_layernorm.weight')
        self.assertNotIn(publish.FINAL_NORM, surface)

    def test_native_identity_and_allowed_write(self):
        original = self.source()
        changed = {k: dict(v) for k, v in original.items()}
        self.assertEqual(publish.verify_locality(original, changed, identity=True), [])
        changed[publish.EMBEDDING]['sha256'] = 'new'
        self.assertEqual(publish.verify_locality(original, changed), [publish.EMBEDDING])
        with self.assertRaises(ValueError):
            publish.verify_locality(original, changed, identity=True)

    def test_norm_edit_namespace_shape_and_dtype_rejected(self):
        original = self.source()
        variants = [dict(original, surprise=dict(next(iter(original.values())))),
                    {k: v for k, v in original.items() if k != publish.EMBEDDING}]
        for key, field, value in [(publish.FINAL_NORM, 'sha256', 'changed'),
                                  (publish.EMBEDDING, 'shape', [4, 3]),
                                  (publish.EMBEDDING, 'dtype', 'torch.float32')]:
            changed = {k: dict(v) for k, v in original.items()}
            changed[key][field] = value
            variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed.keys()), self.assertRaises(ValueError):
                publish.verify_locality(original, changed)


if __name__ == '__main__':
    unittest.main()
