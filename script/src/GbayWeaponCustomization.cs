// GBAY weapon workbench: runtime DLC component discovery, camera and purchases.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Runtime.InteropServices;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal partial class GbayBrowser
    {
        private enum WorkbenchRowKind { Ammo, Component, Tint, ComponentTint, ComponentRemove }
        private int _workbenchPreviewRemovedComponent;

        private sealed class WorkbenchRow
        {
            internal WorkbenchRowKind Kind;
            internal string Label;
            internal string BaseLabel;
            internal string Detail;
            internal int Price;
            internal int ComponentHash;
            internal int AttachmentPoint;
            internal int Tint;
            internal bool SupportsLiveryTint;
        }

        /// <summary>
        /// Detached description of one option from the established native
        /// workbench discovery pipeline. It contains no camera, preview actor,
        /// renderer, or writable authority.
        /// </summary>
        internal sealed class DetachedWorkbenchRow
        {
            internal string Kind;
            internal string Label;
            internal string Detail;
            internal int Price;
            internal int ComponentHash;
            internal int AttachmentPoint;
            internal int Tint;
            internal bool Owned;
            internal bool Active;
            internal bool SupportsLiveryTint;
        }

        // Rockstar's DLC natives expose component hashes that are newer than
        // the fixed component table in the SHVDN SDK used to compile ALLIN1.
        // Keep only the fields GBAY consumes while preserving the native sizes
        // and offsets used by GET_DLC_WEAPON_*_DATA.
        [StructLayout(LayoutKind.Explicit, Size = 0x138)]
        private struct RuntimeDlcWeaponData
        {
            [FieldOffset(0x08)] internal int WeaponHash;
        }

        [StructLayout(LayoutKind.Explicit, Size = 0x110)]
        private unsafe struct RuntimeDlcWeaponComponentData
        {
            [FieldOffset(0x00)] internal int AttachmentPoint;
            [FieldOffset(0x18)] internal int ComponentHash;
            [FieldOffset(0x30)] private fixed byte _displayName[0x40];

            internal string DisplayName
            {
                get
                {
                    fixed (byte* value = _displayName)
                        return Marshal.PtrToStringAnsi(new IntPtr(value)) ?? "";
                }
            }
        }

        private readonly List<WorkbenchRow> _workbenchRows =
            new List<WorkbenchRow>();
        private string _workbenchWeapon = "";
        private string _workbenchDisplayName = "";
        private int _workbenchSelected;
        private int _workbenchScroll;
        private int _workbenchHover = -1;
        private Camera _weaponCamera;
        private Ped _workbenchDummy;
        private int _workbenchPreviousWeapon;
        private float _workbenchCameraAngle = -22f;
        private bool _workbenchPedFrozen;
        private Ped _workbenchPlayer;
        private float _workbenchPreviousHeading;
        private Vector3 _workbenchAnchorPosition;
        private Vector3 _workbenchAnchorForward;
        private Vector3 _workbenchAnchorRight;
        private Vector3 _workbenchHiddenPlayerPosition;
        private bool _workbenchPlayerRelocated;
        private bool _workbenchAimTaskStarted;
        private Vector3 _workbenchAimTarget;
        private Vector3 _workbenchWeaponCenter;
        private bool _workbenchWeaponCenterInitialized;
        private Vector3 _workbenchCameraFocus;
        private Vector3 _workbenchCameraFocusTarget;
        private Vector3 _workbenchCameraPosition;
        private Vector3 _workbenchCameraPositionTarget;
        private int _workbenchCameraFocusUpdatedAt;
        private int _workbenchCameraLastRepairAt;
        private bool _workbenchCameraFocusInitialized;
        private bool _workbenchCameraPositionInitialized;
        private int _workbenchPreviewComponent;
        private int _workbenchPreviewRestoreComponent;
        private int _workbenchPreviewTint = -1;
        private int _workbenchPreviewRestoreTint = -1;
        private int _workbenchPreviewComponentTintComponent;
        private int _workbenchPreviewComponentTint = -1;
        private int _workbenchPreviewRestoreComponentTint = -1;
        private int _workbenchWeaponMismatchSince;
        private bool _workbenchWeaponRecoveryAttempted;
        // Reactor owns the visible menu and input while this mode is active.
        // The established native workbench is retained only as a world-space
        // preview host (dummy, camera, pose, and temporary option preview).
        private bool _reactorVisualWeaponPreview;
        private const int WORKBENCH_VISIBLE_ROWS = 7;
        private const int WORKBENCH_WEAPON_RECOVERY_DELAY_MS = 350;
        private const int WORKBENCH_LIVERY_TINT_COUNT = 32;

        private bool CanUseWeaponWorkbenchHere(bool notify)
        {
            Ped ped = Game.Player.Character;
            string reason = "this location";
            bool available = ped != null && ped.Exists() && !ped.IsDead;
            if (available && ped.IsInVehicle())
            {
                available = false;
                reason = "a vehicle";
            }
            if (available && Function.Call<int>(
                    Hash.GET_INTERIOR_FROM_ENTITY, ped.Handle) != 0)
            {
                available = false;
                reason = "an interior or safehouse";
            }
            if (available && (ped.IsRagdoll ||
                    Function.Call<bool>(Hash.IS_PED_FALLING, ped.Handle) ||
                    Function.Call<bool>(Hash.IS_PED_SWIMMING, ped.Handle)))
            {
                available = false;
                reason = "the current activity";
            }
            if (!available && notify)
            {
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle(
                    $"~y~Weapon customization is unavailable in {reason}. " +
                    "Go outside to a safe place where weapons can be equipped.",
                    5000);
                ClientLog.Warn("GBAY", "weapon_workbench_location_blocked",
                    new Dictionary<string, object> {
                        { "reason", reason },
                        { "interior", ped != null && ped.Exists()
                            ? Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY,
                                ped.Handle) : 0 }
                    });
            }
            return available;
        }

        internal bool IsReactorWeaponPreviewOpen =>
            _reactorVisualWeaponPreview && _workbenchPedFrozen &&
            !string.IsNullOrWhiteSpace(_workbenchWeapon);

        /// <summary>
        /// Starts only the established in-world actor/camera portion of the
        /// workbench. Reactor remains the sole visible menu and input owner.
        /// </summary>
        internal bool TryOpenReactorWeaponPreview(
            string weaponName, string displayName)
        {
            if (_state != BrowserState.Closed)
                return false;
            try
            {
                BeginWeaponCustomization(
                    weaponName, displayName, reactorVisualOnly: true);
            }
            catch
            {
                EndWeaponCustomization();
                throw;
            }
            return IsReactorWeaponPreviewOpen;
        }

        /// <summary>
        /// Updates the temporary dummy preview from a host-validated detached
        /// option. This never charges money or writes character inventory.
        /// </summary>
        internal bool TryPreviewReactorWeaponOption(
            string weaponName, string kind, int componentHash,
            int attachmentPoint, int tint)
        {
            if (!IsReactorWeaponPreviewOpen || !string.Equals(
                    _workbenchWeapon, weaponName,
                    StringComparison.OrdinalIgnoreCase))
                return false;

            // Drop the previous temporary option, then synchronize purchases
            // and equipped state before staging the newly focused option.
            RestoreWorkbenchPreview();
            if (_workbenchDummy != null && _workbenchDummy.Exists())
                CharacterInventory.ApplyWeaponCustomizationNow(
                    _workbenchDummy, _workbenchWeapon);
            int index = _workbenchRows.FindIndex(row =>
                WorkbenchRowMatchesPreview(
                    row, kind, componentHash, attachmentPoint, tint));
            // The option set is stable while hovering. A newly purchased
            // livery can legitimately add tint rows, so refresh from the
            // storefront cache only when the requested row is absent.
            if (index < 0 && TryPopulateWorkbenchRowsFromStorefrontCache())
                index = _workbenchRows.FindIndex(row =>
                    WorkbenchRowMatchesPreview(
                        row, kind, componentHash, attachmentPoint, tint));
            if (index < 0) return false;

            _workbenchSelected = index;
            _workbenchScroll = Math.Max(0,
                Math.Min(index, Math.Max(0,
                    _workbenchRows.Count - WORKBENCH_VISIBLE_ROWS)));
            ApplyWorkbenchPreviewForSelection();
            SetWeaponCameraFocusTarget();
            return true;
        }

        internal void TickReactorWeaponPreview()
        {
            if (!IsReactorWeaponPreviewOpen) return;
            Ped ped = Game.Player.Character;
            if (ped == null || !ped.Exists() || ped.IsDead || Game.IsLoading ||
                !MaintainWeaponWorkbenchPose(ped))
            {
                EndWeaponCustomization();
                return;
            }
            UpdateWeaponCameraFocus();
        }

        internal void CloseReactorWeaponPreview()
        {
            if (_reactorVisualWeaponPreview)
                EndWeaponCustomization();
        }

        private static bool WorkbenchRowMatchesPreview(
            WorkbenchRow row, string kind, int componentHash,
            int attachmentPoint, int tint)
        {
            if (row == null) return false;
            string normalized = (kind ?? "").Trim().ToLowerInvariant();
            switch (row.Kind)
            {
                case WorkbenchRowKind.Ammo:
                    return normalized == "ammo";
                case WorkbenchRowKind.Component:
                    return normalized == "component" &&
                        row.ComponentHash == componentHash &&
                        row.AttachmentPoint == attachmentPoint;
                case WorkbenchRowKind.ComponentRemove:
                    return normalized == "component_remove" &&
                        row.ComponentHash == componentHash &&
                        row.AttachmentPoint == attachmentPoint && tint == 0;
                case WorkbenchRowKind.Tint:
                    return normalized == "tint" && row.Tint == tint;
                case WorkbenchRowKind.ComponentTint:
                    return normalized == "component_tint" &&
                        row.ComponentHash == componentHash &&
                        row.AttachmentPoint == attachmentPoint &&
                        row.Tint == tint;
                default:
                    return false;
            }
        }

        private void BeginWeaponCustomization(
            string weaponName, string displayName,
            bool reactorVisualOnly = false)
        {
            EndWeaponCustomization();
            Ped ped = Game.Player.Character;
            if (!CanUseWeaponWorkbenchHere(true)) return;
            int weaponHash = CharacterInventory.GetWeaponHash(weaponName);
            if (ped == null || !ped.Exists() || !Function.Call<bool>(
                    Hash.HAS_PED_GOT_WEAPON, ped.Handle, weaponHash, false))
            {
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle("~r~The weapon must be owned before it can be customized.", 3000);
                return;
            }

            _workbenchPreviousWeapon = Function.Call<int>(
                Hash.GET_SELECTED_PED_WEAPON, ped.Handle);
            Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                ped.Handle, weaponHash, true);
            if (Function.Call<int>(Hash.GET_SELECTED_PED_WEAPON,
                    ped.Handle) != weaponHash)
            {
                if (_workbenchPreviousWeapon != 0)
                    Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                        ped.Handle, _workbenchPreviousWeapon, true);
                _workbenchPreviousWeapon = 0;
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle(
                    "~y~This location is preventing the weapon from being " +
                    "equipped. Move outside and try again.", 5000);
                ClientLog.Warn("GBAY", "weapon_workbench_equip_blocked",
                    new Dictionary<string, object> {
                        { "weapon", weaponName },
                        { "selected_weapon", Function.Call<int>(
                            Hash.GET_SELECTED_PED_WEAPON, ped.Handle) }
                    });
                return;
            }

            _workbenchWeapon = weaponName;
            _workbenchDisplayName = displayName;
            _workbenchSelected = 0;
            _workbenchScroll = 0;
            BuildWorkbenchRows();
            _workbenchPreviousHeading = ped.Heading;
            _workbenchAnchorPosition = ped.Position;
            _workbenchAnchorForward = ped.ForwardVector;
            _workbenchAnchorRight = ped.RightVector;
            _workbenchAimTarget = _workbenchAnchorPosition +
                _workbenchAnchorForward * 25f + new Vector3(0f, 0f, 1.35f);
            _workbenchCameraAngle = -12f;
            _workbenchWeaponCenter = _workbenchAnchorPosition +
                _workbenchAnchorForward * 0.24f +
                _workbenchAnchorRight * 0.08f +
                new Vector3(0f, 0f, 1.35f);
            _workbenchWeaponCenterInitialized = false;
            _workbenchCameraFocusTarget = GetWeaponFocusPoint(
                GetSelectedWorkbenchRow());
            _workbenchCameraFocus = _workbenchCameraFocusTarget;
            _workbenchCameraFocusUpdatedAt = Game.GameTime;
            _workbenchCameraFocusInitialized = true;
            _workbenchDummy = CreateWeaponWorkbenchDummy(ped, weaponHash);
            if (_workbenchDummy == null || !_workbenchDummy.Exists())
            {
                if (_workbenchPreviousWeapon != 0)
                    Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                        ped.Handle, _workbenchPreviousWeapon, true);
                _workbenchPreviousWeapon = 0;
                _workbenchWeapon = "";
                _workbenchRows.Clear();
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The weapon preview actor could not be created. Try again outside.",
                    4000);
                return;
            }

            // Cleanup must target the exact player entity that was moved and
            // hidden. During loading or a character switch
            // Game.Player.Character can already refer to a replacement ped;
            // restoring that replacement to this workbench's anchor would
            // teleport or otherwise mutate the wrong protagonist.
            _workbenchPlayer = ped;
            SeparateRealPlayerFromWorkbench(ped);
            _workbenchPedFrozen = true;
            _workbenchAimTaskStarted = false;
            _workbenchWeaponMismatchSince = 0;
            _workbenchWeaponRecoveryAttempted = false;
            StartWeaponWorkbenchAim(_workbenchDummy);
            UpdateLiveWeaponCenter(true);
            _workbenchCameraFocusTarget = GetWeaponFocusPoint(
                GetSelectedWorkbenchRow());
            _workbenchCameraFocus = _workbenchCameraFocusTarget;
            _reactorVisualWeaponPreview = reactorVisualOnly;
            if (!reactorVisualOnly)
                _state = BrowserState.WeaponCustomize;
            ApplyWorkbenchPreviewForSelection();
            CreateWeaponCamera(_workbenchDummy, false);
                ClientLog.Info("GBAY", "weapon_workbench_opened",
                    new Dictionary<string, object> {
                        { "weapon", weaponName }, { "options", _workbenchRows.Count },
                        { "anchor_x", _workbenchAnchorPosition.X },
                        { "anchor_y", _workbenchAnchorPosition.Y },
                        { "anchor_z", _workbenchAnchorPosition.Z },
                        { "forward_x", _workbenchAnchorForward.X },
                        { "forward_y", _workbenchAnchorForward.Y },
                        { "focus_x", _workbenchCameraFocus.X },
                        { "focus_y", _workbenchCameraFocus.Y },
                        { "focus_z", _workbenchCameraFocus.Z }
                    });
        }

        private void SeparateRealPlayerFromWorkbench(Ped player)
        {
            // An invisible player can still participate in depth/occlusion.
            // Keeping the real ped inside the preview clone masked the clone in
            // the final render.  Park the frozen player just behind the camera
            // while the visible clone remains at the audited entry transform.
            _workbenchHiddenPlayerPosition = _workbenchAnchorPosition +
                _workbenchAnchorForward * 5.25f +
                new Vector3(0f, 0f, -1.25f);
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player.Handle, true);
            Function.Call(Hash.SET_ENTITY_COLLISION,
                player.Handle, false, false);
            Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET, player.Handle,
                _workbenchHiddenPlayerPosition.X,
                _workbenchHiddenPlayerPosition.Y,
                _workbenchHiddenPlayerPosition.Z,
                false, false, false);
            Function.Call(Hash.SET_PED_CAN_PLAY_AMBIENT_ANIMS,
                player.Handle, false);
            Function.Call(Hash.SET_PED_CAN_PLAY_AMBIENT_BASE_ANIMS,
                player.Handle, false);
            Function.Call(Hash.SET_PED_CAN_PLAY_GESTURE_ANIMS,
                player.Handle, false);
            Function.Call(Hash.SET_PED_CURRENT_WEAPON_VISIBLE,
                player.Handle, false, false, false, false);
            Function.Call(Hash.SET_LOCAL_PLAYER_INVISIBLE_LOCALLY, true);
            Function.Call(Hash.SET_ENTITY_VISIBLE,
                player.Handle, false, false);
            _workbenchPlayerRelocated = true;
            ClientLog.Info("GBAY", "weapon_workbench_player_separated",
                new Dictionary<string, object>
                {
                    { "player", player.Handle },
                    { "preview", _workbenchDummy?.Handle ?? 0 },
                    { "separation", player.Position.DistanceTo(
                        _workbenchAnchorPosition) },
                });
        }

        private Ped CreateWeaponWorkbenchDummy(Ped player, int weaponHash)
        {
            Ped dummy = null;
            try
            {
                dummy = player.Clone(_workbenchPreviousHeading);
                if (dummy == null || !dummy.Exists()) return null;
                dummy.IsPersistent = true;
                dummy.IsInvincible = true;
                dummy.CanRagdoll = false;
                dummy.IsCollisionEnabled = false;
                Function.Call(Hash.SET_BLOCKING_OF_NON_TEMPORARY_EVENTS,
                    dummy.Handle, true);
                Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, dummy.Handle);
                Function.Call(Hash.SET_PED_CAN_PLAY_AMBIENT_ANIMS,
                    dummy.Handle, false);
                Function.Call(Hash.SET_PED_CAN_PLAY_AMBIENT_BASE_ANIMS,
                    dummy.Handle, false);
                Function.Call(Hash.SET_PED_CAN_PLAY_GESTURE_ANIMS,
                    dummy.Handle, false);
                Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET, dummy.Handle,
                    _workbenchAnchorPosition.X, _workbenchAnchorPosition.Y,
                    _workbenchAnchorPosition.Z, false, false, false);
                Function.Call(Hash.SET_ENTITY_HEADING,
                    dummy.Handle, _workbenchPreviousHeading);
                int ammo = Math.Max(1, Function.Call<int>(
                    Hash.GET_AMMO_IN_PED_WEAPON, player.Handle, weaponHash));
                Function.Call(Hash.GIVE_WEAPON_TO_PED, dummy.Handle,
                    weaponHash, ammo, false, true);
                CharacterInventory.ApplyWeaponCustomizationNow(
                    dummy, _workbenchWeapon);
                Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                    dummy.Handle, weaponHash, true);
                Function.Call(Hash.SET_PED_CURRENT_WEAPON_VISIBLE,
                    dummy.Handle, true, true, true, false);
                Function.Call(Hash.SET_ENTITY_VISIBLE,
                    dummy.Handle, true, false);
                Function.Call(Hash.RESET_ENTITY_ALPHA, dummy.Handle);
                Function.Call(Hash.SET_ENTITY_ALWAYS_PRERENDER,
                    dummy.Handle, true);
                Function.Call(Hash.FREEZE_ENTITY_POSITION,
                    dummy.Handle, true);
                ClientLog.Info("GBAY", "weapon_workbench_dummy_created",
                    new Dictionary<string, object> {
                        { "player", player.Handle }, { "dummy", dummy.Handle },
                        { "weapon", _workbenchWeapon }, { "ammo", ammo }
                    });
                return dummy;
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "weapon_workbench_dummy_failed", ex,
                    new Dictionary<string, object> {
                        { "weapon", _workbenchWeapon }
                    });
                if (dummy != null && dummy.Exists()) dummy.Delete();
                return null;
            }
        }

        private void BuildWorkbenchRows(bool allowStorefrontCache = true)
        {
            if (allowStorefrontCache &&
                TryPopulateWorkbenchRowsFromStorefrontCache())
                return;
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
            var seen = new HashSet<int>();
            int mappedComponents = 0;
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
                if (AddWorkbenchComponent(seen, weaponHash, componentHash,
                        (int)component.AttachmentPoint, point, label))
                    mappedComponents++;
            }

            // The SDK component table is versioned. Merge the game's live DLC
            // list so newer Enhanced/DLC attachments and camo liveries appear
            // without requiring an ALLIN1 catalog update.
            int runtimeComponents = AddRuntimeDlcComponents(
                weaponHash, seen, false) + AddRuntimeDlcComponents(
                weaponHash, seen, true);

            // Also validate every component hash exposed by SHVDN's live native
            // memory catalog. Unlike Enum.GetValues, this is not limited to the
            // enum members present in the SDK used to compile ALLIN1.
            int compatibilityComponents = 0;
            foreach (WeaponComponentHash candidate in
                WeaponComponent.GetAllHashes())
            {
                int candidateHash = unchecked((int)candidate);
                if (candidateHash == 0 || candidateHash == -1 ||
                    seen.Contains(candidateHash)) continue;
                string enumName = candidate.ToString();
                int inferredPoint = InferCompatibilityAttachmentPoint(enumName);
                if (AddWorkbenchComponent(seen, weaponHash, candidateHash,
                        inferredPoint, FriendlyCompatibilityPoint(enumName),
                        HumanizeComponentName(enumName)))
                    compatibilityComponents++;
            }

            // Explicit actions, not a toggle: a stale Equip request must never
            // become Unequip (or the reverse) after the live state changes.
            var removals = new List<WorkbenchRow>();
            foreach (WorkbenchRow row in _workbenchRows)
                if (row.Kind == WorkbenchRowKind.Component &&
                    WeaponCustomizationPolicy.CanUnequipComponent(row.AttachmentPoint) &&
                    !WeaponComponentDefaults.IsDefault(weaponHash, row.ComponentHash) &&
                    HasLiveWorkbenchComponent(ped, weaponHash, row.ComponentHash))
                    removals.Add(new WorkbenchRow {
                        Kind = WorkbenchRowKind.ComponentRemove,
                        Label = "Unequip " + row.Label, BaseLabel = row.BaseLabel,
                        Detail = row.Detail + " · Keep owned attachment", Price = 0,
                        ComponentHash = row.ComponentHash, AttachmentPoint = row.AttachmentPoint,
                    });
            _workbenchRows.AddRange(removals);
            int tintCount = RuntimeWeaponCatalog.SupportedTintCount(_workbenchWeapon,
                Function.Call<int>(Hash.GET_WEAPON_TINT_COUNT, weaponHash));
            for (int tint = 0; tint < tintCount; tint++)
            {
                _workbenchRows.Add(new WorkbenchRow {
                    Kind = WorkbenchRowKind.Tint,
                    Label = TintName(tint), Detail = "Weapon finish",
                    Price = WeaponCustomizationPolicy.TintPrice(tint), Tint = tint,
                });
            }
            int liveryTints = AddActiveLiveryTintRows(ped, weaponHash);
            ClientLog.Info("GBAY", "weapon_workbench_catalog_built",
                new Dictionary<string, object> {
                    { "weapon", _workbenchWeapon },
                    { "sdk_components", mappedComponents },
                    { "runtime_dlc_components", runtimeComponents },
                    { "compatibility_components", compatibilityComponents },
                    { "tints", tintCount },
                    { "livery_tints", liveryTints },
                    { "rows", _workbenchRows.Count }
                });
        }

        private bool TryPopulateWorkbenchRowsFromStorefrontCache()
        {
            if (!_shop.TryGetCachedWeaponCustomizationCatalog(
                    _workbenchWeapon,
                    out IReadOnlyList<DetachedWorkbenchRow> cached) ||
                cached == null)
                return false;

            _workbenchRows.Clear();
            foreach (DetachedWorkbenchRow row in cached)
            {
                if (row == null) continue;
                WorkbenchRowKind kind;
                switch ((row.Kind ?? "").Trim().ToLowerInvariant())
                {
                    case "ammo":
                        kind = WorkbenchRowKind.Ammo;
                        break;
                    case "component":
                        kind = WorkbenchRowKind.Component;
                        break;
                    case "component_remove":
                        kind = WorkbenchRowKind.ComponentRemove;
                        break;
                    case "component_tint":
                        kind = WorkbenchRowKind.ComponentTint;
                        break;
                    case "tint":
                        kind = WorkbenchRowKind.Tint;
                        break;
                    default:
                        continue;
                }
                _workbenchRows.Add(new WorkbenchRow
                {
                    Kind = kind,
                    Label = row.Label ?? "Weapon option",
                    BaseLabel = row.Label ?? "Weapon option",
                    Detail = row.Detail ?? "",
                    Price = Math.Max(0, row.Price),
                    ComponentHash = row.ComponentHash,
                    AttachmentPoint = row.AttachmentPoint,
                    Tint = row.Tint,
                    SupportsLiveryTint = row.SupportsLiveryTint,
                });
            }
            return true;
        }

        private bool AddWorkbenchComponent(HashSet<int> seen, int weaponHash,
            int componentHash, int attachmentPoint, string pointName, string label)
        {
            if (seen.Contains(componentHash) || !Function.Call<bool>(
                    Hash.DOES_WEAPON_TAKE_WEAPON_COMPONENT,
                    weaponHash, componentHash)) return false;
            seen.Add(componentHash);
            label = LocalizeComponentLabel(label, componentHash);
            string detail = FriendlyAttachmentPoint(pointName, label);
            if (WeaponCustomizationPolicy.IsOpaqueComponentLabel(label))
                label = WeaponCustomizationPolicy.FallbackComponentLabel(detail);
            string baseLabel = label;
            label = DisambiguateWorkbenchComponentLabel(baseLabel, detail);
            bool livery = IsLiveryComponent(pointName, label, detail);
            _workbenchRows.Add(new WorkbenchRow {
                Kind = WorkbenchRowKind.Component,
                Label = label,
                BaseLabel = baseLabel,
                Detail = detail,
                Price = WeaponComponentDefaults.IsDefault(weaponHash, componentHash)
                    ? 0 : WeaponCustomizationPolicy.ComponentPrice(detail, label),
                ComponentHash = componentHash,
                AttachmentPoint = attachmentPoint,
                SupportsLiveryTint = livery,
            });
            return true;
        }

        private string DisambiguateWorkbenchComponentLabel(
            string label, string detail)
        {
            var matches = new List<WorkbenchRow>();
            foreach (WorkbenchRow row in _workbenchRows)
            {
                if (row.Kind == WorkbenchRowKind.Component &&
                    string.Equals(row.BaseLabel, label,
                        StringComparison.OrdinalIgnoreCase) &&
                    string.Equals(row.Detail, detail,
                        StringComparison.OrdinalIgnoreCase))
                    matches.Add(row);
            }
            if (matches.Count == 0) return label;
            if (matches.Count == 1)
                matches[0].Label = label + " 1";
            return label + " " + (matches.Count + 1);
        }

        private int AddActiveLiveryTintRows(Ped ped, int weaponHash)
        {
            WorkbenchRow activeLivery = null;
            foreach (WorkbenchRow candidate in _workbenchRows)
            {
                if (candidate.Kind != WorkbenchRowKind.Component ||
                    !candidate.SupportsLiveryTint) continue;
                int active = CharacterInventory.GetActiveWeaponComponent(
                    _workbenchWeapon, candidate.AttachmentPoint);
                if (active == candidate.ComponentHash || Function.Call<bool>(
                        Hash.HAS_PED_GOT_WEAPON_COMPONENT, ped.Handle,
                        weaponHash, candidate.ComponentHash))
                {
                    activeLivery = candidate;
                    break;
                }
            }
            if (activeLivery == null) return 0;

            for (int tint = 0; tint < WORKBENCH_LIVERY_TINT_COUNT; tint++)
            {
                _workbenchRows.Add(new WorkbenchRow {
                    Kind = WorkbenchRowKind.ComponentTint,
                    Label = LiveryTintName(tint),
                    Detail = activeLivery.Label + " color",
                    Price = WeaponCustomizationPolicy.ComponentTintPrice(tint),
                    ComponentHash = activeLivery.ComponentHash,
                    AttachmentPoint = activeLivery.AttachmentPoint,
                    Tint = tint,
                });
            }
            return WORKBENCH_LIVERY_TINT_COUNT;
        }

        private static bool IsLiveryComponent(
            string pointName, string label, string detail)
        {
            string text = ((pointName ?? "") + " " + (label ?? "") +
                " " + (detail ?? "")).ToLowerInvariant();
            return text.Contains("camo") || text.Contains("livery") ||
                (text.Contains("gunroot") && text.Contains("finish"));
        }

        private unsafe int AddRuntimeDlcComponents(
            int weaponHash, HashSet<int> seen, bool storyModeList)
        {
            Hash weaponCountNative = storyModeList
                ? Hash.GET_NUM_DLC_WEAPONS_SP : Hash.GET_NUM_DLC_WEAPONS;
            Hash weaponDataNative = storyModeList
                ? Hash.GET_DLC_WEAPON_DATA_SP : Hash.GET_DLC_WEAPON_DATA;
            Hash componentCountNative = storyModeList
                ? Hash.GET_NUM_DLC_WEAPON_COMPONENTS_SP
                : Hash.GET_NUM_DLC_WEAPON_COMPONENTS;
            Hash componentDataNative = storyModeList
                ? Hash.GET_DLC_WEAPON_COMPONENT_DATA_SP
                : Hash.GET_DLC_WEAPON_COMPONENT_DATA;
            int added = 0;
            int weaponDataSize = Marshal.SizeOf(typeof(RuntimeDlcWeaponData));
            int componentDataSize = Marshal.SizeOf(
                typeof(RuntimeDlcWeaponComponentData));
            IntPtr weaponBuffer = Marshal.AllocHGlobal(weaponDataSize);
            IntPtr componentBuffer = Marshal.AllocHGlobal(componentDataSize);
            try
            {
                int weaponCount = Math.Max(0,
                    Function.Call<int>(weaponCountNative));
                for (int weaponIndex = 0;
                    weaponIndex < weaponCount; weaponIndex++)
                {
                    ClearNativeBuffer(weaponBuffer, weaponDataSize);
                    if (!Function.Call<bool>(weaponDataNative,
                            weaponIndex, weaponBuffer)) continue;
                    RuntimeDlcWeaponData weaponData =
                        Marshal.PtrToStructure<RuntimeDlcWeaponData>(
                            weaponBuffer);
                    if (weaponData.WeaponHash != weaponHash) continue;

                    int componentCount = Math.Max(0, Function.Call<int>(
                        componentCountNative, weaponIndex));
                    for (int componentIndex = 0;
                        componentIndex < componentCount; componentIndex++)
                    {
                        ClearNativeBuffer(componentBuffer, componentDataSize);
                        if (!Function.Call<bool>(componentDataNative,
                                weaponIndex, componentIndex, componentBuffer))
                            continue;
                        RuntimeDlcWeaponComponentData componentData =
                            Marshal.PtrToStructure<
                                RuntimeDlcWeaponComponentData>(componentBuffer);
                        if (componentData.ComponentHash == 0) continue;
                        string point = ((WeaponAttachmentPoint)
                            componentData.AttachmentPoint).ToString();
                        if (AddWorkbenchComponent(seen, weaponHash,
                                componentData.ComponentHash,
                                componentData.AttachmentPoint, point,
                                componentData.DisplayName)) added++;
                    }
                }
            }
            catch (Exception ex)
            {
                // DLC natives differ between game editions. The workbench can
                // still use SHVDN's live component catalog if this optional
                // enumeration path is unavailable, so fail this source only.
                ClientLog.Error("GBAY",
                    storyModeList
                        ? "weapon_workbench_story_dlc_catalog_failed"
                        : "weapon_workbench_dlc_catalog_failed",
                    ex);
            }
            finally
            {
                Marshal.FreeHGlobal(componentBuffer);
                Marshal.FreeHGlobal(weaponBuffer);
            }
            return added;
        }

        private static unsafe void ClearNativeBuffer(IntPtr buffer, int size)
        {
            byte* bytes = (byte*)buffer.ToPointer();
            for (int index = 0; index < size; index++) bytes[index] = 0;
        }

        private static string LocalizeComponentLabel(string value, int hash)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                string localized = Game.GetLocalizedString(value);
                if (!string.IsNullOrWhiteSpace(localized) &&
                    !localized.Equals("NULL", StringComparison.OrdinalIgnoreCase))
                    return localized;
                if (!value.StartsWith("WCT_", StringComparison.OrdinalIgnoreCase))
                    return value;
            }
            return $"Component 0x{unchecked((uint)hash):X8}";
        }

        private static int InferCompatibilityAttachmentPoint(string name)
        {
            return Game.GenerateHash("GBAY_COMPONENT_SLOT_" +
                FriendlyCompatibilityPoint(name).ToUpperInvariant());
        }

        private static string FriendlyCompatibilityPoint(string name)
        {
            string value = (name ?? "").ToLowerInvariant();
            if (value.Contains("clip") || value.Contains("mag")) return "Magazine";
            if (value.Contains("scope") || value.Contains("optic")) return "Optic";
            if (value.Contains("supp") || value.Contains("muzzle")) return "Muzzle";
            if (value.Contains("flash") || value.Contains("laser")) return "Flashlight / laser";
            if (value.Contains("grip")) return "Foregrip";
            if (value.Contains("barrel")) return "Barrel";
            if (value.Contains("camo") || value.Contains("livery") ||
                value.Contains("varmod") || value.Contains("finish"))
                return "Finish / livery";
            return "Weapon upgrade";
        }

        private static string HumanizeComponentName(string value)
        {
            if (string.IsNullOrWhiteSpace(value)) return "Weapon component";
            var result = new System.Text.StringBuilder(value.Length + 8);
            for (int i = 0; i < value.Length; i++)
            {
                char current = value[i];
                if (i > 0 && char.IsUpper(current) &&
                    !char.IsUpper(value[i - 1])) result.Append(' ');
                result.Append(current);
            }
            return result.ToString();
        }

        private static string FriendlyAttachmentPoint(
            string value, string label = "")
        {
            if (string.IsNullOrWhiteSpace(value)) return "Weapon upgrade";
            string point = value.ToLowerInvariant();
            string description = (label ?? "").ToLowerInvariant();
            if (description.Contains("camo") ||
                description.Contains("livery") ||
                description.Contains("finish")) return "Finish / livery";
            if (point.Contains("gunroot") || point.Contains("receiver")) return "Receiver";
            if (point.Contains("clip") || point.Contains("magazine")) return "Magazine";
            if (point.Contains("scop") || point.Contains("optic")) return "Optic";
            if (point.Contains("supp") || point.Contains("muzzle")) return "Muzzle";
            if (point.Contains("flsh") || point.Contains("flash") ||
                point.Contains("laser")) return "Flashlight / laser";
            if (point.Contains("grip")) return "Foregrip";
            if (point.Contains("barrel")) return "Barrel";
            if (point.Contains("slide")) return "Slide finish";
            return value;
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

        private static string LiveryTintName(int tint)
        {
            string localized = Game.GetLocalizedString($"WCT_C_TINT_{tint}");
            if (!string.IsNullOrWhiteSpace(localized) &&
                !string.Equals(localized, "NULL",
                    StringComparison.OrdinalIgnoreCase) &&
                !localized.StartsWith("WCT_", StringComparison.OrdinalIgnoreCase))
                return localized;
            return tint == 0 ? "Default livery color" :
                $"Livery color {tint + 1}";
        }

        private void CreateWeaponCamera(Ped previewPed, bool smooth)
        {
            try
            {
                Vector3 target = _workbenchCameraFocusInitialized
                    ? _workbenchCameraFocus
                    : GetWeaponFocusPoint(GetSelectedWorkbenchRow());
                float radians = _workbenchCameraAngle * (float)Math.PI / 180f;
                // Camera placement is based on the immutable entry transform,
                // not the live ped axes. The aiming task may rotate upper-body
                // bones, but it can no longer orbit the camera or pull it
                // through the character model.
                // Keep every option on one camera rail. Selection changes pan
                // the focus point over the weapon without also zooming or
                // orbiting, which avoids the front/back flips visible when a
                // live aiming animation moves the weapon entity.
                _workbenchCameraPositionTarget = GetWeaponCameraPosition(
                    previewPed, radians);

                // Keep one camera alive for the entire workbench session.
                // Recreating and interpolating camera objects while the user
                // scrolls is what caused the visible snaps and occasional
                // return to the gameplay camera in the captured footage.
                if (_weaponCamera != null && _weaponCamera.Exists())
                {
                    if (!smooth || !_workbenchCameraPositionInitialized)
                    {
                        _workbenchCameraPosition =
                            _workbenchCameraPositionTarget;
                        _workbenchCameraPositionInitialized = true;
                        _weaponCamera.Position = _workbenchCameraPosition;
                        PointWeaponCameraAtFocus(_weaponCamera, target);
                    }
                    EnsureWeaponCameraRendering(false);
                    return;
                }

                _workbenchCameraPosition = _workbenchCameraPositionTarget;
                _workbenchCameraPositionInitialized = true;
                _weaponCamera = World.CreateCamera(
                    _workbenchCameraPosition, Vector3.Zero, 34f);
                PointWeaponCameraAtFocus(_weaponCamera, target);

                // Activate explicitly instead of relying solely on the World
                // property wrapper. Enhanced builds can leave a valid script
                // camera non-rendering when another gameplay camera just ended.
                Function.Call(Hash.SET_CAM_ACTIVE,
                    _weaponCamera.Handle, true);
                Function.Call(Hash.RENDER_SCRIPT_CAMS,
                    true, false, 0, true, false, 0);
                _workbenchCameraLastRepairAt = Game.GameTime;
                ClientLog.Info("GBAY", "weapon_camera_activated",
                    new Dictionary<string, object> {
                        { "camera", _weaponCamera.Handle },
                        { "x", _workbenchCameraPosition.X },
                        { "y", _workbenchCameraPosition.Y },
                        { "z", _workbenchCameraPosition.Z },
                        { "fov", 34f }
                    });
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "weapon_camera_create_failed", ex);
            }
        }

        /// <summary>
        /// Reuses the same live SDK/DLC/component discovery as the established
        /// workbench without entering its world-space preview or camera path.
        /// </summary>
        internal static IReadOnlyList<DetachedWorkbenchRow>
            DescribeDetachedWeaponCustomization(
                GbayShop shop, string weaponName,
                bool allowStorefrontCache = true)
        {
            if (shop == null || string.IsNullOrWhiteSpace(weaponName))
                return Array.Empty<DetachedWorkbenchRow>();
            var catalog = new GbayBrowser(shop)
            {
                _workbenchWeapon = weaponName.Trim().ToUpperInvariant(),
            };
            catalog.BuildWorkbenchRows(allowStorefrontCache);
            var result = new List<DetachedWorkbenchRow>(
                catalog._workbenchRows.Count);
            foreach (WorkbenchRow row in catalog._workbenchRows)
            {
                string kind = row.Kind == WorkbenchRowKind.Ammo ? "ammo"
                    : row.Kind == WorkbenchRowKind.Component ? "component"
                    : row.Kind == WorkbenchRowKind.ComponentRemove ? "component_remove"
                    : row.Kind == WorkbenchRowKind.ComponentTint
                        ? "component_tint" : "tint";
                result.Add(new DetachedWorkbenchRow
                {
                    Kind = kind,
                    Label = row.Label ?? "Weapon option",
                    Detail = row.Detail ?? "",
                    Price = Math.Max(0, row.Price),
                    ComponentHash = row.ComponentHash,
                    AttachmentPoint = row.AttachmentPoint,
                    Tint = row.Tint,
                    Owned = catalog.IsWorkbenchRowOwned(row),
                    Active = catalog.IsWorkbenchRowActive(row),
                    SupportsLiveryTint = row.SupportsLiveryTint,
                });
            }
            return result;
        }

        private Vector3 GetWeaponCameraPosition(Ped previewPed, float radians)
        {
            const float distance = 2.42f;
            Vector3 subject = previewPed != null && previewPed.Exists()
                ? previewPed.Position : _workbenchAnchorPosition;
            Vector3 bodyFocus = subject + new Vector3(0f, 0f, 1.30f);
            return bodyFocus +
                _workbenchAnchorForward *
                    (distance * (float)Math.Cos(radians)) +
                _workbenchAnchorRight *
                    (distance * (float)Math.Sin(radians)) +
                new Vector3(0f, 0f, 0.16f);
        }

        private void UpdateWeaponCamera(Ped ped, float delta)
        {
            if (Math.Abs(delta) < 0.01f) return;
            _workbenchCameraAngle += delta;
            // Keep rotation on the front hemisphere. Rear angles obscure the
            // weapon with the player's torso and are never useful here.
            if (_workbenchCameraAngle > 52f) _workbenchCameraAngle = 52f;
            if (_workbenchCameraAngle < -52f) _workbenchCameraAngle = -52f;
            float radians = _workbenchCameraAngle * (float)Math.PI / 180f;
            _workbenchCameraPositionTarget = GetWeaponCameraPosition(
                _workbenchDummy, radians);
            CreateWeaponCamera(_workbenchDummy, true);
        }

        private WorkbenchRow GetSelectedWorkbenchRow()
        {
            return _workbenchRows.Count > 0
                ? _workbenchRows[Math.Max(0, Math.Min(
                    _workbenchSelected, _workbenchRows.Count - 1))]
                : null;
        }

        private static void PointWeaponCameraAtFocus(Camera camera, Vector3 focus)
        {
            if (camera == null || !camera.Exists()) return;
            Vector3 view = focus - camera.Position;
            float horizontal = (float)Math.Sqrt(
                view.X * view.X + view.Y * view.Y);
            Vector3 screenRight = horizontal > 0.001f
                ? new Vector3(view.Y / horizontal,
                    -view.X / horizontal, 0f)
                : new Vector3(1f, 0f, 0f);
            // Aim left of the subject so the weapon and character occupy the
            // unobstructed right side beside the workbench panel.
            Vector3 composedAim = focus - screenRight * 0.34f +
                new Vector3(0f, 0f, 0.03f);
            Function.Call(Hash.POINT_CAM_AT_COORD, camera.Handle,
                composedAim.X, composedAim.Y, composedAim.Z);
        }

        private void SetWeaponCameraFocusTarget()
        {
            _workbenchCameraFocusTarget = GetWeaponFocusPoint(
                GetSelectedWorkbenchRow());
            if (!_workbenchCameraFocusInitialized)
            {
                _workbenchCameraFocus = _workbenchCameraFocusTarget;
                _workbenchCameraFocusInitialized = true;
            }
            _workbenchCameraFocusUpdatedAt = Game.GameTime;
        }

        private void UpdateWeaponCameraFocus()
        {
            if (!_workbenchCameraFocusInitialized) return;
            if (_weaponCamera == null || !_weaponCamera.Exists())
            {
                CreateWeaponCamera(_workbenchDummy, false);
                if (_weaponCamera == null || !_weaponCamera.Exists()) return;
            }
            int now = Game.GameTime;
            int elapsed = Math.Max(1, Math.Min(50,
                unchecked(now - _workbenchCameraFocusUpdatedAt)));
            _workbenchCameraFocusUpdatedAt = now;
            float amount = 1f - (float)Math.Exp(-elapsed / 150f);
            _workbenchCameraFocus +=
                (_workbenchCameraFocusTarget - _workbenchCameraFocus) * amount;
            if (_workbenchCameraPositionInitialized)
            {
                float positionAmount = 1f -
                    (float)Math.Exp(-elapsed / 260f);
                _workbenchCameraPosition +=
                    (_workbenchCameraPositionTarget -
                        _workbenchCameraPosition) * positionAmount;
                _weaponCamera.Position = _workbenchCameraPosition;
            }
            PointWeaponCameraAtFocus(_weaponCamera, _workbenchCameraFocus);
            EnsureWeaponCameraRendering(true);
        }

        private void EnsureWeaponCameraRendering(bool repairIfNeeded)
        {
            if (_weaponCamera == null || !_weaponCamera.Exists()) return;
            bool rendering = Function.Call<bool>(Hash.IS_CAM_RENDERING,
                _weaponCamera.Handle);
            if (rendering || !repairIfNeeded) return;
            int now = Game.GameTime;
            if (unchecked(now - _workbenchCameraLastRepairAt) < 500) return;
            _workbenchCameraLastRepairAt = now;
            Function.Call(Hash.SET_CAM_ACTIVE, _weaponCamera.Handle, true);
            Function.Call(Hash.RENDER_SCRIPT_CAMS,
                true, false, 0, true, false, 0);
            ClientLog.Warn("GBAY", "weapon_camera_render_repaired",
                new Dictionary<string, object> {
                    { "camera", _weaponCamera.Handle },
                    { "weapon", _workbenchWeapon }
                });
        }

        private Vector3 GetWeaponFocusPoint(WorkbenchRow row)
        {
            // Track a filtered live weapon center, then make only small,
            // bounded attachment-point pans around it. This keeps the actor in
            // frame while still showing where each upgrade is fitted.
            Vector3 center = _workbenchWeaponCenterInitialized
                ? _workbenchWeaponCenter
                : _workbenchAnchorPosition +
                    _workbenchAnchorForward * 0.24f +
                    _workbenchAnchorRight * 0.08f +
                    new Vector3(0f, 0f, 1.35f);
            float forward = 0f;
            float right = 0f;
            float vertical = 0f;
            if (row != null)
            {
                string point = (row.Detail ?? "").ToLowerInvariant();
                if (point.Contains("muzzle") || point.Contains("supp") ||
                    point.Contains("barrel"))
                    forward += 0.18f;
                else if (point.Contains("optic") || point.Contains("scop"))
                    vertical = 0.055f;
                else if (point.Contains("magazine") || point.Contains("clip"))
                {
                    forward -= 0.03f; vertical = -0.085f;
                }
                else if (point.Contains("grip"))
                {
                    forward += 0.03f; vertical = -0.060f;
                }
                else if (point.Contains("flashlight") || point.Contains("laser"))
                {
                    forward += 0.09f; vertical = -0.025f;
                }
            }
            return center +
                _workbenchAnchorForward * forward +
                _workbenchAnchorRight * right +
                new Vector3(0f, 0f, vertical);
        }

        private void DrawWeaponCustomization(FrameInput input)
        {
            Ped ped = Game.Player.Character;
            if (ped == null || !ped.Exists()) { Close(); return; }
            if (!MaintainWeaponWorkbenchPose(ped))
            {
                EndWeaponCustomization();
                _state = BrowserState.WeaponBrowser;
                GbayRenderer.PlayError();
                GTA.UI.Screen.ShowSubtitle(
                    "~r~The weapon preview was interrupted and closed safely.",
                    3500);
                return;
            }
            UpdateWeaponCameraFocus();
            if (input.CategoryPrev) UpdateWeaponCamera(ped, -7f);
            if (input.CategoryNext) UpdateWeaponCamera(ped, 7f);

            const float panelLeft = 0.018f;
            const float panelRight = 0.405f;
            const float panelWidth = panelRight - panelLeft;
            const float panelCenter = (panelLeft + panelRight) / 2f;
            GbayRenderer.DrawElevatedPanel(panelCenter, 0.48f,
                panelWidth, 0.90f, Color.FromArgb(249, 240, 244, 241));
            GbayRenderer.DrawRect(panelCenter, 0.075f,
                panelWidth, 0.09f, GbayRenderer.HeaderBg);
            GbayRenderer.DrawHeaderAccent(panelCenter, 0.120f, panelWidth);
            GbayRenderer.DrawTitleBadge("CUSTOMIZE", panelLeft + 0.09f, 0.075f,
                0.14f, 0.045f, 0.31f);
            GbayRenderer.DrawTextFit(_workbenchDisplayName, panelRight - 0.018f,
                0.058f, 0.31f, 0.19f, 0.16f, GbayRenderer.HeaderText,
                GbayRenderer.FONT_CHALET, false, false, true);
            GbayRenderer.DrawTextFit(
                $"WEAPON WORKBENCH   {_workbenchRows.Count} OPTIONS",
                panelLeft + 0.016f, 0.132f, 0.22f, 0.17f,
                panelWidth - 0.032f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED);

            _workbenchHover = -1;
            const float firstY = 0.185f;
            const float rowH = 0.085f;
            int count = Math.Min(WORKBENCH_VISIBLE_ROWS,
                Math.Max(0, _workbenchRows.Count - _workbenchScroll));
            for (int visible = 0; visible < count; visible++)
            {
                int index = _workbenchScroll + visible;
                WorkbenchRow row = _workbenchRows[index];
                float y = firstY + visible * rowH;
                bool selected = index == _workbenchSelected;
                bool hover = GbayRenderer.HitTest(
                    input.MouseX, input.MouseY, panelCenter, y,
                    panelWidth - 0.025f, rowH - 0.006f);
                if (hover) _workbenchHover = index;
                bool owned = IsWorkbenchRowOwned(row);
                bool active = IsWorkbenchRowActive(row);
                bool equipped = active && row.Kind != WorkbenchRowKind.Ammo;
                bool fullAmmo = active && row.Kind == WorkbenchRowKind.Ammo;
                GbayRenderer.DrawCatalogCardSurface(panelCenter, y,
                    panelWidth - 0.025f, rowH - 0.006f, selected, hover);
                if (equipped)
                    GbayRenderer.DrawRect(panelLeft + 0.014f, y,
                        0.005f, rowH - 0.014f, GbayRenderer.Success);
                GbayRenderer.DrawTextFit(row.Label, panelLeft + 0.018f, y - 0.020f,
                    0.34f, 0.25f, 0.245f, GbayRenderer.TextDark,
                    GbayRenderer.FONT_CHALET);
                string status = equipped ? "EQUIPPED" : fullAmmo ? "FULL"
                    : owned ? "OWNED"
                    : row.Price <= 0 || _shop.FreeMode ? "FREE" : $"${row.Price:N0}";
                Color statusFill = equipped ? GbayRenderer.Success
                    : fullAmmo ? GbayRenderer.AccentSoft
                    : owned ? GbayRenderer.AccentSoft : GbayRenderer.FooterBg;
                Color statusText = equipped ? GbayRenderer.TextWhite
                    : fullAmmo ? GbayRenderer.Success
                    : owned ? GbayRenderer.Success
                    : row.Price <= 0 || _shop.FreeMode
                        ? GbayRenderer.TextDim : GbayRenderer.TextPrice;
                GbayRenderer.DrawStatusPill(status,
                    panelRight - 0.071f, y - 0.010f, 0.106f,
                    statusFill, statusText);
                GbayRenderer.DrawTextFit(row.Detail, panelLeft + 0.018f, y + 0.006f,
                    0.26f, 0.20f, 0.240f, GbayRenderer.TextDim,
                    GbayRenderer.FONT_CONDENSED);
            }

            if (_workbenchRows.Count > WORKBENCH_VISIBLE_ROWS)
            {
                float trackTop = firstY - rowH * 0.47f;
                float trackH = rowH * WORKBENCH_VISIBLE_ROWS - 0.006f;
                float visibleRatio = Math.Min(1f,
                    WORKBENCH_VISIBLE_ROWS / (float)_workbenchRows.Count);
                float thumbH = Math.Max(0.045f, trackH * visibleRatio);
                float maxScroll = Math.Max(1,
                    _workbenchRows.Count - WORKBENCH_VISIBLE_ROWS);
                float progress = _workbenchScroll / (float)maxScroll;
                float thumbY = trackTop + thumbH * 0.5f +
                    (trackH - thumbH) * progress;
                GbayRenderer.DrawRect(panelRight - 0.006f,
                    trackTop + trackH * 0.5f, 0.003f, trackH,
                    GbayRenderer.Divider);
                GbayRenderer.DrawRect(panelRight - 0.006f,
                    thumbY, 0.005f, thumbH, GbayRenderer.Accent);
            }

            if (_workbenchRows.Count == 0)
                GbayRenderer.DrawEmptyState("NO UPGRADES REPORTED",
                    "This game build did not expose compatible components.",
                    panelCenter, 0.43f, panelWidth - 0.045f);

            string focus = _workbenchRows.Count > 0
                ? _workbenchRows[_workbenchSelected].Detail.ToUpperInvariant()
                : "WEAPON";
            GbayRenderer.DrawBorderedRect(panelCenter, 0.812f,
                panelWidth - 0.028f, 0.052f, GbayRenderer.CardBg,
                GbayRenderer.Divider, 0.001f);
            GbayRenderer.DrawRect(panelLeft + 0.017f, 0.812f,
                0.005f, 0.045f, GbayRenderer.Accent);
            GbayRenderer.DrawTextFit("CAMERA FOCUS  /  " + focus,
                panelLeft + 0.026f, 0.799f, 0.22f, 0.16f,
                panelWidth - 0.052f, GbayRenderer.TextDim,
                GbayRenderer.FONT_CONDENSED);
            DrawControlHint("A BUY / EQUIP   LT/RT ROTATE   B OWNED WEAPONS",
                panelRight - 0.012f, 0.875f, panelWidth - 0.024f, 0.045f);
            HandleWeaponCustomizationInput(input);
        }

        private bool IsWorkbenchRowOwned(WorkbenchRow row)
        {
            if (row.Kind == WorkbenchRowKind.ComponentRemove) return true;
            if (row.Kind == WorkbenchRowKind.Ammo) return false;
            if (row.Kind == WorkbenchRowKind.Component)
                return WeaponComponentDefaults.IsDefault(
                    CharacterInventory.GetWeaponHash(_workbenchWeapon), row.ComponentHash) ||
                    CharacterInventory.IsWeaponComponentOwned(
                    _workbenchWeapon, row.ComponentHash) || IsWorkbenchRowActive(row);
            if (row.Kind == WorkbenchRowKind.ComponentTint)
                return CharacterInventory.IsWeaponComponentTintOwned(
                    _workbenchWeapon, row.ComponentHash, row.Tint);
            return CharacterInventory.IsWeaponTintOwned(
                _workbenchWeapon, row.Tint);
        }

        private bool IsWorkbenchRowActive(WorkbenchRow row)
        {
            if (row.Kind == WorkbenchRowKind.ComponentRemove) return false;
            if (row.Kind == WorkbenchRowKind.Ammo)
            {
                int rounds;
                return _shop.GetAmmoRefillInfo(_workbenchWeapon, out rounds) == 0 && rounds == 0;
            }
            Ped player = Game.Player.Character;
            int weaponHash = CharacterInventory.GetWeaponHash(_workbenchWeapon);
            if (row.Kind == WorkbenchRowKind.Component)
            {
                bool liveActive = HasLiveWorkbenchComponent(
                    player, weaponHash, row.ComponentHash);
                bool anyLiveInFamily = false;
                foreach (WorkbenchRow candidate in _workbenchRows)
                {
                    if (candidate.Kind == WorkbenchRowKind.Component &&
                        SameWorkbenchComponentFamily(row, candidate) &&
                        HasLiveWorkbenchComponent(player, weaponHash,
                            candidate.ComponentHash))
                    {
                        anyLiveInFamily = true;
                        break;
                    }
                }
                int savedActive = CharacterInventory.GetActiveWeaponComponent(
                    _workbenchWeapon, row.AttachmentPoint);
                return WeaponCustomizationPolicy.IsComponentEquipped(
                    row.ComponentHash, savedActive, liveActive,
                    anyLiveInFamily,
                    WeaponCustomizationPolicy.IsDefaultComponentLabel(
                        row.BaseLabel ?? row.Label));
            }
            if (row.Kind == WorkbenchRowKind.ComponentTint)
            {
                if (HasLiveWorkbenchComponent(
                        player, weaponHash, row.ComponentHash))
                    return Function.Call<int>(
                        Hash.GET_PED_WEAPON_COMPONENT_TINT_INDEX,
                        player.Handle, weaponHash,
                        row.ComponentHash) == row.Tint;
                return CharacterInventory.GetActiveWeaponComponentTint(
                    _workbenchWeapon, row.ComponentHash) == row.Tint;
            }
            if (player != null && player.Exists() && Function.Call<bool>(
                    Hash.HAS_PED_GOT_WEAPON, player.Handle,
                    weaponHash, false))
                return Function.Call<int>(Hash.GET_PED_WEAPON_TINT_INDEX,
                    player.Handle, weaponHash) == row.Tint;
            return CharacterInventory.GetActiveWeaponTint(
                _workbenchWeapon) == row.Tint;
        }

        private static bool HasLiveWorkbenchComponent(
            Ped ped, int weaponHash, int componentHash)
        {
            return ped != null && ped.Exists() &&
                Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON_COMPONENT,
                    ped.Handle, weaponHash, componentHash);
        }

        private static bool SameWorkbenchComponentFamily(
            WorkbenchRow left, WorkbenchRow right)
        {
            if (left == null || right == null) return false;
            if (left.AttachmentPoint != 0 && right.AttachmentPoint != 0)
                return left.AttachmentPoint == right.AttachmentPoint;
            return string.Equals(left.Detail, right.Detail,
                StringComparison.OrdinalIgnoreCase);
        }

        private int GetActiveWorkbenchComponent(
            WorkbenchRow family, Ped ped, int weaponHash)
        {
            foreach (WorkbenchRow candidate in _workbenchRows)
                if (candidate.Kind == WorkbenchRowKind.Component &&
                    SameWorkbenchComponentFamily(family, candidate) &&
                    HasLiveWorkbenchComponent(ped, weaponHash,
                        candidate.ComponentHash))
                    return candidate.ComponentHash;
            return CharacterInventory.GetActiveWeaponComponent(
                _workbenchWeapon, family.AttachmentPoint);
        }

        private void RemoveConflictingWorkbenchComponents(
            WorkbenchRow selected, Ped ped)
        {
            if (selected == null || ped == null || !ped.Exists()) return;
            int weaponHash = CharacterInventory.GetWeaponHash(_workbenchWeapon);
            foreach (WorkbenchRow candidate in _workbenchRows)
            {
                if (candidate.Kind != WorkbenchRowKind.Component ||
                    candidate.ComponentHash == selected.ComponentHash ||
                    !SameWorkbenchComponentFamily(selected, candidate) ||
                    !HasLiveWorkbenchComponent(ped, weaponHash,
                        candidate.ComponentHash)) continue;
                Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED,
                    ped.Handle, weaponHash, candidate.ComponentHash);
            }
        }

        private void HandleWeaponCustomizationInput(FrameInput input)
        {
            if (input.Back || input.MouseRightClick)
            {
                bool returnToReactor = _reactorWeaponWorkbenchHandoff;
                EndWeaponCustomization();
                _reactorWeaponWorkbenchHandoff = false;
                _state = returnToReactor
                    ? BrowserState.Closed : BrowserState.WeaponBrowser;
                GbayRenderer.PlayBack();
                return;
            }
            if (_workbenchRows.Count == 0) return;
            int old = _workbenchSelected;
            bool directionalNavigation = input.DirY != 0 ||
                input.ScrollDelta != 0;
            if (input.DirY < 0) _workbenchSelected = Math.Max(0, _workbenchSelected - 1);
            if (input.DirY > 0) _workbenchSelected = Math.Min(
                _workbenchRows.Count - 1, _workbenchSelected + 1);
            if (input.ScrollDelta < 0) _workbenchSelected = Math.Max(0, _workbenchSelected - 1);
            if (input.ScrollDelta > 0) _workbenchSelected = Math.Min(
                _workbenchRows.Count - 1, _workbenchSelected + 1);
            if (_workbenchHover >= 0 &&
                (input.MouseClick || (!directionalNavigation && input.MouseMoved)))
                _workbenchSelected = _workbenchHover;
            if (_workbenchSelected != old)
            {
                GbayRenderer.PlayNav();
                ApplyWorkbenchPreviewForSelection();
                SetWeaponCameraFocusTarget();
            }
            if (_workbenchSelected < _workbenchScroll) _workbenchScroll = _workbenchSelected;
            if (_workbenchSelected >= _workbenchScroll + WORKBENCH_VISIBLE_ROWS)
                _workbenchScroll = _workbenchSelected - WORKBENCH_VISIBLE_ROWS + 1;

            bool accepted = input.Accept || (input.MouseClick && _workbenchHover >= 0);
            if (!accepted) return;
            WorkbenchRow row = _workbenchRows[_workbenchSelected];
            RestoreWorkbenchPreview();
            bool success;
            if (row.Kind == WorkbenchRowKind.Ammo)
            {
                int refillResult = _shop.ExecuteRefillAmmo(_workbenchWeapon);
                success = refillResult >= 0 ||
                    refillResult == GbayShop.AmmoNotApplicable;
            }
            else if (row.Kind == WorkbenchRowKind.Component)
                success = _shop.ExecuteWeaponComponentPurchase(_workbenchWeapon,
                    row.ComponentHash, row.AttachmentPoint, row.Price);
            else if (row.Kind == WorkbenchRowKind.ComponentRemove)
                success = _shop.ExecuteWeaponComponentRemoval(_workbenchWeapon,
                    row.ComponentHash, row.AttachmentPoint);
            else if (row.Kind == WorkbenchRowKind.ComponentTint)
                success = _shop.ExecuteWeaponComponentTintPurchase(
                    _workbenchWeapon, row.ComponentHash, row.AttachmentPoint,
                    row.Tint, row.Price);
            else
                success = _shop.ExecuteWeaponTintPurchase(
                    _workbenchWeapon, row.Tint, row.Price);
            if (success)
            {
                if (row.Kind == WorkbenchRowKind.Component)
                {
                    RemoveConflictingWorkbenchComponents(
                        row, Game.Player.Character);
                    RemoveConflictingWorkbenchComponents(
                        row, _workbenchDummy);
                }
                bool liveApplied = CharacterInventory.ApplyWeaponCustomizationNow(
                    Game.Player.Character, _workbenchWeapon);
                bool dummyApplied = _workbenchDummy != null &&
                    _workbenchDummy.Exists() &&
                    CharacterInventory.ApplyWeaponCustomizationNow(
                        _workbenchDummy, _workbenchWeapon);
                ClientLog.Info("GBAY", "weapon_customization_live_reapply",
                    new Dictionary<string, object> {
                        { "weapon", _workbenchWeapon },
                        { "verified", liveApplied },
                        { "dummy_verified", dummyApplied }
                    });
                GbayRenderer.PlaySelect();
                BuildWorkbenchRows();
                _workbenchSelected = Math.Min(_workbenchSelected,
                    Math.Max(0, _workbenchRows.Count - 1));
                ApplyWorkbenchPreviewForSelection();
                SetWeaponCameraFocusTarget();
            }
            else
            {
                GbayRenderer.PlayError();
                ApplyWorkbenchPreviewForSelection();
            }
        }

        private bool MaintainWeaponWorkbenchPose(Ped player)
        {
            if (!_workbenchPedFrozen || player == null || !player.Exists() ||
                _workbenchPlayer == null || !_workbenchPlayer.Exists() ||
                player.Handle != _workbenchPlayer.Handle)
                return false;
            int weaponHash = CharacterInventory.GetWeaponHash(
                _workbenchWeapon);
            bool playerOwnsWeapon = Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON,
                player.Handle, weaponHash, false);
            int playerSelectedWeapon = Function.Call<int>(
                Hash.GET_SELECTED_PED_WEAPON, player.Handle);
            if (!GbayWeaponWorkbenchStatePolicy.HasExpectedPlayerWeapon(
                    playerOwnsWeapon, weaponHash, playerSelectedWeapon))
            {
                ClientLog.Warn("GBAY", "weapon_workbench_state_changed",
                    new Dictionary<string, object>
                    {
                        { "weapon", _workbenchWeapon },
                        { "owned", playerOwnsWeapon },
                        { "selected_weapon", playerSelectedWeapon },
                        { "expected_weapon", weaponHash },
                    });
                return false;
            }
            if (_workbenchPlayerRelocated &&
                player.Position.DistanceTo(_workbenchHiddenPlayerPosition) >
                    0.02f)
                Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET, player.Handle,
                    _workbenchHiddenPlayerPosition.X,
                    _workbenchHiddenPlayerPosition.Y,
                    _workbenchHiddenPlayerPosition.Z,
                    false, false, false);
            Function.Call(Hash.SET_ENTITY_COLLISION,
                player.Handle, false, false);
            Function.Call(Hash.SET_LOCAL_PLAYER_INVISIBLE_LOCALLY, true);
            Function.Call(Hash.SET_ENTITY_VISIBLE, player.Handle, false, false);
            Function.Call(Hash.SET_PED_CURRENT_WEAPON_VISIBLE,
                player.Handle, false, false, false, false);

            Ped ped = _workbenchDummy;
            if (ped == null || !ped.Exists()) return false;
            if (ped.Position.DistanceTo(_workbenchAnchorPosition) > 0.005f)
                Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET, ped.Handle,
                    _workbenchAnchorPosition.X, _workbenchAnchorPosition.Y,
                    _workbenchAnchorPosition.Z, false, false, false);
            // The permanent aiming task owns upper-body bones, but it must not
            // be allowed to rotate or rock the character root between options.
            Function.Call(Hash.SET_ENTITY_HEADING,
                ped.Handle, _workbenchPreviousHeading);
            Function.Call(Hash.SET_ENTITY_ANGULAR_VELOCITY,
                ped.Handle, 0f, 0f, 0f);
            Function.Call(Hash.SET_ENTITY_VISIBLE, ped.Handle, true, false);
            Function.Call(Hash.RESET_ENTITY_ALPHA, ped.Handle);
            Function.Call(Hash.SET_ENTITY_ALWAYS_PRERENDER, ped.Handle, true);
            Function.Call(Hash.SET_PED_CURRENT_WEAPON_VISIBLE,
                ped.Handle, true, true, true, false);
            if (Function.Call<int>(Hash.GET_SELECTED_PED_WEAPON,
                    ped.Handle) != weaponHash)
            {
                if (_workbenchWeaponMismatchSince == 0)
                    _workbenchWeaponMismatchSince = Game.GameTime;
                else if (!_workbenchWeaponRecoveryAttempted &&
                    Game.GameTime - _workbenchWeaponMismatchSince >=
                        WORKBENCH_WEAPON_RECOVERY_DELAY_MS)
                {
                    int elapsed = Game.GameTime - _workbenchWeaponMismatchSince;
                    Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                        ped.Handle, weaponHash, true);
                    _workbenchWeaponRecoveryAttempted = true;
                    ClientLog.Info("GBAY", "weapon_workbench_weapon_recovered",
                        new Dictionary<string, object> {
                            { "weapon", _workbenchWeapon },
                            { "mismatch_ms", elapsed }
                        });
                }
                int mismatchMilliseconds = unchecked(
                    Game.GameTime - _workbenchWeaponMismatchSince);
                if (GbayWeaponWorkbenchStatePolicy
                    .ShouldAbortPreviewMismatch(
                        _workbenchWeaponRecoveryAttempted,
                        mismatchMilliseconds))
                {
                    ClientLog.Warn("GBAY",
                        "weapon_workbench_preview_mismatch_aborted",
                        new Dictionary<string, object>
                        {
                            { "weapon", _workbenchWeapon },
                            { "mismatch_ms", mismatchMilliseconds },
                        });
                    return false;
                }
            }
            else
            {
                _workbenchWeaponMismatchSince = 0;
                _workbenchWeaponRecoveryAttempted = false;
            }
            UpdateLiveWeaponCenter(false);
            return true;
        }

        private void UpdateLiveWeaponCenter(bool immediate)
        {
            Ped ped = _workbenchDummy;
            if (ped == null || !ped.Exists()) return;
            Vector3 measured = Vector3.Zero;
            int weaponEntity = Function.Call<int>(
                Hash.GET_CURRENT_PED_WEAPON_ENTITY_INDEX, ped.Handle, 0);
            if (weaponEntity != 0 && Function.Call<bool>(
                    Hash.DOES_ENTITY_EXIST, weaponEntity))
                measured = Function.Call<Vector3>(Hash.GET_ENTITY_COORDS,
                    weaponEntity, false);
            if (measured == Vector3.Zero ||
                measured.DistanceTo(ped.Position) > 2.0f)
            {
                measured = Function.Call<Vector3>(Hash.GET_PED_BONE_COORDS,
                    ped.Handle, 57005, 0f, 0f, 0f) +
                    _workbenchAnchorForward * 0.16f;
            }
            if (measured == Vector3.Zero ||
                measured.DistanceTo(ped.Position) > 2.0f) return;

            if (!_workbenchWeaponCenterInitialized || immediate)
            {
                _workbenchWeaponCenter = measured;
                _workbenchWeaponCenterInitialized = true;
            }
            else
            {
                Vector3 delta = measured - _workbenchWeaponCenter;
                float distance = delta.Length();
                if (distance >= 0.008f && distance <= 0.75f)
                    _workbenchWeaponCenter += delta * 0.12f;
            }
            _workbenchCameraFocusTarget = GetWeaponFocusPoint(
                GetSelectedWorkbenchRow());
        }

        private static float NormalizeHeadingDelta(float value, float target)
        {
            float delta = (value - target) % 360f;
            if (delta > 180f) delta -= 360f;
            if (delta < -180f) delta += 360f;
            return delta;
        }

        private void StartWeaponWorkbenchAim(Ped ped)
        {
            if (ped == null || !ped.Exists() || _workbenchAimTaskStarted) return;
            // A persistent gameplay aiming task produces the correct shouldered
            // pose for pistols, rifles, and heavy weapons. Unlike replaying an
            // upper-body clip every time its status flickers, it does not
            // restart while components or camera focus are changing.
            ped.Task.AimAt(_workbenchAimTarget, -1);
            _workbenchAimTaskStarted = true;
            Function.Call(Hash.SET_ENTITY_HEADING,
                ped.Handle, _workbenchPreviousHeading);
            ClientLog.Info("GBAY", "weapon_workbench_aim_started",
                new Dictionary<string, object> {
                    { "weapon", _workbenchWeapon },
                    { "target_x", _workbenchAimTarget.X },
                    { "target_y", _workbenchAimTarget.Y },
                    { "target_z", _workbenchAimTarget.Z }
                });
        }

        private void ApplyWorkbenchPreviewForSelection()
        {
            RestoreWorkbenchPreview();
            if (_workbenchRows.Count == 0 ||
                _workbenchSelected < 0 ||
                _workbenchSelected >= _workbenchRows.Count) return;
            Ped ped = _workbenchDummy;
            if (ped == null || !ped.Exists()) return;
            WorkbenchRow row = _workbenchRows[_workbenchSelected];
            int weaponHash = CharacterInventory.GetWeaponHash(_workbenchWeapon);
            if (row.Kind == WorkbenchRowKind.ComponentRemove)
            {
                if (HasLiveWorkbenchComponent(ped, weaponHash, row.ComponentHash))
                {
                    Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED,
                        ped.Handle, weaponHash, row.ComponentHash);
                    WeaponComponentDefaults.RestoreAfterRemoval(ped.Handle, weaponHash,
                        row.AttachmentPoint, row.ComponentHash);
                    _workbenchPreviewRemovedComponent = row.ComponentHash;
                }
            }
            else if (row.Kind == WorkbenchRowKind.Component)
            {
                int active = GetActiveWorkbenchComponent(
                    row, ped, weaponHash);
                if (active == row.ComponentHash) return;
                if (active != 0)
                    Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED,
                        ped.Handle, weaponHash, active);
                Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED,
                    ped.Handle, weaponHash, row.ComponentHash);
                _workbenchPreviewComponent = row.ComponentHash;
                _workbenchPreviewRestoreComponent = active;
            }
            else if (row.Kind == WorkbenchRowKind.Tint)
            {
                int activeTint = CharacterInventory.GetActiveWeaponTint(
                    _workbenchWeapon);
                if (activeTint == row.Tint) return;
                Function.Call(Hash.SET_PED_WEAPON_TINT_INDEX,
                    ped.Handle, weaponHash, row.Tint);
                _workbenchPreviewTint = row.Tint;
                _workbenchPreviewRestoreTint = activeTint;
            }
            else if (row.Kind == WorkbenchRowKind.ComponentTint)
            {
                int activeTint = CharacterInventory.GetActiveWeaponComponentTint(
                    _workbenchWeapon, row.ComponentHash);
                if (activeTint == row.Tint) return;
                Function.Call(Hash.SET_PED_WEAPON_COMPONENT_TINT_INDEX,
                    ped.Handle, weaponHash, row.ComponentHash, row.Tint);
                _workbenchPreviewComponentTintComponent = row.ComponentHash;
                _workbenchPreviewComponentTint = row.Tint;
                _workbenchPreviewRestoreComponentTint = activeTint;
            }
        }

        private void RestoreWorkbenchPreview()
        {
            Ped ped = _workbenchDummy;
            if (ped != null && ped.Exists() &&
                !string.IsNullOrWhiteSpace(_workbenchWeapon))
            {
                int weaponHash = CharacterInventory.GetWeaponHash(
                    _workbenchWeapon);
                if (_workbenchPreviewRemovedComponent != 0)
                    Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED,
                        ped.Handle, weaponHash, _workbenchPreviewRemovedComponent);
                if (_workbenchPreviewComponent != 0)
                {
                    Function.Call(Hash.REMOVE_WEAPON_COMPONENT_FROM_PED,
                        ped.Handle, weaponHash, _workbenchPreviewComponent);
                    if (_workbenchPreviewRestoreComponent != 0)
                        Function.Call(Hash.GIVE_WEAPON_COMPONENT_TO_PED,
                            ped.Handle, weaponHash,
                            _workbenchPreviewRestoreComponent);
                }
                if (_workbenchPreviewTint >= 0 &&
                    _workbenchPreviewRestoreTint >= 0)
                    Function.Call(Hash.SET_PED_WEAPON_TINT_INDEX,
                        ped.Handle, weaponHash, _workbenchPreviewRestoreTint);
                if (_workbenchPreviewComponentTintComponent != 0 &&
                    _workbenchPreviewComponentTint >= 0 &&
                    _workbenchPreviewRestoreComponentTint >= 0)
                    Function.Call(Hash.SET_PED_WEAPON_COMPONENT_TINT_INDEX,
                        ped.Handle, weaponHash,
                        _workbenchPreviewComponentTintComponent,
                        _workbenchPreviewRestoreComponentTint);
            }
            _workbenchPreviewComponent = 0;
            _workbenchPreviewRemovedComponent = 0;
            _workbenchPreviewRestoreComponent = 0;
            _workbenchPreviewTint = -1;
            _workbenchPreviewRestoreTint = -1;
            _workbenchPreviewComponentTintComponent = 0;
            _workbenchPreviewComponentTint = -1;
            _workbenchPreviewRestoreComponentTint = -1;
        }

        private void EndWeaponCustomization()
        {
            string customizedWeapon = _workbenchWeapon;
            bool wasActive = _workbenchPedFrozen ||
                !string.IsNullOrWhiteSpace(_workbenchWeapon) ||
                (_workbenchDummy != null && _workbenchDummy.Exists()) ||
                (_weaponCamera != null && _weaponCamera.Exists());
            RestoreWorkbenchPreview();
            if (wasActive)
                World.RenderingCamera = null;
            if (_weaponCamera != null && _weaponCamera.Exists())
            {
                _weaponCamera.Delete();
            }
            _weaponCamera = null;
            DeleteWeaponWorkbenchDummy();
            Ped ped = _workbenchPlayer;
            if (wasActive && ped != null && ped.Exists())
            {
                if (_workbenchPlayerRelocated)
                {
                    Function.Call(Hash.SET_ENTITY_COORDS_NO_OFFSET, ped.Handle,
                        _workbenchAnchorPosition.X,
                        _workbenchAnchorPosition.Y,
                        _workbenchAnchorPosition.Z,
                        false, false, false);
                    Function.Call(Hash.SET_ENTITY_COLLISION,
                        ped.Handle, true, true);
                }
                if (_workbenchPedFrozen)
                    Function.Call(Hash.FREEZE_ENTITY_POSITION,
                        ped.Handle, false);
                Function.Call(Hash.SET_PED_CAN_PLAY_AMBIENT_ANIMS,
                    ped.Handle, true);
                Function.Call(Hash.SET_PED_CAN_PLAY_AMBIENT_BASE_ANIMS,
                    ped.Handle, true);
                Function.Call(Hash.SET_PED_CAN_PLAY_GESTURE_ANIMS,
                    ped.Handle, true);
                ped.Heading = _workbenchPreviousHeading;
                if (_workbenchPreviousWeapon != 0)
                    Function.Call(Hash.SET_CURRENT_PED_WEAPON,
                        ped.Handle, _workbenchPreviousWeapon, true);
                Function.Call(Hash.SET_PED_CURRENT_WEAPON_VISIBLE,
                    ped.Handle, true, true, true, false);
                Function.Call(Hash.SET_ENTITY_VISIBLE, ped.Handle, true, false);
                Function.Call(Hash.RESET_ENTITY_ALPHA, ped.Handle);
                bool liveApplied = CharacterInventory.ApplyWeaponCustomizationNow(
                    ped, customizedWeapon);
                ClientLog.Info("GBAY", "weapon_workbench_exit_reapply",
                    new Dictionary<string, object> {
                        { "weapon", customizedWeapon },
                        { "verified", liveApplied }
                    });
            }
            if (wasActive)
            {
                // These natives affect the local player globally rather than
                // the stored ped handle, so release them even when the
                // original entity disappeared during a loading transition.
                Function.Call(Hash.SET_LOCAL_PLAYER_INVISIBLE_LOCALLY, false);
                Function.Call(Hash.SET_LOCAL_PLAYER_VISIBLE_LOCALLY, true);
            }
            _workbenchPedFrozen = false;
            _workbenchPlayer = null;
            _workbenchPlayerRelocated = false;
            _workbenchHiddenPlayerPosition = Vector3.Zero;
            _workbenchAimTaskStarted = false;
            _workbenchWeaponMismatchSince = 0;
            _workbenchWeaponRecoveryAttempted = false;
            _workbenchAimTarget = Vector3.Zero;
            _workbenchCameraFocus = Vector3.Zero;
            _workbenchCameraFocusTarget = Vector3.Zero;
            _workbenchCameraPosition = Vector3.Zero;
            _workbenchCameraPositionTarget = Vector3.Zero;
            _workbenchCameraFocusUpdatedAt = 0;
            _workbenchCameraLastRepairAt = 0;
            _workbenchCameraFocusInitialized = false;
            _workbenchCameraPositionInitialized = false;
            _workbenchWeaponCenter = Vector3.Zero;
            _workbenchWeaponCenterInitialized = false;
            _workbenchPreviousWeapon = 0;
            _workbenchWeapon = "";
            _workbenchRows.Clear();
            _reactorVisualWeaponPreview = false;
        }

        private void DeleteWeaponWorkbenchDummy()
        {
            Ped dummy = _workbenchDummy;
            _workbenchDummy = null;
            if (dummy == null || !dummy.Exists()) return;
            try
            {
                Function.Call(Hash.SET_ENTITY_ALWAYS_PRERENDER,
                    dummy.Handle, false);
                Function.Call(Hash.FREEZE_ENTITY_POSITION,
                    dummy.Handle, false);
                dummy.Delete();
                if (dummy.Exists()) dummy.MarkAsNoLongerNeeded();
            }
            catch (Exception ex)
            {
                ClientLog.Error("GBAY", "weapon_workbench_dummy_cleanup_failed",
                    ex);
            }
        }
    }
}
