"""Shared preview choices for desktop, CLI and agent requests."""

PREVIEW_CATEGORIES = ('weapons', 'vehicles', 'gear')
STUDIO_BACKDROP = 'data/preview-studio/asphalt-concrete-v1.png'
VEHICLE_TEXTURES = tuple('data/preview-studio/pbr/'+asset+'_'+kind+'_2k.jpg'
    for asset in ('asphalt_01','concrete') for kind in ('diff','nor_gl','rough'))
THROWABLE_TEXTURES = tuple('data/preview-studio/pbr/wood_planks_'+kind+'_2k.jpg' for kind in ('diff','nor_gl','rough'))


def validate_skip_categories(value):
    if type(value) is not list or any(type(item) is not str or item not in PREVIEW_CATEGORIES for item in value):
        raise ValueError('skip_preview_categories must be an array containing only weapons, vehicles, gear')
    if len(value) != len(set(value)):
        raise ValueError('skip_preview_categories must not contain duplicates')
    return tuple(value)
