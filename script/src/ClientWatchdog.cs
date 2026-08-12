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
        private static readonly DateTime RecoveryEndsUtc =
            DateTime.UtcNow.AddSeconds(30);
        private bool _recoveryCompleteLogged;
        internal static bool SafeMode => ForcedSafeMode ||
            (PreviousSessionCrashed && DateTime.UtcNow < RecoveryEndsUtc);

        internal static string SafeModeReason => ForcedSafeMode
            ? "forced safe mode" : "30-second recovery mode";

        public ClientWatchdog()
        {
            Tick += OnTick;
            Aborted += OnAborted;
            AppDomain.CurrentDomain.ProcessExit += OnProcessExit;
            AppDomain.CurrentDomain.DomainUnload += OnDomainUnload;
            Interval = 1000;
            try
            {
                File.WriteAllText(Marker, DateTime.UtcNow.ToString("O"));
                if (PreviousSessionCrashed)
                    ClientLog.Warn("Watchdog", "unclean_shutdown_detected_safe_mode_enabled");
            }
            catch (Exception ex) { ClientLog.Error("Watchdog", "marker_write_failed", ex); }
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (PreviousSessionCrashed && !ForcedSafeMode &&
                !SafeMode && !_recoveryCompleteLogged)
            {
                _recoveryCompleteLogged = true;
                ClientLog.Info("Watchdog", "recovery_window_completed_features_resumed",
                    new Dictionary<string, object> { { "stabilization_seconds", 30 } });
            }
        }

        private void OnAborted(object sender, EventArgs e)
        {
            AppDomain.CurrentDomain.ProcessExit -= OnProcessExit;
            AppDomain.CurrentDomain.DomainUnload -= OnDomainUnload;
            CleanupMarker();
        }

        private void OnProcessExit(object sender, EventArgs e)
        {
            CleanupMarker();
        }

        private void OnDomainUnload(object sender, EventArgs e)
        {
            CleanupMarker();
        }

        private static void CleanupMarker()
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
