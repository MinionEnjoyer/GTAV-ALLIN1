"""A Windows-style Git checkout must preserve the attested Reactor UI bytes."""
from pathlib import Path
import subprocess

from allin1.reactor_dependency import consumer_files


ROOT = Path(__file__).resolve().parents[1]


def test_checksum_protected_reactor_ui_survives_autocrlf_checkout(tmp_path):
    names = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "data/reactor/allin1-ui"],
        text=True, encoding="utf-8").splitlines()
    assert names
    prefix = tmp_path.as_posix() + "/"
    subprocess.run(["git", "-C", str(ROOT), "-c", "core.autocrlf=true", "checkout-index",
        "--prefix=" + prefix, "--", *names], check=True, capture_output=True)
    actual = consumer_files(tmp_path / "data/reactor/allin1-ui")
    # Compare the same index snapshot with/without Windows checkout conversion.
    # A newer, uncommitted UI build must not be compared with an older index.
    # consumer_files validates both inventories against their actual hashes.
    reference = tmp_path / "unconverted-index"
    reference.mkdir()
    subprocess.run(["git", "-C", str(ROOT), "-c", "core.autocrlf=false", "checkout-index",
        "--prefix=" + reference.as_posix() + "/", "--", *names], check=True, capture_output=True)
    expected = consumer_files(reference / "data/reactor/allin1-ui")
    assert actual.keys() == expected.keys()
    assert all(actual[name].read_bytes() == expected[name].read_bytes() for name in actual)
