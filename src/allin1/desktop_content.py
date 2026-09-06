"""Read-only content presentation and validated preinstallation preferences."""
from allin1.extensions import ExtensionManifest, ExtensionRegistry, _MANIFEST_FIELDS, settings_from_config, apply_settings_to_config


def catalog(manager, game, config):
    builtins = {item.extension_id: item for item in manager.extension_catalog.discover()}
    installed = {item["id"]: item for item in ExtensionRegistry(game).inspect()["extensions"]} if game else {}
    rows = []
    for key in sorted(builtins.keys() | installed.keys()):
        manifest = builtins[key] if key in builtins else ExtensionManifest.from_dict(
            {field: value for field, value in installed[key].items() if field in _MANIFEST_FIELDS})
        entry = installed.get(key, {})
        settings = {setting.key: setting.default for setting in manifest.settings}
        settings.update({key: value for key, value in entry.get("settings", {}).items()
                         if key in settings})
        settings.update(settings_from_config(manifest, config))
        rows.append({**manifest.to_dict(), "installed": key in installed,
                     "source": entry.get("source", "built-in"), "enabled": entry.get("enabled", False),
                     "blocked_reason": entry.get("blocked_reason"), "settings": settings,
                     "schema_settings": [setting.to_dict() for setting in manifest.settings]})
    return rows


def prepare_local_settings(manager, package_id, values, config):
    manifests = {item.extension_id: item for item in manager.extension_catalog.discover()}
    if package_id not in manifests:
        raise ValueError("Preinstallation preferences require an included content package")
    manifest = manifests[package_id]
    if not isinstance(values, dict) or not values:
        raise ValueError("Choose at least one content preference")
    for key, value in values.items():
        setting = manifest.setting(key)
        if not setting.config_key:
            raise ValueError("Install this content before saving package-owned settings")
        setting.validate(value)
    apply_settings_to_config(manifest, config, values)
    config.validate()
    return config
