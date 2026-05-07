// RpfPatcher — Patches dlclist.xml inside GTA V's update.rpf
// Uses CodeWalker.Core to read/write RPF7 archives.
//
// Usage:
//   RpfPatcher.exe patch   <gta_path>   — add allin1_previews to dlclist.xml
//   RpfPatcher.exe unpatch <gta_path>   — remove allin1_previews from dlclist.xml

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
        private const string DLCLIST_PATH = "common/data/dlclist.xml";

        static int Main(string[] args)
        {
            if (args.Length < 2)
            {
                Console.Error.WriteLine("Usage: RpfPatcher.exe <patch|unpatch> <gta_path>");
                return 1;
            }

            string command = args[0].ToLower();
            string gtaPath = args[1];

            if (command != "patch" && command != "unpatch")
            {
                Console.Error.WriteLine($"ERROR: Unknown command '{command}'. Use 'patch' or 'unpatch'.");
                return 1;
            }

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

                // --- Open update.rpf ---
                string rpfPath = Path.Combine(gtaPath, "update", "update.rpf");
                if (!File.Exists(rpfPath))
                {
                    Console.Error.WriteLine($"ERROR: {rpfPath} not found");
                    return 4;
                }

                Console.WriteLine($"Opening {rpfPath}...");
                var rpf = new RpfFile(rpfPath, rpfPath);
                rpf.ScanStructure(null, err => Console.Error.WriteLine($"RPF scan warning: {err}"));

                if (rpf.AllEntries == null || rpf.AllEntries.Count == 0)
                {
                    Console.Error.WriteLine("ERROR: RPF scan returned no entries.");
                    return 4;
                }

                Console.WriteLine($"RPF scanned: {rpf.AllEntries.Count} entries");

                // --- Find dlclist.xml ---
                // update.rpf may contain nested RPFs (e.g. common.rpf\data\dlclist.xml).
                // Search all RPFs recursively.
                var dlclistEntry = FindFileRecursive(rpf, "dlclist.xml");

                if (dlclistEntry == null)
                {
                    Console.Error.WriteLine("ERROR: dlclist.xml not found in update.rpf (searched all nested RPFs)");
                    return 5;
                }

                Console.WriteLine($"Found dlclist.xml at: {dlclistEntry.Path}");

                // --- Extract and parse XML ---
                // The entry may be inside a nested RPF, so extract from its own RPF file.
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
                Console.WriteLine($"Writing modified dlclist.xml back to RPF...");

                // Do NOT call EnsureValidEncryption — it converts NG encryption to OPEN,
                // which corrupts the RPF for Enhanced Edition (err_fil_pack_3).
                // CodeWalker's CreateFile/WriteHeader handles NG encryption natively.

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

                Console.WriteLine("dlclist.xml updated successfully.");
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
            // Check if entry already exists
            foreach (var item in paths.Elements("Item"))
            {
                string text = item.Value?.Trim().TrimEnd('/').ToLower() ?? "";
                if (text.Contains("allin1_previews"))
                {
                    Console.WriteLine("Entry 'allin1_previews' already present in dlclist.xml.");
                    return false;
                }
            }

            // Add new entry
            paths.Add(new XElement("Item", DLC_ENTRY));
            Console.WriteLine($"Added '{DLC_ENTRY}' to dlclist.xml.");
            return true;
        }

        private static RpfFileEntry FindFileRecursive(RpfFile rpf, string fileName)
        {
            // Search this RPF's entries
            var entry = rpf.AllEntries?
                .OfType<RpfFileEntry>()
                .FirstOrDefault(e =>
                    e.Name != null &&
                    e.Name.Equals(fileName, StringComparison.OrdinalIgnoreCase));

            if (entry != null) return entry;

            // Recurse into nested RPFs
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
