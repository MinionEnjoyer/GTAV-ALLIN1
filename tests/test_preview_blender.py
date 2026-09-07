import json
import struct
import subprocess
import sys
from pathlib import Path
import pytest
from allin1 import preview_blender as b


@pytest.fixture
def settings(tmp_path,monkeypatch):
    monkeypatch.delenv('BLENDER_EXECUTABLE',raising=False)
    config=tmp_path/'preview-tools.json'
    monkeypatch.setattr(b,'settings_path',lambda:config)
    monkeypatch.setattr(b.shutil,'which',lambda _:None)
    monkeypatch.setenv('ProgramFiles',str(tmp_path/'programs'))
    return config


def test_portable_sdk_blender_discovery(settings,tmp_path):
    exe=tmp_path/'ALLIN1-SDK/build/dependencies/blender-4.5-windows-x64/blender.exe'
    exe.parent.mkdir(parents=True);exe.write_bytes(b'blender')
    assert b.select_blender(tmp_path/'ALLIN1')==exe.resolve()


def test_saved_path_spaces_and_invalid_override(settings,tmp_path):
    exe=tmp_path/'Tools With Spaces/blender.exe';exe.parent.mkdir();exe.touch()
    settings.write_text(json.dumps({'blender_executable':str(exe)}))
    assert b.select_blender(tmp_path)==exe.resolve()
    exe.unlink()
    with pytest.raises(ValueError,match='Invalid Blender override'): b.select_blender(tmp_path)


def test_missing_blender_actionable(settings,tmp_path):
    with pytest.raises(ValueError,match='Existing artwork is retained'): b.select_blender(tmp_path)


def test_blender_identity_tracks_content_not_machine_path(tmp_path):
    first=tmp_path/'a';second=tmp_path/'b';first.write_bytes(b'a');second.write_bytes(b'a')
    assert b.identity(first)==b.identity(second)
    second.write_bytes(b'b');assert b.identity(first)!=b.identity(second)


def test_dds_a8_and_truncation(tmp_path):
    from allin1.vehicle_blender_renderer import open_texture
    header=bytearray(128);header[:4]=b'DDS '
    struct.pack_into('<I',header,4,124);struct.pack_into('<III',header,12,1,2,2)
    struct.pack_into('<I',header,76,32);struct.pack_into('<I',header,80,2);struct.pack_into('<I',header,88,8)
    path=tmp_path/'mask.dds';path.write_bytes(header+b'\x00\xff')
    with open_texture(path) as image:
        assert image.size==(2,1) and image.getpixel((1,0))==(255,255,255,255)
    path.write_bytes(header+b'\x00')
    with pytest.raises(ValueError,match='Truncated'):open_texture(path)


def test_vehicle_program_compiles_without_blender_import():
    from allin1.vehicle_blender_scene import SCENE_SCRIPT
    compile(SCENE_SCRIPT,'vehicle-scene','exec')


def test_worker_selection_does_not_load_renderer_or_numpy(tmp_path):
    from allin1.preview_policy import STUDIO_BACKDROP, VEHICLE_TEXTURES, THROWABLE_TEXTURES
    backdrop=tmp_path/STUDIO_BACKDROP;backdrop.parent.mkdir(parents=True);backdrop.write_bytes(b'fixture')
    for name in VEHICLE_TEXTURES + THROWABLE_TEXTURES:
        texture=tmp_path/name;texture.parent.mkdir(exist_ok=True);texture.write_bytes(b'fixture')
    worker=tmp_path/'tools/WeaponPreview/WeaponPreview.exe';worker.parent.mkdir(parents=True);worker.write_bytes(b'worker')
    helper=tmp_path/'tools/RpfPatcher';helper.mkdir();(helper/'fixture.dll').write_bytes(b'helper')
    code='from allin1.prelaunch_previews import worker_command; import sys; worker_command(sys.argv[1]); assert "numpy" not in sys.modules; assert "allin1.weapon_card_renderer" not in sys.modules'
    subprocess.run([sys.executable,'-c',code,str(tmp_path)],check=True,timeout=15,stdin=subprocess.DEVNULL)
