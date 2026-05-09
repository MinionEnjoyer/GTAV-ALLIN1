// GbayInput.cs -- Input polling for the GBAY browser UI.
//
// Handles keyboard navigation, mouse position/clicks, and disabling
// conflicting game controls while the browser is open.

using System;
using System.IO;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal struct FrameInput
    {
        internal bool Accept;
        internal bool Back;
        internal int DirX;             // -1, 0, +1
        internal int DirY;             // -1, 0, +1
        internal bool PageLeft;
        internal bool PageRight;
        internal bool CategoryPrev;
        internal bool CategoryNext;
        internal float MouseX;         // 0.0 - 1.0
        internal float MouseY;         // 0.0 - 1.0
        internal bool MouseClick;
        internal bool MouseRightClick;
    }

    internal static class GbayInput
    {
        private static readonly string _logPath = Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "ALLIN1_gbay.log");

        private static void ILog(string msg)
        {
            try
            {
                File.AppendAllText(_logPath,
                    $"[{DateTime.Now:HH:mm:ss.fff}] [Input] {msg}{Environment.NewLine}");
            }
            catch { }
        }

        /// <summary>
        /// Poll all inputs for this frame. Call once per tick.
        /// </summary>
        internal static FrameInput Poll()
        {
            try
            {
                var input = new FrameInput();

                input.MouseX = Function.Call<float>(
                    Hash.GET_DISABLED_CONTROL_NORMAL, 0, (int)Control.CursorX);
                input.MouseY = Function.Call<float>(
                    Hash.GET_DISABLED_CONTROL_NORMAL, 0, (int)Control.CursorY);

                input.MouseClick = Function.Call<bool>(
                    Hash.IS_DISABLED_CONTROL_JUST_PRESSED, 0, (int)Control.CursorAccept);
                input.MouseRightClick = Function.Call<bool>(
                    Hash.IS_DISABLED_CONTROL_JUST_PRESSED, 0, (int)Control.CursorCancel);

                if (Game.IsControlJustPressed(Control.FrontendUp))
                    input.DirY = -1;
                else if (Game.IsControlJustPressed(Control.FrontendDown))
                    input.DirY = 1;

                if (Game.IsControlJustPressed(Control.FrontendLeft))
                    input.DirX = -1;
                else if (Game.IsControlJustPressed(Control.FrontendRight))
                    input.DirX = 1;

                if (Game.IsControlJustPressed(Control.FrontendAccept))
                    input.Accept = true;
                if (Game.IsControlJustPressed(Control.FrontendCancel))
                    input.Back = true;

                if (Game.IsControlJustPressed(Control.FrontendLb))
                    input.PageLeft = true;
                if (Game.IsControlJustPressed(Control.FrontendRb))
                    input.PageRight = true;

                if (Game.IsControlJustPressed(Control.FrontendLt))
                    input.CategoryPrev = true;
                if (Game.IsControlJustPressed(Control.FrontendRt))
                    input.CategoryNext = true;

                return input;
            }
            catch (Exception ex)
            {
                ILog($"EXCEPTION in Poll: {ex.Message}\n  {ex.StackTrace}");
                return new FrameInput();
            }
        }

        /// <summary>
        /// Disable all game controls except cursor and frontend navigation.
        /// </summary>
        internal static void DisableGameControls()
        {
            try
            {
            Game.DisableAllControlsThisFrame();

            // Re-enable frontend navigation (keyboard arrows, enter, esc)
            Game.EnableControlThisFrame(Control.FrontendAccept);
            Game.EnableControlThisFrame(Control.FrontendCancel);
            Game.EnableControlThisFrame(Control.FrontendUp);
            Game.EnableControlThisFrame(Control.FrontendDown);
            Game.EnableControlThisFrame(Control.FrontendLeft);
            Game.EnableControlThisFrame(Control.FrontendRight);
            Game.EnableControlThisFrame(Control.FrontendLb);
            Game.EnableControlThisFrame(Control.FrontendRb);
            Game.EnableControlThisFrame(Control.FrontendLt);
            Game.EnableControlThisFrame(Control.FrontendRt);

            // Re-enable cursor controls
            Game.EnableControlThisFrame(Control.CursorX);
            Game.EnableControlThisFrame(Control.CursorY);
            Game.EnableControlThisFrame(Control.CursorAccept);
            Game.EnableControlThisFrame(Control.CursorCancel);
            Game.EnableControlThisFrame(Control.CursorScrollUp);
            Game.EnableControlThisFrame(Control.CursorScrollDown);
            }
            catch (Exception ex)
            {
                ILog($"EXCEPTION in DisableGameControls: {ex.Message}\n  {ex.StackTrace}");
            }
        }
    }
}
