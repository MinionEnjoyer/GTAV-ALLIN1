import hashlib
import json
import subprocess

import pytest
from PIL import Image

from allin1.preview_inventory import preview_counts
from allin1.prelaunch_previews import PUBLIC
from tests.test_desktop_service import service


@pytest.fixture
def roots(tmp_path):
    project = tmp_path / 'project'
    game = tmp_path / 'game'
    (project / 'data').mkdir(parents=True)
    game.mkdir()
    (project / 'data/weapons.toml').write_text('''[[weapons]]
name="WEAPON_PISTOL"
category="pistols"
[[weapons]]
name="WEAPON_GRENADE"
category="throwables"
''')
    (project / 'data/vehicles.toml').write_text('''[[vehicles]]
model="adder"
[[vehicles]]
model="sultan"
''')
    (project / 'data/story_vehicles.json').write_text('{"vehicles":[{"model":"adder"}]}')
    (project / 'prices_gear.toml').write_text('')
    return project, game


def publish(game, category, names):
    public = game / PUBLIC.replace('generated-weapons', 'generated-' + category)
    public.mkdir(parents=True)
    images = {}
    for name in names:
        filename = name + '.' + 'a' * 64 + '.png'
        Image.new('RGB', (512, 320)).save(public / filename)
        images[name] = filename
    (public / 'index.json').write_text(json.dumps(dict(schema_version=1, owner='allin1.prelaunch-previews', images=images)))
    return public, images


def test_counts_are_deduplicated_category_specific_read_only_and_no_workers(roots, monkeypatch):
    project, game = roots
    publish(game, 'weapons', ['weapon_pistol', 'weapon_grenade', 'weapon_orphan'])
    publish(game, 'vehicles', ['adder'])
    def forbidden(*a, **kw):
        pytest.fail('Counting must not spawn discovery/render processes')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    before = sorted(str(p.relative_to(game)) for p in game.rglob('*'))
    result = preview_counts(project, game)
    assert result['weapons'] == dict(existing=2, total=2, status='available')
    assert result['vehicles'] == dict(existing=1, total=2, status='available')
    assert result['gear'] == dict(existing=0, total=10, status='available')
    assert sorted(str(p.relative_to(game)) for p in game.rglob('*')) == before
    other = game.parent / 'other edition'
    other.mkdir()
    assert preview_counts(project, other)['weapons']['existing'] == 0


def test_recheck_reads_newly_published_images(roots):
    project, game = roots
    assert preview_counts(project, game)['vehicles']['existing'] == 0
    publish(game, 'vehicles', ['adder', 'sultan'])
    assert preview_counts(project, game)['vehicles'] == dict(existing=2, total=2, status='available')


def test_downloaded_defaults_count_without_double_counting_generated(roots):
    project, game = roots
    public, images = publish(game, 'vehicles', ['adder', 'sultan'])
    defaults = public.with_name('default-vehicles')
    public.rename(defaults)
    data = json.loads((defaults / 'index.json').read_text())
    data['owner'] = 'allin1.default-previews'
    (defaults / 'index.json').write_text(json.dumps(data))
    publish(game, 'vehicles', ['adder'])
    assert preview_counts(project, game)['vehicles']['existing'] == 2


@pytest.mark.parametrize('damage', ['missing', 'empty', 'wrong_size', 'traversal'])
def test_bad_or_missing_images_not_counted(roots, damage):
    project, game = roots
    public, images = publish(game, 'weapons', ['weapon_pistol'])
    path = public / images['weapon_pistol']
    if damage == 'missing':
        path.unlink()
    elif damage == 'empty':
        path.write_bytes(b'')
    elif damage == 'wrong_size':
        Image.new('RGB', (20, 20)).save(path)
    else:
        images['weapon_pistol'] = '../' + path.name
        (public / 'index.json').write_text(json.dumps(dict(schema_version=1, owner='allin1.prelaunch-previews', images=images)))
    assert preview_counts(project, game)['weapons']['existing'] == 0


def test_invalid_index_is_unknown_not_zero_or_complete(roots):
    project, game = roots
    public, _ = publish(game, 'weapons', ['weapon_pistol'])
    (public / 'index.json').write_text('{}')
    result = preview_counts(project, game)
    assert result['weapons']['status'] == 'unavailable'
    assert result['weapons']['existing'] is None
    assert result['vehicles']['total'] == 2


def test_enabled_owned_custom_catalog_included_without_reading_rpf(roots):
    project, game = roots
    root = game / 'scripts/.allin1/mods'
    root.mkdir(parents=True)
    source = 'scripts/custom.json'
    catalog = {'schema_version': 1, 'id': 'test.weapons', 'name': 'Test weapons', 'weapons': [
        dict(weapon='WEAPON_TEST_CUSTOM', name='Test', category='rifles', price=1,
             ammo_cost_per_round=1, source_pack='testpack')]}
    data = json.dumps(catalog).encode()
    (game / source).write_bytes(data)
    receipt = dict(enabled=True, dlc_packs=['testpack'], files=[
        dict(destination=source, sha256=hashlib.sha256(data).hexdigest()),
        dict(destination='mods/absent-huge-archive.rpf', sha256='b'*64)],
        extension={'gbay': {'catalogs': [dict(kind='weapon', source=source, id='test.weapons')]}})
    path = root / 'test.json'
    path.write_text(json.dumps(receipt))
    publish(game, 'weapons', ['weapon_test_custom'])
    assert preview_counts(project, game)['weapons'] == dict(existing=1, total=3, status='available')
    receipt['enabled'] = False
    path.write_text(json.dumps(receipt))
    assert preview_counts(project, game)['weapons'] == dict(existing=0, total=2, status='available')
    receipt['enabled'] = True
    path.write_text(json.dumps(receipt))
    (game / source).write_text('{}')
    assert preview_counts(project, game)['weapons']['status'] == 'unavailable'


def test_launch_and_prepare_reviews_expose_counts_without_changing_request(service):
    service.allow_launch = True
    for request in [dict(action='launch', quick_launch=True), dict(action='prepare_previews')]:
        result = service.review(request)
        assert result['preview_counts']['weapons']['total'] > 0
        assert result['preview_counts']['weapons']['existing'] == 0
        assert result['request'] == request
