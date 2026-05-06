// GbayPreviewCapture.cs -- Automated vehicle preview screenshot tool.
//
// Press F10 to start. Automatically cycles through all 444 vehicles,
// spawning each in Simeon's showroom with a fixed camera angle, capturing
// a screenshot, and saving it as {model}.png to scripts/previews/.
//
// The tool runs fully automated -- just press F10 and wait. Progress is
// shown on screen. Press F10 again to stop early.
//
// Output: <GTA V>/scripts/previews/{model}.png (one per vehicle)

using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class GbayPreviewCapture : Script
    {
        // LSIA runway -- wide open, flat, clean background, fits any vehicle size
        private static readonly Vector3 SHOWROOM_POS = new Vector3(-1336f, -3044f, 13.9f);
        private const float VEHICLE_HEADING = 330f;

        // Camera setup
        private const float CAM_ANGLE = 210f; // degrees -- front-quarter view
        private const float CAM_FOV = 50f;
        private const float CAM_RADIUS_DEFAULT = 6.5f;
        private const float CAM_HEIGHT_DEFAULT = 1.2f;

        // Timing (in frames)
        private const int SETTLE_FRAMES = 30;  // frames to wait after spawn for model to load
        private const int CAPTURE_FRAME = 1;   // frames after settle to capture (HUD hidden)

        // State
        private bool _active;
        private int _currentIndex;
        private int _frameCounter;
        private int _capturedCount;
        private int _failedCount;
        private Vehicle _vehicle;
        private Camera _camera;
        private Vector3 _savedPlayerPos;
        private float _savedPlayerHeading;
        private string _outputDir;
        private bool _settling;   // waiting for vehicle to render
        private bool _capturing;  // HUD hidden, about to capture

        // Screen dimensions (cached on start)
        private int _screenW;
        private int _screenH;

        public GbayPreviewCapture()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.F10)
            {
                if (!_active)
                    StartCapture();
                else
                    StopCapture();
            }
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!_active)
                return;

            GbayInput.DisableGameControls();

            // Hide game HUD elements
            Function.Call(Hash.HIDE_HUD_AND_RADAR_THIS_FRAME);

            // Keep vehicle frozen
            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.IsPositionFrozen = true;
                Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, _vehicle, 0f);
            }

            // State machine: settle -> capture -> next
            if (_settling)
            {
                _frameCounter++;
                if (_frameCounter >= SETTLE_FRAMES)
                {
                    _settling = false;
                    _capturing = true;
                    _frameCounter = 0;
                }
                // Draw progress while settling
                DrawProgress("Loading...");
                return;
            }

            if (_capturing)
            {
                _frameCounter++;
                if (_frameCounter >= CAPTURE_FRAME)
                {
                    // Take screenshot this frame (no HUD drawn yet)
                    CaptureScreenshot();
                    _capturing = false;
                    _frameCounter = 0;

                    // Advance to next vehicle
                    _currentIndex++;
                    if (_currentIndex >= VehicleList.All.Length)
                    {
                        // All done
                        StopCapture();
                        GTA.UI.Notification.Show(
                            $"~g~Preview Capture complete!~w~\n" +
                            $"~b~{_capturedCount}~w~ captured, ~r~{_failedCount}~w~ failed\n" +
                            $"Saved to: scripts/previews/");
                        return;
                    }

                    SpawnCurrent();
                }
                return;
            }

            // Draw progress overlay
            DrawProgress("Capturing...");
        }

        private void StartCapture()
        {
            // Set up output directory
            string scriptsDir = AppDomain.CurrentDomain.BaseDirectory;
            _outputDir = Path.Combine(scriptsDir, "previews");
            try
            {
                Directory.CreateDirectory(_outputDir);
            }
            catch (Exception ex)
            {
                GTA.UI.Notification.Show($"~r~Cannot create output folder:~w~ {ex.Message}");
                return;
            }

            // Cache screen dimensions
            _screenW = Screen.PrimaryScreen.Bounds.Width;
            _screenH = Screen.PrimaryScreen.Bounds.Height;

            _active = true;
            _currentIndex = 0;
            _capturedCount = 0;
            _failedCount = 0;

            // Save player state
            Ped player = Game.Player.Character;
            _savedPlayerPos = player.Position;
            _savedPlayerHeading = player.Heading;

            // Hide player below showroom floor
            player.Position = SHOWROOM_POS + new Vector3(0f, 0f, -5f);
            player.IsVisible = false;
            player.IsPositionFrozen = true;

            // Set time to noon for consistent lighting
            World.CurrentTimeOfDay = new TimeSpan(12, 0, 0);

            // Create camera
            _camera = World.CreateCamera(Vector3.Zero, Vector3.Zero, CAM_FOV);
            World.RenderingCamera = _camera;

            GTA.UI.Notification.Show(
                $"~g~Preview Capture~w~ started.\n" +
                $"Capturing {VehicleList.All.Length} vehicles...\n" +
                $"Output: scripts/previews/\n" +
                $"Press ~b~F10~w~ to stop.");

            // Spawn first vehicle
            SpawnCurrent();
        }

        private void StopCapture()
        {
            _active = false;
            _settling = false;
            _capturing = false;

            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.Delete();
                _vehicle = null;
            }

            if (_camera != null)
            {
                World.RenderingCamera = null;
                _camera.Delete();
                _camera = null;
            }

            Ped player = Game.Player.Character;
            player.IsVisible = true;
            player.IsPositionFrozen = false;
            player.Position = _savedPlayerPos;
            player.Heading = _savedPlayerHeading;
        }

        private void SpawnCurrent()
        {
            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.Delete();
                _vehicle = null;
            }

            string modelName = VehicleList.All[_currentIndex];
            _vehicle = VehicleHelper.CreateVehicle(modelName, SHOWROOM_POS, VEHICLE_HEADING);

            if (_vehicle == null)
            {
                _failedCount++;
                // Skip to next on failure
                _currentIndex++;
                if (_currentIndex < VehicleList.All.Length)
                    SpawnCurrent();
                return;
            }

            _vehicle.IsPositionFrozen = true;
            _vehicle.IsCollisionEnabled = false;
            _vehicle.IsInvincible = true;
            _vehicle.LockStatus = VehicleLockStatus.IgnoredByPlayer;
            Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, _vehicle, 0f);
            _vehicle.AreLightsOn = true;

            UpdateCamera();

            // Start settling (wait for model to fully render)
            _settling = true;
            _frameCounter = 0;
        }

        private void UpdateCamera()
        {
            if (_camera == null || _vehicle == null || !_vehicle.Exists())
                return;

            int hash = _vehicle.Model.Hash;
            OutputArgument minArg = new OutputArgument();
            OutputArgument maxArg = new OutputArgument();
            Function.Call(Hash.GET_MODEL_DIMENSIONS, hash, minArg, maxArg);
            Vector3 vMin = minArg.GetResult<Vector3>();
            Vector3 vMax = maxArg.GetResult<Vector3>();

            float length = Math.Max(vMax.Y - vMin.Y, 3f);
            float width = Math.Max(vMax.X - vMin.X, 2f);
            float height = Math.Max(vMax.Z - vMin.Z, 1.5f);
            float extent = (float)Math.Sqrt(length * length + width * width);
            float radius = Math.Max(extent * 1.1f, CAM_RADIUS_DEFAULT);
            float camH = Math.Max(height * 0.6f, CAM_HEIGHT_DEFAULT);

            Vector3 target = _vehicle.Position + new Vector3(0f, 0f, height * 0.3f);

            float rad = CAM_ANGLE * (float)Math.PI / 180f;
            float camX = target.X + radius * (float)Math.Cos(rad);
            float camY = target.Y + radius * (float)Math.Sin(rad);
            float camZ = target.Z + camH;

            _camera.Position = new Vector3(camX, camY, camZ);
            _camera.PointAt(_vehicle);
        }

        private void CaptureScreenshot()
        {
            string modelName = VehicleList.All[_currentIndex];
            string filePath = Path.Combine(_outputDir, $"{modelName}.png");

            try
            {
                using (var bmp = new Bitmap(_screenW, _screenH, PixelFormat.Format32bppArgb))
                {
                    using (var gfx = Graphics.FromImage(bmp))
                    {
                        gfx.CopyFromScreen(0, 0, 0, 0, new Size(_screenW, _screenH),
                            CopyPixelOperation.SourceCopy);
                    }
                    bmp.Save(filePath, ImageFormat.Png);
                }
                _capturedCount++;
            }
            catch
            {
                _failedCount++;
            }
        }

        private void DrawProgress(string status)
        {
            string modelName = _currentIndex < VehicleList.All.Length
                ? VehicleList.All[_currentIndex] : "done";
            string displayName = VehicleList.DisplayNames.ContainsKey(modelName)
                ? VehicleList.DisplayNames[modelName] : modelName;

            int total = VehicleList.All.Length;
            int pct = total > 0 ? (_currentIndex * 100) / total : 100;

            // Progress bar background
            GbayRenderer.DrawRect(0.5f, 0.03f, 0.5f, 0.05f,
                Color.FromArgb(200, 0, 0, 0));

            // Progress bar fill
            float fillW = 0.48f * pct / 100f;
            GbayRenderer.DrawRect(0.26f + fillW / 2f, 0.03f, fillW, 0.035f,
                Color.FromArgb(200, 45, 156, 80));

            // Text
            string text = $"{status} {_currentIndex + 1}/{total}  ({pct}%)  {modelName}";
            GbayRenderer.DrawText(text, 0.5f, 0.012f,
                0.30f, Color.White, GbayRenderer.FONT_CONDENSED, true);
        }
    }
}
