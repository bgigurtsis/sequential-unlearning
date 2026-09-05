"""Cached Gemma3 text forwarding, qualified against the installed full forward.

No intervention hooks are needed for deployment. Cache entries remain on GPU;
the capture utility excludes padding from the two record-level positions.
"""
import torch
from transformers.models.gemma3.modeling_gemma3 import (
    create_causal_mask, create_sliding_window_causal_mask,
)
try:
    import capture_residual_contrast as capture
except ModuleNotFoundError:
    from scripts import capture_residual_contrast as capture


def make_batch(text, tokenized, pad_token_id):
    if text.config.use_bidirectional_attention:
        raise ValueError('Only causal text configuration qualified')
    device = next(text.parameters()).device
    ids, valid, answer, last = capture.padded_batch(
        tokenized, pad_token_id, torch=torch, device=device)
    hidden = text.embed_tokens(ids)
    positions = torch.arange(ids.shape[1], device=device).unsqueeze(0)
    args = dict(config=text.config, inputs_embeds=hidden,
                attention_mask=valid.long(), past_key_values=None,
                position_ids=positions)
    masks = {'full_attention': create_causal_mask(**args),
             'sliding_attention': create_sliding_window_causal_mask(**args)}
    rotary = {kind: text.rotary_emb(hidden, positions, kind)
              for kind in set(text.config.layer_types)}
    return dict(ids=ids, valid=valid, answer=answer, last=last, hidden=hidden,
                masks=masks, rotary=rotary, positions=positions)


def attention_half(layer, batch, layer_type):
    residual = batch['hidden']
    normalized = layer.input_layernorm(residual)
    out, _ = layer.self_attn(
        hidden_states=normalized, position_embeddings=batch['rotary'][layer_type],
        attention_mask=batch['masks'][layer_type], position_ids=batch['positions'],
        past_key_values=None)
    return residual + layer.post_attention_layernorm(out)


def mlp_half(layer, hidden):
    return hidden + layer.post_feedforward_layernorm(
        layer.mlp(layer.pre_feedforward_layernorm(hidden)))


def site_activations(batches, norm):
    return torch.cat([capture.reduce_hidden(norm(b['hidden']), b['answer'],
                      b['last'], torch=torch) for b in batches])


def qualify_forward(text, tokenized, pad_token_id):
    """Exact native BF16 parity at all34 blocks and final norm on16 records."""
    selected = tokenized[:8] + tokenized[520:528]
    if len(selected) != 16:
        raise ValueError('Qualification requires the full pinned1040 input order')
    receipts = []
    for start in (0, 8):
        batch = make_batch(text, selected[start:start+8], pad_token_id)
        reference, handles = {}, []
        def hook(index):
            def save(module, inputs, output):
                reference[index] = output.detach().cpu()
            return save
        try:
            for i, layer in enumerate(text.layers):
                handles.append(layer.register_forward_hook(hook(i)))
            expected = text(input_ids=batch['ids'], attention_mask=batch['valid'].long(),
                            use_cache=False).last_hidden_state.detach().cpu()
        finally:
            for handle in handles:
                handle.remove()
        for i, layer in enumerate(text.layers):
            batch['hidden'] = mlp_half(layer, attention_half(layer, batch, text.config.layer_types[i]))
            if not torch.equal(batch['hidden'].cpu(), reference[i]):
                error = float((batch['hidden'].cpu().float()-reference[i].float()).abs().max())
                raise RuntimeError(f'Cached forward differs at layer{i}: {error}')
        if not torch.equal(text.norm(batch['hidden']).cpu(), expected):
            raise RuntimeError('Cached final normalization differs')
        receipts.append({'records':8, 'width':batch['ids'].shape[1], 'all_blocks_exact':True,
                         'final_norm_exact':True, 'right_padding_tokens':int((~batch['valid']).sum())})
    return {'batches':receipts, 'max_absolute_error':0., 'sites_compared':70,
            'claim':'Exact for these16 qualification records at native BF16, not every possible input'}
