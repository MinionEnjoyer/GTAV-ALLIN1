// RpfPatcher — Tools for managing ALLIN1 DLC content in GTA V RPF archives.
// Uses CodeWalker.Core to read/write RPF7 archives.
//
// Commands:
//   RpfPatcher.exe inject-ytd   <gta_path> <ytd_folder>  — inject .ytd files into script_txds.rpf
//   RpfPatcher.exe remove-ytd   <gta_path> <prefix>      — remove ALLIN1 .ytd files from script_txds.rpf
//   RpfPatcher.exe verify-ytd   <gta_path> <ytd_folder>  — verify expected .ytd files in script_txds.rpf
//   RpfPatcher.exe patch        <gta_path>                — add allin1_previews to dlclist.xml
//   RpfPatcher.exe unpatch      <gta_path>                — remove allin1_previews from dlclist.xml
//   RpfPatcher.exe build-dlc    <loose_folder> <output_rpf> [--embed-rpf <src_folder> <dest_path>]
//   RpfPatcher.exe verify-dlc   <dlc_rpf> <ytd_folder>      — verify a preview DLC and its dictionaries
//   RpfPatcher.exe convert-gen9 <ytd_folder>              — convert .ytd files from Legacy to Enhanced format
//   RpfPatcher.exe inspect      <gta_path> <rpf_path>    — dump RPF structure + XML contents
//   RpfPatcher.exe extract-entries <gta_path> <rpf_path> <manifest_tsv> <output_root>
//   RpfPatcher.exe audit-seats  <gta_path> <output_json> [output_cs]
//   RpfPatcher.exe install-euphoria <gta_path> <payload_folder> [--allow-enhanced]
//   RpfPatcher.exe verify-euphoria  <gta_path> <payload_folder>
//   RpfPatcher.exe validate-euphoria <payload_folder_or_archive>
//   RpfPatcher.exe remove-euphoria  <gta_path>

using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Xml.Linq;
using CodeWalker.Core.Utils;
using CodeWalker.GameFiles;
using CodeWalker.Utils;

namespace RpfPatcher
{
    class Program
    {
        private static readonly Dictionary<string, string> OwnedDlcEntries =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                { "allin1_previews", "dlcpacks:/allin1_previews/" },
                { "allin1_maps", "dlcpacks:/allin1_maps/" },
            };

        static int Main(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine(
                    "Usage:\n" +
                    "  RpfPatcher.exe inject-ytd   <gta_path> <ytd_folder>\n" +
                    "  RpfPatcher.exe remove-ytd   <gta_path> <prefix>\n" +
                    "  RpfPatcher.exe verify-ytd   <gta_path> <ytd_folder>\n" +
                    "  RpfPatcher.exe patch        <gta_path>\n" +
                    "  RpfPatcher.exe unpatch      <gta_path>\n" +
                    "  RpfPatcher.exe build-dlc    <loose_folder> <output_rpf> [--embed-rpf <src> <dest>]\n" +
                    "  RpfPatcher.exe verify-dlc   <dlc_rpf> <ytd_folder>\n" +
                    "  RpfPatcher.exe verify-map-dlc <dlc_rpf> <manifest_tsv>\n" +
                    "  RpfPatcher.exe convert-gen9 <ytd_folder>\n" +
                    "  RpfPatcher.exe inspect      <gta_path> <rpf_path>\n" +
                    "  RpfPatcher.exe audit-seats  <gta_path> <output_json> [output_cs]\n" +
                    "  RpfPatcher.exe build-ytd    <dds_folder> <output_ytd> [legacy|gen9]\n" +
                    "  RpfPatcher.exe unpack-ytd   <ytd_path> <output_folder> [legacy|gen9]\n" +
                    "  RpfPatcher.exe extract-entry <gta_path> <rpf_path> <name> <output>\n" +
                    "  RpfPatcher.exe extract-entries <gta_path> <rpf_path> <manifest_tsv> <output_root>\n" +
                    "  RpfPatcher.exe open-rpfs <gta_path> <manifest_tsv> <output_root>\n" +
                    "  RpfPatcher.exe install-euphoria <gta_path> <payload_folder_or_archive> [--allow-enhanced]\n" +
                    "  RpfPatcher.exe verify-euphoria <gta_path> <payload_folder_or_archive>\n" +
                    "  RpfPatcher.exe validate-euphoria <payload_folder_or_archive>\n" +
                    "  RpfPatcher.exe remove-euphoria <gta_path>\n" +
                    "  RpfPatcher.exe dump-ytd      <ytd_path> [legacy|gen9]");
                return 1;
            }

            string command = args[0].ToLower();

            if (command == "inject-ytd")
                return InjectYtd(args);
            if (command == "remove-ytd")
                return RemoveYtd(args);
            if (command == "verify-ytd")
                return VerifyYtd(args);
            if (command == "build-dlc")
                return BuildDlc(args);
            if (command == "verify-dlc")
                return VerifyDlc(args);
            if (command == "verify-map-dlc")
                return VerifyMapDlc(args);
            if (command == "convert-gen9")
                return ConvertGen9(args);
            if (command == "inspect")
                return InspectRpf(args);
            if (command == "audit-seats")
                return SeatCatalogAudit.Run(args);
            if (command == "build-ytd")
                return BuildYtd(args);
            if (command == "unpack-ytd")
                return UnpackYtd(args);
            if (command == "extract-entry")
                return ExtractEntry(args);
            if (command == "extract-entries")
                return ExtractEntries(args);
            if (command == "open-rpfs")
                return OpenRpfs(args);
            if (command == "install-euphoria")
                return InstallEuphoria(args);
            if (command == "verify-euphoria")
                return VerifyEuphoria(args);
            if (command == "validate-euphoria")
                return ValidateEuphoria(args);
            if (command == "remove-euphoria")
                return RemoveEuphoria(args);
            if (command == "dump-ytd")
                return DumpYtd(args);
            if (command == "patch" || command == "unpatch")
                return PatchCommand(command, args);

            Console.Error.WriteLine($"ERROR: Unknown command '{command}'.");
            return 1;
        }

        // ================================================================
        //  Shared: Open mods/update/update.rpf with encryption keys
        // ================================================================

        /// <summary>
        /// Detect edition, load keys, copy update.rpf to mods/ if needed,
        /// open and scan the mods copy, convert to OPEN encryption.
        /// Returns the opened RpfFile or null on failure (error printed).
        /// </summary>
        static RpfFile OpenModsUpdateRpf(string gtaPath, out int errorCode,
                                         string archiveName = "update.rpf",
                                         bool createModsCopy = true)
        {
            errorCode = 0;

            bool isGen9 = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"))
                       || File.Exists(Path.Combine(gtaPath, "eboot.bin"));
            string exeName = isGen9 ? "GTA5_Enhanced.exe" : "GTA5.exe";

            if (!File.Exists(Path.Combine(gtaPath, exeName)))
            {
                Console.Error.WriteLine($"ERROR: {exeName} not found in {gtaPath}");
                errorCode = 2;
                return null;
            }

            Console.WriteLine($"Edition: {(isGen9 ? "Enhanced" : "Legacy")}");

            Console.WriteLine("Loading encryption keys...");
            GTA5Keys.LoadFromPath(gtaPath, isGen9, null);

            if (GTA5Keys.PC_AES_KEY == null)
            {
                Console.Error.WriteLine("ERROR: Failed to load encryption keys.");
                errorCode = 3;
                return null;
            }
            Console.WriteLine("Encryption keys loaded.");

            string originalRpf = Path.Combine(gtaPath, "update", archiveName);
            string modsDir = Path.Combine(gtaPath, "mods", "update");
            string modsRpf = Path.Combine(modsDir, archiveName);

            if (!File.Exists(originalRpf))
            {
                Console.Error.WriteLine($"ERROR: {originalRpf} not found");
                errorCode = 4;
                return null;
            }

            if (Directory.Exists(modsRpf))
            {
                if (!createModsCopy)
                {
                    Console.Error.WriteLine(
                        $"ERROR: Expected an RPF file but found a directory: {modsRpf}");
                    errorCode = 7;
                    return null;
                }
                Console.WriteLine($"Removing stale directory at {modsRpf}...");
                Directory.Delete(modsRpf, true);
            }

            if (!File.Exists(modsRpf))
            {
                if (!createModsCopy)
                {
                    Console.Error.WriteLine(
                        $"ERROR: Mods archive is not installed: {modsRpf}");
                    errorCode = 7;
                    return null;
                }
                Console.WriteLine($"Copying update.rpf to mods folder...");
                Directory.CreateDirectory(modsDir);
                File.Copy(originalRpf, modsRpf);
                Console.WriteLine("Copied update.rpf to mods folder.");
            }
            else
            {
                if (File.GetLastWriteTimeUtc(modsRpf).AddSeconds(1) <
                    File.GetLastWriteTimeUtc(originalRpf))
                {
                    Console.Error.WriteLine(
                        $"ERROR: mods/update/{archiveName} predates the current game archive. " +
                        "Refresh it before using the RPF loader.");
                    errorCode = 6;
                    return null;
                }
                Console.WriteLine("Mods copy of update.rpf already exists.");
            }

            Console.WriteLine($"Opening {modsRpf}...");
            var rpf = new RpfFile(modsRpf, modsRpf);
            rpf.ScanStructure(null, err => Console.Error.WriteLine($"RPF scan warning: {err}"));

            if (rpf.AllEntries == null || rpf.AllEntries.Count == 0)
            {
                Console.Error.WriteLine("ERROR: RPF scan returned no entries.");
                errorCode = 4;
                return null;
            }

            Console.WriteLine($"RPF scanned: {rpf.AllEntries.Count} entries");

            if (createModsCopy)
            {
                Console.WriteLine("Ensuring OPEN encryption...");
                RpfFile.EnsureValidEncryption(rpf, null, true);
                Console.WriteLine("Encryption converted to OPEN.");
            }

            return rpf;
        }

        /// <summary>Find script_txds.rpf nested inside update.rpf.</summary>
        static RpfFile FindScriptTxdsRpf(RpfFile updateRpf)
        {
            // Path: x64/textures/script_txds.rpf (nested RPF inside update.rpf)
            if (updateRpf.Children == null) return null;

            foreach (var child in updateRpf.Children)
            {
                if (child.Name != null &&
                    child.Name.Equals("script_txds.rpf", StringComparison.OrdinalIgnoreCase))
                    return child;
            }

            // Search deeper — it might be nested inside another child
            foreach (var child in updateRpf.Children)
            {
                var found = FindScriptTxdsRpf(child);
                if (found != null) return found;
            }

            return null;
        }

        static RpfDirectoryEntry FindDirectory(
            RpfDirectoryEntry root, string name)
        {
            if (root == null) return null;
            if (root.Name != null &&
                root.Name.Equals(name, StringComparison.OrdinalIgnoreCase))
                return root;
            if (root.Directories == null) return null;
            foreach (var directory in root.Directories)
            {
                var found = FindDirectory(directory, name);
                if (found != null) return found;
            }
            return null;
        }

        /// <summary>
        /// Open the edition-specific archive that supplies globally streamed
        /// script textures. Enhanced moved these resources to update2.rpf's
        /// root textures directory; Legacy keeps them in nested script_txds.rpf.
        /// </summary>
        static RpfDirectoryEntry OpenPreviewTextureDirectory(
            string gtaPath, out RpfFile archive, out string label, out int errorCode)
        {
            bool isGen9 = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"))
                       || File.Exists(Path.Combine(gtaPath, "eboot.bin"));
            string archiveName = isGen9 ? "update2.rpf" : "update.rpf";
            archive = OpenModsUpdateRpf(gtaPath, out errorCode, archiveName);
            label = isGen9 ? "update2.rpf/textures" : "script_txds.rpf";
            if (archive == null) return null;

            if (isGen9)
            {
                return FindDirectory(archive.Root, "textures");
            }

            return FindScriptTxdsRpf(archive)?.Root;
        }

        // ================================================================
        //  verify-ytd: Re-open script_txds.rpf and ensure every expected
        //  dictionary is actually present after injection.
        // ================================================================

        static int VerifyYtd(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe verify-ytd <gta_path> <ytd_folder>");
                return 1;
            }

            string gtaPath = args[1];
            string ytdFolder = args[2];
            if (!Directory.Exists(ytdFolder))
            {
                Console.Error.WriteLine($"ERROR: Folder not found: {ytdFolder}");
                return 4;
            }

            string[] expected = Directory.GetFiles(ytdFolder, "*.ytd")
                .Select(Path.GetFileName)
                .ToArray();
            if (expected.Length == 0)
            {
                Console.Error.WriteLine("ERROR: No .ytd files found in folder.");
                return 4;
            }

            try
            {
                var target = OpenPreviewTextureDirectory(
                    gtaPath, out var rpf, out string label, out int err);
                if (rpf == null) return err;
                if (target == null)
                {
                    Console.Error.WriteLine(
                        $"ERROR: Preview texture directory not found: {label}");
                    return 5;
                }

                var present = target.Files?
                    .OfType<RpfFileEntry>()
                    .Where(e => !string.IsNullOrEmpty(e.Name))
                    .Select(e => e.Name)
                    .ToHashSet(StringComparer.OrdinalIgnoreCase)
                    ?? new System.Collections.Generic.HashSet<string>(
                        StringComparer.OrdinalIgnoreCase);
                string[] missing = expected.Where(name => !present.Contains(name)).ToArray();
                if (missing.Length > 0)
                {
                    foreach (string name in missing)
                        Console.Error.WriteLine($"MISSING: {name}");
                    Console.Error.WriteLine(
                        $"ERROR: {missing.Length}/{expected.Length} preview dictionaries are missing.");
                    return 7;
                }

                Console.WriteLine(
                    $"Verified {expected.Length} preview dictionaries in {label}.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
        }

        // ================================================================
        //  inject-ytd: Add .ytd files into script_txds.rpf inside
        //  mods/update/update.rpf so they're available via
        //  REQUEST_STREAMED_TEXTURE_DICT.
        // ================================================================

        static int InjectYtd(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe inject-ytd <gta_path> <ytd_folder>");
                return 1;
            }

            string gtaPath = args[1];
            string ytdFolder = args[2];

            if (!Directory.Exists(ytdFolder))
            {
                Console.Error.WriteLine($"ERROR: Folder not found: {ytdFolder}");
                return 4;
            }

            string[] ytdFiles = Directory.GetFiles(ytdFolder, "*.ytd");
            if (ytdFiles.Length == 0)
            {
                Console.Error.WriteLine("ERROR: No .ytd files found in folder.");
                return 4;
            }

            try
            {
                var target = OpenPreviewTextureDirectory(
                    gtaPath, out var rpf, out string label, out int err);
                if (rpf == null) return err;
                if (target == null)
                {
                    Console.Error.WriteLine(
                        $"ERROR: Preview texture directory not found: {label}");
                    return 5;
                }

                Console.WriteLine($"Found {label} ({target.Files?.Count ?? 0} files)");

                int injected = 0;
                foreach (string ytdPath in ytdFiles)
                {
                    string fileName = Path.GetFileName(ytdPath);
                    byte[] data = File.ReadAllBytes(ytdPath);

                    // Check if already exists — overwrite if so
                    var existing = target.Files?
                        .OfType<RpfFileEntry>()
                        .FirstOrDefault(e => e.Name != null &&
                            e.Name.Equals(fileName, StringComparison.OrdinalIgnoreCase));

                    if (existing != null)
                    {
                        RpfFile.CreateFile(existing.Parent, fileName, data, true);
                        Console.WriteLine($"  ~ {fileName} ({data.Length:N0} bytes, replaced)");
                    }
                    else
                    {
                        RpfFile.CreateFile(target, fileName, data, true);
                        Console.WriteLine($"  + {fileName} ({data.Length:N0} bytes)");
                    }
                    injected++;
                }

                Console.WriteLine($"Injected {injected} .ytd files into {label}.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
        }

        // ================================================================
        //  remove-ytd: Remove .ytd files matching a prefix from
        //  script_txds.rpf inside mods/update/update.rpf.
        // ================================================================

        static int RemoveYtd(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe remove-ytd <gta_path> <prefix>\n" +
                    "  Removes all .ytd entries whose name starts with <prefix>.");
                return 1;
            }

            string gtaPath = args[1];
            string prefix = args[2].ToLowerInvariant();

            try
            {
                var target = OpenPreviewTextureDirectory(
                    gtaPath, out var rpf, out string label, out int err);
                if (rpf == null) return err;
                if (target == null)
                {
                    Console.Error.WriteLine(
                        $"ERROR: Preview texture directory not found: {label}");
                    return 5;
                }

                Console.WriteLine($"Found {label} ({target.Files?.Count ?? 0} files)");

                // Find matching entries
                var toRemove = target.Files?
                    .OfType<RpfFileEntry>()
                    .Where(e => e.Name != null &&
                        e.Name.ToLowerInvariant().StartsWith(prefix) &&
                        e.Name.ToLowerInvariant().EndsWith(".ytd"))
                    .ToList() ?? new System.Collections.Generic.List<RpfFileEntry>();

                if (toRemove.Count == 0)
                {
                    Console.WriteLine($"No .ytd files matching prefix '{prefix}' found.");
                    return 0;
                }

                foreach (var entry in toRemove)
                {
                    RpfFile.DeleteEntry(entry);
                    Console.WriteLine($"  - {entry.Name}");
                }

                Console.WriteLine($"Removed {toRemove.Count} .ytd files from {label}.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
        }

        // ================================================================
        //  build-dlc: Pack a loose DLC folder into a dlc.rpf archive
        //
        //  Recursively adds all files/directories from the loose folder
        //  into a flat RPF archive with OPEN encryption.
        //
        //  Optional --embed-rpf <src_folder> <dest_path>:
        //    First builds a standalone RPF from <src_folder>, then embeds
        //    its raw bytes at <dest_path> inside the outer DLC RPF.
        //    Example: --embed-rpf /tmp/ytds x64/textures/textures.rpf
        //    This avoids CodeWalker's buggy in-place nested RPF creation.
        // ================================================================

        static int BuildDlc(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe build-dlc <loose_folder> <output_rpf> " +
                    "[--embed-rpf <src_folder> <dest_path>] [--gta-path <path>]");
                return 1;
            }

            string looseFolder = args[1];
            string outputRpf = args[2];

            // Parse optional --embed-rpf flag
            string embedSrcFolder = null;
            string embedDestPath = null;
            string gtaKeysPath = null;

            for (int i = 3; i < args.Length; i++)
            {
                if (args[i] == "--embed-rpf" && i + 2 < args.Length)
                {
                    embedSrcFolder = args[i + 1];
                    embedDestPath = args[i + 2];
                    i += 2;
                }
                else if (args[i] == "--gta-path" && i + 1 < args.Length)
                {
                    gtaKeysPath = args[i + 1];
                    i += 1;
                }
            }

            if (!Directory.Exists(looseFolder))
            {
                Console.Error.WriteLine($"ERROR: Folder not found: {looseFolder}");
                return 4;
            }

            if (embedSrcFolder != null && !Directory.Exists(embedSrcFolder))
            {
                Console.Error.WriteLine($"ERROR: Embed source folder not found: {embedSrcFolder}");
                return 4;
            }

            try
            {
                if (gtaKeysPath != null)
                {
                    bool isGen9 = File.Exists(
                                      Path.Combine(gtaKeysPath, "GTA5_Enhanced.exe"))
                               || File.Exists(Path.Combine(gtaKeysPath, "eboot.bin"));
                    GTA5Keys.LoadFromPath(gtaKeysPath, isGen9, null);
                    Console.WriteLine("Loaded GTA encryption keys for nested RPFs.");
                }
                byte[] innerRpfBytes = null;

                // Phase 1: Build inner RPF as standalone file if requested
                if (embedSrcFolder != null)
                {
                    Console.WriteLine($"Building inner RPF from: {embedSrcFolder}");

                    string tempDir = Path.GetDirectoryName(outputRpf);
                    if (string.IsNullOrEmpty(tempDir)) tempDir = ".";
                    string tempInnerPath = Path.Combine(tempDir, "_inner_temp.rpf");

                    // Clean up any previous temp file
                    if (File.Exists(tempInnerPath))
                        File.Delete(tempInnerPath);

                    var innerRpf = RpfFile.CreateNew(tempDir, "_inner_temp.rpf",
                        RpfEncryption.OPEN);

                    int innerCount = AddDirectoryContents(innerRpf.Root, embedSrcFolder);
                    Console.WriteLine($"Inner RPF: {innerCount} files packed.");

                    // Read the finished RPF bytes
                    innerRpfBytes = File.ReadAllBytes(tempInnerPath);
                    Console.WriteLine($"Inner RPF size: {innerRpfBytes.Length:N0} bytes");

                    // Clean up temp file
                    File.Delete(tempInnerPath);
                }

                // Phase 2: Build outer dlc.rpf
                Console.WriteLine($"Building dlc.rpf from: {looseFolder}");
                Console.WriteLine($"Output: {outputRpf}");

                string outputDir = Path.GetDirectoryName(outputRpf);
                if (!string.IsNullOrEmpty(outputDir))
                    Directory.CreateDirectory(outputDir);

                if (File.Exists(outputRpf))
                    File.Delete(outputRpf);

                var rpf = RpfFile.CreateNew(outputDir ?? ".", Path.GetFileName(outputRpf),
                    RpfEncryption.OPEN);
                Console.WriteLine("Created dlc.rpf.");

                int fileCount = AddDirectoryContents(rpf.Root, looseFolder);

                // Phase 3: Embed inner RPF at the specified path
                if (innerRpfBytes != null && embedDestPath != null)
                {
                    // Navigate/create directory structure for dest path
                    // e.g. "x64/textures/textures.rpf"
                    string[] parts = embedDestPath.Replace('\\', '/').Split('/');
                    RpfDirectoryEntry currentDir = rpf.Root;

                    // Create intermediate directories (all parts except last)
                    for (int i = 0; i < parts.Length - 1; i++)
                    {
                        string dirName = parts[i];
                        // Check if directory already exists
                        var existingDir = currentDir.Directories?
                            .FirstOrDefault(d => d.Name.Equals(dirName,
                                StringComparison.OrdinalIgnoreCase));
                        if (existingDir != null)
                        {
                            currentDir = existingDir;
                        }
                        else
                        {
                            currentDir = RpfFile.CreateDirectory(currentDir, dirName);
                        }
                    }

                    string innerFileName = parts[parts.Length - 1];
                    RpfFile.CreateFile(currentDir, innerFileName, innerRpfBytes, true);
                    Console.WriteLine($"  + {embedDestPath} ({innerRpfBytes.Length:N0} bytes, nested RPF)");
                    fileCount++;
                }

                Console.WriteLine($"dlc.rpf built successfully ({fileCount} files).");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: Failed to build dlc.rpf: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 7;
            }
        }

        static int AddDirectoryContents(RpfDirectoryEntry parentEntry, string sourceDir)
        {
            int count = 0;

            foreach (string filePath in Directory.GetFiles(sourceDir))
            {
                string fileName = Path.GetFileName(filePath);
                byte[] data = File.ReadAllBytes(filePath);
                RpfFile.CreateFile(parentEntry, fileName, data, true);
                Console.WriteLine($"  + {fileName} ({data.Length:N0} bytes)");
                count++;
            }

            foreach (string subDir in Directory.GetDirectories(sourceDir))
            {
                string dirName = Path.GetFileName(subDir);
                var subEntry = RpfFile.CreateDirectory(parentEntry, dirName);
                Console.WriteLine($"  / {dirName}/");
                count += AddDirectoryContents(subEntry, subDir);
            }

            return count;
        }

        // ================================================================
        //  verify-dlc: Ensure metadata, nested RPF and every expected YTD
        //  can be read back before the archive is placed in the game.
        // ================================================================

        static int VerifyDlc(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe verify-dlc <dlc_rpf> <ytd_folder>");
                return 1;
            }

            string dlcPath = args[1];
            string ytdFolder = args[2];
            if (!File.Exists(dlcPath) || !Directory.Exists(ytdFolder))
            {
                Console.Error.WriteLine("ERROR: DLC archive or YTD folder not found.");
                return 4;
            }

            try
            {
                var rpf = new RpfFile(dlcPath, dlcPath);
                rpf.ScanStructure(null,
                    err => Console.Error.WriteLine($"RPF scan warning: {err}"));
                var texturesEntry = FindFileRecursive(rpf, "textures.rpf");
                if (FindFileRecursive(rpf, "content.xml") == null ||
                    FindFileRecursive(rpf, "setup2.xml") == null ||
                    texturesEntry == null)
                {
                    Console.Error.WriteLine(
                        "ERROR: DLC is missing content.xml, setup2.xml, or textures.rpf.");
                    return 5;
                }

                string[] expected = Directory.GetFiles(ytdFolder, "*.ytd")
                    .Select(Path.GetFileName)
                    .ToArray();
                if (expected.Length == 0)
                {
                    Console.Error.WriteLine("ERROR: No expected YTD files were supplied.");
                    return 4;
                }

                // CodeWalker's automatic child-RPF discovery depends on the
                // archive's surrounding directory. Extract and scan the
                // embedded file explicitly so verification is path-neutral
                // and proves the bytes GTA will actually mount.
                string tempInner = Path.Combine(
                    Path.GetTempPath(), $"allin1-verify-{Guid.NewGuid():N}.rpf");
                try
                {
                    byte[] innerBytes = texturesEntry.File.ExtractFile(texturesEntry);
                    if (innerBytes == null || innerBytes.Length == 0)
                    {
                        Console.Error.WriteLine("ERROR: Embedded textures.rpf is empty.");
                        return 5;
                    }
                    File.WriteAllBytes(tempInner, innerBytes);
                    var innerRpf = new RpfFile(tempInner, tempInner);
                    innerRpf.ScanStructure(null,
                        err => Console.Error.WriteLine($"Nested RPF scan warning: {err}"));
                    var missing = expected
                        .Where(name => FindFileRecursive(innerRpf, name) == null)
                        .ToArray();
                    if (missing.Length > 0)
                    {
                        Console.Error.WriteLine(
                            "ERROR: Missing dictionaries: " + string.Join(", ", missing));
                        return 5;
                    }
                }
                finally
                {
                    if (File.Exists(tempInner)) File.Delete(tempInner);
                }

                Console.WriteLine(
                    $"Verified preview DLC: {expected.Length} texture dictionaries present.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: DLC verification failed: {ex.Message}");
                return 7;
            }
        }

        // ================================================================
        //  convert-gen9: Convert .ytd files from Legacy to Enhanced format
        //
        //  GTA V Enhanced (gen9) uses different resource file versions.
        //  YTD files built by YTDToolio are in Legacy format (version 13).
        //  Enhanced requires version 5.  This command loads each .ytd and
        //  re-saves it via CodeWalker with RpfManager.IsGen9 = true,
        //  producing Enhanced-compatible files.
        // ================================================================

        static int ConvertGen9(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe convert-gen9 <ytd_folder>\n" +
                    "  Converts all .ytd files in the folder from Legacy to Enhanced format.");
                return 1;
            }

            string ytdFolder = args[1];

            if (!Directory.Exists(ytdFolder))
            {
                Console.Error.WriteLine($"ERROR: Folder not found: {ytdFolder}");
                return 4;
            }

            string[] ytdFiles = Directory.GetFiles(ytdFolder, "*.ytd");
            if (ytdFiles.Length == 0)
            {
                Console.Error.WriteLine("ERROR: No .ytd files found in folder.");
                return 4;
            }

            try
            {
                // Enable gen9 mode so Save() produces Enhanced-format files
                var prevGen9 = RpfManager.IsGen9;
                RpfManager.IsGen9 = true;

                int converted = 0;
                int skipped = 0;

                foreach (string ytdPath in ytdFiles)
                {
                    string fileName = Path.GetFileName(ytdPath);
                    byte[] data = File.ReadAllBytes(ytdPath);

                    byte[] result = Gen9Converter.TryConvert(
                        data, ".ytd",
                        msg => Console.WriteLine($"  {msg}"),
                        fileName, false, out bool wasConverted);

                    if (wasConverted && result != null)
                    {
                        File.WriteAllBytes(ytdPath, result);
                        Console.WriteLine($"  + {fileName} converted ({data.Length:N0} -> {result.Length:N0} bytes)");
                        converted++;
                    }
                    else
                    {
                        Console.WriteLine($"  ~ {fileName} already gen9, skipped");
                        skipped++;
                    }
                }

                RpfManager.IsGen9 = prevGen9;

                Console.WriteLine($"Converted {converted} .ytd files to gen9 format ({skipped} already up to date).");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
        }

        // ================================================================
        //  inspect: Dump RPF structure and XML file contents
        // ================================================================

        static int InspectRpf(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine("Usage: RpfPatcher.exe inspect <gta_path> <rpf_path>");
                Console.Error.WriteLine("  gta_path: GTA V root (needed for encryption keys)");
                Console.Error.WriteLine("  rpf_path: path to the .rpf file to inspect");
                return 1;
            }

            string gtaPath = args[1];
            string rpfPath = args[2];

            if (!File.Exists(rpfPath))
            {
                Console.Error.WriteLine($"ERROR: File not found: {rpfPath}");
                return 4;
            }

            try
            {
                // Try to load encryption keys (optional — OPEN RPFs don't need them)
                try
                {
                    bool isGen9 = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"))
                               || File.Exists(Path.Combine(gtaPath, "eboot.bin"));
                    GTA5Keys.LoadFromPath(gtaPath, isGen9, null);
                }
                catch
                {
                    Console.WriteLine("Warning: Could not load encryption keys. Encrypted RPFs may fail.");
                }

                // Open and scan RPF
                var rpf = new RpfFile(rpfPath, rpfPath);
                rpf.ScanStructure(null, err => { });

                Console.WriteLine($"=== RPF: {rpfPath} ===");
                Console.WriteLine($"Version: {rpf.Version}");
                Console.WriteLine($"Encryption: {rpf.Encryption}");
                Console.WriteLine($"Entries: {rpf.AllEntries?.Count ?? 0}");
                Console.WriteLine();

                // Print file tree
                Console.WriteLine("--- File Tree ---");
                PrintTree(rpf, "", rpf.Root);
                Console.WriteLine();

                // Extract and print XML files, plus MLO entity-set names from
                // YTYP resources. The latter is useful when auditing native
                // interiors: ACTIVATE_INTERIOR_ENTITY_SET requires the exact
                // name stored in the archetype rather than the drawable name.
                if (rpf.AllEntries != null)
                {
                    var assetNamesByHash = rpf.AllEntries
                        .OfType<RpfFileEntry>()
                        .Where(file => !string.IsNullOrEmpty(file.Name))
                        .Select(file => Path.GetFileNameWithoutExtension(file.Name)
                            .ToLowerInvariant())
                        .Distinct(StringComparer.OrdinalIgnoreCase)
                        .GroupBy(name => JenkHash.GenHash(name))
                        .ToDictionary(group => group.Key, group => group.First());
                    foreach (var entry in rpf.AllEntries.OfType<RpfFileEntry>())
                    {
                        if (entry.Name == null) continue;
                        string lower = entry.Name.ToLowerInvariant();
                        if (lower.EndsWith(".xml") || lower.EndsWith(".meta"))
                        {
                            Console.WriteLine($"--- {entry.Path} ---");
                            try
                            {
                                byte[] data = entry.File.ExtractFile(entry);
                                if (data != null && data.Length > 0)
                                {
                                    string text = Encoding.UTF8.GetString(data).TrimStart('\uFEFF');
                                    Console.WriteLine(text);
                                }
                                else
                                {
                                    Console.WriteLine("(empty)");
                                }
                            }
                            catch (Exception ex)
                            {
                                Console.WriteLine($"(extract failed: {ex.Message})");
                            }
                            Console.WriteLine();
                        }
                        else if (lower.EndsWith(".ytyp"))
                        {
                            Console.WriteLine($"--- MLO entity sets: {entry.Path} ---");
                            try
                            {
                                byte[] data = entry.File.ExtractFile(entry);
                                var ytyp = new YtypFile(entry);
                                ytyp.Load(data, entry);
                                bool foundMlo = false;
                                foreach (var mlo in (ytyp.AllArchetypes ?? Array.Empty<Archetype>())
                                    .OfType<MloArchetype>())
                                {
                                    foundMlo = true;
                                    Console.WriteLine($"MLO {mlo.Name}");
                                    foreach (var set in mlo.entitySets ?? Array.Empty<MCMloEntitySet>())
                                    {
                                        Console.WriteLine($"  {set.Name} ({set.Entities?.Length ?? 0} entities)");
                                        foreach (var entity in set.Entities ?? Array.Empty<MCEntityDef>())
                                        {
                                            var position = entity.Data.position;
                                            uint archetypeHash = entity.Data.archetypeName.Hash;
                                            string archetypeName = assetNamesByHash.TryGetValue(
                                                archetypeHash, out string resolvedName)
                                                ? resolvedName
                                                : archetypeHash.ToString();
                                            Console.WriteLine(
                                                $"    {archetypeName} " +
                                                $"at ({position.X:F3}, {position.Y:F3}, {position.Z:F3})");
                                        }
                                    }
                                }
                                if (!foundMlo)
                                    Console.WriteLine("(no MLO archetypes)");
                            }
                            catch (Exception ex)
                            {
                                Console.WriteLine($"(YTYP parse failed: {ex.Message})");
                            }
                            Console.WriteLine();
                        }
                        else if (lower.EndsWith(".ymap"))
                        {
                            Console.WriteLine($"--- MLO instances: {entry.Path} ---");
                            try
                            {
                                byte[] data = entry.File.ExtractFile(entry);
                                var ymap = new YmapFile(entry);
                                ymap.Load(data, entry);
                                bool foundMlo = false;
                                foreach (var entity in ymap.AllEntities ?? Array.Empty<YmapEntityDef>())
                                {
                                    if (!entity.IsMlo || entity.MloInstance == null) continue;
                                    foundMlo = true;
                                    Console.WriteLine(
                                        $"MLO {entity.CEntityDef.archetypeName} at " +
                                        $"({entity.Position.X:F3}, {entity.Position.Y:F3}, {entity.Position.Z:F3})");
                                    foreach (var set in entity.MloInstance.defaultEntitySets
                                        ?? Array.Empty<MetaHash>())
                                        Console.WriteLine($"  default {set.Hash}");
                                }
                                if (!foundMlo)
                                    Console.WriteLine("(no MLO instances)");
                            }
                            catch (Exception ex)
                            {
                                Console.WriteLine($"(YMAP parse failed: {ex.Message})");
                            }
                            Console.WriteLine();
                        }
                    }
                }

                // Recurse into child RPFs
                if (rpf.Children != null)
                {
                    foreach (var child in rpf.Children)
                    {
                        Console.WriteLine($"\n=== Nested RPF: {child.Name} ===");
                        Console.WriteLine($"Version: {child.Version}");
                        Console.WriteLine($"Encryption: {child.Encryption}");
                        Console.WriteLine($"Entries: {child.AllEntries?.Count ?? 0}");
                        Console.WriteLine();
                        Console.WriteLine("--- File Tree ---");
                        PrintTree(child, "", child.Root);
                        Console.WriteLine();

                        if (child.AllEntries != null)
                        {
                            foreach (var entry in child.AllEntries.OfType<RpfFileEntry>())
                            {
                                if (entry.Name == null) continue;
                                string lower = entry.Name.ToLowerInvariant();
                                if (lower.EndsWith(".xml") || lower.EndsWith(".meta"))
                                {
                                    Console.WriteLine($"--- {entry.Path} ---");
                                    try
                                    {
                                        byte[] data = entry.File.ExtractFile(entry);
                                        if (data != null && data.Length > 0)
                                        {
                                            string text = Encoding.UTF8.GetString(data).TrimStart('\uFEFF');
                                            Console.WriteLine(text);
                                        }
                                        else
                                        {
                                            Console.WriteLine("(empty)");
                                        }
                                    }
                                    catch (Exception ex)
                                    {
                                        Console.WriteLine($"(extract failed: {ex.Message})");
                                    }
                                    Console.WriteLine();
                                }
                            }
                        }
                    }
                }

                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
        }

        static void PrintTree(RpfFile rpf, string indent, RpfDirectoryEntry dir)
        {
            if (dir == null) return;

            if (dir.Directories != null)
            {
                foreach (var sub in dir.Directories)
                {
                    Console.WriteLine($"{indent}{sub.Name}/");
                    PrintTree(rpf, indent + "  ", sub);
                }
            }

            if (dir.Files != null)
            {
                foreach (var file in dir.Files)
                {
                    string size = file is RpfResourceFileEntry res
                        ? $"{res.FileSize:N0}b (res v{res.Version})"
                        : file is RpfBinaryFileEntry bin
                            ? $"{bin.FileUncompressedSize:N0}b"
                            : "?b";
                    Console.WriteLine($"{indent}{file.Name}  [{size}]");
                }
            }
        }

        // Build a texture dictionary from standards-compliant DDS files.
        // PNG-to-BC3 conversion is intentionally performed by the Python
        // installer because the historical YTDToolio PNG encoder emits
        // corrupt scanlines on current Windows systems.
        static int BuildYtd(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe build-ytd <dds_folder> <output_ytd> [legacy|gen9]");
                return 1;
            }

            string ddsFolder = args[1];
            string outputPath = args[2];
            bool isGen9 = args.Length >= 4 &&
                args[3].Equals("gen9", StringComparison.OrdinalIgnoreCase);
            if (!Directory.Exists(ddsFolder))
            {
                Console.Error.WriteLine($"ERROR: Folder not found: {ddsFolder}");
                return 4;
            }

            string[] files = Directory.GetFiles(ddsFolder, "*.dds")
                .OrderBy(path => path, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            if (files.Length == 0)
            {
                Console.Error.WriteLine("ERROR: No .dds files found.");
                return 4;
            }

            var previous = RpfManager.IsGen9;
            try
            {
                var textures = new List<Texture>();
                foreach (string file in files)
                {
                    var texture = DDSIO.GetTexture(File.ReadAllBytes(file));
                    if (texture == null)
                        throw new InvalidDataException($"Unsupported DDS: {file}");
                    texture.Name = Path.GetFileNameWithoutExtension(file).ToLowerInvariant();
                    texture.NameHash = JenkHash.GenHash(texture.Name);
                    texture.Usage = TextureUsage.DIFFUSE;
                    textures.Add(texture);
                    Console.WriteLine(
                        $"  + {texture.Name} ({texture.Width}x{texture.Height}, {texture.Format})");
                }

                var dictionary = new TextureDictionary();
                dictionary.BuildFromTextureList(textures);
                var ytd = new YtdFile { TextureDict = dictionary };
                RpfManager.IsGen9 = isGen9;
                byte[] data = ytd.Save();
                string parent = Path.GetDirectoryName(Path.GetFullPath(outputPath));
                if (!string.IsNullOrEmpty(parent)) Directory.CreateDirectory(parent);
                File.WriteAllBytes(outputPath, data);
                Console.WriteLine(
                    $"Built {(isGen9 ? "Gen9" : "Legacy")} YTD with {textures.Count} textures: {outputPath}");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
            finally
            {
                RpfManager.IsGen9 = previous;
            }
        }

        static int UnpackYtd(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe unpack-ytd <ytd_path> <output_folder> [legacy|gen9]");
                return 1;
            }

            string ytdPath = args[1];
            string outputFolder = args[2];
            bool isGen9 = args.Length < 4 ||
                !args[3].Equals("legacy", StringComparison.OrdinalIgnoreCase);
            if (!File.Exists(ytdPath))
            {
                Console.Error.WriteLine($"ERROR: File not found: {ytdPath}");
                return 4;
            }

            var previous = RpfManager.IsGen9;
            try
            {
                RpfManager.IsGen9 = isGen9;
                var ytd = new YtdFile();
                ytd.Load(File.ReadAllBytes(ytdPath));
                var textures = ytd.TextureDict?.Textures?.data_items ?? Array.Empty<Texture>();
                Directory.CreateDirectory(outputFolder);
                foreach (var texture in textures)
                {
                    if (texture == null || string.IsNullOrWhiteSpace(texture.Name)) continue;
                    string output = Path.Combine(outputFolder, texture.Name + ".dds");
                    File.WriteAllBytes(output, DDSIO.GetDDSFile(texture));
                    Console.WriteLine($"  + {texture.Name}.dds");
                }
                Console.WriteLine($"Unpacked {textures.Length} textures to {outputFolder}");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
            finally
            {
                RpfManager.IsGen9 = previous;
            }
        }

        // Read-only diagnostics used to compare ALLIN1 resources with native
        // Enhanced files without requiring a GUI archive editor.
        static int ExtractEntry(string[] args)
        {
            if (args.Length < 5)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe extract-entry <gta_path> <rpf_path> <name> <output>");
                return 1;
            }

            string gtaPath = args[1];
            string rpfPath = args[2];
            string entryName = args[3];
            string outputPath = args[4];
            if (!File.Exists(rpfPath))
            {
                Console.Error.WriteLine($"ERROR: File not found: {rpfPath}");
                return 4;
            }

            try
            {
                bool isGen9 = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"))
                           || File.Exists(Path.Combine(gtaPath, "eboot.bin"));
                GTA5Keys.LoadFromPath(gtaPath, isGen9, null);
                var rpf = new RpfFile(rpfPath, rpfPath);
                rpf.ScanStructure(null,
                    err => Console.Error.WriteLine($"RPF scan warning: {err}"));
                string normalizedRequest = entryName
                    .Replace('\\', '/').TrimStart('/');
                bool pathRequest = normalizedRequest.Contains('/');
                string archivePrefix = Path.GetFullPath(rpfPath)
                    .Replace('\\', '/').TrimEnd('/') + "/";
                var matches = rpf.AllEntries?
                    .OfType<RpfFileEntry>()
                    .Where(entry => pathRequest
                        ? string.Equals(
                            entry.Path.Replace('\\', '/').StartsWith(
                                archivePrefix, StringComparison.OrdinalIgnoreCase)
                                ? entry.Path.Replace('\\', '/').Substring(
                                    archivePrefix.Length)
                                : entry.Path.Replace('\\', '/'),
                            normalizedRequest,
                            StringComparison.OrdinalIgnoreCase)
                        : string.Equals(entry.Name, entryName,
                            StringComparison.OrdinalIgnoreCase))
                    .ToArray() ?? Array.Empty<RpfFileEntry>();
                if (matches.Length == 0)
                {
                    Console.Error.WriteLine($"ERROR: Entry not found: {entryName}");
                    return 5;
                }
                if (matches.Length > 1)
                {
                    Console.Error.WriteLine(
                        "ERROR: Entry name is ambiguous: " +
                        string.Join(", ", matches.Select(entry => entry.Path)));
                    return 5;
                }

                byte[] data = matches[0].File.ExtractFile(matches[0]);
                if (data == null || data.Length == 0)
                {
                    Console.Error.WriteLine("ERROR: Extracted entry was empty.");
                    return 5;
                }
                // ExtractFile returns decompressed resource payloads. Re-wrap
                // them as standalone OpenIV-compatible resource files so the
                // result can be opened and compared outside its source RPF.
                if (matches[0] is RpfResourceFileEntry resourceEntry)
                {
                    data = ResourceBuilder.AddResourceHeader(
                        resourceEntry, ResourceBuilder.Compress(data));
                }
                string parent = Path.GetDirectoryName(Path.GetFullPath(outputPath));
                if (!string.IsNullOrEmpty(parent)) Directory.CreateDirectory(parent);
                File.WriteAllBytes(outputPath, data);
                Console.WriteLine(
                    $"Extracted {matches[0].Path} ({data.Length:N0} bytes) to {outputPath}");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                return 99;
            }
        }

        // Extract a manifest of entries while scanning the large source RPF
        // only once. Each non-empty TSV line is: source/path<TAB>dest/path.
        static int ExtractEntries(string[] args)
        {
            if (args.Length < 5)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe extract-entries <gta_path> <rpf_path> <manifest_tsv> <output_root>");
                return 1;
            }

            string gtaPath = args[1];
            string rpfPath = args[2];
            string manifestPath = args[3];
            string outputRoot = Path.GetFullPath(args[4]);
            if (!File.Exists(rpfPath) || !File.Exists(manifestPath))
            {
                Console.Error.WriteLine("ERROR: Source RPF or extraction manifest not found.");
                return 4;
            }

            try
            {
                var requests = File.ReadAllLines(manifestPath)
                    .Where(line => !string.IsNullOrWhiteSpace(line)
                        && !line.TrimStart().StartsWith("#"))
                    .Select(line => line.Split(new[] { '\t' }, 2))
                    .ToArray();
                if (requests.Length == 0 || requests.Any(parts => parts.Length != 2))
                {
                    Console.Error.WriteLine(
                        "ERROR: Extraction manifest is empty or malformed.");
                    return 4;
                }

                bool isGen9 = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"))
                           || File.Exists(Path.Combine(gtaPath, "eboot.bin"));
                GTA5Keys.LoadFromPath(gtaPath, isGen9, null);
                var rpf = new RpfFile(rpfPath, rpfPath);
                rpf.ScanStructure(null,
                    err => Console.Error.WriteLine($"RPF scan warning: {err}"));

                string archivePrefix = Path.GetFullPath(rpfPath)
                    .Replace('\\', '/').TrimEnd('/') + "/";
                string outputPrefix = outputRoot.TrimEnd(
                    Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    + Path.DirectorySeparatorChar;
                var destinations = new HashSet<string>(
                    StringComparer.OrdinalIgnoreCase);
                int extracted = 0;

                foreach (string[] request in requests)
                {
                    string source = request[0].Replace('\\', '/').TrimStart('/');
                    string relativeDestination = request[1]
                        .Replace('/', Path.DirectorySeparatorChar)
                        .TrimStart(Path.DirectorySeparatorChar);
                    string destination = Path.GetFullPath(
                        Path.Combine(outputRoot, relativeDestination));
                    if (!destination.StartsWith(
                            outputPrefix, StringComparison.OrdinalIgnoreCase)
                        || !destinations.Add(destination))
                    {
                        Console.Error.WriteLine(
                            $"ERROR: Unsafe or duplicate destination: {request[1]}");
                        return 4;
                    }

                    var matches = rpf.AllEntries?
                        .OfType<RpfFileEntry>()
                        .Where(entry => string.Equals(
                            entry.Path.Replace('\\', '/').StartsWith(
                                archivePrefix, StringComparison.OrdinalIgnoreCase)
                                ? entry.Path.Replace('\\', '/').Substring(
                                    archivePrefix.Length)
                                : entry.Path.Replace('\\', '/'),
                            source, StringComparison.OrdinalIgnoreCase))
                        .ToArray() ?? Array.Empty<RpfFileEntry>();
                    if (matches.Length != 1)
                    {
                        Console.Error.WriteLine(
                            $"ERROR: Expected one match for {source}; found {matches.Length}.");
                        return 5;
                    }

                    byte[] data = matches[0].File.ExtractFile(matches[0]);
                    if (data == null || data.Length == 0)
                    {
                        Console.Error.WriteLine($"ERROR: Extracted entry was empty: {source}");
                        return 5;
                    }
                    if (matches[0] is RpfResourceFileEntry resourceEntry)
                    {
                        data = ResourceBuilder.AddResourceHeader(
                            resourceEntry, ResourceBuilder.Compress(data));
                    }
                    string parent = Path.GetDirectoryName(destination);
                    if (!string.IsNullOrEmpty(parent)) Directory.CreateDirectory(parent);
                    File.WriteAllBytes(destination, data);
                    extracted++;
                    Console.WriteLine(
                        $"Extracted {source} -> {request[1]} ({data.Length:N0} bytes)");
                }

                Console.WriteLine($"Extracted {extracted} entries from {rpfPath}.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                return 99;
            }
        }

        // Rewrite staged game-owned nested RPFs to Open encryption. This is
        // required when moving them under a different DLC device/mount path.
        static int OpenRpfs(string[] args)
        {
            if (args.Length < 4)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe open-rpfs <gta_path> <manifest_tsv> <output_root>");
                return 1;
            }

            string gtaPath = args[1];
            string manifestPath = args[2];
            string outputRoot = Path.GetFullPath(args[3]);
            if (!File.Exists(manifestPath) || !Directory.Exists(outputRoot))
            {
                Console.Error.WriteLine("ERROR: Manifest or staging root not found.");
                return 4;
            }

            try
            {
                bool isGen9 = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"))
                           || File.Exists(Path.Combine(gtaPath, "eboot.bin"));
                GTA5Keys.LoadFromPath(gtaPath, isGen9, null);
                string outputPrefix = outputRoot.TrimEnd(
                    Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                    + Path.DirectorySeparatorChar;
                string[] destinations = File.ReadAllLines(manifestPath)
                    .Where(line => !string.IsNullOrWhiteSpace(line)
                        && !line.TrimStart().StartsWith("#"))
                    .Select(line => line.Split(new[] { '\t' }, 2))
                    .Where(parts => parts.Length == 2
                        && parts[1].EndsWith(".rpf", StringComparison.OrdinalIgnoreCase))
                    .Select(parts => parts[1])
                    .ToArray();
                if (destinations.Length == 0)
                {
                    Console.Error.WriteLine("ERROR: Manifest contains no nested RPFs.");
                    return 4;
                }

                int converted = 0;
                foreach (string relative in destinations)
                {
                    string path = Path.GetFullPath(Path.Combine(
                        outputRoot,
                        relative.Replace('/', Path.DirectorySeparatorChar)
                            .TrimStart(Path.DirectorySeparatorChar)));
                    if (!path.StartsWith(outputPrefix, StringComparison.OrdinalIgnoreCase)
                        || !File.Exists(path))
                    {
                        Console.Error.WriteLine(
                            $"ERROR: Unsafe or missing staged RPF: {relative}");
                        return 4;
                    }

                    var rpf = new RpfFile(path, path);
                    rpf.ScanStructure(null,
                        err => Console.Error.WriteLine($"RPF scan warning: {err}"));
                    RpfFile.EnsureValidEncryption(rpf, null, false);
                    if (!RpfFile.IsValidEncryption(rpf, false))
                    {
                        Console.Error.WriteLine(
                            $"ERROR: Could not convert staged RPF to Open: {relative}");
                        return 5;
                    }
                    converted++;
                    Console.WriteLine($"Converted staged RPF to Open: {relative}");
                }

                Console.WriteLine($"Converted {converted} staged RPFs to Open encryption.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: Open RPF conversion failed: {ex.Message}");
                return 99;
            }
        }

        private const string EroBehavioursSha256 =
            "884805ff75e2e40b8a27f6909c2bcc2f7f7024687e0288a6f6126f2ec49793b5";
        private const string EroPhysicsTasksSha256 =
            "d06f620686ccddbc94e260dfc9a5e0d7aa3e0caa392541009ad6405bd2d0a9a0";

        private sealed class EuphoriaArchiveSpec
        {
            internal string Archive;
            internal Dictionary<string, byte[]> Entries;
        }

        private sealed class EuphoriaArchiveTarget
        {
            internal EuphoriaArchiveSpec Spec;
            internal RpfFile Rpf;
            internal string ModsPath;
        }

        // E.R.O.'s OIV writes both update.rpf and the two base fallback
        // archives. Installing all four declared entries matters on builds
        // whose load order ignores one copy. Stock archives are never edited:
        // only OpenRPF's mods copies are created or changed.
        static int InstallEuphoria(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe install-euphoria <gta_path> <payload_folder_or_oiv> [--allow-enhanced]");
                return 1;
            }
            string gtaPath = Path.GetFullPath(args[1]);
            string source = Path.GetFullPath(args[2]);
            if (IsGtaProcessRunning())
            {
                Console.Error.WriteLine(
                    "ERROR: Close GTA V before installing Euphoria archive tuning.");
                return 11;
            }
            bool enhanced = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"));
            bool allowEnhanced = args.Skip(3).Any(value =>
                value.Equals("--allow-enhanced", StringComparison.OrdinalIgnoreCase));
            if (enhanced && !allowEnhanced)
            {
                Console.Error.WriteLine(
                    "ERROR: E.R.O. 1.9.4 targets GTA V Legacy. Enhanced compatibility " +
                    "is experimental; rerun with --allow-enhanced to acknowledge that risk.");
                return 8;
            }

            if (!TryLoadEuphoriaPayload(source, out var payload,
                    out string sourceLabel, out string payloadError))
            {
                Console.Error.WriteLine("ERROR: " + payloadError);
                return 4;
            }

            var targets = new List<EuphoriaArchiveTarget>();
            bool tuningWritesStarted = false;
            try
            {
                EuphoriaArchiveSpec[] specs = BuildEuphoriaArchiveSpecs(payload);
                foreach (EuphoriaArchiveSpec spec in specs)
                {
                    RpfFile rpf = OpenEuphoriaArchive(
                        gtaPath, spec.Archive, true, out int errorCode);
                    if (rpf == null) return errorCode;
                    targets.Add(new EuphoriaArchiveTarget
                    {
                        Spec = spec,
                        Rpf = rpf,
                        ModsPath = GetModsArchivePath(gtaPath, spec.Archive),
                    });
                }

                // Do not write a single tuning entry until every archive can be
                // opened and every complete pre-install snapshot is available.
                foreach (EuphoriaArchiveTarget target in targets)
                    EnsureEuphoriaBackup(target.ModsPath);

                tuningWritesStarted = true;
                foreach (EuphoriaArchiveTarget target in targets)
                {
                    InstallEuphoriaEntries(target.Rpf, target.Spec.Entries);
                    int verification = VerifyEuphoriaArchive(
                        target.Rpf, target.Spec.Entries,
                        "mods/" + target.Spec.Archive);
                    if (verification != 0)
                    {
                        TryRollbackEuphoriaInstall(gtaPath, targets);
                        return verification;
                    }
                }
                WriteEuphoriaMarker(gtaPath, enhanced, payload, sourceLabel);
                int markerVerification = VerifyEuphoriaMarker(gtaPath, payload);
                if (markerVerification != 0)
                {
                    TryRollbackEuphoriaInstall(gtaPath, targets);
                    return markerVerification;
                }
                return 0;
            }
            catch (Exception ex)
            {
                if (tuningWritesStarted)
                    TryRollbackEuphoriaInstall(gtaPath, targets);
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
        }

        static int VerifyEuphoria(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe verify-euphoria <gta_path> <payload_folder_or_oiv>");
                return 1;
            }
            string gtaPath = Path.GetFullPath(args[1]);
            if (!TryLoadEuphoriaPayload(Path.GetFullPath(args[2]),
                    out var payload, out _, out string payloadError))
            {
                Console.Error.WriteLine("ERROR: " + payloadError);
                return 4;
            }
            try
            {
                foreach (EuphoriaArchiveSpec spec in
                    BuildEuphoriaArchiveSpecs(payload))
                {
                    RpfFile rpf = OpenEuphoriaArchive(
                        gtaPath, spec.Archive, false, out int errorCode);
                    if (rpf == null) return errorCode;
                    int result = VerifyEuphoriaArchive(
                        rpf, spec.Entries, "mods/" + spec.Archive);
                    if (result != 0) return result;
                }
                int markerResult = VerifyEuphoriaMarker(gtaPath, payload);
                if (markerResult != 0) return markerResult;
                Console.WriteLine("All Euphoria archive tuning entries verified.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                return 99;
            }
        }

        static int ValidateEuphoria(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe validate-euphoria <payload_folder_or_archive>");
                return 1;
            }
            if (!TryLoadEuphoriaPayload(Path.GetFullPath(args[1]),
                    out var payload, out string sourceLabel,
                    out string payloadError))
            {
                Console.Error.WriteLine("ERROR: " + payloadError);
                return 4;
            }
            Console.WriteLine($"Euphoria payload is valid: {sourceLabel}");
            Console.WriteLine(
                $"  behaviours.xml: {payload["behaviours.xml"].Length:N0} bytes");
            Console.WriteLine(
                $"  physicstasks.ymt: {payload["physicstasks.ymt"].Length:N0} bytes");
            return 0;
        }

        static int RemoveEuphoria(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe remove-euphoria <gta_path>");
                return 1;
            }
            string gtaPath = Path.GetFullPath(args[1]);
            if (IsGtaProcessRunning())
            {
                Console.Error.WriteLine(
                    "ERROR: Close GTA V before removing Euphoria archive tuning.");
                return 11;
            }
            string[] archives = { "update/update.rpf", "common.rpf", "x64a.rpf" };
            var restore = new List<KeyValuePair<string, string>>();
            foreach (string archive in archives)
            {
                string target = GetModsArchivePath(gtaPath, archive);
                string backup = target + ".allin1-euphoria.bak";
                if (!File.Exists(backup))
                {
                    Console.Error.WriteLine($"MISSING ROLLBACK SNAPSHOT: {backup}");
                    return 10;
                }
                restore.Add(new KeyValuePair<string, string>(target, backup));
            }
            foreach (KeyValuePair<string, string> item in restore)
            {
                string target = item.Key;
                string backup = item.Value;
                File.Copy(backup, target, true);
                Console.WriteLine($"Restored: {target}");
            }
            string marker = Path.Combine(gtaPath, "scripts",
                "ALLIN1_euphoria_tuning.json");
            if (File.Exists(marker)) File.Delete(marker);
            Console.WriteLine("Euphoria archive tuning removed; rollback snapshots retained.");
            return 0;
        }

        static bool TryLoadEuphoriaPayload(string source,
            out Dictionary<string, byte[]> payload, out string sourceLabel,
            out string error)
        {
            payload = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase);
            sourceLabel = source;
            error = null;
            try
            {
                if (Directory.Exists(source))
                {
                    string behaviours = Directory.GetFiles(source,
                        "behaviours.xml", SearchOption.AllDirectories).FirstOrDefault();
                    string physics = Directory.GetFiles(source,
                        "physicstasks.ymt", SearchOption.AllDirectories).FirstOrDefault();
                    if (behaviours == null || physics == null)
                    {
                        error = "Payload directory must contain behaviours.xml and physicstasks.ymt.";
                        return false;
                    }
                    payload["behaviours.xml"] = File.ReadAllBytes(behaviours);
                    payload["physicstasks.ymt"] = File.ReadAllBytes(physics);
                }
                else if (File.Exists(source))
                {
                    using (ZipArchive archive = ZipFile.OpenRead(source))
                    {
                        if (!TryReadEuphoriaEntries(archive, payload))
                        {
                            ZipArchiveEntry oiv = archive.Entries.FirstOrDefault(entry =>
                                entry.FullName.EndsWith(".oiv",
                                    StringComparison.OrdinalIgnoreCase) &&
                                entry.FullName.IndexOf("1.9.4",
                                    StringComparison.OrdinalIgnoreCase) >= 0)
                                ?? archive.Entries.FirstOrDefault(entry =>
                                    entry.FullName.EndsWith(".oiv",
                                        StringComparison.OrdinalIgnoreCase));
                            if (oiv == null)
                            {
                                error = "Archive contains neither the tuning files nor an OIV package.";
                                return false;
                            }
                            using (var memory = new MemoryStream())
                            {
                                using (Stream input = oiv.Open()) input.CopyTo(memory);
                                memory.Position = 0;
                                using (var inner = new ZipArchive(memory,
                                    ZipArchiveMode.Read, false))
                                    if (!TryReadEuphoriaEntries(inner, payload))
                                    {
                                        error = $"OIV payload is missing required tuning files: {oiv.FullName}";
                                        return false;
                                    }
                            }
                            sourceLabel += "::" + oiv.FullName;
                        }
                    }
                }
                else
                {
                    error = $"Payload source not found: {source}";
                    return false;
                }
            }
            catch (Exception ex)
            {
                error = "Could not read Euphoria payload: " + ex.Message;
                return false;
            }

            string behavioursHash = Sha256(payload["behaviours.xml"]);
            string physicsHash = Sha256(payload["physicstasks.ymt"]);
            if (!behavioursHash.Equals(EroBehavioursSha256,
                    StringComparison.OrdinalIgnoreCase) ||
                !physicsHash.Equals(EroPhysicsTasksSha256,
                    StringComparison.OrdinalIgnoreCase))
            {
                error = "Payload does not match the audited E.R.O. 1.9.4 tuning files. " +
                    $"behaviours={behavioursHash}, physicstasks={physicsHash}";
                return false;
            }
            Console.WriteLine($"Validated E.R.O. 1.9.4 payload: {sourceLabel}");
            return true;
        }

        static bool TryReadEuphoriaEntries(ZipArchive archive,
            Dictionary<string, byte[]> payload)
        {
            ZipArchiveEntry behaviours = archive.Entries.FirstOrDefault(entry =>
                entry.FullName.EndsWith("/behaviours.xml",
                    StringComparison.OrdinalIgnoreCase) ||
                entry.FullName.Equals("behaviours.xml",
                    StringComparison.OrdinalIgnoreCase));
            ZipArchiveEntry physics = archive.Entries.FirstOrDefault(entry =>
                entry.FullName.EndsWith("/physicstasks.ymt",
                    StringComparison.OrdinalIgnoreCase) ||
                entry.FullName.Equals("physicstasks.ymt",
                    StringComparison.OrdinalIgnoreCase));
            if (behaviours == null || physics == null) return false;
            payload["behaviours.xml"] = ReadZipEntry(behaviours);
            payload["physicstasks.ymt"] = ReadZipEntry(physics);
            return true;
        }

        static byte[] ReadZipEntry(ZipArchiveEntry entry)
        {
            using (var memory = new MemoryStream())
            {
                using (Stream stream = entry.Open()) stream.CopyTo(memory);
                return memory.ToArray();
            }
        }

        static EuphoriaArchiveSpec[] BuildEuphoriaArchiveSpecs(
            Dictionary<string, byte[]> payload)
        {
            byte[] behaviours = payload["behaviours.xml"];
            byte[] physics = payload["physicstasks.ymt"];
            return new[]
            {
                new EuphoriaArchiveSpec
                {
                    Archive = "update/update.rpf",
                    Entries = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase)
                    {
                        { "common/data/naturalmotion/behaviours.xml", behaviours },
                        { "x64/data/tune/physicstasks.ymt", physics },
                    },
                },
                new EuphoriaArchiveSpec
                {
                    Archive = "common.rpf",
                    Entries = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase)
                    {
                        { "data/naturalmotion/behaviours.xml", behaviours },
                    },
                },
                new EuphoriaArchiveSpec
                {
                    Archive = "x64a.rpf",
                    Entries = new Dictionary<string, byte[]>(StringComparer.OrdinalIgnoreCase)
                    {
                        { "data/tune/physicstasks.ymt", physics },
                    },
                },
            };
        }

        static RpfFile OpenEuphoriaArchive(string gtaPath,
            string archive, bool createModsCopy, out int errorCode)
        {
            return archive.Equals("update/update.rpf",
                    StringComparison.OrdinalIgnoreCase)
                ? OpenModsUpdateRpf(gtaPath, out errorCode, "update.rpf",
                    createModsCopy)
                : OpenModsRootRpf(gtaPath, archive, createModsCopy,
                    out errorCode);
        }

        static RpfFile OpenModsRootRpf(string gtaPath,
            string archive, bool createModsCopy, out int errorCode)
        {
            errorCode = 0;
            bool enhanced = File.Exists(Path.Combine(gtaPath,
                "GTA5_Enhanced.exe"));
            string exe = enhanced ? "GTA5_Enhanced.exe" : "GTA5.exe";
            if (!File.Exists(Path.Combine(gtaPath, exe)))
            {
                Console.Error.WriteLine($"ERROR: {exe} not found in {gtaPath}");
                errorCode = 2;
                return null;
            }
            GTA5Keys.LoadFromPath(gtaPath, enhanced, null);
            if (GTA5Keys.PC_AES_KEY == null)
            {
                Console.Error.WriteLine("ERROR: Failed to load encryption keys.");
                errorCode = 3;
                return null;
            }
            string original = Path.Combine(gtaPath,
                archive.Replace('/', Path.DirectorySeparatorChar));
            string mods = GetModsArchivePath(gtaPath, archive);
            if (!File.Exists(original))
            {
                Console.Error.WriteLine($"ERROR: Stock archive not found: {original}");
                errorCode = 4;
                return null;
            }
            Directory.CreateDirectory(Path.GetDirectoryName(mods));
            if (!File.Exists(mods))
            {
                if (!createModsCopy)
                {
                    Console.Error.WriteLine(
                        $"ERROR: Mods archive is not installed: {mods}");
                    errorCode = 7;
                    return null;
                }
                File.Copy(original, mods, false);
                Console.WriteLine($"Copied stock archive to mods: {mods}");
            }
            else if (File.GetLastWriteTimeUtc(mods).AddSeconds(1) <
                     File.GetLastWriteTimeUtc(original))
            {
                Console.Error.WriteLine(
                    $"ERROR: Mods archive predates stock archive: {mods}");
                errorCode = 6;
                return null;
            }
            var rpf = new RpfFile(mods, mods);
            rpf.ScanStructure(null,
                warning => Console.Error.WriteLine($"RPF scan warning: {warning}"));
            if (rpf.AllEntries == null || rpf.AllEntries.Count == 0)
            {
                Console.Error.WriteLine($"ERROR: RPF scan returned no entries: {mods}");
                errorCode = 4;
                return null;
            }
            if (createModsCopy)
                RpfFile.EnsureValidEncryption(rpf, null, true);
            Console.WriteLine($"Opened mods archive: {mods} ({rpf.AllEntries.Count} entries)");
            return rpf;
        }

        static string GetModsArchivePath(string gtaPath, string archive)
        {
            return Path.GetFullPath(Path.Combine(gtaPath, "mods",
                archive.Replace('/', Path.DirectorySeparatorChar)));
        }

        static bool IsGtaProcessRunning()
        {
            return System.Diagnostics.Process.GetProcessesByName("GTA5").Length > 0 ||
                System.Diagnostics.Process.GetProcessesByName("GTA5_Enhanced").Length > 0;
        }

        static void EnsureEuphoriaBackup(string modsRpf)
        {
            string backup = modsRpf + ".allin1-euphoria.bak";
            if (!File.Exists(backup))
            {
                File.Copy(modsRpf, backup, false);
                Console.WriteLine($"Created rollback snapshot: {backup}");
            }
            else Console.WriteLine($"Preserving rollback snapshot: {backup}");
        }

        static void TryRollbackEuphoriaInstall(string gtaPath,
            IEnumerable<EuphoriaArchiveTarget> targets)
        {
            Console.Error.WriteLine(
                "Installation did not complete; restoring every pre-install snapshot.");
            foreach (EuphoriaArchiveTarget target in targets)
            {
                string backup = target.ModsPath + ".allin1-euphoria.bak";
                try
                {
                    if (!File.Exists(backup))
                    {
                        Console.Error.WriteLine(
                            $"ROLLBACK SNAPSHOT MISSING: {backup}");
                        continue;
                    }
                    File.Copy(backup, target.ModsPath, true);
                    Console.Error.WriteLine($"Rolled back: {target.ModsPath}");
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine(
                        $"ROLLBACK FAILED: {target.ModsPath}: {ex.Message}");
                }
            }
            string marker = GetEuphoriaMarkerPath(gtaPath);
            try
            {
                if (File.Exists(marker)) File.Delete(marker);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(
                    $"ROLLBACK MARKER CLEANUP FAILED: {marker}: {ex.Message}");
            }
        }

        static void InstallEuphoriaEntries(RpfFile rpf,
            Dictionary<string, byte[]> entries)
        {
            foreach (KeyValuePair<string, byte[]> item in entries)
            {
                string[] parts = item.Key.Split('/');
                RpfDirectoryEntry directory = rpf.Root;
                for (int index = 0; index < parts.Length - 1; index++)
                {
                    string name = parts[index];
                    RpfDirectoryEntry existing = directory.Directories?
                        .FirstOrDefault(entry => entry.Name.Equals(name,
                            StringComparison.OrdinalIgnoreCase));
                    directory = existing ?? RpfFile.CreateDirectory(directory, name);
                }
                string fileName = parts[parts.Length - 1];
                RpfFile.CreateFile(directory, fileName, item.Value, true);
                Console.WriteLine($"  ~ {item.Key} ({item.Value.Length:N0} bytes, " +
                    $"sha256={Sha256(item.Value)})");
            }
        }

        static int VerifyEuphoriaArchive(RpfFile rpf,
            Dictionary<string, byte[]> payload, string label)
        {
            int failures = 0;
            foreach (KeyValuePair<string, byte[]> item in payload)
            {
                RpfFileEntry entry = FindRelativeEntry(rpf, item.Key);
                byte[] actual = entry?.File.ExtractFile(entry);
                bool matches = actual != null && actual.SequenceEqual(item.Value);
                Console.WriteLine($"  {(matches ? "OK" : "FAIL")} {label}/{item.Key}" +
                    (actual == null ? " (missing)" :
                    $" ({actual.Length:N0} bytes, sha256={Sha256(actual)})"));
                if (!matches) failures++;
            }
            if (failures > 0)
            {
                Console.Error.WriteLine(
                    $"ERROR: Euphoria payload verification failed for {label} ({failures} entries). ");
                return 9;
            }
            Console.WriteLine($"Euphoria archive tuning verified in {label}.");
            return 0;
        }

        static RpfFileEntry FindRelativeEntry(RpfFile rpf, string requested)
        {
            string normalized = requested.Replace('\\', '/').TrimStart('/');
            return rpf.AllEntries?.OfType<RpfFileEntry>().FirstOrDefault(entry =>
            {
                string path = entry.Path.Replace('\\', '/');
                return path.Equals(normalized, StringComparison.OrdinalIgnoreCase) ||
                    path.EndsWith("/" + normalized,
                        StringComparison.OrdinalIgnoreCase);
            });
        }

        static string Sha256(byte[] data)
        {
            using (SHA256 algorithm = SHA256.Create())
                return BitConverter.ToString(algorithm.ComputeHash(data))
                    .Replace("-", "").ToLowerInvariant();
        }

        static void WriteEuphoriaMarker(string gtaPath, bool enhanced,
            Dictionary<string, byte[]> payload, string source)
        {
            string scripts = Path.Combine(gtaPath, "scripts");
            Directory.CreateDirectory(scripts);
            string marker = GetEuphoriaMarkerPath(gtaPath);
            string json = "{\n" +
                $"  \"installed_utc\": \"{DateTime.UtcNow:o}\",\n" +
                $"  \"edition\": \"{(enhanced ? "Enhanced" : "Legacy")}\",\n" +
                "  \"archives\": [\"mods/update/update.rpf\", \"mods/common.rpf\", \"mods/x64a.rpf\"],\n" +
                $"  \"source\": \"{JsonEscape(source)}\",\n" +
                $"  \"behaviours_sha256\": \"{Sha256(payload["behaviours.xml"])}\",\n" +
                $"  \"physicstasks_sha256\": \"{Sha256(payload["physicstasks.ymt"])}\"\n" +
                "}\n";
            File.WriteAllText(marker, json, new UTF8Encoding(false));
            Console.WriteLine($"Wrote archive tuning marker: {marker}");
        }

        static int VerifyEuphoriaMarker(string gtaPath,
            Dictionary<string, byte[]> payload)
        {
            string marker = GetEuphoriaMarkerPath(gtaPath);
            if (!File.Exists(marker))
            {
                Console.Error.WriteLine(
                    $"ERROR: Euphoria archive marker is missing: {marker}");
                return 12;
            }
            string json = File.ReadAllText(marker);
            string[] expected =
            {
                "mods/update/update.rpf",
                "mods/common.rpf",
                "mods/x64a.rpf",
                Sha256(payload["behaviours.xml"]),
                Sha256(payload["physicstasks.ymt"]),
            };
            foreach (string value in expected)
            {
                if (json.IndexOf(value, StringComparison.OrdinalIgnoreCase) >= 0)
                    continue;
                Console.Error.WriteLine(
                    $"ERROR: Euphoria archive marker is incomplete: {value}");
                return 12;
            }
            Console.WriteLine($"Euphoria archive marker verified: {marker}");
            return 0;
        }

        static string GetEuphoriaMarkerPath(string gtaPath)
        {
            return Path.Combine(gtaPath, "scripts",
                "ALLIN1_euphoria_tuning.json");
        }

        static string JsonEscape(string value)
        {
            return (value ?? "").Replace("\\", "\\\\")
                .Replace("\"", "\\\"")
                .Replace("\r", "\\r").Replace("\n", "\\n");
        }

        static int DumpYtd(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine("Usage: RpfPatcher.exe dump-ytd <ytd_path> [legacy|gen9]");
                return 1;
            }

            string ytdPath = args[1];
            bool isGen9 = args.Length < 3 ||
                !args[2].Equals("legacy", StringComparison.OrdinalIgnoreCase);
            if (!File.Exists(ytdPath))
            {
                Console.Error.WriteLine($"ERROR: File not found: {ytdPath}");
                return 4;
            }

            var previous = RpfManager.IsGen9;
            try
            {
                RpfManager.IsGen9 = isGen9;
                var ytd = new YtdFile();
                ytd.Load(File.ReadAllBytes(ytdPath));
                var textures = ytd.TextureDict?.Textures?.data_items ?? Array.Empty<Texture>();
                Console.WriteLine(
                    $"YTD: {ytdPath} mode={(isGen9 ? "gen9" : "legacy")} textures={textures.Length}");
                foreach (var texture in textures)
                {
                    if (texture == null) continue;
                    Console.WriteLine(
                        $"  {texture.Name}: {texture.Width}x{texture.Height}x{texture.Depth}, " +
                        $"levels={texture.Levels}, legacy={texture.Format}, stride={texture.Stride}, " +
                        $"g9format={texture.G9_Format}, flags=0x{texture.G9_Flags:X8}, " +
                        $"blocks={texture.G9_BlockCount}, blockStride={texture.G9_BlockStride}, " +
                        $"tile={texture.G9_TileMode}, data={texture.Data?.FullData?.Length ?? 0}, " +
                        $"srv={(texture.G9_SRV == null ? "none" : "present")}");
                }
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
            finally
            {
                RpfManager.IsGen9 = previous;
            }
        }

        static int VerifyMapDlc(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine(
                    "Usage: RpfPatcher.exe verify-map-dlc <dlc_rpf> <manifest_tsv>");
                return 1;
            }

            string dlcPath = args[1];
            string manifestPath = args[2];
            if (!File.Exists(dlcPath) || !File.Exists(manifestPath))
            {
                Console.Error.WriteLine("ERROR: Map DLC or manifest not found.");
                return 4;
            }

            try
            {
                var expected = File.ReadAllLines(manifestPath)
                    .Where(line => !string.IsNullOrWhiteSpace(line)
                        && !line.TrimStart().StartsWith("#"))
                    .Select(line => line.Split(new[] { '\t' }, 2))
                    .ToArray();
                if (expected.Length == 0 || expected.Any(parts => parts.Length != 2))
                {
                    Console.Error.WriteLine("ERROR: Map manifest is empty or malformed.");
                    return 4;
                }

                var rpf = new RpfFile(dlcPath, dlcPath);
                rpf.ScanStructure(null,
                    err => Console.Error.WriteLine($"RPF scan warning: {err}"));
                if (FindFileRecursive(rpf, "content.xml") == null
                    || FindFileRecursive(rpf, "setup2.xml") == null)
                {
                    Console.Error.WriteLine(
                        "ERROR: Map DLC is missing content.xml or setup2.xml.");
                    return 5;
                }

                string archivePrefix = Path.GetFullPath(dlcPath)
                    .Replace('\\', '/').TrimEnd('/') + "/";
                foreach (string[] request in expected)
                {
                    string destination = request[1].Replace('\\', '/').TrimStart('/');
                    var matches = rpf.AllEntries?
                        .OfType<RpfFileEntry>()
                        .Where(entry => string.Equals(
                            entry.Path.Replace('\\', '/').StartsWith(
                                archivePrefix, StringComparison.OrdinalIgnoreCase)
                                ? entry.Path.Replace('\\', '/').Substring(
                                    archivePrefix.Length)
                                : entry.Path.Replace('\\', '/'),
                            destination, StringComparison.OrdinalIgnoreCase))
                        .ToArray() ?? Array.Empty<RpfFileEntry>();
                    if (matches.Length != 1)
                    {
                        Console.Error.WriteLine(
                            $"ERROR: Expected one packed entry for {destination}; found {matches.Length}.");
                        return 5;
                    }

                    byte[] data = matches[0].File.ExtractFile(matches[0]);
                    if (data == null || data.Length == 0)
                    {
                        Console.Error.WriteLine($"ERROR: Packed entry is empty: {destination}");
                        return 5;
                    }
                    if (destination.EndsWith(".rpf", StringComparison.OrdinalIgnoreCase))
                    {
                        string temporary = Path.Combine(
                            Path.GetTempPath(), $"allin1-map-verify-{Guid.NewGuid():N}.rpf");
                        try
                        {
                            File.WriteAllBytes(temporary, data);
                            var nested = new RpfFile(temporary, temporary);
                            nested.ScanStructure(null,
                                err => Console.Error.WriteLine(
                                    $"Nested RPF scan warning: {err}"));
                            if (nested.Encryption != RpfEncryption.OPEN)
                            {
                                Console.Error.WriteLine(
                                    $"ERROR: Packed nested archive is not Open: {destination}");
                                return 5;
                            }
                        }
                        finally
                        {
                            if (File.Exists(temporary)) File.Delete(temporary);
                        }
                    }
                }

                Console.WriteLine(
                    $"Verified standalone map DLC: {expected.Length} local assets present.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: Map DLC verification failed: {ex.Message}");
                return 7;
            }
        }

        // ================================================================
        //  patch / unpatch: Modify dlclist.xml inside mods/update.rpf
        // ================================================================

        static int PatchCommand(string command, string[] args)
        {
            string gtaPath = args[1];

            try
            {
                var rpf = OpenModsUpdateRpf(gtaPath, out int err);
                if (rpf == null) return err;

                // --- Find dlclist.xml ---
                var dlclistEntry = FindFileRecursive(rpf, "dlclist.xml");

                if (dlclistEntry == null)
                {
                    Console.Error.WriteLine("ERROR: dlclist.xml not found in update.rpf (searched all nested RPFs)");
                    return 5;
                }

                Console.WriteLine($"Found dlclist.xml at: {dlclistEntry.Path}");

                // --- Extract and parse XML ---
                byte[] xmlBytes = dlclistEntry.File.ExtractFile(dlclistEntry);
                if (xmlBytes == null || xmlBytes.Length == 0)
                {
                    Console.Error.WriteLine("ERROR: Failed to extract dlclist.xml (empty data).");
                    return 5;
                }

                // Strip BOM if present
                string xmlStr = Encoding.UTF8.GetString(xmlBytes).TrimStart('\uFEFF');

                XDocument doc;
                try
                {
                    doc = XDocument.Parse(xmlStr);
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"ERROR: Failed to parse dlclist.xml: {ex.Message}");
                    return 6;
                }

                var paths = doc.Root?.Element("Paths");
                if (paths == null)
                {
                    Console.Error.WriteLine("ERROR: <Paths> element not found in dlclist.xml");
                    return 6;
                }

                // --- Patch or unpatch ---
                bool modified;
                if (command == "patch")
                    modified = PatchDlcList(paths, args.Skip(2).ToArray());
                else
                    modified = UnpatchDlcList(paths);

                if (!modified)
                {
                    Console.WriteLine("No changes needed — dlclist.xml already up to date.");
                    return 0;
                }

                // --- Write modified XML back into RPF ---
                Console.WriteLine("Writing modified dlclist.xml back to mods RPF...");

                byte[] newXmlBytes = Encoding.UTF8.GetBytes(doc.Declaration + "\n" + doc.ToString());

                try
                {
                    RpfFile.CreateFile(dlclistEntry.Parent, dlclistEntry.Name, newXmlBytes, true);
                }
                catch (Exception ex)
                {
                    Console.Error.WriteLine($"ERROR: Failed to write dlclist.xml: {ex.Message}");
                    return 7;
                }

                Console.WriteLine("dlclist.xml updated successfully in mods/update/update.rpf.");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: Unexpected error: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 99;
            }
        }

        private static bool PatchDlcList(XElement paths, string[] requested)
        {
            string[] packs = requested != null && requested.Length > 0
                ? requested
                : new[] { "allin1_previews" };
            foreach (string pack in packs)
            {
                if (!OwnedDlcEntries.ContainsKey(pack))
                {
                    Console.Error.WriteLine(
                        $"ERROR: Refusing to register unowned DLC pack '{pack}'.");
                    throw new ArgumentException($"Unknown ALLIN1 DLC pack: {pack}");
                }
            }

            bool modified = false;
            foreach (string pack in packs.Distinct(StringComparer.OrdinalIgnoreCase))
            {
                string entry = OwnedDlcEntries[pack];
                bool exists = paths.Elements("Item").Any(item =>
                    string.Equals(
                        item.Value?.Trim().TrimEnd('/'),
                        entry.TrimEnd('/'),
                        StringComparison.OrdinalIgnoreCase));
                if (exists)
                {
                    Console.WriteLine($"Entry '{pack}' already present in dlclist.xml.");
                    continue;
                }
                paths.Add(new XElement("Item", entry));
                Console.WriteLine($"Added '{entry}' to dlclist.xml.");
                modified = true;
            }
            return modified;
        }

        private static RpfFileEntry FindFileRecursive(RpfFile rpf, string fileName)
        {
            var entry = rpf.AllEntries?
                .OfType<RpfFileEntry>()
                .FirstOrDefault(e =>
                    e.Name != null &&
                    e.Name.Equals(fileName, StringComparison.OrdinalIgnoreCase));

            if (entry != null) return entry;

            if (rpf.Children != null)
            {
                foreach (var child in rpf.Children)
                {
                    entry = FindFileRecursive(child, fileName);
                    if (entry != null) return entry;
                }
            }

            return null;
        }

        private static bool UnpatchDlcList(XElement paths)
        {
            bool removed = false;
            var toRemove = paths.Elements("Item")
                .Where(item =>
                {
                    string text = item.Value?.Trim().TrimEnd('/').ToLower() ?? "";
                    return OwnedDlcEntries.Keys.Any(name => text.Contains(name));
                })
                .ToList();

            foreach (var item in toRemove)
            {
                item.Remove();
                removed = true;
            }

            if (removed)
                Console.WriteLine("Removed ALLIN1-owned DLC entries from dlclist.xml.");
            else
                Console.WriteLine("No ALLIN1-owned DLC entries found in dlclist.xml.");

            return removed;
        }
    }
}
