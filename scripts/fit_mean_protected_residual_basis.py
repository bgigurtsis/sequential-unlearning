"""Fixed rank1/4 residual bases with clean negative FIT means protected.

Uses the original68 unit-normalized contrasts, projects them outside
span(M,D_final M), and does NOT normalize again. No diagnostic means enter fit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

try:
    import native_residual_projection_math as geometry
except ModuleNotFoundError:
    from scripts import native_residual_projection_math as geometry

MEANS_SHA256 = '3b4db99329c1afe3d97bddc00c17659dfaf6eaedf0dcfdd3f04c634ec9331c4a'
REFERENCE_SHA256 = 'afc75b21292b18ae2e47d52413d823d0891a66ed6e713aedb910098590044f7c'


def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def verify_source(path, expected):
    actual=sha256_file(path)
    if actual!=expected:raise ValueError('Source hash mismatch: '+str(path))
    return actual


def fit_bases(means, final_scale, *, torch):
    positive,negative=means['fit_positive'],means['fit_negative']
    for value in (positive,negative):
        if value.ndim!=3 or value.shape[1]!=2 or value.dtype!=torch.float64 or value.device.type!='cpu' or not bool(torch.isfinite(value).all()):
            raise ValueError('FIT means must be finite CPU float64 [layers,2,hidden]')
    if positive.shape!=negative.shape or min(positive.shape)<=0:
        raise ValueError('FIT mean shapes differ or are empty')
    d=positive.shape[-1]
    geometry._scale(final_scale,d,torch=torch)
    m=negative.reshape(-1,d).T.contiguous()
    r,rdiag=geometry.orthonormal_basis(torch.cat((m,final_scale[:,None]*m),dim=1),torch=torch)
    contrasts=(positive-negative).reshape(-1,d)
    norms=contrasts.norm(dim=1)
    if not bool((norms>0).all()):raise ValueError('Frozen fit requires every original contrast row nonzero')
    unit=contrasts/norms[:,None]
    residual=unit-(unit@r)@r.T
    _,singular,right=torch.linalg.svd(residual,full_matrices=False)
    tolerance=32*torch.finfo(torch.float64).eps*max(residual.shape)*float(singular[0])
    rank=int((singular>tolerance).sum())
    if rank<4:raise ValueError('Protected contrasts lack rank4')
    outputs,rank_records={},{}
    for target_rank in (1,4):
        u=right[:target_rank].T.contiguous()
        pivots=u.abs().argmax(dim=0)
        u=(u*torch.sign(u[pivots,torch.arange(target_rank)])).contiguous()
        v,closure=geometry.closure_basis(u,final_scale,torch=torch)
        mean_action=float((v.T@m).norm())/max(float(m.norm()),1e-30)
        orthogonality=float((u.T@r).norm())
        if mean_action>1e-10 or orthogonality>1e-10 or not target_rank<=v.shape[1]<=2*target_rank:
            raise RuntimeError('Protected basis failed mean/closure gate')
        outputs[target_rank]={'U':u,'V':v,'final_scale':final_scale}
        rank_records[target_rank]={'concept_rank':target_rank,'closure':closure,'V_mean_action_relative':mean_action,
                                   'U_protected_span_overlap_l2':orthogonality,
                                   'surviving_contrast_energy_captured':float((residual@u).square().sum()/residual.square().sum()),
                                   'original_unit_contrast_energy_captured':float((unit@u).square().sum()/unit.square().sum())}
    diagnostics={'method':'R=orth([M,D_final M]);C=original unit contrasts;Cperp=C-(CR)R^T;single SVD top1/4;no renormalization',
                 'fit_only_keys':['fit_positive','fit_negative'],'original_contrast_count':contrasts.shape[0],
                 'protected_span':rdiag,'protected_contrast_rank':rank,'rank_tolerance':tolerance,
                 'singular_values':singular.tolist(),'remaining_original_unit_energy_fraction':float(residual.square().sum()/unit.square().sum()),
                 'rank_results':rank_records,'post_projection_renormalization':False,
                 'claim':'Orthogonality to stored clean negative FIT means only; not individual-retain protection, updated-model mean preservation, or semantic erasure.'}
    return outputs,diagnostics,{'R':r,'protected_contrasts':residual}


def publish_bases(class_means, reference_basis, output_dir):
    import torch
    from safetensors.torch import load_file,save_file
    try:import apply_checkpoint_delta_dare as checked
    except ModuleNotFoundError:from scripts import apply_checkpoint_delta_dare as checked
    destination=Path(output_dir).absolute()
    if checked._path_lexists(destination):raise FileExistsError(destination)
    source_paths=[Path(class_means).resolve(strict=True),Path(reference_basis).resolve(strict=True)]
    for path in source_paths:
        if path.is_relative_to(destination.resolve()):raise ValueError('Source inside output directory')
    verify_source(class_means,MEANS_SHA256);verify_source(reference_basis,REFERENCE_SHA256)
    implementation={str(Path(path).resolve()):sha256_file(path) for path in (__file__,geometry.__file__,checked.__file__,Path(__file__).with_name('test_fit_mean_protected_residual_basis.py'))}
    torch.set_num_threads(8)
    means=load_file(str(class_means),device='cpu')
    reference=load_file(str(reference_basis),device='cpu')
    if means['fit_positive'].shape!=(34,2,2560):raise ValueError('Production requires34 layers/2positions/2560features')
    bases,diagnostics,geometry_tensors=fit_bases(means,reference['final_scale'],torch=torch)
    verify_source(class_means,MEANS_SHA256);verify_source(reference_basis,REFERENCE_SHA256)
    if any(sha256_file(path)!=expected for path,expected in implementation.items()):raise RuntimeError('Implementation changed')
    destination.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.'+destination.name+'.staging-',dir=destination.parent))
    for rank,tensors in bases.items():save_file({k:v.contiguous() for k,v in tensors.items()},str(stage/f'basis_rank{rank}.safetensors'))
    save_file(geometry_tensors,str(stage/'geometry.safetensors'))
    manifest={path.name:{'sha256':sha256_file(path),'bytes':path.stat().st_size} for path in sorted(stage.iterdir())}
    metadata={'complete':True,'source_class_means':str(source_paths[0]),'source_class_means_sha256':MEANS_SHA256,
              'source_reference_basis':str(source_paths[1]),'source_reference_basis_sha256':REFERENCE_SHA256,
              'implementation':implementation,'torch':torch.__version__,'device':'CPU float64','cpu_threads':torch.get_num_threads(),
              'diagnostics':diagnostics,'artifacts':manifest,'model_forward_passes':0,'evaluation_inputs_used':0}
    (stage/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    checked._fsync_files(stage);checked._fsync_directory(stage)
    checked._publish_directory_no_replace(stage,destination);checked._fsync_directory(destination.parent)
    return metadata


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('class-means','reference-basis','output-dir'):parser.add_argument('--'+name,required=True)
    print(json.dumps(publish_bases(**vars(parser.parse_args())),indent=2))
