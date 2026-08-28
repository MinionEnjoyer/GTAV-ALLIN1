using System;
using System.IO;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    /// <summary>
    /// Detects and probes the locally generated allin1_maps compatibility DLC.
    /// The pack exposes only the Rockstar interior archives used by ALLIN1 to
    /// Story Mode without changing global map state. A failed probe is terminal
    /// for that interaction; callers must never switch the whole session to the
    /// Online map as a fallback.
    /// </summary>
    internal static class StandaloneMapPack
    {
        private const string PackName = "allin1_maps";

        internal static bool IsInstalled
        {
            get
            {
                try
                {
                    string scripts = AppDomain.CurrentDomain.BaseDirectory
                        .TrimEnd(Path.DirectorySeparatorChar,
                            Path.AltDirectorySeparatorChar);
                    string gameRoot = Directory.GetParent(scripts)?.FullName;
                    if (string.IsNullOrEmpty(gameRoot)) return false;
                    string packRoot = Path.Combine(
                        gameRoot, "mods", "update", "x64", "dlcpacks",
                        PackName);
                    var archive = new FileInfo(Path.Combine(packRoot, "dlc.rpf"));
                    return archive.Exists && archive.Length > 0 &&
                        File.Exists(Path.Combine(packRoot, "allin1_maps.active"));
                }
                catch
                {
                    return false;
                }
            }
        }

        internal static bool TryActivate(string[] ipls, int timeoutMs = 750)
        {
            if (!IsInstalled || ipls == null || ipls.Length == 0)
                return false;

            int startedAt = Game.GameTime;
            do
            {
                bool active = true;
                foreach (string ipl in ipls)
                {
                    if (string.IsNullOrWhiteSpace(ipl)) continue;
                    if (!Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl))
                    {
                        Function.Call(Hash.REQUEST_IPL, ipl);
                        active = false;
                    }
                }
                if (active)
                {
                    ClientLog.Info("World", "standalone_map_ready");
                    return true;
                }
                if (timeoutMs <= 0) break;
                Script.Wait(50);
            }
            while (Game.GameTime - startedAt < timeoutMs);

            ClientLog.Warn("World", "standalone_map_probe_failed");
            return false;
        }
    }
}
