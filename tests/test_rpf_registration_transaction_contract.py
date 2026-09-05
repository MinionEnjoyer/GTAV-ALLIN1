"""Static safety contracts for RpfPatcher's full-archive dlclist transaction.

The CodeWalker write path needs real encrypted GTA archives, so the portable
test suite verifies the ordering and recovery invariants at the source seam.
Real-archive integration remains covered by the Windows toolchain job.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "RpfPatcher" / "Program.cs"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _method(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end, source.index(start))]


def test_register_and_unregister_keep_the_existing_cli_dispatch_contract():
    source = _source()
    assert 'if (command == "register-dlc")' in source
    assert 'return PatchCommand("patch", args, true);' in source
    assert 'if (command == "unregister-dlc")' in source
    assert 'return PatchCommand("unpatch", args, true);' in source


def test_patch_command_mutates_only_a_same_volume_sibling_stage_before_commit():
    source = _source()
    patch = _method(
        source,
        "        static int PatchCommand(",
        "        private static void ValidateManagedDlcPackName",
    )

    assert "OpenModsUpdateRpf" not in patch
    assert 'target + ".allin1-dlclist." + transactionId + ".stage"' in source
    assert "CopyFileWithHash(\n                    source, stage" in patch
    assert "OpenDlcListArchive(stage, true)" in patch
    assert "RpfFile.CreateFile(dlclistEntry.Parent" in patch
    assert "VerifyDlcListArchive(stage)" in patch

    copy = patch.index("CopyFileWithHash(")
    open_stage = patch.index("OpenDlcListArchive(stage, true)")
    mutate = patch.index("RpfFile.CreateFile(")
    verify_stage = patch.index("VerifyDlcListArchive(stage)")
    commit = patch.index("File.Replace(stage, target, backup, true)")
    verify_live = patch.index("VerifyDlcListArchive(\n                    target")
    assert copy < open_stage < mutate < verify_stage < commit < verify_live


def test_commit_is_atomic_for_existing_and_absent_mods_archives():
    source = _source()
    patch = _method(
        source,
        "        static int PatchCommand(",
        "        private static void ValidateManagedDlcPackName",
    )

    assert "string source = File.Exists(target) ? target : stock;" in patch
    assert "File.Replace(stage, target, backup, true);" in patch
    assert "File.Move(stage, target);" in patch
    assert "The live mods archive changed before commit" in patch
    assert "A live mods archive appeared before commit" in patch
    assert "rollback archive failed pre-image verification" in patch
    assert "committed mods archive failed post-image verification" in patch
    assert "HashFileSha256(target)" in patch
    assert "HashFileSha256(backup)" in patch


def test_transaction_recovery_is_owner_bound_and_fails_closed_on_unknown_data():
    source = _source()
    recovery = _method(
        source,
        "        private static void RecoverDlcListArchiveTransaction",
        "        private static void VerifyPreparedDlcListMutation",
    )
    artifact_guard = _method(
        source,
        "        private static void EnsureNoUnknownDlcListTransactionArtifacts",
        "        private static void RecoverDlcListArchiveTransaction",
    )

    assert '"ALLIN1.RpfPatcher.dlclist"' in source
    assert "ValidateDlcListTransactionJournal(journal)" in source
    assert "Unknown dlclist transaction artifacts require manual review" in artifact_guard
    assert 'journal.Phase == "copying"' in recovery
    assert 'journal.Phase == "staged"' in recovery
    assert 'journal.Phase == "prepared" && preCommit' in recovery
    assert "bool committed = journal.TargetExisted" in recovery
    assert "VerifyDlcListArchive(target, journal.ExpectedDlcListSha256)" in recovery
    assert "do not match a verified pre- or post-image; no files were removed" in recovery
    assert "AcquireDlcListTransactionLock(target)" in source
    assert "FileShare.None" in source
    assert "Another dlclist archive transaction is already active" in source
    assert "reserved dlclist transaction lock contains unknown data" in source


def test_journal_and_archive_verification_preserve_crash_and_xml_invariants():
    source = _source()
    journal_writer = _method(
        source,
        "        private static void WriteDlcListJournal",
        "        private static string HashFileSha256",
    )
    mutation_verifier = _method(
        source,
        "        private static void VerifyPreparedDlcListMutation",
        "        static int PatchCommand(",
    )
    patch = _method(
        source,
        "        static int PatchCommand(",
        "        private static void ValidateManagedDlcPackName",
    )

    assert "FileOptions.WriteThrough" in journal_writer
    assert "stream.Flush(true)" in journal_writer
    assert "File.Replace(pending, path, null, true)" in journal_writer
    assert "XNode.DeepEquals(expected, actual)" in mutation_verifier
    assert "unrelated entries were not committed" in mutation_verifier
    assert "Close GTA V before modifying dlclist.xml" in patch
    assert "RecoverDlcListArchiveTransaction(transactionTarget)" in patch
    assert "finally" in patch
