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
        internal float MouseX;         // 0.0 - 1.0
        internal float MouseY;         // 0.0 - 1.0
        internal bool MouseClick;
        internal bool MouseRightClick;
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
    }
}
