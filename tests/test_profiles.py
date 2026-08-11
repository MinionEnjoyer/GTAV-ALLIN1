import pytest
from allin1.config import Config
from allin1.profiles import ProfileStore


def test_profile_lifecycle(tmp_path):
    store = ProfileStore(tmp_path / "profiles"); assert store.list() == []
    config = Config.default(); config.general.free_mode = True
    assert store.save("Full ALLIN1", config).name == "Full ALLIN1.toml"
    assert store.list() == ["Full ALLIN1"] and store.load("Full ALLIN1").general.free_mode
    assert store.export("Full ALLIN1", tmp_path / "out/profile.toml").is_file()
    store.delete("Full ALLIN1")
    with pytest.raises(FileNotFoundError): store.load("Full ALLIN1")


@pytest.mark.parametrize("name", ["", "../bad", ".hidden", "x" * 49, "bad/name"])
def test_profile_names_are_safe(tmp_path, name):
    with pytest.raises(ValueError): ProfileStore(tmp_path).path_for(name)
