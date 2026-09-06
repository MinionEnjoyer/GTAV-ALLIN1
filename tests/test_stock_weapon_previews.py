import json
import os
import subprocess
from pathlib import Path
import pytest
from allin1 import stock_weapon_previews as s
from allin1 import prelaunch_previews as p


def test_catalog_excludes_throwables_even_misc_acid_package(tmp_path):
    (tmp_path/'data').mkdir()
    (tmp_path/'data/weapons.toml').write_text('''
[[weapons]]
name="WEAPON_PISTOL"
category="pistols"
[[weapons]]
name="WEAPON_KNIFE"
category="melee"
[[weapons]]
name="WEAPON_GRENADE"
category="throwables"
[[weapons]]
name="WEAPON_ACIDPACKAGE"
category="misc"
''')
    assert s.catalog_names(tmp_path)==['WEAPON_KNIFE','WEAPON_PISTOL']


@pytest.mark.parametrize('path',['../a','x/../a','C:/a','/a','a\\b','a\nb','x//y'])
def test_archive_entry_paths_block_traversal(path):
    with pytest.raises(ValueError):s.safe_virtual(path)


def test_nested_archive_paths_and_root_archive():
    assert s.safe_virtual('',archive=True)==''
    assert s.safe_virtual('x/weapons.rpf!weapons_hi.rpf',archive=True)=='x/weapons.rpf!weapons_hi.rpf'


def test_overlay_union_retains_enhanced_split_siblings(tmp_path):
    stock=tmp_path/'update/x64/dlcpacks/mpfixture';stock.mkdir(parents=True)
    overlay=tmp_path/'mods/update/x64/dlcpacks/mpfixture';overlay.mkdir(parents=True)
    for path in (stock/'dlc.rpf',stock/'dlc1.rpf',overlay/'dlc.rpf'):path.write_bytes(b'rpf')
    assert set(s.archives(tmp_path,{'mpfixture'}))=={overlay/'dlc.rpf',stock/'dlc1.rpf'}


def test_stock_invalidation_does_not_rehash_large_archives(tmp_path,monkeypatch):
    path=tmp_path/'x64e.rpf';path.write_bytes(b'first')
    item={'kind':'stock','assets':[{'archive':'x64e.rpf','state':s.file_state(path)}]}
    monkeypatch.setattr(p,'sha',lambda *_:pytest.fail('Must not hash gigabytes per weapon/cache hit'))
    assert p.source_unchanged(tmp_path,item)
    path.write_bytes(b'changed-source')
    assert not p.source_unchanged(tmp_path,item)


def test_stock_extraction_blocks_changed_source_before_helper(tmp_path,monkeypatch):
    path=tmp_path/'x64e.rpf';path.write_bytes(b'first')
    ref={'archive':'x64e.rpf','state':s.file_state(path),'archive_path':'','path':'weapons/pistol.ydr'}
    path.write_bytes(b'changed')
    monkeypatch.setattr(s.subprocess,'run',lambda *_args,**_kw:pytest.fail('Changed source must not be extracted'))
    with pytest.raises(ValueError,match='source changed'):s.extract(tmp_path,tmp_path,ref,tmp_path/'out.ydr')


def test_installed_catalog_selection_matches_gbay_source():
    root=Path(__file__).resolve().parents[1]
    names=s.catalog_names(root)
    assert 'WEAPON_PISTOL' in names and 'WEAPON_KNIFE' in names
    assert 'WEAPON_GRENADE' not in names and 'WEAPON_MOLOTOV' not in names
    assert len(names)>80


def test_inventory_uses_supported_exact_extraction_and_reuses_cache(tmp_path,monkeypatch):
    game=tmp_path/'game';game.mkdir();archive=game/'x64e.rpf';archive.write_bytes(b'archive')
    cache=tmp_path/'cache';cache.mkdir();calls=[]
    entries=[{'name':'weapons.meta','path':'common/data/weapons.meta','archive_path':'nested.rpf','kind':'binary'},
             {'name':'w_pi_pistol.ydr','path':'w_pi_pistol.ydr','archive_path':'nested.rpf','kind':'resource'}]
    def run(args,**kwargs):
        calls.append(args[1])
        if args[1]=='index-json':Path(args[-1]).write_text(json.dumps({'entries':entries}))
        elif args[1]=='extract-virtual-entries':
            assert Path(args[4]).read_text()=='nested.rpf\tcommon/data/weapons.meta\t0.meta\n'
            output=Path(args[-1]);assert not output.exists();output.mkdir()
            (output/'0.meta').write_text('<Root><Item type="CWeaponInfo"><Name>WEAPON_PISTOL</Name><Model>w_pi_pistol</Model></Item></Root>')
        else:pytest.fail('Unsupported helper command: '+args[1])
    monkeypatch.setattr(s.subprocess,'run',run)
    first=s.inventory(tmp_path,game,archive,cache,'helper-1')
    assert first['definitions']['WEAPON_PISTOL']['model']=='w_pi_pistol'
    assert s.inventory(tmp_path,game,archive,cache,'helper-1')==first
    assert calls==['index-json','extract-virtual-entries']


@pytest.mark.windows_integration
@pytest.mark.skipif(os.name!='nt' or os.environ.get('ALLIN1_RUN_TOOL_INTEGRATION')!='1',reason='Opt-in compiled Windows archive helper')
@pytest.mark.parametrize('filename',['../escape.meta','C:/escape.meta','nested/escape.meta'])
def test_batch_helper_rejects_unsafe_outputs_before_reading_game(tmp_path,filename):
    helper=Path(__file__).resolve().parents[1]/'tools/RpfPatcher/RpfPatcher.exe'
    manifest=tmp_path/'request.tsv';manifest.write_text('\tweapons.meta\t'+filename+'\n')
    output=tmp_path/'new-output'
    result=subprocess.run([str(helper),'extract-virtual-entries',str(tmp_path),str(tmp_path/'missing.rpf'),str(manifest),str(output)],capture_output=True,text=True)
    assert result.returncode!=0 and 'Unsafe or duplicate' in result.stderr
    assert not output.exists()


@pytest.mark.windows_integration
@pytest.mark.skipif(os.name!='nt' or os.environ.get('ALLIN1_RUN_TOOL_INTEGRATION')!='1',reason='Opt-in compiled Windows archive helper')
def test_batch_helper_never_overwrites_existing_output(tmp_path):
    helper=Path(__file__).resolve().parents[1]/'tools/RpfPatcher/RpfPatcher.exe'
    output=tmp_path/'existing';output.mkdir();(output/'user.meta').write_text('keep')
    result=subprocess.run([str(helper),'extract-virtual-entries',str(tmp_path),str(tmp_path/'missing.rpf'),str(tmp_path/'missing.tsv'),str(output)],capture_output=True,text=True)
    assert result.returncode!=0 and 'new directory' in result.stderr
    assert (output/'user.meta').read_text()=='keep'
