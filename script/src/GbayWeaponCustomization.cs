// GBAY weapon workbench: runtime DLC component discovery, camera and purchases.
using System;
using System.Collections.Generic;
using System.Drawing;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal partial class GbayBrowser
    {
        private enum WorkbenchRowKind { Ammo, Component, Tint }

        private sealed class WorkbenchRow
        {
            internal WorkbenchRowKind Kind;
            internal string Label;
            internal string Detail;
            internal int Price;
            internal int ComponentHash;
            internal int AttachmentPoint;
            internal int Tint;
        }

        private readonly List<WorkbenchRow> _workbenchRows =
            new List<WorkbenchRow>();
        private string _workbenchWeapon = "";
        private string _workbenchDisplayName = "";
        private int _workbenchSelected;
        private int _workbenchScroll;
        private int _workbenchHover = -1;
        private Camera _weaponCamera;
        private int _workbenchPreviousWeapon;
        private float _workbenchCameraAngle = 22f;
        private bool _workbenchPedFrozen;
        private const int WORKBENCH_VISIBLE_ROWS = 10;

        private void BeginWeaponCustomization(string weaponName, string displayName)
        {
            EndWeaponCustomization();
            Ped ped = Game.Player.Character;
            int weaponHash = CharacterInventory.GetWeaponHash(weaponName);
            if (ped == null || !ped.Exists() || !Function.Call<bool>(
                    Hash.HAS_PED_GOT_WEAPON, ped.Handle, weaponHash, false))
            {
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle("~r~The weapon must be owned before it can be customized.", 3000);
                return;
            }

            _workbenchWeapon = weaponName;
            _workbenchDisplayName = displayName;
            _workbenchSelected = 0;
            _workbenchScroll = 0;
            BuildWorkbenchRows();
            _workbenchPreviousWeapon = Function.Call<int>(
                Hash.GET_SELECTED_PED_WEAPON, ped.Handle);
            Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                ped.Handle, weaponHash, true);
            Function.Call(Hash.SET_PED_CURRENT_WEAPON_VISIBLE,
                ped.Handle, true, true, true, false);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, ped.Handle, true);
            _workbenchPedFrozen = true;
            CreateWeaponCamera(ped);
            _state = BrowserState.WeaponCustomize;
            ClientLog.Info("GBAY", "weapon_workbench_opened",
                new Dictionary<string, object> {
                    { "weapon", weaponName }, { "options", _workbenchRows.Count }
                });
        }

        private void BuildWorkbenchRows()
        {
            _workbenchRows.Clear();
            int rounds;
            int ammoCost = _shop.GetAmmoRefillInfo(_workbenchWeapon, out rounds);
            if (ammoCost != GbayShop.AmmoNotApplicable &&
                ammoCost != GbayShop.AmmoCapacityUnavailable)
            {
                _workbenchRows.Add(new WorkbenchRow {
                    Kind = WorkbenchRowKind.Ammo,
                    Label = "Ammunition refill",
                    Detail = rounds > 0 ? $"{rounds:N0} rounds" : "Fully stocked",
                    Price = Math.Max(0, ammoCost),
                });
            }

            Ped ped = Game.Player.Character;
            int weaponHash = CharacterInventory.GetWeaponHash(_workbenchWeapon);
            Weapon weapon = ped.Weapons[(WeaponHash)(uint)weaponHash];
            WeaponComponentCollection components = weapon.Components;
            for (int i = 0; i < components.Count; i++)
            {
                WeaponComponent component = components[i];
                int componentHash = unchecked((int)component.ComponentHash);
                if (componentHash == 0) continue;
                string label = component.LocalizedName;
                if (string.IsNullOrWhiteSpace(label))
                    label = component.DisplayName;
                if (string.IsNullOrWhiteSpace(label))
                    label = $"Component {i + 1}";
                string point = component.AttachmentPoint.ToString();
                _workbenchRows.Add(new WorkbenchRow {
                    Kind = WorkbenchRowKind.Component,
                    Label = label,
                    Detail = FriendlyAttachmentPoint(point),
                    Price = WeaponCustomizationPolicy.ComponentPrice(point, label),
                    ComponentHash = componentHash,
                    AttachmentPoint = (int)component.AttachmentPoint,
                });
            }

            int tintCount = Function.Call<int>(Hash.GET_WEAPON_TINT_COUNT, weaponHash);
            for (int tint = 0; tint < tintCount; tint++)
            {
                _workbenchRows.Add(new WorkbenchRow {
                    Kind = WorkbenchRowKind.Tint,
                    Label = TintName(tint), Detail = "Weapon finish",
                    Price = WeaponCustomizationPolicy.TintPrice(tint), Tint = tint,
                });
            }
        }

        private static string FriendlyAttachmentPoint(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return "Weapon upgrade";
            return value.Replace("GunRoot", "Finish").Replace("GunGripR", "Grip");
        }

        private static string TintName(int tint)
        {
            string[] names = {
                "Black", "Green", "Gold", "Pink", "Army", "LSPD",
                "Orange", "Platinum", "Classic Gray", "Classic Two-Tone",
                "Classic White", "Classic Beige", "Classic Green", "Classic Blue",
                "Classic Earth", "Classic Brown", "Classic Red", "Classic Orange",
                "Classic Yellow", "Classic Platinum", "Classic Gray & Black",
                "Classic Two-Tone Gray", "Classic White & Black", "Classic Red Contrast",
                "Classic Blue Contrast", "Classic Yellow Contrast", "Classic Orange Contrast",
                "Bold Pink", "Bold Yellow", "Bold Orange", "Bold Green", "Bold Blue"
            };
            return tint >= 0 && tint < names.Length
                ? $"{names[tint]} finish" : $"Finish {tint + 1}";
        }

        private void CreateWeaponCamera(Ped ped)
        {
            try
            {
                Vector3 target = ped.Position + new Vector3(0f, 0f, 1.15f);
                float radians = _workbenchCameraAngle * (float)Math.PI / 180f;
                Vector3 forward = ped.ForwardVector;
                Vector3 right = ped.RightVector;
                Vector3 position = target + forward * (1.9f * (float)Math.Cos(radians))
                    + right * (1.9f * (float)Math.Sin(radians))
                    + new Vector3(0f, 0f, 0.18f);
                _weaponCamera = World.CreateCamera(position, Vector3.Zero, 42f);
                Function.Call(Hash.POINT_CAM_AT_ENTITY,
                    _weaponCamera.Handle, ped.Handle, 0f, 0f, 1.12f, true);
                World.RenderingCamera = _weaponCamera;
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "weapon_camera_create_failed", ex);
            }
        }

        private void UpdateWeaponCamera(Ped ped, float delta)
        {
            if (Math.Abs(delta) < 0.01f) return;
            _workbenchCameraAngle += delta;
            if (_workbenchCameraAngle > 80f) _workbenchCameraAngle = 80f;
            if (_workbenchCameraAngle < -80f) _workbenchCameraAngle = -80f;
            if (_weaponCamera != null && _weaponCamera.Exists())
            {
                World.RenderingCamera = null;
                _weaponCamera.Delete();
                _weaponCamera = null;
            }
            CreateWeaponCamera(ped);
        }

        private void DrawWeaponCustomization(FrameInput input)
        {
            Ped ped = Game.Player.Character;
            if (ped == null || !ped.Exists()) { Close(); return; }
            if (input.CategoryPrev) UpdateWeaponCamera(ped, -7f);
            if (input.CategoryNext) UpdateWeaponCamera(ped, 7f);

            const float panelLeft = 0.50f;
            const float panelRight = 0.93f;
            const float panelWidth = panelRight - panelLeft;
            GbayRenderer.DrawRect((panelLeft + panelRight) / 2f, 0.48f,
                panelWidth, 0.90f, Color.FromArgb(238, 242, 239, 232));
            GbayRenderer.DrawRect((panelLeft + panelRight) / 2f, 0.075f,
                panelWidth, 0.09f, GbayRenderer.HeaderBg);
            GbayRenderer.DrawTitleBadge("WEAPON WORKBENCH", 0.61f, 0.075f,
                0.20f, 0.045f, 0.31f);
            GbayRenderer.DrawTextFit(_workbenchDisplayName, panelRight - 0.02f,
                0.058f, 0.34f, 0.22f, 0.17f, GbayRenderer.HeaderText,
                GbayRenderer.FONT_CHALET, false, false, true);

            _workbenchHover = -1;
            const float firstY = 0.145f;
            const float rowH = 0.064f;
            int count = Math.Min(WORKBENCH_VISIBLE_ROWS,
                Math.Max(0, _workbenchRows.Count - _workbenchScroll));
            for (int visible = 0; visible < count; visible++)
            {
                int index = _workbenchScroll + visible;
                WorkbenchRow row = _workbenchRows[index];
                float y = firstY + visible * rowH;
                bool selected = index == _workbenchSelected;
                bool hover = GbayRenderer.HitTest(
                    input.MouseX, input.MouseY, 0.715f, y, panelWidth - 0.035f, rowH - 0.006f);
                if (hover) _workbenchHover = index;
                bool owned = IsWorkbenchRowOwned(row);
                bool active = IsWorkbenchRowActive(row);
                Color background = selected ? GbayRenderer.CardSelected
                    : hover ? GbayRenderer.CardHover : GbayRenderer.CardBg;
                GbayRenderer.DrawBorderedRect(0.715f, y, panelWidth - 0.035f,
                    rowH - 0.006f, background,
                    selected ? FocusBorderColor() : GbayRenderer.CardBorder,
                    selected ? FocusBorderWidth() : 0.0015f);
                GbayRenderer.DrawTextFit(row.Label, panelLeft + 0.025f, y - 0.020f,
                    0.29f, 0.20f, 0.25f, GbayRenderer.TextDark, GbayRenderer.FONT_CHALET);
                string status = active ? "INSTALLED" : owned ? "OWNED"
                    : row.Price <= 0 || _shop.FreeMode ? "FREE" : $"${row.Price:N0}";
                GbayRenderer.DrawTextFit(status, panelRight - 0.025f, y - 0.020f,
                    0.27f, 0.18f, 0.12f,
                    active || owned ? GbayRenderer.TextPriceFree : GbayRenderer.TextPrice,
                    GbayRenderer.FONT_CONDENSED, false, false, true);
                GbayRenderer.DrawTextFit(row.Detail, panelLeft + 0.025f, y + 0.006f,
                    0.22f, 0.17f, 0.34f, GbayRenderer.TextDim, GbayRenderer.FONT_CONDENSED);
            }

            if (_workbenchRows.Count == 0)
                GbayRenderer.DrawText("No compatible upgrades reported by this game build.",
                    0.715f, 0.43f, 0.30f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CHALET, true);

            DrawControlHint("A BUY / EQUIP    LT/RT ROTATE    B RETURN TO WEAPONS",
                panelRight - 0.02f, 0.885f, panelWidth - 0.04f, 0.04f);
            HandleWeaponCustomizationInput(input);
        }

        private bool IsWorkbenchRowOwned(WorkbenchRow row)
        {
            if (row.Kind == WorkbenchRowKind.Ammo) return false;
            if (row.Kind == WorkbenchRowKind.Component)
                return CharacterInventory.IsWeaponComponentOwned(
                    _workbenchWeapon, row.ComponentHash) || IsWorkbenchRowActive(row);
            return CharacterInventory.IsWeaponTintOwned(_workbenchWeapon, row.Tint);
        }

        private bool IsWorkbenchRowActive(WorkbenchRow row)
        {
            int weaponHash = CharacterInventory.GetWeaponHash(_workbenchWeapon);
            Ped ped = Game.Player.Character;
            if (row.Kind == WorkbenchRowKind.Ammo)
            {
                int rounds;
                return _shop.GetAmmoRefillInfo(_workbenchWeapon, out rounds) == 0 && rounds == 0;
            }
            if (row.Kind == WorkbenchRowKind.Component)
                return Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                    ped.Handle, weaponHash, row.ComponentHash);
            return Function.Call<int>(Hash.GET_PED_WEAPON_TINT_INDEX,
                ped.Handle, weaponHash) == row.Tint;
        }

        private void HandleWeaponCustomizationInput(FrameInput input)
        {
            if (input.Back || input.MouseRightClick)
            {
                EndWeaponCustomization();
                _state = BrowserState.WeaponBrowser;
                GbayRenderer.PlayBack();
                return;
            }
            if (_workbenchRows.Count == 0) return;
            int old = _workbenchSelected;
            if (input.DirY < 0) _workbenchSelected = Math.Max(0, _workbenchSelected - 1);
            if (input.DirY > 0) _workbenchSelected = Math.Min(
                _workbenchRows.Count - 1, _workbenchSelected + 1);
            if (input.ScrollDelta < 0) _workbenchSelected = Math.Max(0, _workbenchSelected - 1);
            if (input.ScrollDelta > 0) _workbenchSelected = Math.Min(
                _workbenchRows.Count - 1, _workbenchSelected + 1);
            if (_workbenchHover >= 0) _workbenchSelected = _workbenchHover;
            if (_workbenchSelected != old) GbayRenderer.PlayNav();
            if (_workbenchSelected < _workbenchScroll) _workbenchScroll = _workbenchSelected;
            if (_workbenchSelected >= _workbenchScroll + WORKBENCH_VISIBLE_ROWS)
                _workbenchScroll = _workbenchSelected - WORKBENCH_VISIBLE_ROWS + 1;

            bool accepted = input.Accept || (input.MouseClick && _workbenchHover >= 0);
            if (!accepted) return;
            WorkbenchRow row = _workbenchRows[_workbenchSelected];
            bool success;
            if (row.Kind == WorkbenchRowKind.Ammo)
                success = _shop.ExecuteRefillAmmo(_workbenchWeapon) >= 0;
            else if (row.Kind == WorkbenchRowKind.Component)
                success = _shop.ExecuteWeaponComponentPurchase(_workbenchWeapon,
                    row.ComponentHash, row.AttachmentPoint, row.Price);
            else
                success = _shop.ExecuteWeaponTintPurchase(
                    _workbenchWeapon, row.Tint, row.Price);
            if (success) { GbayRenderer.PlaySelect(); BuildWorkbenchRows(); }
            else GbayRenderer.PlayError();
        }

        private void EndWeaponCustomization()
        {
            if (_weaponCamera != null && _weaponCamera.Exists())
            {
                World.RenderingCamera = null;
                _weaponCamera.Delete();
            }
            _weaponCamera = null;
            Ped ped = Game.Player.Character;
            if (ped != null && ped.Exists())
            {
                if (_workbenchPedFrozen)
                    Function.Call(Hash.FREEZE_ENTITY_POSITION, ped.Handle, false);
                if (_workbenchPreviousWeapon != 0)
                    Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                        ped.Handle, _workbenchPreviousWeapon, true);
            }
            _workbenchPedFrozen = false;
            _workbenchPreviousWeapon = 0;
            _workbenchWeapon = "";
            _workbenchRows.Clear();
        }
    }
}
