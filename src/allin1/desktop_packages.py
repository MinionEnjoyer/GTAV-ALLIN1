"""Package inspector data without archive-extraction paths or write side effects."""
from allin1.extensions import ExtensionRegistry


def settings(manifest, values):
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise ValueError("Package settings must be an object")
    if values and manifest.extension is None:
        raise ValueError("Initial settings require a schema-2 ALLIN1 content package")
    for key, value in values.items():
        manifest.extension.setting(key).validate(value)
    return dict(values)


def describe(manifest, game):
    extension = manifest.extension
    initial = {item.key: item.default for item in extension.settings} if extension else {}
    if extension and game:
        existing = next((item for item in ExtensionRegistry(game).inspect()["extensions"]
                         if item["id"] == extension.extension_id), None)
        if existing:
            # Reinstalling must not silently reset a user's package preferences.
            for item in extension.settings:
                if item.key in existing["settings"]:
                    value = existing["settings"][item.key]
                    item.validate(value)
                    initial[item.key] = value
    return {"id": manifest.mod_id, "name": manifest.name, "version": manifest.version,
            "description": manifest.description, "editions": list(manifest.editions),
            "schema_version": manifest.schema_version, "type": manifest.mod_type,
            "dependencies": list(manifest.dependencies), "conflicts": list(manifest.conflicts),
            "files": [{"source": str(item.source), "destination": str(item.destination)} for item in manifest.files],
            "rpf_entry_count": len(manifest.rpf_entries),
            "extension": extension.to_dict() if extension else None, "settings": initial}
