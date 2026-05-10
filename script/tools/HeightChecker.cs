// HeightChecker.cs -- Automated garage vehicle height measurement tool.
//
// Press F12 to start.  Cycles through all ground vehicles in VehicleList,
// spawning each at representative garage parking slots with physics enabled.
// After settling, records the actual Z position, bounding-box dimensions,
// and collision state.  Results are written to scripts/ALLIN1_height_check.toml.
//
// The tool runs fully automated -- press F12 and wait (~10 min).
// Press F12 again to stop early (partial results are still written).

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class HeightChecker : Script
    {
        // ------------------------------------------------------------------ //
        //  Configuration                                                      //
        // ------------------------------------------------------------------ //

        // Test 2 representative slots (one per row) or all 10
        private const bool TEST_ALL_SLOTS = false;

        private static readonly int[] TEST_SLOTS = TEST_ALL_SLOTS
            ? new int[] { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 }
            : new int[] { 0, 5 };

        // Physics settling
        private const int SETTLE_FRAMES_MIN = 30;
        private const int SETTLE_FRAMES_MAX = 60;
        private const float VELOCITY_THRESHOLD = 0.01f;

        // Model loading
        private const int MODEL_TIMEOUT_MS = 5000;

        // Classes that can't meaningfully sit in a ground garage
        private static readonly HashSet<string> SKIP_CLASSES = new HashSet<string>
        {
            "Boats", "Helicopters", "Planes", "Cycles"
        };

        // Player hide position (garage interior)
        private static readonly Vector3 PLAYER_POS =
            new Vector3(240.7f, -1004.8f, -99f);
        private const float PLAYER_HEADING = 82.8f;

        // ------------------------------------------------------------------ //
        //  Types                                                              //
        // ------------------------------------------------------------------ //

        private enum State
        {
            Idle,
            Loading,    // requesting model
            Settling,   // physics settling
            Measuring,  // taking measurement
            Next,       // advancing to next vehicle/slot
            Writing,    // writing output file
            Done        // finished
        }

        private struct Measurement
        {
            public string Model;
            public string DisplayName;
            public string VehicleClass;
            public int SlotIndex;
            public float SpawnZ;
            public float MeasuredZ;
            public float DeltaZ;
            public float Length;
            public float Width;
            public float Height;
            public bool Collided;
            public bool InAir;
            public float HeightAboveGround;
        }

        // ------------------------------------------------------------------ //
        //  State                                                              //
        // ------------------------------------------------------------------ //

        private State _state = State.Idle;
        private int _vehicleIndex;
        private int _slotTestIndex;
        private int _frameCounter;
        private Vehicle _vehicle;
        private List<Measurement> _results;
        private List<string> _collidedModels;
        private int _failedCount;
        private int _completedMeasurements;
        private int _totalMeasurements;

        // Testable vehicle indices (pre-filtered, no boats/helis/planes/cycles)
        private int[] _testableIndices;

        // Saved player state
        private Vector3 _savedPlayerPos;
        private float _savedPlayerHeading;
        private bool _savedPlayerVisible;

        // Output
        private static readonly string SCRIPTS_DIR =
            AppDomain.CurrentDomain.BaseDirectory;
        private static readonly string OUTPUT_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_height_check.toml");
        private static readonly string LOG_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_gbay.log");

        // ------------------------------------------------------------------ //
        //  Constructor                                                        //
        // ------------------------------------------------------------------ //

        public HeightChecker()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        // ------------------------------------------------------------------ //
        //  Key handler                                                        //
        // ------------------------------------------------------------------ //

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.F12)
            {
                if (_state == State.Idle)
                    StartCheck();
                else
                    StopCheck(writeResults: true);
            }
        }

        // ------------------------------------------------------------------ //
        //  Tick                                                               //
        // ------------------------------------------------------------------ //

        private void OnTick(object sender, EventArgs e)
        {
            if (_state == State.Idle)
                return;

            GbayInput.DisableGameControls();

            switch (_state)
            {
                case State.Loading:
                    TickLoading();
                    break;

                case State.Settling:
                    TickSettling();
                    break;

                case State.Measuring:
                    TickMeasuring();
                    break;

                case State.Next:
                    TickNext();
                    break;

                case State.Writing:
                    WriteResults();
                    _state = State.Done;
                    break;

                case State.Done:
                    StopCheck(writeResults: false);
                    break;
            }
        }

        // ------------------------------------------------------------------ //
        //  Start / Stop                                                       //
        // ------------------------------------------------------------------ //

        private void StartCheck()
        {
            // Build testable vehicle index list (skip non-ground classes)
            var indices = new List<int>();
            for (int i = 0; i < VehicleList.All.Length; i++)
            {
                string model = VehicleList.All[i];
                if (VehicleList.ClassNames.ContainsKey(model))
                {
                    string cls = VehicleList.ClassNames[model];
                    if (SKIP_CLASSES.Contains(cls))
                        continue;
                }
                indices.Add(i);
            }
            _testableIndices = indices.ToArray();
            _totalMeasurements = _testableIndices.Length * TEST_SLOTS.Length;

            Log($"HeightChecker: starting, {_testableIndices.Length} vehicles, " +
                $"{TEST_SLOTS.Length} slots each, {_totalMeasurements} total measurements");

            _results = new List<Measurement>();
            _collidedModels = new List<string>();
            _failedCount = 0;
            _completedMeasurements = 0;
            _vehicleIndex = 0;
            _slotTestIndex = 0;

            // Save and hide player
            Ped player = Game.Player.Character;
            _savedPlayerPos = player.Position;
            _savedPlayerHeading = player.Heading;
            _savedPlayerVisible = player.IsVisible;

            player.IsVisible = false;
            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                PLAYER_POS.X, PLAYER_POS.Y, PLAYER_POS.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player, PLAYER_HEADING);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, true);

            GTA.UI.Screen.ShowSubtitle(
                $"~b~Height Checker~w~ started: {_testableIndices.Length} vehicles. F12 to stop.", 3000);

            _state = State.Loading;
            SpawnCurrent();
        }

        private void StopCheck(bool writeResults)
        {
            if (writeResults && _results != null && _results.Count > 0)
                WriteResults();

            // Cleanup vehicle
            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.Delete();
                _vehicle = null;
            }

            // Restore player
            Ped player = Game.Player.Character;
            player.IsVisible = _savedPlayerVisible;
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            player.IsPositionFrozen = false;
            player.Position = _savedPlayerPos;
            player.Heading = _savedPlayerHeading;

            int collisions = _collidedModels != null ? _collidedModels.Count : 0;
            GTA.UI.Screen.ShowSubtitle(
                $"~b~Height Checker~w~ done. " +
                $"~g~{_completedMeasurements}~w~ measured, " +
                $"~r~{_failedCount}~w~ failed, " +
                $"~y~{collisions}~w~ collisions.\n" +
                $"Output: {OUTPUT_PATH}", 5000);

            Log($"HeightChecker: done. {_completedMeasurements} measured, " +
                $"{_failedCount} failed, {collisions} collisions");

            _state = State.Idle;
        }

        // ------------------------------------------------------------------ //
        //  Vehicle Spawn                                                      //
        // ------------------------------------------------------------------ //

        private void SpawnCurrent()
        {
            // Delete previous vehicle
            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.Delete();
                _vehicle = null;
            }

            if (_vehicleIndex >= _testableIndices.Length)
            {
                _state = State.Writing;
                return;
            }

            int allIdx = _testableIndices[_vehicleIndex];
            string modelName = VehicleList.All[allIdx];
            int slotIdx = TEST_SLOTS[_slotTestIndex];
            var slot = GarageManager.Slots[slotIdx];

            // Request model
            var model = new Model(modelName);
            model.Request(MODEL_TIMEOUT_MS);

            // Wait for model to load
            DateTime deadline = DateTime.UtcNow.AddMilliseconds(MODEL_TIMEOUT_MS);
            while (!model.IsLoaded)
            {
                if (DateTime.UtcNow > deadline)
                {
                    model.MarkAsNoLongerNeeded();
                    Log($"HeightChecker: model load timeout for {modelName}");
                    _failedCount++;
                    _state = State.Next;
                    return;
                }
                Script.Wait(0);
            }

            // Create vehicle directly (no VehicleHelper -- it calls PlaceOnGround)
            _vehicle = World.CreateVehicle(model, slot.Position, slot.Heading);
            model.MarkAsNoLongerNeeded();

            if (_vehicle == null)
            {
                Log($"HeightChecker: CreateVehicle returned null for {modelName}");
                _failedCount++;
                _state = State.Next;
                return;
            }

            // Configure for physics settling
            _vehicle.IsPositionFrozen = false;
            _vehicle.IsCollisionEnabled = true;
            _vehicle.IsInvincible = true;
            _vehicle.IsEngineRunning = false;
            _vehicle.IsPersistent = true;
            Function.Call(Hash.SET_VEHICLE_HANDBRAKE, _vehicle, true);

            // Force exact starting position
            Function.Call(Hash.SET_ENTITY_COORDS, _vehicle,
                slot.Position.X, slot.Position.Y, slot.Position.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, _vehicle, slot.Heading);

            _frameCounter = 0;
            _state = State.Settling;
        }

        // ------------------------------------------------------------------ //
        //  State Tick Methods                                                 //
        // ------------------------------------------------------------------ //

        private void TickLoading()
        {
            // Loading is handled synchronously in SpawnCurrent via Script.Wait
            // This state is only reached briefly before SpawnCurrent transitions
            DrawProgress("Loading...");
        }

        private void TickSettling()
        {
            _frameCounter++;
            DrawProgress("Settling...");

            if (_vehicle == null || !_vehicle.Exists())
            {
                _failedCount++;
                _state = State.Next;
                return;
            }

            // Early exit: after minimum frames, check if velocity is near zero
            if (_frameCounter >= SETTLE_FRAMES_MIN)
            {
                Vector3 vel = Function.Call<Vector3>(
                    Hash.GET_ENTITY_VELOCITY, _vehicle);
                if (Math.Abs(vel.Z) < VELOCITY_THRESHOLD)
                {
                    _state = State.Measuring;
                    return;
                }
            }

            // Hard cap
            if (_frameCounter >= SETTLE_FRAMES_MAX)
            {
                _state = State.Measuring;
            }
        }

        private void TickMeasuring()
        {
            if (_vehicle == null || !_vehicle.Exists())
            {
                _failedCount++;
                _state = State.Next;
                return;
            }

            int allIdx = _testableIndices[_vehicleIndex];
            string modelName = VehicleList.All[allIdx];
            int slotIdx = TEST_SLOTS[_slotTestIndex];
            var slot = GarageManager.Slots[slotIdx];

            // Get actual position after physics settling
            Vector3 actualPos = Function.Call<Vector3>(
                Hash.GET_ENTITY_COORDS, _vehicle, true);

            // Get bounding box dimensions
            int hash = _vehicle.Model.Hash;
            OutputArgument minArg = new OutputArgument();
            OutputArgument maxArg = new OutputArgument();
            Function.Call(Hash.GET_MODEL_DIMENSIONS, hash, minArg, maxArg);
            Vector3 bMin = minArg.GetResult<Vector3>();
            Vector3 bMax = maxArg.GetResult<Vector3>();

            // Collision and air checks
            bool collided = Function.Call<bool>(
                Hash.HAS_ENTITY_COLLIDED_WITH_ANYTHING, _vehicle);
            bool inAir = Function.Call<bool>(
                Hash.IS_ENTITY_IN_AIR, _vehicle);
            float heightAboveGround = Function.Call<float>(
                Hash.GET_ENTITY_HEIGHT_ABOVE_GROUND, _vehicle);

            // Build measurement
            var m = new Measurement
            {
                Model = modelName,
                DisplayName = VehicleList.DisplayNames.ContainsKey(modelName)
                    ? VehicleList.DisplayNames[modelName] : modelName,
                VehicleClass = VehicleList.ClassNames.ContainsKey(modelName)
                    ? VehicleList.ClassNames[modelName] : "Unknown",
                SlotIndex = slotIdx,
                SpawnZ = slot.Position.Z,
                MeasuredZ = actualPos.Z,
                DeltaZ = actualPos.Z - slot.Position.Z,
                Length = bMax.Y - bMin.Y,
                Width = bMax.X - bMin.X,
                Height = bMax.Z - bMin.Z,
                Collided = collided,
                InAir = inAir,
                HeightAboveGround = heightAboveGround,
            };

            _results.Add(m);
            _completedMeasurements++;

            if (collided && !_collidedModels.Contains(modelName))
                _collidedModels.Add(modelName);

            Log($"HeightChecker: {modelName} slot={slotIdx} " +
                $"z={actualPos.Z:F3} delta={m.DeltaZ:F3} " +
                $"collided={collided} inAir={inAir} " +
                $"dims={m.Length:F2}x{m.Width:F2}x{m.Height:F2}");

            // Clean up vehicle
            _vehicle.Delete();
            _vehicle = null;

            _state = State.Next;
        }

        private void TickNext()
        {
            // Advance slot index
            _slotTestIndex++;
            if (_slotTestIndex < TEST_SLOTS.Length)
            {
                // More slots for this vehicle
                SpawnCurrent();
                return;
            }

            // All slots done for this vehicle -- advance to next vehicle
            _slotTestIndex = 0;
            _vehicleIndex++;

            if (_vehicleIndex >= _testableIndices.Length)
            {
                _state = State.Writing;
                return;
            }

            SpawnCurrent();
        }

        // ------------------------------------------------------------------ //
        //  Output                                                             //
        // ------------------------------------------------------------------ //

        private void WriteResults()
        {
            try
            {
                var sb = new StringBuilder();
                sb.AppendLine("# ALLIN1 Height Check Results");
                sb.AppendLine($"# Generated: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
                sb.AppendLine($"# Vehicles tested: {_testableIndices.Length}");
                sb.AppendLine($"# Slots per vehicle: {TEST_SLOTS.Length} ({string.Join(", ", TEST_SLOTS)})");
                sb.AppendLine($"# Total measurements: {_completedMeasurements}");
                sb.AppendLine($"# Failed: {_failedCount}");
                sb.AppendLine();

                // Summary section
                sb.AppendLine("[summary]");
                sb.AppendLine($"total_vehicles = {_testableIndices.Length}");
                sb.AppendLine($"total_measurements = {_completedMeasurements}");
                sb.AppendLine($"failed = {_failedCount}");
                sb.AppendLine($"collisions_detected = {_collidedModels.Count}");
                sb.AppendLine();

                // Review list (collided vehicles)
                sb.AppendLine("[review]");
                sb.Append("models = [");
                if (_collidedModels.Count > 0)
                {
                    sb.AppendLine();
                    for (int i = 0; i < _collidedModels.Count; i++)
                    {
                        sb.Append($"    \"{_collidedModels[i]}\"");
                        if (i < _collidedModels.Count - 1)
                            sb.AppendLine(",");
                        else
                            sb.AppendLine();
                    }
                }
                sb.AppendLine("]");
                sb.AppendLine();

                // Per-measurement data
                foreach (var m in _results)
                {
                    sb.AppendLine("[[measurements]]");
                    sb.AppendLine($"model = \"{m.Model}\"");
                    sb.AppendLine($"display_name = \"{EscapeToml(m.DisplayName)}\"");
                    sb.AppendLine($"class = \"{m.VehicleClass}\"");
                    sb.AppendLine($"slot = {m.SlotIndex}");
                    sb.AppendLine($"spawn_z = {m.SpawnZ:F1}");
                    sb.AppendLine($"measured_z = {m.MeasuredZ:F3}");
                    sb.AppendLine($"delta_z = {m.DeltaZ:F3}");
                    sb.AppendLine($"length = {m.Length:F2}");
                    sb.AppendLine($"width = {m.Width:F2}");
                    sb.AppendLine($"height = {m.Height:F2}");
                    sb.AppendLine($"collided = {(m.Collided ? "true" : "false")}");
                    sb.AppendLine($"in_air = {(m.InAir ? "true" : "false")}");
                    sb.AppendLine($"height_above_ground = {m.HeightAboveGround:F3}");
                    sb.AppendLine();
                }

                // Write atomically via temp file
                string tmp = OUTPUT_PATH + ".tmp";
                File.WriteAllText(tmp, sb.ToString(), Encoding.UTF8);
                if (File.Exists(OUTPUT_PATH))
                    File.Delete(OUTPUT_PATH);
                File.Move(tmp, OUTPUT_PATH);

                Log($"HeightChecker: wrote {_results.Count} measurements to {OUTPUT_PATH}");
            }
            catch (Exception ex)
            {
                Log($"HeightChecker: WRITE ERROR: {ex.Message}");
                GTA.UI.Screen.ShowSubtitle(
                    $"~r~Height Checker write error:~w~ {ex.Message}", 5000);
            }
        }

        private static string EscapeToml(string s)
        {
            if (s == null) return "";
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        // ------------------------------------------------------------------ //
        //  Progress Display                                                   //
        // ------------------------------------------------------------------ //

        private void DrawProgress(string status)
        {
            int pct = _totalMeasurements > 0
                ? (_completedMeasurements * 100) / _totalMeasurements : 0;

            string modelName = "...";
            if (_vehicleIndex < _testableIndices.Length)
            {
                int allIdx = _testableIndices[_vehicleIndex];
                modelName = VehicleList.All[allIdx];
            }
            int slotNum = _slotTestIndex < TEST_SLOTS.Length
                ? TEST_SLOTS[_slotTestIndex] : 0;

            // Background bar
            GbayRenderer.DrawRect(0.5f, 0.03f, 0.5f, 0.05f,
                Color.FromArgb(200, 0, 0, 0));

            // Fill bar
            float fillW = 0.48f * pct / 100f;
            GbayRenderer.DrawRect(0.26f + fillW / 2f, 0.03f, fillW, 0.035f,
                Color.FromArgb(200, 45, 156, 80));

            // Main text
            string text = $"{status} {_completedMeasurements}/{_totalMeasurements} " +
                          $"({pct}%) {modelName} @ slot {slotNum}";
            GbayRenderer.DrawText(text, 0.5f, 0.012f, 0.30f, Color.White,
                GbayRenderer.FONT_CONDENSED, true);

            // Stats line
            int collisions = _collidedModels != null ? _collidedModels.Count : 0;
            string stats = $"Collisions: {collisions}  |  Failed: {_failedCount}";
            GbayRenderer.DrawText(stats, 0.5f, 0.055f, 0.25f,
                Color.FromArgb(200, 255, 200, 100),
                GbayRenderer.FONT_CONDENSED, true);
        }

        // ------------------------------------------------------------------ //
        //  Logging                                                            //
        // ------------------------------------------------------------------ //

        private static void Log(string msg)
        {
            try
            {
                File.AppendAllText(LOG_PATH,
                    $"[{DateTime.Now:HH:mm:ss}] {msg}{Environment.NewLine}");
            }
            catch { }
        }
    }
}
