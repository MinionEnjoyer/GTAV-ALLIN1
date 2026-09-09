using System;
using System.IO;
using System.Reflection;
using CodeWalker.GameFiles;

var method = Type.GetType("RpfPatcher.Program, RpfPatcher", true)
    .GetMethod("HasArchiveKeyContext", BindingFlags.Static | BindingFlags.NonPublic);
var root = Path.Combine(Path.GetTempPath(), "allin1-key-context-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
int checks = 0;
void Check(string path, bool enhanced, bool expected)
{
    if ((bool)method.Invoke(null, new object[] { path, enhanced }) != expected)
        throw new Exception("Incorrect game-key context classification");
    checks++;
}
try
{
    Check(null, true, false);
    Check("", false, false);
    Check(root, false, false);
    Check(root, true, false);
    // Fixture presence only: never load these bytes as encryption keys.
    File.WriteAllBytes(Path.Combine(root, "GTA5.exe"), new byte[] { 1 });
    Check(root, false, true);
    Check(root, true, false);
    File.WriteAllBytes(Path.Combine(root, "GTA5_Enhanced.exe"), new byte[] { 1 });
    Check(root, false, true);
    Check(root, true, true);
    var sizes = Type.GetType("RpfPatcher.Program, RpfPatcher", true)
        .GetMethod("ValidateExactIoSizes", BindingFlags.Static | BindingFlags.NonPublic);
    void Size(long outer, long payload, bool valid)
    {
        try
        {
            sizes.Invoke(null, new object[] { outer, payload });
            if (!valid) throw new Exception("Oversized archive/payload was accepted");
        }
        catch (TargetInvocationException error) when (error.InnerException is InvalidDataException && !valid) { }
        checks++;
    }
    Size(3208742400L, 1024, true);
    Size(4L * 1024 * 1024 * 1024, 128L * 1024 * 1024, true);
    Size(4L * 1024 * 1024 * 1024 + 1, 1024, false);
    Size(1024, 128L * 1024 * 1024 + 1, false);
    Size(0, 1, false);
    Size(-1, 1, false);
    Size(1, 0, false);
    Size(1, -1, false);
    var fingerprint = Type.GetType("RpfPatcher.Program, RpfPatcher", true)
        .GetMethod("ExactStoredFingerprint", BindingFlags.Static | BindingFlags.NonPublic);
    var fixture = Path.Combine(root, "fixture.rpf");
    var bytes = new byte[2048];
    bytes[512] = bytes[1024] = 42;
    File.WriteAllBytes(fixture, bytes);
    var archive = new RpfFile(fixture, "fixture.rpf");
    // A tiny compressed member with a large decoded size must not be decoded.
    var entry = new RpfBinaryFileEntry { File = archive, Name = "large.bin", FileOffset = 1,
        FileSize = 32, FileUncompressedSize = 256 * 1024 * 1024 };
    string Fingerprint() => (string)fingerprint.Invoke(null, new object[] { entry });
    void Assert(bool condition)
    {
        if (!condition) throw new Exception("Stored-member preservation regression");
        checks++;
    }
    var baseline = Fingerprint();
    entry.FileOffset = 2;
    Assert(Fingerprint() == baseline); // Same bytes relocated, offset is not content.
    bytes[1024] = 43; File.WriteAllBytes(fixture, bytes);
    Assert(Fingerprint() != baseline);
    bytes[1024] = 42; File.WriteAllBytes(fixture, bytes);
    entry.FileUncompressedSize--;
    Assert(Fingerprint() != baseline); // Decoding metadata must be preserved too.
    entry.FileUncompressedSize++;
    entry.IsEncrypted = true;
    Assert(Fingerprint() != baseline);
    var encrypted = Fingerprint(); archive.IsNGEncrypted = true;
    Assert(Fingerprint() == encrypted); // OPEN and NG TOCs decode encrypted leaves as NG.
    archive.IsAESEncrypted = true;
    Assert(Fingerprint() != encrypted);
    void Refused()
    {
        try { Fingerprint(); throw new Exception("Out-of-bounds stored member accepted"); }
        catch (TargetInvocationException error) when (error.InnerException is InvalidDataException) { checks++; }
    }
    entry.FileOffset = 4; Refused(); // Beyond end.
    entry.FileOffset = 0; Refused(); // Header area.
    entry.FileOffset = 3; entry.FileSize = 513; Refused(); // Partial overrun.
    entry.FileOffset = 2; entry.FileSize = 32;
    archive.FileSize = 4096; Refused(); // Truncated physical archive.
    archive.FileSize = 2048; archive.StartPos = -1; Refused();
    Console.WriteLine($"{checks} game-key context, bounded-I/O and stored-fingerprint checks passed.");
}
finally
{
    File.Delete(Path.Combine(root, "GTA5.exe"));
    File.Delete(Path.Combine(root, "GTA5_Enhanced.exe"));
    File.Delete(Path.Combine(root, "fixture.rpf"));
    Directory.Delete(root);
}
