// WorldVectorTool.cs -- Lightweight coordinate overlay for world placement work.

using System;
using System.Drawing;
using System.IO;
using System.Windows.Forms;
using GTA;

namespace ALLIN1
{
    public class WorldVectorTool : Script
    {
        private Keys _toggleKey = Keys.F10;
        private bool _visible;

        public WorldVectorTool()
        {
            LoadToggleKey();
            KeyDown += OnKeyDown;
            Tick += OnTick;
            Interval = 0;
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode != _toggleKey)
                return;

            _visible = !_visible;
            GbayRenderer.PlaySelect();
            GTA.UI.Notification.Show(
                $"~g~World vector overlay:~w~ {(_visible ? "ON" : "OFF")}");
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!_visible || Game.IsLoading)
                return;

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists())
                return;

            var position = player.Position;
            float heading = player.Heading;
            GbayRenderer.DrawBorderedRect(0.205f, 0.085f, 0.37f, 0.115f,
                Color.FromArgb(220, 8, 16, 12), GbayRenderer.BtnGreen, 0.002f);
            GbayRenderer.DrawText("WORLD VECTOR", 0.035f, 0.041f, 0.33f,
                GbayRenderer.TextMfg, GbayRenderer.FONT_CONDENSED, false, true);
            GbayRenderer.DrawTextFit(
                $"X {position.X:F4}   Y {position.Y:F4}   Z {position.Z:F4}",
                0.035f, 0.071f, 0.30f, 0.21f, 0.34f,
                Color.White, GbayRenderer.FONT_CHALET, false, true);
            GbayRenderer.DrawText($"Heading {heading:F2}",
                0.035f, 0.101f, 0.28f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CHALET, false, true);
        }

        private void LoadToggleKey()
        {
            string path = Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory, "ALLIN1.toml");
            if (!File.Exists(path))
                return;

            try
            {
                foreach (string raw in File.ReadAllLines(path))
                {
                    string line = raw.Trim();
                    if (!line.StartsWith(
                        "world_vector_key", StringComparison.OrdinalIgnoreCase))
                        continue;

                    int equals = line.IndexOf('=');
                    if (equals < 0)
                        continue;
                    string value = line.Substring(equals + 1)
                        .Trim().Trim('"', '\'');
                    if (Enum.TryParse(value, true, out Keys parsed))
                        _toggleKey = parsed;
                    return;
                }
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }
    }
}
