using System;
using System.Collections.Generic;
using System.IO;
using GTA;

namespace ALLIN1
{
    /// <summary>Detects unclean shutdowns and enables a conservative recovery session.</summary>
    public class ClientWatchdog : Script
    {
        private static readonly string Marker = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_session.lock");
        internal static bool PreviousSessionCrashed { get; private set; } = File.Exists(Marker);
        internal static bool ForcedSafeMode { get; private set; }
        internal static bool SafeMode => PreviousSessionCrashed || ForcedSafeMode;

        public ClientWatchdog()
        {
            Tick += OnTick;
            Aborted += OnAborted;
            Interval = 1000;
            try
            {
                File.WriteAllText(Marker, DateTime.UtcNow.ToString("O"));
                if (PreviousSessionCrashed)
                    ClientLog.Warn("Watchdog", "unclean_shutdown_detected_safe_mode_enabled");
            }
            catch (Exception ex) { ClientLog.Error("Watchdog", "marker_write_failed", ex); }
        }

        private void OnTick(object sender, EventArgs e) { }

        private void OnAborted(object sender, EventArgs e)
        {
            try { if (File.Exists(Marker)) File.Delete(Marker); }
            catch (Exception ex) { ClientLog.Error("Watchdog", "marker_cleanup_failed", ex); }
        }

        internal static void Configure(bool safeMode)
        {
            ForcedSafeMode = safeMode;
            ClientLog.Info("Watchdog", "safe_mode_configured", new Dictionary<string, object> {
                { "enabled", SafeMode }, { "forced", ForcedSafeMode },
                { "previous_crash", PreviousSessionCrashed }
            });
        }
    }
}
