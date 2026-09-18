using System;
using System.Globalization;

namespace ALLIN1
{
    // Immutable snapshots keep GBAY reads separate from script-owned native work.
    internal sealed class PopulationRuntimeDiagnostics
    {
        internal PopulationRuntimeDiagnostics(bool enabled = false,
            string state = "starting", string detail = "Waiting for runtime",
            int selections = 0, int active = 0, int limit = 0, long scanned = 0,
            long added = 0, long replaced = 0, long rejected = 0,
            int quarantined = 0, float replacementChance = 0f,
            string lastError = "", bool throttled = false, long attempted = 0,
            int configured = 0, double smoothedFps = 60d)
        {
            Enabled = enabled; State = state ?? "starting";
            Detail = detail ?? ""; Selections = selections; Active = active;
            Limit = limit; Scanned = scanned; Added = added; Replaced = replaced;
            Rejected = rejected; Quarantined = quarantined;
            ReplacementChance = replacementChance; LastError = lastError ?? "";
            Throttled = throttled; Attempted = attempted; Configured = configured;
            SmoothedFps = smoothedFps;
        }

        internal bool Enabled { get; }
        internal string State { get; }
        internal string Detail { get; }
        internal int Selections { get; }
        internal int Active { get; }
        internal int Limit { get; }
        internal long Scanned { get; }
        internal long Attempted { get; }
        internal int Configured { get; }
        internal long Added { get; }
        internal long Replaced { get; }
        internal long Rejected { get; }
        internal int Quarantined { get; }
        internal float ReplacementChance { get; }
        internal string LastError { get; }
        internal bool Throttled { get; }
        internal double SmoothedFps { get; }

        // Match Traffic's steady neutral status; waiting/streaming/active are
        // normal phases, not reasons to flash the row between colors.
        internal string Tone => LastError.Length > 0 || Quarantined > 0
            ? "warning" : "neutral";

        internal string Status => Bounded(State.Replace('_', ' ') +
            (Detail.Length == 0 ? "" : " — " + Detail), 256);

        // The headline is deliberately independent of scan progress and other
        // momentary runtime details, so normal waiting never reads as a fault.
        internal string Summary(bool pedestrians)
        {
            string value = pedestrians
                ? Active + "/" + Limit + " managed, " + RoundedFps() + " FPS"
                : Replaced + " swaps, " + RoundedFps() + " FPS";
            if (Throttled) value += " (adaptive throttle)";
            if (IsState("paused"))
            {
                string reason = Bounded(Detail, 120);
                value += reason.Length == 0 ? " (paused)" : " (paused: " +
                    reason + ")";
            }
            if (IsState("disabled")) value += " (disabled)";
            if (IsState("unconfigured")) value += " (unconfigured)";
            if (IsState("configuration_error") || IsState("configuration_rejected"))
                value += " (configuration error)";
            if (IsState("authorization_expired"))
                value += " (authorization unavailable)";
            if (Quarantined > 0) value += " (" + Quarantined +
                " quarantined)";
            return Bounded(value, 256);
        }

        private static string Bounded(string value, int maximum)
        {
            string clean = value.Replace('\r', ' ').Replace('\n', ' ');
            return clean.Length <= maximum ? clean : clean.Substring(0, maximum - 3) + "...";
        }

        internal string Describe(bool pedestrians)
        {
            string value = pedestrians
                ? Selections + " " + (Selections == 1 ? "model" : "models") +
                    " • " + Added + " spawned this session"
                : Selections + " " + (Selections == 1 ? "weapon" : "weapons") + " • " +
                    (ReplacementChance * 100f).ToString("0.#",
                        CultureInfo.InvariantCulture) + "% replacement chance";
            if (LastError.Length > 0)
                value += " • Last error: " + Bounded(LastError, 240);
            return Bounded(value, 512);
        }

        private bool IsState(string value) => string.Equals(State, value,
            StringComparison.OrdinalIgnoreCase);

        private string RoundedFps() => Math.Round(SmoothedFps).ToString("0",
            CultureInfo.InvariantCulture);
    }
}
