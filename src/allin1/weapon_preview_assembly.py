"""Bounded bind-pose attachment assembly, local to the offline preview worker."""
from dataclasses import replace
import numpy as np

def unique_component(roots, name):
    rows=[row for root in roots for row in root.xpath('.//Item[Name=$name]',name=name)]
    if len(rows)!=1:raise ValueError('Missing or ambiguous default component '+name)
    return rows[0]

def bone_matrix(root, name):
    from allin1_sdk.native_assets import _model_trs_matrix
    bones=root.findall('Skeleton/Bones/Item')
    matches=[i for i,b in enumerate(bones) if b.findtext('Name','').casefold()==name.casefold()]
    if len(matches)!=1:raise ValueError('Missing or ambiguous preview attachment bone: '+name)
    def world(i, seen=()):
        if not 0<=i<len(bones) or i in seen:raise ValueError('Invalid preview bone hierarchy')
        b=bones[i];parent=int(b.find('ParentIndex').get('value'))
        local=np.asarray(_model_trs_matrix(b),dtype=float)
        return world(parent,seen+(i,))@local if parent>=0 else local
    result=world(matches[0])
    if not np.isfinite(result).all():raise ValueError('Nonfinite preview bind transform')
    return result

def attach_geometry(parent, child, geometries, parent_bone, child_bone):
    # Match the two attachment frames, including orientation and child pivot.
    transform=bone_matrix(parent,parent_bone)@np.linalg.inv(bone_matrix(child,child_bone))
    result=[]
    for g in geometries:
        vertices=np.asarray(g.vertices,dtype=float)
        transformed=np.c_[vertices,np.ones(len(vertices))]@transform.T
        if not np.isfinite(transformed).all():raise ValueError('Invalid assembled preview vertices')
        result.append(replace(g,vertices=tuple(map(tuple,transformed[:,:3]))))
    return result
