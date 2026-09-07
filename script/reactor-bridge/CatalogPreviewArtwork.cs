#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using Newtonsoft.Json.Linq;

namespace ALLIN1.ReactorBridge
{
    // Optional preview stores are independent of the consumer UI installer receipt.
    internal static class CatalogPreviewArtwork
    {
        internal static Dictionary<string, string> Read(string gameRoot, string category, int limit)
        {
            var images = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrWhiteSpace(gameRoot) ||
                (category != "weapons" && category != "vehicles" && category != "gear")) return images;
            ReadStore(images, gameRoot, category, limit, "default-", "allin1.default-previews");
            ReadStore(images, gameRoot, category, limit, "generated-", "allin1.prelaunch-previews");
            return images;
        }

        private static void ReadStore(Dictionary<string, string> images, string root,
            string category, int limit, string prefix, string owner)
        {
            try
            {
                string relative = "assets/allin1/" + prefix + category + "/";
                string folder = Path.Combine(root, "plugins", "ReactorV", "ui", "assets", "allin1", prefix + category);
                string index = Path.Combine(folder, "index.json");
                if (!File.Exists(index) || new FileInfo(index).Length > 524288) return;
                JObject data = JObject.Parse(File.ReadAllText(index));
                if ((int?)data["schema_version"] != 1 || (string?)data["owner"] != owner) return;
                if (!(data["images"] is JObject entries) || entries.Count > limit) return;
                foreach (JProperty entry in entries.Properties())
                {
                    string name = entry.Name.ToLowerInvariant();
                    if (entry.Value?.Type != Newtonsoft.Json.Linq.JTokenType.String) continue;
                    string filename = (string?)entry.Value ?? "";
                    if (!Regex.IsMatch(name, category == "weapons" ? @"\Aweapon_[a-z0-9_]{1,56}\z" : @"\A[a-z0-9][a-z0-9_-]{0,63}\z") ||
                        !Regex.IsMatch(filename, @"\A" + Regex.Escape(name) + @"\.[a-f0-9]{64}\.png\z")) continue;
                    if (IsUsableImage(Path.Combine(folder, filename))) images[name] = relative + filename;
                }
            }
            catch (Exception) { /* Missing or invalid optional artwork never blocks the menu. */ }
        }

        private static bool IsUsableImage(string path)
        {
            // Only inspect a small header, never hash/decode the whole catalog
            // on the game thread. A damaged local image must not mask a default.
            try
            {
                using var stream = File.OpenRead(path);
                if (stream.Length < 33 || stream.Length > 4 * 1024 * 1024) return false;
                var header = new byte[24];
                int read = 0;
                while (read < header.Length)
                {
                    int count = stream.Read(header, read, header.Length - read);
                    if (count == 0) return false;
                    read += count;
                }
                byte[] signature = { 137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82 };
                for (int i = 0; i < signature.Length; i++) if (header[i] != signature[i]) return false;
                for (int offset = 16; offset <= 20; offset += 4)
                {
                    uint size = ((uint)header[offset] << 24) | ((uint)header[offset + 1] << 16) |
                        ((uint)header[offset + 2] << 8) | header[offset + 3];
                    if (size == 0 || size > 4096) return false;
                }
                return true;
            }
            catch (IOException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
        }
    }
}
