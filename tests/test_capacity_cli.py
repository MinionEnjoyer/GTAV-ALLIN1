import hashlib
import json

from click.testing import CliRunner

from allin1.capacity_cli import capacity, read_source, read_text


SOURCE = '<CGameConfig><Pools><Item><Name>CVehicle</Name><Size value="100"/></Item></Pools></CGameConfig>'


def test_inspect_and_export_leave_source_untouched(tmp_path):
    source = tmp_path / 'stock.xml'
    source.write_text(SOURCE)
    runner = CliRunner()
    inspected = runner.invoke(capacity, ['inspect', str(source)])
    assert inspected.exit_code == 0, inspected.output
    fingerprint = json.loads(inspected.output)['source_sha256']
    output = tmp_path / 'candidate'
    args = ['build', str(source), '--edition', 'legacy', '--game-build', '1.0.3889.0',
            '--source-sha256', fingerprint, '--pool', 'CVehicle=120', '--output', str(output)]
    result = runner.invoke(capacity, args)
    assert result.exit_code == 0, result.output
    assert source.read_text() == SOURCE
    receipt = json.loads((output / 'profile.json').read_text())
    assert receipt['runtime_qualified'] is False
    assert receipt['output_sha256'] == hashlib.sha256((output / 'gameconfig.xml').read_bytes()).hexdigest()
    assert receipt['changes']['CVehicle'] == {'before': 100, 'after': 120}
    assert runner.invoke(capacity, args).exit_code != 0
    assert source.read_text() == SOURCE


def test_stale_hash_does_not_create_export(tmp_path):
    source = tmp_path / 'stock.xml'
    source.write_text(SOURCE)
    output = tmp_path / 'candidate'
    result = CliRunner().invoke(capacity, ['build', str(source), '--edition', 'legacy',
        '--game-build', '1.0.3889.0', '--source-sha256', '0'*64, '--output', str(output)])
    assert result.exit_code != 0
    assert not output.exists()


def test_cli_hashes_and_exports_original_bytes_while_normalizing_parse_text(tmp_path):
    raw = b'\xef\xbb\xbf<CGameConfig>\r\n<Pools><Item><Name>CVehicle</Name><Size value="100"/></Item></Pools>\r\n</CGameConfig>\r\n'
    source = tmp_path / "stock.xml"
    source.write_bytes(raw)
    text = read_source(source)
    assert text == SOURCE.replace("<CGameConfig>", "<CGameConfig>\n").replace("</CGameConfig>", "\n</CGameConfig>\n")
    assert read_text(raw).startswith("<CGameConfig>")

    runner = CliRunner()
    inspected = runner.invoke(capacity, ["inspect", str(source)])
    assert inspected.exit_code == 0, inspected.output
    fingerprint = json.loads(inspected.output)["source_sha256"]
    assert fingerprint == hashlib.sha256(raw).hexdigest()
    output = tmp_path / "candidate"
    result = runner.invoke(capacity, ["build", str(source), "--edition", "legacy",
        "--game-build", "1.0.3889.0", "--source-sha256", fingerprint,
        "--pool", "CVehicle=120", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert (output / "stock-gameconfig.xml").read_bytes() == raw
    receipt = json.loads((output / "profile.json").read_text())
    assert receipt["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["output_sha256"] == hashlib.sha256(
        (output / "gameconfig.xml").read_bytes()).hexdigest()
