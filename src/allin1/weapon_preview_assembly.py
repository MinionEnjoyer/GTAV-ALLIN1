"""Bounded bind-pose attachment assembly, local to the offline preview worker."""
from dataclasses import replace
import numpy as np

def unique_component(roots, name):
    rows=[row for root in roots for row in root.xpath('.//Item[Name=$name]',name=name)]
    if len(rows)!=1:raise ValueError('Missing or ambiguous default component '+name)
    return rows[0]

def bone_matrix(root, name, *, component_root=False):
    from allin1_sdk.native_assets import _model_trs_matrix
    bones=root.findall('Skeleton/Bones/Item')
    if not 0<len(bones)<=512:raise ValueError('Missing or excessive preview skeleton')
    matches=[i for i,b in enumerate(bones) if name and b.findtext('Name','').casefold()==name.casefold()]
    # Component metadata may name AAPClip/AAPScop even when the drawable is
    # rooted at tag zero under its model name (or AAPSight). Never do this for
    # missing parent anchors: that would place attachments at the gun origin.
    if not matches and component_root:
        matches=[i for i,b in enumerate(bones) if b.find('Tag') is not None
                 and b.find('Tag').get('value')=='0' and b.find('ParentIndex').get('value')=='-1']
    if not matches:raise ValueError('Missing or ambiguous preview attachment bone: '+name)
    def world(i):
        result=np.eye(4);seen=[]
        while i>=0:
            if i>=len(bones) or i in seen:raise ValueError('Invalid preview bone hierarchy')
            seen.append(i);b=bones[i];parent=int(b.find('ParentIndex').get('value'))
            if parent < -1:raise ValueError('Invalid preview bone hierarchy')
            local=np.asarray(_model_trs_matrix(b),dtype=float)
            if local.shape!=(4,4) or not np.isfinite(local).all():raise ValueError('Nonfinite preview bind transform')
            result=local@result;i=parent
        if not np.isfinite(result).all():raise ValueError('Nonfinite preview bind transform')
        return result,seen
    result,chain=world(matches[0])
    for index in matches[1:]:
        other,other_chain=world(index)
        tags=[bones[i].find('Tag') for i in (matches[0],index)]
        # Converted drawables can duplicate an anchor as an identity child.
        # Accept only same-tag, same-frame aliases along the same ancestry.
        if (any(t is None for t in tags) or tags[0].get('value')!=tags[1].get('value')
                or not (index in chain or matches[0] in other_chain)
                or not np.allclose(result,other,rtol=0,atol=1e-8)):
            raise ValueError('Missing or ambiguous preview attachment bone: '+name)
    return result

def attach_geometry(parent, child, geometries, parent_bone, child_bone):
    # Match the two attachment frames, including orientation and child pivot.
    try:transform=bone_matrix(parent,parent_bone)@np.linalg.inv(bone_matrix(child,child_bone,component_root=True))
    except np.linalg.LinAlgError as error:raise ValueError('Singular preview attachment transform') from error
    result=[]
    for g in geometries:
        vertices=np.asarray(g.vertices,dtype=float)
        transformed=np.c_[vertices,np.ones(len(vertices))]@transform.T
        if not np.isfinite(transformed).all():raise ValueError('Invalid assembled preview vertices')
        result.append(replace(g,vertices=tuple(map(tuple,transformed[:,:3]))))
    return result
