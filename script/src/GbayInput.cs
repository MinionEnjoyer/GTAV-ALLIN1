// GbayInput.cs -- Input polling for the GBAY browser UI.
//
// Handles keyboard navigation, mouse position/clicks, and disabling
// conflicting game controls while the browser is open.

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
        internal bool FilterNext;
        internal bool Search;
        internal bool Favorite;
        internal float MouseX;         // 0.0 - 1.0
        internal float MouseY;         // 0.0 - 1.0
        internal bool MouseClick;
        internal bool MouseRightClick;
        internal int ScrollDelta;       // -1 = up, +1 = down
    }

    internal static class GbayInput
    {

        /// <summary>
        /// Poll all inputs for this frame. Call once per tick.
        /// </summary>
        internal static FrameInput Poll()
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
            if (Function.Call<bool>(Hash.IS_DISABLED_CONTROL_JUST_PRESSED,
                    0, (int)Control.CursorScrollUp))
                input.ScrollDelta = -1;
            else if (Function.Call<bool>(Hash.IS_DISABLED_CONTROL_JUST_PRESSED,
                    0, (int)Control.CursorScrollDown))
                input.ScrollDelta = 1;

            if (ControllerBindings.JustPressed(ControllerBindings.Up))
                input.DirY = -1;
            else if (ControllerBindings.JustPressed(ControllerBindings.Down))
                input.DirY = 1;

            if (ControllerBindings.JustPressed(ControllerBindings.Left))
                input.DirX = -1;
            else if (ControllerBindings.JustPressed(ControllerBindings.Right))
                input.DirX = 1;

            if (ControllerBindings.JustPressed(ControllerBindings.Accept))
                input.Accept = true;
            if (ControllerBindings.JustPressed(ControllerBindings.Back))
                input.Back = true;

            if (ControllerBindings.JustPressed(ControllerBindings.PageLeft))
                input.PageLeft = true;
            if (ControllerBindings.JustPressed(ControllerBindings.PageRight))
                input.PageRight = true;

            if (ControllerBindings.JustPressed(ControllerBindings.CategoryPrev))
                input.CategoryPrev = true;
            if (ControllerBindings.JustPressed(ControllerBindings.CategoryNext))
                input.CategoryNext = true;
            if (ControllerBindings.JustPressed(ControllerBindings.Filter))
                input.FilterNext = true;
            if (ControllerBindings.JustPressed(ControllerBindings.Search))
                input.Search = true;
            if (ControllerBindings.JustPressed(ControllerBindings.Favorite))
                input.Favorite = true;

            return input;
        }

        /// <summary>
        /// Disable all game controls except cursor and frontend navigation.
        /// </summary>
        internal static void DisableGameControls()
        {
            Game.DisableAllControlsThisFrame();

            // Explicitly disable attack/aim in both control groups to prevent shooting
            Function.Call(Hash.DISABLE_CONTROL_ACTION, 0, (int)Control.Attack, true);
            Function.Call(Hash.DISABLE_CONTROL_ACTION, 0, (int)Control.Attack2, true);
            Function.Call(Hash.DISABLE_CONTROL_ACTION, 0, (int)Control.Aim, true);
            Function.Call(Hash.DISABLE_CONTROL_ACTION, 0, (int)Control.VehicleAttack, true);
            Function.Call(Hash.DISABLE_CONTROL_ACTION, 0, (int)Control.VehicleAttack2, true);
            Function.Call(Hash.DISABLE_CONTROL_ACTION, 0, (int)Control.MeleeAttack1, true);
            Function.Call(Hash.DISABLE_CONTROL_ACTION, 0, (int)Control.MeleeAttack2, true);

            // Re-enable frontend navigation (keyboard arrows, enter, esc)
            foreach (Control control in ControllerBindings.MenuControls)
                Game.EnableControlThisFrame(control);

            // Re-enable cursor controls
            Game.EnableControlThisFrame(Control.CursorX);
            Game.EnableControlThisFrame(Control.CursorY);
            Game.EnableControlThisFrame(Control.CursorAccept);
            Game.EnableControlThisFrame(Control.CursorCancel);
            Game.EnableControlThisFrame(Control.CursorScrollUp);
            Game.EnableControlThisFrame(Control.CursorScrollDown);
        }
    }
}
