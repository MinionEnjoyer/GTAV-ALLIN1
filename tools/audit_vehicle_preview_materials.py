"""Read-only full-catalog shader/UV audit using the production model decoder."""
import concurrent.futures
import json
from pathlib import Path
import tempfile
import time

from allin1.catalog_model_renderer import select_geometries, parked_rotors
from allin1.prelaunch_previews import stock_items, mounted_packs, document, contained, render
from allin1.stock_weapon_previews import extract
from allin1.vehicle_preview_paint import apply_paint, select_paint
from allin1_sdk.native_assets import NativeAssetInspector, load_native_model_scene
from allin1_sdk.compiled_render import _material_properties
from allin1.catalog_model_previews import catalog_names


def audit(project, game, row, output):
    result=dict(model=row['model'], graphics=False, materials=[], errors=[])
    try:
        with tempfile.TemporaryDirectory(prefix='model-',dir=output) as temp:
            work=Path(temp);inspector=NativeAssetInspector(project,game)
            refs=[r for r in row['assets'][:2] if r['path'].lower().endswith('.yft')]
            for index,ref in enumerate(refs):
                asset=extract(project,game,ref,work/f'asset{index}.yft')
                folder=inspector.export_workspace(asset,work/f'decoded{index}',edition='Enhanced')
                manifest=document(folder/'native-workspace.json')
                scene,_,warning=load_native_model_scene(contained(folder,manifest['xml']['path']),name=row['model'],defer_uv_validation=True)
                if scene is None:raise ValueError(str(warning))
                for g in parked_rotors(select_geometries(scene)):
                    if len(refs)==2 and (g.component.startswith('wheel_') != (index==0)):
                        continue
                    bindings=[dict(slot=slot,name=name,path='audit.png',role=(
                        'diffuse' if 'Diffuse' in slot else 'normal' if 'Bump' in slot else
                        'specular' if 'Spec' in slot else 'auxiliary')) for slot,name in g.texture_parameters]
                    record=dict(source_name=g.material_name,semantic=_material_properties(g)[1],texture_bindings=bindings)
                    apply_paint({'materials':[record]},select_paint(row['model']))
                    is_graphic=any(b['role']=='overlay' for b in record['texture_bindings']) or record['semantic']=='decal'
                    result['graphics'] |= is_graphic
                    channels=g.texcoord_sets or (g.texcoords,)
                    uses=[]
                    for b in record['texture_bindings']:
                        if b['role'] not in ('overlay','diffuse','normal','specular'):continue
                        channel=int(b.get('uv_map','UV0')[2:])
                        uses.append((b['slot'],channel))
                        if channel>=len(channels) or len(channels[channel])!=len(g.vertices):
                            result['errors'].append(f"{g.material_name}: {b['slot']} missing UV{channel}")
                    entry=dict(shader=g.material_name,channels=len(channels),uses=uses,graphics=is_graphic,
                               samplers=g.texture_parameters)
                    if entry not in result['materials']:result['materials'].append(entry)
    except Exception as error:result['errors'].append(str(error))
    if result['errors']:
        # Structural flags alone cannot distinguish a transparent blank texture
        # from visible artwork. Exercise the real renderer to resolve these.
        import sys
        work=output/('render-'+row['model']);work.mkdir()
        result['material_flags']=result['errors'][:]
        try:
            render([sys.executable,'-m','allin1.weapon_preview_worker'],
                   {**row,'project':str(project),'game':str(game),'edition':'Enhanced','render_threads':4},
                   work,180)
            result['render_verified']=str(work/'preview.png')
            result['material_warnings']=document(work/'blender/scene.json',32*1024*1024).get('material_warnings',[])
            result['errors']=[]
        except Exception as error:
            result['errors']=[str(error)[-1800:]]
    return result


def main():
    import argparse,sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',required=True,type=Path)
    parser.add_argument('--retry-report',type=Path)
    parser.add_argument('--cache',type=Path)
    args=parser.parse_args()
    project=Path(__file__).resolve().parents[1]
    output=project/'build'/('vehicle-material-audit-'+str(time.time_ns()));output.mkdir()
    previous=document(args.retry_report,32*1024*1024) if args.retry_report else None
    cache=args.cache or (args.retry_report.parent/'discovery' if args.retry_report else output/'discovery')
    cache.mkdir(exist_ok=True)
    report=stock_items([sys.executable,'-m','allin1.weapon_preview_worker'],project,args.game,
                       cache,mounted_packs(project,args.game),lambda *a:None,category='vehicles')
    (output/'discovery.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    active={r['model'] for r in report['items']}
    previous_names={r['model'] for r in previous['vehicles']} if previous else set()
    wanted=({r['model'] for r in previous['vehicles'] if r['errors']} |
            {r['model'] for r in report['items'] if r['model'] not in previous_names}) if previous else None
    rows=[r for r in report['items'] if wanted is None or r['model'] in wanted]
    results=[r for r in previous['vehicles'] if r['model'] in active and r['model'] not in wanted] if previous else []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(audit,project,args.game,row,output) for row in rows]
        for completed,future in enumerate(concurrent.futures.as_completed(futures),1):
            results.append(future.result())
            if completed%25==0:print(f"Audited {completed}/{len(futures)}",flush=True)
    result=dict(catalog_count=len(catalog_names(project,'vehicles')),discovery_cache=str(cache.resolve()),
                vehicles=sorted(results,key=lambda r:r['model']),discovery_errors=report.get('errors',[]))
    (output/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('REPORT',output/'report.json',flush=True)
    print('MODELS',len(results),'GRAPHICS',sum(r['graphics'] for r in results),
          'FAILURES',sum(bool(r['errors']) for r in results),flush=True)


if __name__=='__main__':main()
