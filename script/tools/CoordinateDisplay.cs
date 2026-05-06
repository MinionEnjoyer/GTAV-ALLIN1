// CoordinateDisplay.cs -- Shows player X, Y, Z, Heading on screen.
//
// Toggle with F11. Useful for finding spawn positions for other tools.

using System;
using System.Drawing;
using System.Windows.Forms;
using GTA;
using GTA.Math;

namespace ALLIN1
{
    public class CoordinateDisplay : Script
    {
        private bool _active;

        public CoordinateDisplay()
        {
            Tick += OnTick;
            KeyDown += OnKeyDown;
            Interval = 0;
        }

        private void OnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.F11)
                _active = !_active;
        }

        private void OnTick(object sender, EventArgs e)
        {
            if (!_active)
                return;

            Vector3 pos = Game.Player.Character.Position;
            float heading = Game.Player.Character.Heading;

            GbayRenderer.DrawText(
                $"X:{pos.X:F1}  Y:{pos.Y:F1}  Z:{pos.Z:F1}  H:{heading:F1}",
                0.5f, 0.01f, 0.35f, Color.FromArgb(200, 100, 255, 100),
                GbayRenderer.FONT_CONDENSED, true);
        }
    }
}
