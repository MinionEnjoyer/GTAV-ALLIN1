import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image
import pytest
from allin1 import default_previews as p
from tests.test_desktop_service import service, apply


@pytest.fixture
def pack(tmp_path):
    project, game, cache = (tmp_path / name for name in ("project", "game", "cache"))
    (project / "data").mkdir(parents=True)
    game.mkdir()
    image = io.BytesIO()
    Image.new("RGB", (512, 320), "green").save(image, format="PNG")
    data = image.getvalue()
    filename = "weapon_pistol." + "a" * 64 + ".png"
    index = dict(schema_version=1, owner=p.OWNER, images={"weapon_pistol": filename},
                 image_sha256={filename: hashlib.sha256(data).hexdigest()})
    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("index.json", json.dumps(index))
        z.writestr(filename, data)
    asset = dict(url="https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/download/gbay-previews-2026-09-07/gbay-weapons.zip",
                 sha256=p.sha(archive), bytes=archive.stat().st_size, count=1)
    manifest = dict(schema_version=1, version="gbay-previews-2026-09-07", categories={"weapons": asset})
    (project / "data/default_previews.json").write_text(json.dumps(manifest))
    return project, game, cache, archive, asset, index


def test_download_preserves_generated_and_reuses_cache_across_editions(pack, monkeypatch):
    project, game, cache, archive, asset, index = pack
    calls = []
    def download(asset, target, progress):
        calls.append(asset["url"])
        shutil.copyfile(archive, target)
    monkeypatch.setattr(p, "_download", download)
    custom = game / p.BASE / "generated-weapons/custom.png"
    custom.parent.mkdir(parents=True)
    custom.write_bytes(b"USER ARTWORK")
    assert p.install(project, game, cache, categories=["weapons"])["counts"] == {"weapons": 1}
    assert custom.read_bytes() == b"USER ARTWORK"
    assert json.loads((game / p.BASE / "default-weapons/index.json").read_text()) == index
    p.install(project, game.parent / "Legacy", cache, categories=["weapons"])
    assert len(calls) == 1


@pytest.mark.parametrize("damage", ["traversal", "duplicate", "symlink", "unlisted", "image_hash", "owner", "oversize", "identity"])
def test_archive_rejects_untrusted_contents_before_writes(pack, damage):
    _, game, _, archive, asset, index = pack
    filename = next(iter(index["images"].values()))
    with zipfile.ZipFile(archive) as z: data = z.read(filename)
    if damage == "image_hash": index["image_sha256"][filename] = "b" * 64
    if damage == "owner": index["owner"] = "other"
    if damage == "identity": index["images"] = {"weapon_other": filename}
    if damage == "unlisted": index["images"] = {"weapon_pistol": "other.png"}
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("index.json", json.dumps(index))
        if damage == "symlink":
            member = zipfile.ZipInfo(filename); member.external_attr = 0o120777 << 16
            z.writestr(member, data)
        else: z.writestr("../outside.png" if damage == "traversal" else filename, b"x" * (p.MAX_IMAGE + 1) if damage == "oversize" else data)
        if damage == "duplicate":
            with pytest.warns(UserWarning): z.writestr(filename, data)
    asset.update(bytes=archive.stat().st_size, sha256=p.sha(archive))
    with pytest.raises(ValueError): p.validate_archive(archive, asset)
    assert list(game.iterdir()) == []


def test_tampered_download_and_existing_foreign_index_never_overwrite(pack, monkeypatch):
    project, game, cache, archive, asset, _ = pack
    def bad_download(asset, target, progress): target.write_bytes(b"tampered")
    monkeypatch.setattr(p, "_download", bad_download)
    with pytest.raises(ValueError, match="mismatch"): p.install(project, game, cache, categories=["weapons"])
    assert list(game.iterdir()) == []
    monkeypatch.setattr(p, "_download", lambda a, target, progress: shutil.copyfile(archive, target))
    index = game / p.BASE / "default-weapons/index.json"
    index.parent.mkdir(parents=True); index.write_text('{"owner":"someone-else"}')
    with pytest.raises(ValueError, match="another owner"): p.install(project, game, cache, categories=["weapons"])
    assert index.read_text() == '{"owner":"someone-else"}'


@pytest.mark.parametrize("selection", [[], ["bogus"], ["weapons", "weapons"], "weapons", [{}]])
def test_invalid_categories(pack, selection):
    with pytest.raises(ValueError): p.plan(pack[0], selection)


def test_redirect_and_truncation_are_rejected(pack):
    *_, asset, index = pack
    pack[2].mkdir()
    class Response(io.BytesIO):
        def geturl(self): return "http://localhost/secret"
    with pytest.raises(ValueError, match="redirect"):
        p._download(asset, pack[2] / "bad.zip", lambda *_: None, opener=lambda *a, **kw: Response())
    class ShortResponse(io.BytesIO):
        def geturl(self): return asset["url"]
    with pytest.raises(ValueError, match="Incomplete"):
        p._download(asset, pack[2] / "short.zip", lambda *_: None, opener=lambda *a, **kw: ShortResponse(b"short"))


def test_review_api_binds_manifest_and_requires_game_write_authority(service, pack, monkeypatch):
    shutil.copyfile(pack[0] / "data/default_previews.json", service.project / "data/default_previews.json")
    review = service.review({"action": "download_previews", "categories": ["weapons"]})
    assert review["preview_download"]["count"] == 1
    assert review["game_write"]
    calls = []
    monkeypatch.setattr(p, "install", lambda *a, **kw: calls.append(kw) or {"counts": {"weapons": 1}})
    applied = service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})
    assert applied["result"]["counts"] == {"weapons": 1}
    assert calls[0]["categories"] == ["weapons"]
    service.allow_game_writes = False
    with pytest.raises(ValueError, match="authority"):
        service.review({"action": "download_previews", "categories": ["weapons"]})


def test_changed_manifest_requires_new_review(service, pack):
    target = service.project / "data/default_previews.json"
    shutil.copyfile(pack[0] / "data/default_previews.json", target)
    review = service.review({"action": "download_previews", "categories": ["weapons"]})
    data = json.loads(target.read_text()); data["categories"]["weapons"]["count"] = 2
    target.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="changed"):
        service.apply({"review_id": review["review_id"], "review_sha256": review["review_sha256"], "confirmed": True})


def test_bundled_manifest_is_packaged_resource():
    from allin1.release import collect_public_files
    root = Path(__file__).resolve().parents[1]
    public = {path.relative_to(root).as_posix() for path in collect_public_files(root, require_toolchain=False)}
    assert "data/default_previews.json" in public
    assert p.plan(root)["count"] == 1056


def test_bundled_manifest_pins_public_launcher_releases():
    root = Path(__file__).resolve().parents[1]
    plan = p.plan(root)
    prefix = "https://github.com/MinionEnjoyer/GTAV-ALLIN1/releases/download/"
    assert all(asset["url"].startswith(prefix + plan["version"] + "/gbay-")
               for asset in plan["assets"])


def test_download_exposed_by_public_agent_and_cli_contract():
    from allin1.launcher_api import contract
    catalog = contract()
    action = next(a for a in catalog["actions"] if a["name"] == "download_previews")
    assert action["risk"] == "game_write"
    review = next(o for o in catalog["operations"] if o["name"] == "review")
    schema = next(s for s in review["input_schema"]["oneOf"] if s["properties"]["action"]["const"] == "download_previews")
    assert schema["properties"]["categories"]["type"] == "array"
