using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal static class DrivingRuntime
    {
        [DllImport("user32.dll")] private static extern short GetAsyncKeyState(int key);
        [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr GetModuleHandle(string module);
        private static readonly uint ProcessId = (uint)Process.GetCurrentProcess().Id;
        private static readonly Keys[] KeysUsed = { Keys.Multiply, Keys.Add, Keys.Subtract, Keys.Decimal };
        private static readonly bool[] Held = new bool[4];
        private static DrivingOptions _options;
        private static DrivingTelemetryLog _log;
        private static bool _safeMode, _manual, _externalTransmission, _faulted, _logWarning;
        private static int _vehicle, _model, _selected, _nextSample, _nextDetection, _lastShift;
        private static IntPtr _address;
        private static string _provider, _notice = "", _pair;
        private static int _noticeUntil;
        private static float _lastSpeed;
        private static int _lastSample;
        private static bool _sampleValid;

        internal static void Initialize(string configPath, bool safeMode)
        {
            if (_options != null) return;
            _safeMode = safeMode;
            try { _options = DrivingOptions.Parse(File.Exists(configPath) ? File.ReadAllLines(configPath) : Array.Empty<string>()); }
            catch (Exception ex)
            {
                // Invalid config must not accidentally enable controls or logging.
                _options = new DrivingOptions { Provider = "off", Telemetry = "off", ShiftControls = false };
                ClientLog.Error("Driving", "invalid_config", ex);
            }
            if (_options.Telemetry != "off")
            {
                _log = new DrivingTelemetryLog(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_driving.jsonl"));
                Event("session_started", new Dictionary<string, object> {
                    ["version"] = typeof(DrivingRuntime).Assembly.GetName().Version.ToString(),
                    ["game_version"] = Game.Version.ToString(), ["telemetry_mode"] = _options.Telemetry,
                    ["provider_requested"] = _options.Provider, ["units"] = _options.Units,
                    ["shift_controls_enabled"] = _options.ShiftControls, ["safe_mode"] = safeMode,
                });
            }
            DetectProviders();
        }
        internal static void Event(string kind, Dictionary<string, object> fields = null) => _log?.Record(kind, fields);
        private static void Notice(string text)
        {
            _notice = text; _noticeUntil = Game.GameTime + 3500;
            Event("control_status", new Dictionary<string, object> { ["message"] = text });
        }
        private static bool Loaded(string name) => GetModuleHandle(name) != IntPtr.Zero;
        private static void DetectProviders()
        {
            // Read-only discovery. No LoadLibrary, config edits, or private third-party calls.
            bool rex = AppDomain.CurrentDomain.GetAssemblies().Any(a => string.Equals(a.GetName().Name, "FSS", StringComparison.OrdinalIgnoreCase));
            bool lefix = Loaded("LeFixSpeedo.asi");
            string next = DrivingPolicy.Provider(_options.Provider, rex, lefix);
            _externalTransmission = Loaded("Gears.asi") || Loaded("ManualTransmission.asi") || Loaded("CustomGearRatios.asi");
            if (_provider != next)
            {
                _provider = next;
                ClientLog.Info("Driving", "display_provider", new Dictionary<string, object> {
                    ["requested"] = _options.Provider, ["effective"] = next,
                    ["rex_assembly_loaded"] = rex, ["lefix_module_loaded"] = lefix,
                });
                Event("display_provider", new Dictionary<string, object> { ["provider"] = next });
                if ((_options.Provider == "rex" || _options.Provider == "lefix") && next == "builtin")
                    Notice("External speedometer not detected; using ALLIN1");
            }
            _nextDetection = Game.GameTime + 2000;
        }
        private static void Auto(string reason)
        {
            if (_manual) { _manual = false; Notice("Automatic: " + reason); }
            // Only CurrentGear/NextGear are changed. No persistent ratios, high-gear limits or handling to restore.
        }
        internal static void Tick(bool menuActive)
        {
            if (_options == null || _faulted) return;
            try { TickCore(menuActive); }
            catch (Exception ex)
            {
                _manual = false; _faulted = true;
                Event("runtime_disabled", new Dictionary<string, object> { ["error"] = ex.GetType().Name });
                ClientLog.Error("Driving", "runtime_disabled", ex);
            }
        }
        private static void TickCore(bool menuActive)
        {
            int now = Game.GameTime;
            // Observe releases even when a menu/pause/another window owns input; never replay held keys.
            var edges = new bool[4];
            for (int n = 0; n < KeysUsed.Length; n++)
            {
                bool down = (GetAsyncKeyState((int)KeysUsed[n]) & 0x8000) != 0;
                edges[n] = down && !Held[n]; Held[n] = down;
            }
            GetWindowThreadProcessId(GetForegroundWindow(), out uint foreground);
            bool available = foreground == ProcessId && !Game.IsLoading && !Game.IsPaused
                && !Game.IsCutsceneActive && !menuActive && !GarageManager.IsTransitionInProgress
                && !Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT)
                && !Function.Call<bool>(Hash.NETWORK_IS_SESSION_ACTIVE)
                && !Function.Call<bool>(Hash.GET_MISSION_FLAG);
            if (!available) { Auto("controls suspended"); EndObservation("suspended"); return; }
            var ped = Game.Player.Character;
            var vehicle = ped != null && ped.Exists() && ped.IsAlive ? ped.CurrentVehicle : null;
            if (vehicle == null || !vehicle.Exists() || vehicle.IsDead || vehicle.Driver != ped)
            { Auto("left driver seat"); EndObservation("driver_unavailable"); _vehicle = 0; return; }
            if (_vehicle != vehicle.Handle || _address != vehicle.MemoryAddress || _model != vehicle.Model.Hash)
            {
                Auto("vehicle changed"); EndObservation("vehicle_changed");
                _vehicle = vehicle.Handle; _address = vehicle.MemoryAddress; _model = vehicle.Model.Hash;
            }
            if (now >= _nextDetection || now < _nextDetection - 2000) DetectProviders();
            // Check loaded transmission modules before every gear write, not just on the display polling interval.
            bool external = _externalTransmission || Loaded("Gears.asi") || Loaded("ManualTransmission.asi") || Loaded("CustomGearRatios.asi");
            int actual = vehicle.CurrentGear, gears = vehicle.HighGear;
            float rpm = vehicle.CurrentRPM, speed = vehicle.Speed;
            bool canHold = DrivingPolicy.CanHold(!_safeMode && !ClientWatchdog.SafeMode, true, vehicle.Model.IsCar || vehicle.Model.IsBike,
                external, vehicle.IsEngineRunning, actual, gears, rpm);
            if (_manual && !canHold) Auto(external ? "external transmission owns gears" : "gear control unavailable");
            if (_manual && (_selected < 1 || _selected > gears)) Auto("gear limit changed");
            bool modifier = HeldKey(Keys.ControlKey) || HeldKey(Keys.Menu) || HeldKey(Keys.ShiftKey);
            if (!modifier)
            {
                if (edges[3]) { _options.Units = _options.Units == "kmh" ? "mph" : "kmh"; Notice("ALLIN1 units: " + _options.Units.ToUpperInvariant()); }
                if (edges[0])
                {
                    if (_manual) Auto("player selected");
                    else if (!_options.ShiftControls || !canHold) Notice("Shifting unavailable: enable controls, select a forward gear, and disable competing controllers");
                    else { _selected = actual; _manual = true; _lastShift = now; Notice("Sequential gear hold (+ / -); * returns to automatic"); }
                }
                if (_manual && edges[1] != edges[2] && (edges[1] || edges[2]) && now - _lastShift >= 250)
                {
                    int next = DrivingPolicy.Shift(_selected, edges[1] ? 1 : -1, gears, rpm);
                    Event("shift_requested", new Dictionary<string, object> { ["from"] = _selected, ["to"] = next, ["rpm_normalized"] = DrivingPolicy.Number(rpm) });
                    if (next == _selected) Notice("Shift refused: gear limit or high RPM");
                    else _selected = next;
                    _lastShift = now;
                }
            }
            if (_manual)
            {
                // Experimental sequential hold, not clutch/neutral/torque simulation. Use only SHVDN's supported properties.
                vehicle.NextGear = _selected; vehicle.CurrentGear = _selected;
                if (vehicle.CurrentGear != _selected || vehicle.NextGear != _selected)
                    Auto("gear write could not be verified");
            }
            if (_provider == "builtin") Draw(speed, vehicle.CurrentGear, gears);
            if (now < _noticeUntil) GbayRenderer.DrawText(_notice, .5f, .86f, .32f, Color.White, centered: true, shadow: true);
            if (_log != null && (now >= _nextSample || now < _nextSample - 200))
            {
                _nextSample = now + 200;
                Sample(vehicle, now);
                if (_log.Failed && !_logWarning)
                {
                    _logWarning = true; Notice("Driving telemetry stopped: log could not be written");
                    ClientLog.Warn("Driving", "telemetry_write_failed");
                }
            }
        }
        private static bool HeldKey(Keys key) => (GetAsyncKeyState((int)key) & 0x8000) != 0;
        private static void Draw(float speed, int gear, int gears)
        {
            // Honour safe-zone margins and aspect ratio; independent of the interactive Reactor surface.
            float margin = (1f - Function.Call<float>(Hash.GET_SAFE_ZONE_SIZE)) * .5f;
            float right = .965f - margin, bottom = .94f - margin;
            float width = .23f / Math.Max(1f, Function.Call<float>(Hash.GET_ASPECT_RATIO, false));
            GbayRenderer.DrawRect(right - width / 2, bottom - .047f, width, .105f, Color.FromArgb(190, 12, 23, 19));
            GbayRenderer.DrawText(Math.Round(DrivingPolicy.DisplaySpeed(speed, _options.Units)).ToString(), right - .01f, bottom - .105f, .70f, Color.White, rightAlign: true);
            GbayRenderer.DrawText(_options.Units.ToUpperInvariant() + "   " + (_manual ? "M" : "A") + " " + DrivingPolicy.Gear(gear, gears), right - .01f, bottom - .041f, .34f, Color.White, rightAlign: true);
        }
        private static void Sample(Vehicle v, int now)
        {
            var row = TrailerHitchRuntime.Telemetry(v, out string pair);
            if (_pair != pair)
            {
                if (_pair != null) Event("coupling_no_longer_observed", new Dictionary<string, object> { ["pair"] = _pair });
                if (pair != null) Event("coupling_observed", new Dictionary<string, object>(row) { ["pair"] = pair });
                _pair = pair; _sampleValid = false;
            }
            if (pair == null && _options.Telemetry != "all") { _sampleValid = false; return; }
            float speed = v.Speed, dt = (now - _lastSample) / 1000f;
            var velocity = v.Velocity; var forward = v.ForwardVector;
            float signedSpeed = velocity.X * forward.X + velocity.Y * forward.Y + velocity.Z * forward.Z;
            row["game_ms"] = now; row["vehicle_handle"] = v.Handle; row["vehicle_model_hash"] = v.Model.Hash;
            row["speed_mps"] = DrivingPolicy.Number(speed); row["longitudinal_speed_mps"] = DrivingPolicy.Number(signedSpeed);
            row["acceleration_mps2"] = _sampleValid && dt > 0 && dt <= 1 ? DrivingPolicy.Number((speed - _lastSpeed) / dt) : null;
            row["sample_dt_s"] = _sampleValid ? DrivingPolicy.Number(dt) : null;
            row["frame_time_s"] = DrivingPolicy.Number(Game.LastFrameTime);
            row["gear"] = v.CurrentGear; row["next_gear"] = v.NextGear; row["high_gear"] = v.HighGear;
            row["held_gear"] = _manual ? (object)_selected : null; row["rpm_normalized"] = DrivingPolicy.Number(v.CurrentRPM);
            row["steering_angle_deg"] = DrivingPolicy.Number(v.SteeringAngle);
            row["throttle_input"] = DrivingPolicy.Number(Function.Call<float>(Hash.GET_CONTROL_NORMAL, 0, 71));
            row["brake_input"] = DrivingPolicy.Number(Function.Call<float>(Hash.GET_CONTROL_NORMAL, 0, 72));
            row["roll_deg"] = DrivingPolicy.Number(v.Rotation.Y); row["pitch_deg"] = DrivingPolicy.Number(v.Rotation.X);
            row["collided"] = v.HasCollided; row["pair"] = pair;
            Event("sample", row); _lastSpeed = speed; _lastSample = now; _sampleValid = true;
        }
        private static void EndObservation(string reason)
        {
            if (_pair != null) Event("observation_ended", new Dictionary<string, object> { ["pair"] = _pair, ["reason"] = reason });
            _pair = null; _sampleValid = false;
        }
        internal static void Shutdown()
        {
            _manual = false; EndObservation("shutdown"); Event("session_ended"); _log?.Dispose(); _log = null;
        }
    }
}
