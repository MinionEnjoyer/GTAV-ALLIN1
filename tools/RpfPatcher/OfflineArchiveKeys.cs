using System;
using System.IO;
using CodeWalker.GameFiles;

namespace RpfPatcher
{
    partial class Program
    {
        static bool IsUnencryptedRpf(string path)
        {
            using var stream = System.IO.File.OpenRead(path);
            if (stream.Length < 16) return false;
            using var reader = new BinaryReader(stream);
            if (reader.ReadUInt32() != 0x52504637) return false;
            reader.ReadUInt32();
            reader.ReadUInt32();
            var encryption = (RpfEncryption)reader.ReadUInt32();
            return encryption == RpfEncryption.OPEN || encryption == RpfEncryption.NONE;
        }

        static string LoadReadOnlyArchiveKeys(string gtaPath, bool gen9, string archivePath)
        {
            // An OPEN root can still contain encrypted Scaleform members. Use
            // the supplied game's key context; only offline authoring fixtures
            // without a matching executable may skip key loading.
            if (IsUnencryptedRpf(archivePath) && !HasArchiveKeyContext(gtaPath, gen9))
            {
                // OPEN/NONE authoring archives do not need game encryption keys.
                // Callers still require a complete, warning-free structure scan;
                // an encrypted nested archive remains an error without its keys.
                Console.Error.WriteLine("No game context; reading an unencrypted authoring archive.");
                return "not-required-unencrypted-root";
            }
            GTA5Keys.LoadFromPath(gtaPath, gen9, null);
            return "loaded";
        }

        static bool HasArchiveKeyContext(string gtaPath, bool gen9)
        {
            return !string.IsNullOrWhiteSpace(gtaPath) && File.Exists(Path.Combine(
                gtaPath, gen9 ? "GTA5_Enhanced.exe" : "GTA5.exe"));
        }
    }
}
