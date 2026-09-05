"""Reviewed Launcher-owned assistant provisioning; never starts inference."""
from dataclasses import asdict

from allin1 import assistant_manager as manager


def configuration(value, root):
    expected = asdict(manager.AssistantConfig())
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("Invalid assistant configuration fields")
    for key, default in expected.items():
        actual = value[key]
        valid = (type(actual) in (int, float) if type(default) is float else
                 isinstance(actual, list) and all(isinstance(item, str) for item in actual) if isinstance(default, tuple) else
                 type(actual) is type(default))
        if not valid:
            raise ValueError("Invalid assistant configuration type: " + key)
        if isinstance(actual, str) and (len(actual) > 4096 or any(c in actual for c in "\0\r\n")):
            raise ValueError("Invalid assistant configuration text: " + key)
    config = manager.AssistantConfig.from_dict(value)
    config.validate(root)
    return config


def hardware(profile, root, archive=None):
    if archive is not None:
        package = manager.inspect_assistant_archive(archive)
        return manager.assess_assistant_hardware(package.profile, root,
            archive_size=archive.stat().st_size, unpacked_size=package.unpacked_size, package=package)
    source = manager.assistant_source(profile)
    return manager.assess_assistant_hardware(source.profile, root,
        archive_size=source.total_download_bytes, unpacked_size=source.runtime.size + source.model.size)


def catalog(root):
    return {"status": asdict(manager.read_assistant_status(root)),
            "sources": [{**asdict(source), "total_download_bytes": source.total_download_bytes}
                        for source in manager.ASSISTANT_SOURCES]}
