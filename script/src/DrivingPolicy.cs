using System;
using System.Collections.Generic;
using System.IO;

namespace ALLIN1
{
    internal sealed class DrivingOptions
    {
        internal string Provider = "auto", Units = "kmh", Telemetry = "towing";
        internal bool ShiftControls = true;
        internal static DrivingOptions Parse(IEnumerable<string> lines)
        {
            var result = new DrivingOptions(); bool script = false;
            foreach (var raw in lines)
            {
                var line = raw.Split('#')[0].Trim();
                if (line.StartsWith("[")) { script = line == "[script]"; continue; }
                int split = line.IndexOf('='); if (!script || split < 0) continue;
                var key = line.Substring(0, split).Trim();
                var value = line.Substring(split + 1).Trim().Trim('"').ToLowerInvariant();
                switch (key)
                {
                    case "speedometer_provider":
                        if (Array.IndexOf(new[] { "auto", "builtin", "rex", "lefix", "off" }, value) < 0) throw new InvalidDataException("Invalid speedometer_provider");
                        result.Provider = value; break;
                    case "speedometer_units":
                        if (value != "kmh" && value != "mph") throw new InvalidDataException("Invalid speedometer_units");
                        result.Units = value; break;
                    case "driving_telemetry":
                        if (value != "off" && value != "towing" && value != "all") throw new InvalidDataException("Invalid driving_telemetry");
                        result.Telemetry = value; break;
                    case "shift_controls_enabled":
                        if (value != "true" && value != "false") throw new InvalidDataException("Invalid shift_controls_enabled");
                        result.ShiftControls = value == "true"; break;
                }
            }
            return result;
        }
    }
    internal static class DrivingPolicy
    {
        // Mission scripts own transmission input, not the read-only driving display.
        internal static (bool Hud, bool Controls) Availability(bool sceneAvailable, bool missionActive)
            => (sceneAvailable, sceneAvailable && !missionActive);
        // Native UI only hides our readout; it must not reset transmission or telemetry.
        internal static string HudReason(string provider, bool phoneTask, bool phoneCall, bool phoneCamera,
            bool characterWheel = false, bool characterSwitch = false)
            => provider != "builtin" ? "provider_" + provider
                : characterWheel || characterSwitch ? "character_switch"
                : phoneTask || phoneCall || phoneCamera ? "phone" : "driving";
        // Phone and character-selector probes are visual-only. A missing or
        // incompatible native must not disable telemetry or transmission
        // handling for the rest of the session.
        internal static string HudReason(string provider, Func<bool> phoneTask,
            Func<bool> phoneCall, Func<bool> phoneCamera,
            Func<bool> characterWheel, Func<bool> characterSwitch)
        {
            if (provider != "builtin") return "provider_" + provider;
            return HudReason(provider, Probe(phoneTask), Probe(phoneCall),
                Probe(phoneCamera), Probe(characterWheel),
                Probe(characterSwitch));
        }
        private static bool Probe(Func<bool> read)
        {
            try { return read != null && read(); }
            catch (Exception) { return false; }
        }
        internal static bool Finite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
        internal static object Number(float value) => Finite(value) ? (object)value : null;
        internal static float DisplaySpeed(float metresPerSecond, string units) => Finite(metresPerSecond)
            ? Math.Max(0, metresPerSecond) * (units == "mph" ? 2.2369363f : 3.6f) : 0;
        internal static float Angle(float degrees) => (degrees % 360 + 540) % 360 - 180;
        // GTA gear 0 is reverse, not neutral. Unsupported memory reads must not be labelled N.
        internal static string Gear(int gear, int count) => count < 1 || count > 10 || gear < 0 || gear > count
            ? "?" : gear == 0 ? "R" : gear.ToString(System.Globalization.CultureInfo.InvariantCulture);
        internal static string Provider(string requested, bool rexLoaded, bool lefixLoaded)
        {
            if (requested == "off" || requested == "builtin") return requested;
            if ((requested == "auto" || requested == "rex") && rexLoaded) return "rex";
            if ((requested == "auto" || requested == "lefix") && lefixLoaded) return "lefix";
            return "builtin";
        }
        internal static bool CanHold(bool safe, bool driver, bool landVehicle, bool externalController,
            bool engineRunning, int actual, int count, float rpm) => safe && driver && landVehicle
            && !externalController && engineRunning && count >= 1 && count <= 10
            && actual >= 1 && actual <= count && Finite(rpm) && rpm >= 0 && rpm <= 1.1f;
        internal static int Shift(int current, int direction, int count, float rpm)
        {
            if (count < 1 || count > 10 || current < 1 || current > count || !Finite(rpm)
                || rpm < 0 || rpm > 1.1f || (direction != -1 && direction != 1)) return current;
            // Conservative guard, not a gear-ratio/redline simulation.
            if (direction < 0 && rpm > .7f) return current;
            return Math.Max(1, Math.Min(count, current + direction));
        }
    }
}
