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
    bundle = manifest if manifest.schema_version in (5, 6) else None
    if bundle and game:
        from allin1.mods import ModIntegrationService
        manifest = bundle.for_edition(ModIntegrationService(game).edition)
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
    components = []
    if bundle and bundle.schema_version == 6 and game:
        installed = {item.mod_id: item for item in ModIntegrationService(game).list_installed()}
        for child in manifest.variants:
            info = describe(child, game)
            existing = installed.get(child.mod_id)
            info["installed"] = existing is not None
            info["installed_version"] = existing.version if existing else None
            info["enabled"] = existing.enabled if existing else False
            info["install_blocked_reason"] = (
                "Already installed with RPF ownership. Keep it, or reset this import and uninstall the existing package before reinstalling."
                if existing and child.rpf_entries else None)
            components.append(info)
    return {"id": manifest.mod_id, "name": manifest.name, "version": manifest.version,
            "components": components,
            "bundle_editions": list(bundle.editions) if bundle else [],
            "selected_edition": manifest.editions[0] if bundle and game else None,
            "description": manifest.description, "editions": list(manifest.editions),
            "schema_version": manifest.schema_version, "type": manifest.mod_type,
            "dependencies": list(manifest.dependencies), "conflicts": list(manifest.conflicts),
            "files": [{"source": str(item.source), "destination": str(item.destination)} for item in manifest.files],
            "rpf_entry_count": len(manifest.rpf_entries),
            "extension": extension.to_dict() if extension else None, "settings": initial}
