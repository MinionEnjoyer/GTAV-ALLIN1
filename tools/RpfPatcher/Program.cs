// RpfPatcher — Tools for managing ALLIN1 DLC content in GTA V RPF archives.
// Uses CodeWalker.Core to read/write RPF7 archives.
//
// Commands:
//   RpfPatcher.exe patch     <gta_path>                  — add allin1_previews to dlclist.xml
//   RpfPatcher.exe unpatch   <gta_path>                  — remove allin1_previews from dlclist.xml
//   RpfPatcher.exe build-dlc <loose_folder> <output_rpf> — pack loose DLC folder into dlc.rpf

using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Xml.Linq;
using CodeWalker.GameFiles;

namespace RpfPatcher
{
    class Program
    {
        private const string DLC_ENTRY = "dlcpacks:/allin1_previews/";

        static int Main(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine(
                    "Usage:\n" +
                    "  RpfPatcher.exe patch     <gta_path>\n" +
                    "  RpfPatcher.exe unpatch   <gta_path>\n" +
                    "  RpfPatcher.exe build-dlc <loose_folder> <output_rpf>");
                return 1;
            }

            string command = args[0].ToLower();

            if (command == "build-dlc")
                return BuildDlc(args);
            if (command == "patch" || command == "unpatch")
                return PatchCommand(command, args);

            Console.Error.WriteLine($"ERROR: Unknown command '{command}'.");
            return 1;
        }

        // ================================================================
        //  build-dlc: Pack a loose DLC folder into a dlc.rpf archive
        //
        //  The loose folder is expected to contain:
        //    content.xml, setup2.xml, x64/textures/*.ytd
        //
        //  The output dlc.rpf will have:
        //    content.xml, setup2.xml at root
        //    x64/textures/allin1_textures.rpf (nested RPF with all .ytd files)
        //
        //  GTA V requires texture dictionaries to be inside a nested RPF
        //  registered as RPF_FILE in content.xml — loose .ytd files inside
        //  the dlc.rpf are not loaded by the streaming system.
        // ================================================================

        private const string TEXTURES_RPF_NAME = "allin1_textures.rpf";

        static int BuildDlc(string[] args)
        {
            if (args.Length < 3)
            {
                Console.Error.WriteLine("Usage: RpfPatcher.exe build-dlc <loose_folder> <output_rpf>");
                return 1;
            }

            string looseFolder = args[1];
            string outputRpf = args[2];

            if (!Directory.Exists(looseFolder))
            {
                Console.Error.WriteLine($"ERROR: Folder not found: {looseFolder}");
                return 4;
            }

            try
            {
                Console.WriteLine($"Building dlc.rpf from: {looseFolder}");
                Console.WriteLine($"Output: {outputRpf}");

                // Ensure output directory exists
                string outputDir = Path.GetDirectoryName(outputRpf);
                if (!string.IsNullOrEmpty(outputDir))
                    Directory.CreateDirectory(outputDir);

                // Delete existing output file if present
                if (File.Exists(outputRpf))
                    File.Delete(outputRpf);

                // Create the outer dlc.rpf (OPEN encryption, no keys needed)
                var rpf = RpfFile.CreateNew(outputDir ?? ".", Path.GetFileName(outputRpf),
                    RpfEncryption.OPEN);
                Console.WriteLine("Created dlc.rpf.");

                // Add content.xml and setup2.xml at root
                AddFileIfExists(rpf.Root, looseFolder, "content.xml");
                AddFileIfExists(rpf.Root, looseFolder, "setup2.xml");

                // Create x64/textures/ directory structure
                var x64Dir = RpfFile.CreateDirectory(rpf.Root, "x64");
                var texturesDir = RpfFile.CreateDirectory(x64Dir, "textures");

                // Find all .ytd files from the loose folder's x64/textures/
                string ytdSourceDir = Path.Combine(looseFolder, "x64", "textures");
                if (!Directory.Exists(ytdSourceDir))
                {
                    Console.Error.WriteLine($"ERROR: No x64/textures/ directory in {looseFolder}");
                    return 4;
                }

                string[] ytdFiles = Directory.GetFiles(ytdSourceDir, "*.ytd");
                if (ytdFiles.Length == 0)
                {
                    Console.Error.WriteLine("ERROR: No .ytd files found in x64/textures/");
                    return 4;
                }

                // Create a nested RPF inside x64/textures/ containing all .ytd files
                Console.WriteLine($"Creating nested {TEXTURES_RPF_NAME} with {ytdFiles.Length} .ytd files...");
                var nestedRpf = RpfFile.CreateNew(texturesDir, TEXTURES_RPF_NAME,
                    RpfEncryption.OPEN);

                foreach (string ytdPath in ytdFiles)
                {
                    string ytdName = Path.GetFileName(ytdPath);
                    byte[] data = File.ReadAllBytes(ytdPath);
                    RpfFile.CreateFile(nestedRpf.Root, ytdName, data, true);
                    Console.WriteLine($"  + {ytdName} ({data.Length:N0} bytes)");
                }

                Console.WriteLine($"dlc.rpf built successfully ({ytdFiles.Length} textures).");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"ERROR: Failed to build dlc.rpf: {ex.Message}");
                Console.Error.WriteLine(ex.StackTrace);
                return 7;
            }
        }

        static void AddFileIfExists(RpfDirectoryEntry parent, string sourceDir, string fileName)
        {
            string path = Path.Combine(sourceDir, fileName);
            if (File.Exists(path))
            {
                byte[] data = File.ReadAllBytes(path);
                RpfFile.CreateFile(parent, fileName, data, true);
                Console.WriteLine($"  + {fileName} ({data.Length:N0} bytes)");
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
                // --- Detect edition ---
                bool isGen9 = File.Exists(Path.Combine(gtaPath, "GTA5_Enhanced.exe"))
                           || File.Exists(Path.Combine(gtaPath, "eboot.bin"));
                string exeName = isGen9 ? "GTA5_Enhanced.exe" : "GTA5.exe";

                if (!File.Exists(Path.Combine(gtaPath, exeName)))
                {
                    Console.Error.WriteLine($"ERROR: {exeName} not found in {gtaPath}");
                    return 2;
                }

                Console.WriteLine($"Edition: {(isGen9 ? "Enhanced" : "Legacy")}");

                // --- Load encryption keys from game exe ---
                Console.WriteLine("Loading encryption keys...");
                GTA5Keys.LoadFromPath(gtaPath, isGen9, null);

                if (GTA5Keys.PC_AES_KEY == null)
                {
                    Console.Error.WriteLine("ERROR: Failed to load encryption keys from game executable.");
                    return 3;
                }

                Console.WriteLine("Encryption keys loaded.");

                // --- Set up mods folder copy of update.rpf ---
                string originalRpf = Path.Combine(gtaPath, "update", "update.rpf");
                string modsDir = Path.Combine(gtaPath, "mods", "update");
                string modsRpf = Path.Combine(modsDir, "update.rpf");

                if (!File.Exists(originalRpf))
                {
                    Console.Error.WriteLine($"ERROR: {originalRpf} not found");
                    return 4;
                }

                // If a directory exists at the target path (left by another tool),
                // remove it so we can place the RPF file there.
                if (Directory.Exists(modsRpf))
                {
                    Console.WriteLine($"Removing stale directory at {modsRpf}...");
                    Directory.Delete(modsRpf, true);
                }

                if (!File.Exists(modsRpf))
                {
                    Console.WriteLine($"Copying update.rpf to mods folder ({modsDir})...");
                    Directory.CreateDirectory(modsDir);
                    File.Copy(originalRpf, modsRpf);
                    Console.WriteLine("Copied update.rpf to mods folder.");
                }
                else
                {
                    Console.WriteLine("Mods copy of update.rpf already exists.");
                }

                // --- Open the mods copy ---
                Console.WriteLine($"Opening {modsRpf}...");
                var rpf = new RpfFile(modsRpf, modsRpf);
                rpf.ScanStructure(null, err => Console.Error.WriteLine($"RPF scan warning: {err}"));

                if (rpf.AllEntries == null || rpf.AllEntries.Count == 0)
                {
                    Console.Error.WriteLine("ERROR: RPF scan returned no entries.");
                    return 4;
                }

                Console.WriteLine($"RPF scanned: {rpf.AllEntries.Count} entries");

                // --- Convert mods copy to OPEN encryption (recursively) ---
                Console.WriteLine("Ensuring mods RPF uses OPEN encryption...");
                RpfFile.EnsureValidEncryption(rpf, null, true);
                Console.WriteLine("Encryption converted to OPEN.");

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
                    modified = PatchDlcList(paths);
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

        private static bool PatchDlcList(XElement paths)
        {
            foreach (var item in paths.Elements("Item"))
            {
                string text = item.Value?.Trim().TrimEnd('/').ToLower() ?? "";
                if (text.Contains("allin1_previews"))
                {
                    Console.WriteLine("Entry 'allin1_previews' already present in dlclist.xml.");
                    return false;
                }
            }

            paths.Add(new XElement("Item", DLC_ENTRY));
            Console.WriteLine($"Added '{DLC_ENTRY}' to dlclist.xml.");
            return true;
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
                    return text.Contains("allin1_previews");
                })
                .ToList();

            foreach (var item in toRemove)
            {
                item.Remove();
                removed = true;
            }

            if (removed)
                Console.WriteLine("Removed 'allin1_previews' entry from dlclist.xml.");
            else
                Console.WriteLine("Entry 'allin1_previews' not found in dlclist.xml.");

            return removed;
        }
    }
}
