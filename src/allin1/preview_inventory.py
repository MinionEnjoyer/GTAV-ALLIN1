"""Read-only preview coverage; never discovers models or starts render workers.

Counts published generated and downloaded default images for the selected
game's catalog. This is a presence check, not source/cache validation.
"""
from pathlib import Path
import re
import struct

from allin1.prelaunch_previews import PUBLIC, MAX_IMAGE_BYTES, contained, document, sha
from allin1.preview_policy import PREVIEW_CATEGORIES


def _managed_names(game):
    from allin1.weapon_catalog import WeaponCatalog
    from allin1.vehicle_catalog import VehicleCatalog
    names = {'weapons': set(), 'vehicles': set()}
    root = contained(game, 'scripts/.allin1/mods')
    receipts = list(root.glob('*.json'))
    if len(receipts) > 256:
        raise ValueError('Too many installed catalog receipts')
    for path in receipts:
        receipt = document(path)
        if receipt.get('enabled') is not True:
            continue
        declarations = (receipt.get('extension') or {}).get('gbay', {}).get('catalogs', [])
        if not isinstance(declarations, list) or len(declarations) > 256:
            raise ValueError('Invalid installed catalog declarations')
        for declaration in declarations:
            kind = declaration.get('kind')
            if kind not in ('weapon', 'vehicle'):
                continue
            records = receipt.get('files', [])
            if not isinstance(records, list) or len(records) > 8192:
                raise ValueError('Invalid catalog receipt files')
            source = declaration['source']
            owned = [r for r in records if r.get('destination') == source]
            if len(owned) != 1:
                raise ValueError('Catalog is not uniquely receipt-owned')
            catalog_path = contained(game, source)
            # Only the small catalog is hashed, never its RPF/model payloads.
            data = document(catalog_path)
            if sha(catalog_path) != owned[0].get('sha256'):
                raise ValueError('Installed catalog changed')
            catalog = (WeaponCatalog if kind == 'weapon' else VehicleCatalog).from_dict(data)
            if catalog.catalog_id != declaration['id']:
                raise ValueError('Installed catalog identity mismatch')
            if kind == 'weapon':
                catalog.validate_package_ownership(receipt.get('dlc_packs', []))
                names['weapons'].update(row.weapon.lower() for row in catalog.weapons)
            else:
                catalog.validate_package_ownership(receipt.get('dlc_packs', []), allow_traffic=True)
                names['vehicles'].update(row.model.lower() for row in catalog.vehicles)
    return names


def _store_names(game, category, names, prefix, owner):
    public = contained(game, PUBLIC.replace('generated-weapons', prefix + category))
    index = public / 'index.json'
    if not index.exists():
        return set()
    data = document(index)
    images = data.get('images')
    if data.get('schema_version') != 1 or data.get('owner') != owner or not isinstance(images, dict) or len(images) > 4096:
        raise ValueError('Generated preview index is invalid')
    found = set()
    for name in names:
        filename = images.get(name)
        if not isinstance(filename, str) or not re.fullmatch(re.escape(name) + r'\.[0-9a-f]{64}\.png', filename):
            continue
        try:
            path = contained(public, filename)
            if not 33 <= path.stat().st_size <= MAX_IMAGE_BYTES:
                continue
            with path.open('rb') as stream:
                header = stream.read(24)
            if header[:16] == b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' and header[16:24] == struct.pack('>II', 512, 320):
                found.add(name)
        except (OSError, ValueError):
            continue
    return found


def _existing(game, category, names):
    generated = _store_names(game, category, names, 'generated-', 'allin1.prelaunch-previews')
    defaults = _store_names(game, category, names, 'default-', 'allin1.default-previews')
    return len(generated | defaults)


def preview_counts(project, game):
    """Unavailable data stays unknown; a count failure never blocks launching."""
    from allin1.stock_weapon_previews import catalog_names as weapons
    from allin1.catalog_model_previews import catalog_names, GEAR_MODELS
    result = {}
    try:
        managed = _managed_names(Path(game))
        managed_error = None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
        managed, managed_error = {}, str(error)
    for category in PREVIEW_CATEGORIES:
        try:
            if category != 'gear' and managed_error:
                raise ValueError(managed_error)
            names = set(n.lower() for n in (weapons(project) if category == 'weapons' else catalog_names(project, category)))
            if category == 'gear':
                names.intersection_update(n.lower() for n in GEAR_MODELS)
            names.update(managed.get(category, ()))
            if len(names) > 4096:
                raise ValueError('Catalog exceeds preview count limit')
            result[category] = dict(existing=_existing(game, category, names), total=len(names), status='available')
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as error:
            result[category] = dict(existing=None, total=None, status='unavailable', reason=str(error))
    return result
