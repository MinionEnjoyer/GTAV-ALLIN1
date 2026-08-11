from allin1.compatibility import build_compatible, load_content_compatibility


def test_content_manifest_build_ranges(tmp_path):
    path = tmp_path / "compat.toml"
    path.write_text('[editions.legacy]\nmin_build=100\nmax_build=200\n')
    manifest = load_content_compatibility(path)
    assert build_compatible(150, "legacy", manifest) == (True, "supported")
    assert build_compatible(99, "legacy", manifest)[0] is False
    assert build_compatible(201, "legacy", manifest)[0] is False
    assert build_compatible(150, "enhanced", manifest)[0] is False


def test_unbounded_maximum(tmp_path):
    path = tmp_path / "compat.toml"
    path.write_text('[editions.enhanced]\nmin_build=1\nmax_build=0\n')
    assert build_compatible(99999, "enhanced", load_content_compatibility(path))[0]
