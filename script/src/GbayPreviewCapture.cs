// GbayPreviewCapture.cs -- Temporary tool for capturing vehicle preview screenshots.
//
// Press F10 to start. Teleports player to Simeon's showroom, spawns each
// vehicle one at a time with a fixed camera angle. Use N/B to cycle through
// vehicles, take screenshots with Steam (F12) or Print Screen.
//
// The model name is displayed on screen so you can name files accordingly.
// This script is a development tool, not part of the normal GBAY experience.

using System;
using System.Drawing;
using System.Windows.Forms;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public class GbayPreviewCapture : Script
    {
        // Simeon's showroom -- center of the main floor area
        private static readonly Vector3 SHOWROOM_POS = new Vector3(-44.7f, -1098.5f, 26.4f);
        private const float VEHICLE_HEADING = 60f; // angled nicely in the showroom

        // Camera offset from vehicle center
        private const float CAM_RADIUS = 7.5f;
        private const float CAM_HEIGHT = 2.0f;
        private const float CAM_ANGLE = 210f; // degrees -- front-quarter view
        private const float CAM_FOV = 50f;

        private bool _active;
        private int _currentIndex;
        private Vehicle _vehicle;
        private Camera _camera;
        private Vector3 _savedPlayerPos;
        private float _savedPlayerHeading;
        private bool _hideHud;
        private float _orbitAngle;
        private bool _autoOrbit;

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
                return;
            }

            if (!_active)
                return;

            switch (e.KeyCode)
            {
                case Keys.N: // Next vehicle
                    _currentIndex = (_currentIndex + 1) % VehicleList.All.Length;
                    SpawnCurrent();
                    break;

                case Keys.B: // Previous vehicle
                    _currentIndex--;
                    if (_currentIndex < 0)
                        _currentIndex = VehicleList.All.Length - 1;
                    SpawnCurrent();
                    break;

                case Keys.H: // Toggle HUD overlay
                    _hideHud = !_hideHud;
                    break;

                case Keys.R: // Toggle auto-orbit
                    _autoOrbit = !_autoOrbit;
                    break;

                case Keys.T: // Reset camera angle
                    _orbitAngle = CAM_ANGLE;
                    UpdateCamera();
                    break;
            }
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!_active)
                return;

            GbayInput.DisableGameControls();

            // Manual orbit with Left/Right
            if (Game.IsControlPressed(GTA.Control.FrontendLeft))
            {
                _orbitAngle -= 60f * Game.LastFrameTime;
                UpdateCamera();
            }
            else if (Game.IsControlPressed(GTA.Control.FrontendRight))
            {
                _orbitAngle += 60f * Game.LastFrameTime;
                UpdateCamera();
            }

            // Auto orbit
            if (_autoOrbit)
            {
                _orbitAngle += 15f * Game.LastFrameTime;
                UpdateCamera();
            }

            // Keep vehicle frozen and clean
            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.IsPositionFrozen = true;
                Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, _vehicle, 0f);
            }

            // Draw HUD overlay
            if (!_hideHud)
                DrawOverlay();
        }

        private void StartCapture()
        {
            _active = true;
            _currentIndex = 0;
            _hideHud = false;
            _autoOrbit = false;
            _orbitAngle = CAM_ANGLE;

            // Save player position
            Ped player = Game.Player.Character;
            _savedPlayerPos = player.Position;
            _savedPlayerHeading = player.Heading;

            // Teleport player to showroom (hide them)
            player.Position = SHOWROOM_POS + new Vector3(0f, 0f, -5f); // below floor
            player.IsVisible = false;
            player.IsPositionFrozen = true;

            // Create camera
            _camera = World.CreateCamera(Vector3.Zero, Vector3.Zero, CAM_FOV);
            World.RenderingCamera = _camera;

            // Spawn first vehicle
            SpawnCurrent();

            GTA.UI.Notification.Show("~g~Preview Capture~w~ started.\n~b~N~w~/~b~B~w~ = Next/Prev\n~b~H~w~ = Toggle HUD\n~b~R~w~ = Auto-orbit\n~b~Left/Right~w~ = Rotate\n~b~T~w~ = Reset angle\n~b~F10~w~ = Stop");
        }

        private void StopCapture()
        {
            _active = false;

            // Clean up vehicle
            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.Delete();
                _vehicle = null;
            }

            // Clean up camera
            if (_camera != null)
            {
                World.RenderingCamera = null;
                _camera.Delete();
                _camera = null;
            }

            // Restore player
            Ped player = Game.Player.Character;
            player.IsVisible = true;
            player.IsPositionFrozen = false;
            player.Position = _savedPlayerPos;
            player.Heading = _savedPlayerHeading;

            GTA.UI.Notification.Show("~g~Preview Capture~w~ stopped.");
        }

        private void SpawnCurrent()
        {
            // Delete old vehicle
            if (_vehicle != null && _vehicle.Exists())
            {
                _vehicle.Delete();
                _vehicle = null;
            }

            string modelName = VehicleList.All[_currentIndex];

            // Spawn at showroom position
            _vehicle = VehicleHelper.CreateVehicle(modelName, SHOWROOM_POS, VEHICLE_HEADING);

            if (_vehicle == null)
            {
                GTA.UI.Screen.ShowSubtitle($"~r~Failed to spawn: {modelName}", 2000);
                return;
            }

            _vehicle.IsPositionFrozen = true;
            _vehicle.IsCollisionEnabled = false;
            _vehicle.IsInvincible = true;
            _vehicle.LockStatus = VehicleLockStatus.IgnoredByPlayer;
            Function.Call(Hash.SET_VEHICLE_DIRT_LEVEL, _vehicle, 0f);

            // Turn on headlights for dramatic effect
            _vehicle.AreLightsOn = true;

            // Reset orbit angle and update camera
            _orbitAngle = CAM_ANGLE;
            UpdateCamera();
        }

        private void UpdateCamera()
        {
            if (_camera == null || _vehicle == null || !_vehicle.Exists())
                return;

            // Get vehicle dimensions for framing
            int hash = _vehicle.Model.Hash;
            OutputArgument minArg = new OutputArgument();
            OutputArgument maxArg = new OutputArgument();
            Function.Call(Hash.GET_MODEL_DIMENSIONS, hash, minArg, maxArg);
            Vector3 vMin = minArg.GetResult<Vector3>();
            Vector3 vMax = maxArg.GetResult<Vector3>();

            float length = Math.Max(vMax.Y - vMin.Y, 3f);
            float width = Math.Max(vMax.X - vMin.X, 2f);
            float extent = (float)Math.Sqrt(length * length + width * width);
            float radius = Math.Max(extent * 1.1f, CAM_RADIUS);
            float height = Math.Max((vMax.Z - vMin.Z) * 0.6f, CAM_HEIGHT);

            // Camera looks at center of vehicle (slightly raised)
            Vector3 target = _vehicle.Position + new Vector3(0f, 0f, (vMax.Z - vMin.Z) * 0.3f);

            float rad = _orbitAngle * (float)Math.PI / 180f;
            float camX = target.X + radius * (float)Math.Cos(rad);
            float camY = target.Y + radius * (float)Math.Sin(rad);
            float camZ = target.Z + height;

            _camera.Position = new Vector3(camX, camY, camZ);
            _camera.PointAt(_vehicle);
        }

        private void DrawOverlay()
        {
            string modelName = VehicleList.All[_currentIndex];
            string displayName = VehicleList.DisplayNames.ContainsKey(modelName)
                ? VehicleList.DisplayNames[modelName] : modelName;

            // Top bar
            GbayRenderer.DrawRect(0.5f, 0.03f, 1f, 0.06f,
                Color.FromArgb(180, 0, 0, 0));

            // Model name (for file naming)
            GbayRenderer.DrawText($"Model: {modelName}", 0.02f, 0.008f,
                0.35f, Color.FromArgb(255, 100, 255, 100),
                GbayRenderer.FONT_CONDENSED);

            // Display name
            GbayRenderer.DrawText(displayName, 0.5f, 0.008f,
                0.40f, Color.White, GbayRenderer.FONT_CHALET, true);

            // Counter
            string counter = $"{_currentIndex + 1} / {VehicleList.All.Length}";
            GbayRenderer.DrawText(counter, 0.98f, 0.008f,
                0.35f, Color.White, GbayRenderer.FONT_CONDENSED,
                false, false, true);

            // Bottom controls bar
            GbayRenderer.DrawRect(0.5f, 0.965f, 1f, 0.05f,
                Color.FromArgb(180, 0, 0, 0));

            string status = _autoOrbit ? "Orbit: ON" : "Orbit: OFF";
            GbayRenderer.DrawText(
                $"[N] Next  [B] Prev  [H] Hide HUD  [R] {status}  [T] Reset  [F10] Stop",
                0.5f, 0.948f, 0.25f, Color.White,
                GbayRenderer.FONT_CONDENSED, true);
        }
    }
}
