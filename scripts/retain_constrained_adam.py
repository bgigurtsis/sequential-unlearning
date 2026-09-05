"""Opt-in Euclidean projection of actual Adam displacement, not its gradients.

Only the <=3 dimensional active-set problem is solved densely. Tensor-list
inner products accumulate in float64 chunks; optimizer moments are untouched.
The stored FP32 displacement is checked with an explicit numerical allowance.
"""
import hashlib
import itertools
import json
import math


ABS_TOL = 1e-7
REL_TOL = 1e-5


def dot(left, right, *, torch):
    total = 0.0
    for a, b in zip(left, right, strict=True):
        if a is None or b is None:
            continue
        if a.shape != b.shape:
            raise ValueError("gradient/parameter shapes differ")
        av, bv = a.reshape(-1), b.reshape(-1)
        subtotal = torch.zeros((), dtype=torch.float64, device=a.device)
        for start in range(0, av.numel(), 1048576):
            subtotal += (av[start:start+1048576].double() * bv[start:start+1048576].double()).sum()
        total += float(subtotal)
    if not math.isfinite(total):
        raise FloatingPointError("nonfinite tensor-list inner product")
    return total


def solve_halfspaces(gram, proposal_dots, *, torch):
    """Return multipliers for normalized rows; enumerate all KKT active sets."""
    gram = torch.as_tensor(gram, dtype=torch.float64, device="cpu")
    b = torch.as_tensor(proposal_dots, dtype=torch.float64, device="cpu")
    m = b.numel()
    if m > 3 or gram.shape != (m, m) or not bool(torch.isfinite(gram).all() and torch.isfinite(b).all()):
        raise ValueError("expected finite square Gram for at most three constraints")
    if not torch.allclose(gram, gram.T, atol=1e-12, rtol=1e-12):
        raise ValueError("Gram is not symmetric")
    if m and float(torch.linalg.eigvalsh(gram).min()) < -1e-10:
        raise ValueError("Gram is not positive semidefinite")
    tolerance = 1e-11 * max(1.0, float(b.abs().max()) if m else 0.0)
    candidates = []
    for size in range(m + 1):
        for active in itertools.combinations(range(m), size):
            lam = torch.zeros(m, dtype=torch.float64)
            if active:
                ix = torch.tensor(active)
                sub = gram[ix[:, None], ix[None, :]]
                lam[ix] = torch.linalg.pinv(sub, rtol=1e-12, atol=0.0, hermitian=True) @ b[ix]
            residual = b - gram @ lam
            if bool((lam < -tolerance).any()) or bool((residual > tolerance).any()):
                continue
            if active and float(residual[list(active)].abs().max()) > tolerance:
                continue
            if m and float((lam * residual).abs().max()) > tolerance * max(1.0, float(lam.abs().max())):
                continue
            candidates.append((float(lam @ gram @ lam), lam, residual, active))
    if not candidates:
        raise FloatingPointError("no feasible KKT active set; no fallback update")
    removed_sq, lam, residual, active = min(candidates, key=lambda item: item[0])
    return lam.tolist(), {"active_set": list(active), "ideal_normalized_post_dots": residual.tolist(),
                         "multipliers": lam.tolist(), "ideal_removed_squared_norm": removed_sq,
                         "kkt_tolerance": tolerance}


def preservation_gradients(losses, parameters, *, torch):
    """Losses already include their objective coefficients; no .grad mutation."""
    result = []
    for loss in losses:
        if not loss.requires_grad:
            raise ValueError("every preservation component must have a gradient graph")
        result.append(tuple(g.detach() if g is not None else None for g in
                            torch.autograd.grad(loss, parameters, retain_graph=True, allow_unused=True)))
    return result


def parameter_identity(named_parameters):
    inventory = [{"name": name, "shape": list(p.shape), "dtype": str(p.dtype)} for name, p in named_parameters]
    return {"tensor_count": len(inventory), "numel": sum(p.numel() for _, p in named_parameters),
            "inventory_sha256": hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()}


def constrained_adam_step(optimizer, named_parameters, component_gradients, *, mode, torch):
    """Apply Adam, project its stored proposal, and roll back weights on failure.

    On failure the process must abort: optimizer moments have already advanced.
    There is deliberately no retry, zero-update fallback, or checkpoint here.
    """
    if mode == "none":
        optimizer.step()
        return None
    if mode not in ("aggregate", "separate"):
        raise ValueError("invalid constraint mode")
    named_parameters = list(named_parameters)
    params = [p for _, p in named_parameters]
    if not params or any(p.dtype != torch.float32 or not p.requires_grad for p in params):
        raise ValueError("projection requires trainable FP32 master parameters")
    if len(component_gradients) != 3 or any(len(g) != len(params) for g in component_gradients):
        raise ValueError("exactly three complete component gradient lists are required")
    before = [p.detach().clone() for p in params]
    total_gradients = [p.grad for p in params]
    aggregate = [sum((g[i] for g in component_gradients if g[i] is not None), torch.zeros_like(p))
                 for i, p in enumerate(params)]
    constraints = component_gradients if mode == "separate" else [aggregate]
    component_norms = [math.sqrt(max(0.0, dot(g, g, torch=torch))) for g in component_gradients]
    norms = [math.sqrt(max(0.0, dot(g, g, torch=torch))) for g in constraints]
    eligible = [i for i, n in enumerate(norms) if n > 0.0]
    try:
        optimizer.step()
        proposal = [p.detach() - old for p, old in zip(params, before, strict=True)]
        pre_norm = math.sqrt(max(0.0, dot(proposal, proposal, torch=torch)))
        pre_components = [dot(g, proposal, torch=torch) for g in component_gradients]
        pre_aggregate = dot(aggregate, proposal, torch=torch)
        pre_target = dot(total_gradients, proposal, torch=torch) - sum(pre_components)
        gram = [[dot(constraints[i], constraints[j], torch=torch) / (norms[i] * norms[j])
                 for j in eligible] for i in eligible]
        b = [dot(constraints[i], proposal, torch=torch) / norms[i] for i in eligible]
        multipliers, solver = solve_halfspaces(torch.tensor(gram, dtype=torch.float64).reshape(len(eligible), len(eligible)), b, torch=torch)
        # Apply correction directly to Adam's stored proposal. A feasible proposal
        # is left bit-identical, including signed zeros and sub-ULP values.
        with torch.no_grad():
            for index, p in enumerate(params):
                correction = torch.zeros_like(p)
                for multiplier, i in zip(multipliers, eligible, strict=True):
                    g = constraints[i][index]
                    if g is not None and multiplier != 0.0:
                        correction.add_(g, alpha=multiplier / norms[i])
                if any(v != 0.0 for v in multipliers):
                    p.sub_(correction)
        stored = [p.detach() - old for p, old in zip(params, before, strict=True)]
        stored_norm = math.sqrt(max(0.0, dot(stored, stored, torch=torch)))
        bound = ABS_TOL + REL_TOL * stored_norm
        post_dots = [dot(constraints[i], stored, torch=torch) / norms[i] for i in eligible]
        if any(value > bound for value in post_dots):
            raise FloatingPointError(f"stored FP32 delta infeasible: {post_dots}, bound={bound}")
        if stored_norm > pre_norm + bound:
            raise FloatingPointError("stored projection unexpectedly increases displacement norm")
        removed = [a - b for a, b in zip(proposal, stored, strict=True)]
        removed_norm = math.sqrt(max(0.0, dot(removed, removed, torch=torch)))
        post_components = [dot(g, stored, torch=torch) for g in component_gradients]
        return {"mode": mode, "source_parameters": parameter_identity(named_parameters),
                "component_names": ["weighted_generic_jsd", "weighted_chat_jsd", "weighted_ordinary_ce"],
                "component_gradient_norms": component_norms, "component_pre_dots": pre_components,
                "component_post_dots": post_components,
                "aggregate_pre_dot": pre_aggregate, "aggregate_post_dot": dot(aggregate, stored, torch=torch),
                "target_pre_dot": pre_target,
                "target_post_dot": dot(total_gradients, stored, torch=torch) - sum(post_components),
                "selected_constraint_indices": eligible, "zero_constraint_indices": [i for i in range(len(norms)) if i not in eligible],
                "selected_gradient_norms": norms, "normalized_pre_dots": b, "normalized_stored_post_dots": post_dots,
                "proposal_norm": pre_norm, "stored_delta_norm": stored_norm, "removed_norm": removed_norm,
                "removed_fraction": removed_norm / pre_norm if pre_norm else 0.0,
                "stored_update_fraction": stored_norm / pre_norm if pre_norm else 0.0,
                "feasibility_bound": bound, "absolute_tolerance": ABS_TOL, "relative_tolerance": REL_TOL,
                "optimizer_moments": "unchanged after nominal Adam step", "solver": solver}
    except Exception:
        with torch.no_grad():
            for p, old in zip(params, before, strict=True):
                p.copy_(old)
        raise
