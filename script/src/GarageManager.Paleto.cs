// GarageManager.Paleto.cs -- Paleto Bay ten-car casino penthouse garage.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Text;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    internal static partial class GarageManager
    {
        private const int PALETO_SLOT_COUNT = 10;
        private static readonly GarageDefinition PALETO_GARAGE =
            GarageDefinitions.Paleto;

        internal static Vector3 PALETO_VEHICLE_ENTRANCE_POS =
            new Vector3(-221.9008f, 6252.8020f, 31.4894f);
        private static float PALETO_VEHICLE_ENTRANCE_HEADING = 45f;
        internal static Vector3 PALETO_PED_ENTRANCE_POS =
            new Vector3(-224.5180f, 6244.2620f, 31.4926f);
        private static float PALETO_PED_ENTRANCE_HEADING = 45f;

        // Surveyed elevator landings in vw_dlc_casino_garage. The first is
        // also the pedestrian arrival point; either landing exits to Paleto.
        private static Vector3[] PALETO_INTERIOR_PED_EXITS =
        {
            new Vector3(1295.3110f, 221.1703f, -49.0574f),
            new Vector3(1295.3350f, 260.7359f, -49.0574f),
        };
        private static float[] PALETO_INTERIOR_PED_EXIT_HEADINGS =
        {
            0f,
            180f,
        };
        private const float PALETO_FLOOR_Z = -50.0574f;
        private static Vector3 PALETO_INTERIOR_CENTER =
            new Vector3(1295.0000f, 230.0000f, -50.0000f);
        private const int PALETO_INTERIOR_LOAD_TIMEOUT_MS = 10000;
        private const int PALETO_INTERIOR_FALLBACK_SETTLE_MS = 1500;

        private static string[] PALETO_IPLS =
        {
            "vw_casino_garage",
        };

        // Native Casino Penthouse Garage parking roots and headings from
        // Rockstar's am_mp_casino_apartment script (func_6196/func_6191).
        internal static ParkingSlot[] PaletoSlots =
        {
            new ParkingSlot(1281.4710f, 241.6617f, -49.3467f, 270f, PALETO_FLOOR_Z),
            new ParkingSlot(1281.4710f, 249.7067f, -49.3467f, 270f, PALETO_FLOOR_Z),
            new ParkingSlot(1281.4710f, 257.8117f, -49.3467f, 270f, PALETO_FLOOR_Z),
            new ParkingSlot(1309.3640f, 257.8120f, -49.3470f, 90f, PALETO_FLOOR_Z),
            new ParkingSlot(1309.3640f, 249.7070f, -49.3470f, 90f, PALETO_FLOOR_Z),
            new ParkingSlot(1309.3640f, 241.6620f, -49.3470f, 90f, PALETO_FLOOR_Z),
            new ParkingSlot(1309.3640f, 232.0345f, -49.3470f, 90f, PALETO_FLOOR_Z),
            new ParkingSlot(1295.5920f, 231.7867f, -49.3470f, 211.32f, PALETO_FLOOR_Z),
            new ParkingSlot(1295.5920f, 241.3592f, -49.3470f, 211.32f, PALETO_FLOOR_Z),
            new ParkingSlot(1295.5920f, 249.7942f, -49.3470f, 211.32f, PALETO_FLOOR_Z),
        };

        private static readonly string PALETO_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_paleto_garage.json");
        private static readonly Dictionary<string, List<StoredVehicle>> _paletoStored =
            new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL, new List<StoredVehicle>() },
                { KEY_FRANKLIN, new List<StoredVehicle>() },
                { KEY_TREVOR, new List<StoredVehicle>() },
            };
        private static readonly Vehicle[] _paletoHandles =
            new Vehicle[PALETO_SLOT_COUNT];
        private static bool _isPlayerInPaletoGarage;
        private static bool _paletoMapLeaseHeld;
        private static bool _paletoInitialized;
        private static int _paletoExitCooldownFrames;
        private static Blip _paletoVehicleBlip;
        private static Blip _paletoPedBlip;

        internal static bool IsPlayerInPaletoGarage => _isPlayerInPaletoGarage;
        internal static bool IsPaletoGarageInitialized => _paletoInitialized;

        internal static void InitializePaletoGarage()
        {
            if (_paletoInitialized) return;
            try
            {
                PaletoLoad();
                _paletoVehicleBlip = World.CreateBlip(PALETO_VEHICLE_ENTRANCE_POS);
                _paletoVehicleBlip.Sprite = BlipSprite.Garage;
                _paletoVehicleBlip.Color = CharacterBlipColor();
                _paletoVehicleBlip.Name = "ALLIN1 Paleto Bay Garage (Vehicle)";
                _paletoVehicleBlip.IsShortRange = true;

                _paletoPedBlip = World.CreateBlip(PALETO_PED_ENTRANCE_POS);
                _paletoPedBlip.Sprite = BlipSprite.Garage;
                _paletoPedBlip.Color = CharacterBlipColor();
                _paletoPedBlip.Name = "ALLIN1 Paleto Bay Garage (Pedestrian)";
                _paletoPedBlip.IsShortRange = true;

                int count = 0;
                foreach (List<StoredVehicle> list in _paletoStored.Values)
                    count += list.Count;
                Log($"Paleto Bay Garage initialized ({count} stored vehicles)");
            }
            catch (Exception ex)
            {
                LogException("InitializePaletoGarage", ex);
            }
            _paletoInitialized = true;
        }

        internal static int GetPaletoGarageUsedSlots()
        {
            return _paletoStored.TryGetValue(CharacterKey(), out var list)
                ? list.Count : 0;
        }

        internal static int GetPaletoGarageCapacity() => PALETO_SLOT_COUNT;

        internal static List<StoredVehicle> GetPaletoGarageStoredVehicles()
        {
            return _paletoStored.TryGetValue(CharacterKey(), out var list)
                ? list : new List<StoredVehicle>();
        }

        internal static bool DeliverToPaletoGarage(
            string model, int color1, int color2)
        {
            if (GetGarageSizeTier(model) >= 2) return false;
            if (!_paletoStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (list.Count >= PALETO_SLOT_COUNT) return false;
            int slotIndex = FindEmptyPaletoSlot(list);
            if (slotIndex < 0) return false;

            var stored = new StoredVehicle
            {
                Model = model,
                ModelHash = Game.GenerateHash(model),
                Slot = slotIndex,
                Color1 = color1,
                Color2 = color2,
            };
            list.Add(stored);
            if (_isPlayerInPaletoGarage) SpawnPaletoVehicle(stored);
            if (!PaletoSave())
            {
                list.Remove(stored);
                DeletePaletoHandle(slotIndex);
                return false;
            }
            Log($"DeliverToPaletoGarage: {model} -> slot {slotIndex}");
            return true;
        }

        internal static bool RemovePaletoGarageVehicle(int listIndex)
        {
            if (!_paletoStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (listIndex < 0 || listIndex >= list.Count) return false;
            StoredVehicle stored = list[listIndex];
            DeletePaletoHandle(stored.Slot);
            list.RemoveAt(listIndex);
            if (!PaletoSave())
            {
                list.Insert(listIndex, stored);
                return false;
            }
            Log($"RemovePaletoGarageVehicle: {stored.Model} from slot {stored.Slot}");
            return true;
        }

        internal static void OnPaletoGarageTick()
        {
            if (!_paletoInitialized || _transitionInProgress) return;
            if (_isPlayerInGarage || _isPlayerInFloorGarage ||
                _isPlayerInDavisGarage || _isPlayerInGarmentGarage ||
                _isPlayerInRuralGarage)
                return;
            if (_paletoExitCooldownFrames > 0)
            {
                _paletoExitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;
            Color markerColor;

            if (!_isPlayerInPaletoGarage)
            {
                bool inVehicle = player.IsInVehicle();
                Vector3 activeEntrance = inVehicle
                    ? PALETO_VEHICLE_ENTRANCE_POS
                    : PALETO_PED_ENTRANCE_POS;
                if (!ShouldServiceExteriorMarker(
                        player.Position, activeEntrance))
                    return;
                if (!GbayShop.TryGetCurrentCharacter(out _))
                    return;
                markerColor = CharacterMarkerColor();

                if (!ShouldServiceGarageExterior()) return;
                if (inVehicle)
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        PALETO_VEHICLE_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(2.5f, 2.5f, 1.5f),
                        markerColor);
                    if (player.Position.DistanceTo(PALETO_VEHICLE_ENTRANCE_POS) <
                        ENTER_RADIUS + 0.5f)
                    {
                        Vehicle vehicle = player.CurrentVehicle;
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            PALETO_GARAGE, vehicle);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(PALETO_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Paleto Bay Garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterPaletoGarage();
                        }
                    }
                }
                else
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        PALETO_PED_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(1.5f, 1.5f, 1.2f),
                        markerColor);
                    if (player.Position.DistanceTo(PALETO_PED_ENTRANCE_POS) < ENTER_RADIUS)
                    {
                        GarageEntryDenial denial = EvaluateGarageEntry(PALETO_GARAGE);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(PALETO_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Paleto Bay Garage.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterPaletoGarage();
                        }
                    }
                }
                return;
            }

            markerColor = CharacterMarkerColor();
            EnforcePaletoVehicleState();
            if (player.IsInVehicle())
            {
                GTA.UI.Screen.ShowHelpTextThisFrame(
                    "Press ~INPUT_CONTEXT~ to leave the Paleto Bay Garage with your vehicle.");
                if (Game.IsControlJustPressed(GTA.Control.Context))
                    LeavePaletoGarage();
            }
            else
            {
                bool nearPedExit = false;
                for (int i = 0; i < PALETO_INTERIOR_PED_EXITS.Length; i++)
                {
                    Vector3 exit = PALETO_INTERIOR_PED_EXITS[i];
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        exit - new Vector3(0f, 0f, 1f), Vector3.Zero,
                        new Vector3(0f, 0f, PALETO_INTERIOR_PED_EXIT_HEADINGS[i]),
                        new Vector3(1.5f, 1.5f, 1.2f), markerColor);
                    nearPedExit |= player.Position.DistanceTo(exit) < EXIT_RADIUS;
                }
                if (nearPedExit)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to leave the Paleto Bay Garage.");
                    if (Game.IsControlJustPressed(GTA.Control.Context))
                        LeavePaletoGarage();
                }
            }
        }

        private static void EnterPaletoGarage()
        {
            if (RejectGarageEntry(PALETO_GARAGE)) return;
            if (!DeferredMapContentRuntime.CanBeginOfficialGarageEntry(
                    DeferredMapProperty.Paleto, out _)) return;
            if (!BeginTransition("EnterPaletoGarage")) return;
            bool newLease = !_paletoMapLeaseHeld;
            var transition = CreateScopedInteriorEntryTransition(
                PALETO_GARAGE.Id, () =>
                {
                    _isPlayerInPaletoGarage = false;
                    ClearPaletoHandles();
                    UnloadPaletoInterior(force: newLease);
                });
            try { EnterPaletoGarageCore(transition); }
            catch (Exception ex)
            {
                transition.Fail("entry_exception:" + ex.GetType().Name);
                LogException("EnterPaletoGarage", ex);
                RecoverTransition("EnterPaletoGarage",
                    PALETO_PED_ENTRANCE_POS, PALETO_PED_ENTRANCE_HEADING);
                Script.Wait(100);
                UnloadPaletoInterior();
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Paleto Bay Garage entry failed safely. See ALLIN1_gbay.log.", 4000);
            }
            finally
            {
                transition.Dispose();
                EndTransition("EnterPaletoGarage");
            }
        }

        private static void EnterPaletoGarageCore(OfficialGarageTransitionCoordinator transition)
        {
            Ped player = Game.Player.Character;
            Vehicle rideInToDelete = null;
            string confirmation = null;
            transition.HoldFade(() => BeginGarageBlackTransition("EnterPaletoGarage"));
            transition.Advance(OfficialGarageTransitionPhase.LeaseRequested);
            if (!LoadPaletoInterior(transition))
            {
                transition.Fail("map_activation_failed");
                GTA.UI.Screen.ShowSubtitle(
                    DeferredMapContentRuntime.GarageUnavailableMessage("Paleto Bay"), 4000);
                return;
            }
            transition.Advance(OfficialGarageTransitionPhase.IplReady);
            transition.Advance(OfficialGarageTransitionPhase.InteriorReady);
            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
                    string modelName = ResolveGarageVehicleName(rideIn);
                    if (RejectGarageEntry(
                        PALETO_GARAGE, rideIn, modelName, rideIn.Model.Hash)) return;
                    List<StoredVehicle> list = GetPaletoGarageStoredVehicles();
                    if (list.Count >= PALETO_SLOT_COUNT)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~The Paleto Bay Garage is full.~w~ ({list.Count}/{PALETO_SLOT_COUNT})",
                            3000);
                        return;
                    }
                    int slotIndex = FindEmptyPaletoSlot(list);
                    if (slotIndex < 0) return;
                    StoredVehicle stored = CaptureVehicleState(
                        rideIn, modelName, slotIndex);
                    list.Add(stored);
                    if (!PaletoSave())
                    {
                        list.Remove(stored);
                        UnloadPaletoInterior();
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The vehicle could not be saved.", 3000);
                        return;
                    }
                    string display = RuntimeVehicleCatalog.GetDisplayName(modelName);
                    confirmation = $"~g~{display}~w~ stored in the Paleto Bay Garage.";
                    rideIn.IsPersistent = true;
                    rideInToDelete = rideIn;
                }
            }

            ClearPaletoHandles();
            _isPlayerInPaletoGarage = true;
            player.IsPositionFrozen = true;
            Vector3 pedArrival = PALETO_INTERIOR_PED_EXITS[0];
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                pedArrival.X, pedArrival.Y, pedArrival.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player,
                PALETO_INTERIOR_PED_EXIT_HEADINGS[0]);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            if (rideInToDelete != null && rideInToDelete.Exists())
                rideInToDelete.Delete();
            SpawnPaletoGarageVehicles();
            player.IsPositionFrozen = false;
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            transition.Complete(OfficialGarageTransitionPhase.Occupied,
                () => CompleteGarageBlackTransition("EnterPaletoGarage", player, null,
                    () => IsPlayerInReadyInterior(player), _paletoHandles));
            if (!string.IsNullOrEmpty(confirmation))
                GTA.UI.Screen.ShowSubtitle(confirmation, 4000);
        }

        private static void LeavePaletoGarage()
        {
            if (!BeginTransition("LeavePaletoGarage")) return;
            try { LeavePaletoGarageCore(); }
            catch (Exception ex)
            {
                LogException("LeavePaletoGarage", ex);
                RecoverTransition("LeavePaletoGarage",
                    PALETO_PED_ENTRANCE_POS, PALETO_PED_ENTRANCE_HEADING);
            }
            finally { EndTransition("LeavePaletoGarage"); }
        }

        private static void LeavePaletoGarageCore()
        {
            PaletoUpdateStoredFromLive();
            Ped player = Game.Player.Character;
            Vehicle playerVehicle = null;
            int playerSlot = -1;
            if (player.IsInVehicle())
            {
                Vehicle current = player.CurrentVehicle;
                for (int i = 0; i < _paletoHandles.Length; i++)
                {
                    if (_paletoHandles[i] != null && _paletoHandles[i] == current)
                    {
                        playerVehicle = current;
                        playerSlot = i;
                        _paletoHandles[i] = null;
                        break;
                    }
                }
            }

            ClearPaletoHandles();
            BeginGarageBlackTransition("LeavePaletoGarage");

            player.IsPositionFrozen = true;
            if (playerVehicle != null)
                playerVehicle.IsPositionFrozen = true;

            if (playerVehicle != null)
            {
                List<StoredVehicle> list = GetPaletoGarageStoredVehicles();
                for (int i = list.Count - 1; i >= 0; i--)
                    if (list[i].Slot == playerSlot) { list.RemoveAt(i); break; }
                playerVehicle.IsPersistent = true;
                ReleaseGarageVehicleForDriving(playerVehicle,
                    PALETO_VEHICLE_ENTRANCE_POS,
                    PALETO_VEHICLE_ENTRANCE_HEADING, "Paleto Bay");
            }
            else
            {
                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    PALETO_PED_ENTRANCE_POS.X, PALETO_PED_ENTRANCE_POS.Y,
                    PALETO_PED_ENTRANCE_POS.Z, false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player,
                    PALETO_PED_ENTRANCE_HEADING);
                player.IsPositionFrozen = false;
            }
            Script.Wait(100);
            UnloadPaletoInterior();
            PaletoSave();
            _isPlayerInPaletoGarage = false;
            _paletoExitCooldownFrames = 60;
            CompleteGarageBlackTransition(
                "LeavePaletoGarage", player, playerVehicle,
                () => Function.Call<int>(
                    Hash.GET_INTERIOR_FROM_ENTITY, player) == 0);
        }

        private static bool LoadPaletoInterior(OfficialGarageTransitionCoordinator transition)
        {
            bool focusSet = false;
            try
            {
                if (IsUnsafeGarageTransitionActive())
                {
                    Log("LoadPaletoInterior: blocked during unsafe game transition");
                    return false;
                }
                if (!_paletoMapLeaseHeld)
                {
                    DeferredMapContentResult activation =
                        DeferredMapContentRuntime.TryAcquireInteriorUnderBlackTransition(
                            DeferredMapProperty.Paleto, transition, PALETO_IPLS,
                            PALETO_INTERIOR_LOAD_TIMEOUT_MS);
                    if (!activation.Success)
                    {
                        Log("LoadPaletoInterior: deferred map unavailable " +
                            $"outcome={activation.Outcome} detail={activation.Detail}");
                        return false;
                    }
                    _paletoMapLeaseHeld = true;
                }
                foreach (string ipl in PALETO_IPLS)
                    Function.Call(Hash.REQUEST_IPL, ipl);

                Function.Call(Hash.SET_FOCUS_POS_AND_VEL,
                    PALETO_INTERIOR_CENTER.X, PALETO_INTERIOR_CENTER.Y,
                    PALETO_INTERIOR_CENTER.Z, 0f, 0f, 0f);
                focusSet = true;
                Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                    PALETO_INTERIOR_CENTER.X, PALETO_INTERIOR_CENTER.Y,
                    PALETO_INTERIOR_CENTER.Z);

                int startedAt = Game.GameTime;
                int interior = 0;
                bool interiorReady = false;
                bool iplActive = false;
                int firstResolvedAt = -1;
                while (Game.GameTime - startedAt < PALETO_INTERIOR_LOAD_TIMEOUT_MS)
                {
                    foreach (string ipl in PALETO_IPLS)
                        Function.Call(Hash.REQUEST_IPL, ipl);
                    Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                        PALETO_INTERIOR_CENTER.X, PALETO_INTERIOR_CENTER.Y,
                        PALETO_INTERIOR_CENTER.Z);
                    interior = Function.Call<int>(Hash.GET_INTERIOR_AT_COORDS,
                        PALETO_INTERIOR_CENTER.X, PALETO_INTERIOR_CENTER.Y,
                        PALETO_INTERIOR_CENTER.Z);
                    if (interior != 0)
                    {
                        Function.Call(Hash.DISABLE_INTERIOR, interior, false);
                        Function.Call(Hash.PIN_INTERIOR_IN_MEMORY, interior);
                        Function.Call(Hash.REFRESH_INTERIOR, interior);
                        interiorReady = Function.Call<bool>(
                            Hash.IS_INTERIOR_READY, interior);
                        if (firstResolvedAt < 0)
                            firstResolvedAt = Game.GameTime;
                    }
                    else firstResolvedAt = -1;
                    iplActive = true;
                    foreach (string ipl in PALETO_IPLS)
                        iplActive &= Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl);
                    int resolvedForMs = firstResolvedAt < 0 ? 0
                        : Game.GameTime - firstResolvedAt;
                    if (GarageInteriorReadinessPolicy.IsUsable(
                        interior, true, iplActive, interiorReady,
                        resolvedForMs, PALETO_INTERIOR_FALLBACK_SETTLE_MS))
                    {
                        Log($"LoadPaletoInterior: interior={interior} ready " +
                            $"readySignal={interiorReady} iplActive={iplActive} " +
                            $"fallback={!interiorReady} " +
                            $"elapsed={Game.GameTime - startedAt}ms");
                        return true;
                    }
                    Script.Wait(100);
                }

                Log($"LoadPaletoInterior: FAILED interior={interior} " +
                    $"interiorReady={interiorReady} iplActive={iplActive}");
            }
            catch (Exception ex)
            {
                LogException("LoadPaletoInterior", ex);
            }
            finally
            {
                if (focusSet) Function.Call(Hash.CLEAR_FOCUS);
            }
            UnloadPaletoInterior();
            return false;
        }

        private static void UnloadPaletoInterior(bool force = false)
        {
            if (!_paletoMapLeaseHeld || !force) return;
            DeferredMapContentResult released =
                DeferredMapContentRuntime.Release(
                    DeferredMapProperty.Paleto, PALETO_IPLS, force: force);
            if (released.ReleaseComplete)
                _paletoMapLeaseHeld = false;
            else
                Log("UnloadPaletoInterior: map release failed; lease retained " +
                    released.Detail);
        }

        private static void SpawnPaletoGarageVehicles()
        {
            ClearPaletoHandles();
            foreach (StoredVehicle stored in GetPaletoGarageStoredVehicles())
                SpawnPaletoVehicle(stored);
        }

        private static void SpawnPaletoVehicle(StoredVehicle stored)
        {
            if (stored.Slot < 0 || stored.Slot >= PALETO_SLOT_COUNT) return;
            try
            {
                ParkingSlot slot = PaletoSlots[stored.Slot];
                Model model = GetStoredModel(stored);
                model.Request(10000);
                if (!model.IsLoaded)
                {
                    Log($"SpawnPaletoVehicle: model unavailable {stored.Model}");
                    return;
                }
                Vehicle vehicle = World.CreateVehicle(model, slot.Position, slot.Heading);
                model.MarkAsNoLongerNeeded();
                if (vehicle == null) return;
                ApplyVehicleState(vehicle, stored);
                vehicle.IsPersistent = true;
                vehicle.IsEngineRunning = false;
                PlaceVehicleInParkingSpace(
                    vehicle, slot, stored.Model, "Paleto");
                vehicle.IsPositionFrozen = true;
                _paletoHandles[stored.Slot] = vehicle;
            }
            catch (Exception ex)
            {
                LogException($"SpawnPaletoVehicle({stored.Model})", ex);
            }
        }

        private static void EnforcePaletoVehicleState()
        {
            foreach (Vehicle vehicle in _paletoHandles)
            {
                if (vehicle == null || !vehicle.Exists()) continue;
                vehicle.IsPositionFrozen = true;
                vehicle.IsEngineRunning = false;
            }
        }

        private static void ClearPaletoHandles()
        {
            for (int i = 0; i < _paletoHandles.Length; i++)
                DeletePaletoHandle(i);
        }

        private static void DeletePaletoHandle(int slot)
        {
            if (slot < 0 || slot >= _paletoHandles.Length) return;
            Vehicle vehicle = _paletoHandles[slot];
            if (vehicle != null && vehicle.Exists())
            {
                vehicle.IsPersistent = true;
                vehicle.Delete();
            }
            _paletoHandles[slot] = null;
        }

        private static int FindEmptyPaletoSlot(List<StoredVehicle> list)
        {
            var occupied = new HashSet<int>();
            foreach (StoredVehicle stored in list) occupied.Add(stored.Slot);
            for (int i = 0; i < PALETO_SLOT_COUNT; i++)
                if (!occupied.Contains(i)) return i;
            return -1;
        }

        private static void PaletoUpdateStoredFromLive()
        {
            if (!_isPlayerInPaletoGarage) return;
            List<StoredVehicle> list = GetPaletoGarageStoredVehicles();
            for (int i = 0; i < list.Count; i++)
            {
                StoredVehicle stored = list[i];
                if (stored.Slot < 0 || stored.Slot >= PALETO_SLOT_COUNT) continue;
                Vehicle vehicle = _paletoHandles[stored.Slot];
                if (vehicle == null || !vehicle.Exists()) continue;
                list[i] = CaptureVehicleState(vehicle, stored.Model, stored.Slot);
            }
            PaletoSave();
        }

        private static void PaletoLoad()
        {
            string loadPath = File.Exists(PALETO_SAVE_PATH)
                ? PALETO_SAVE_PATH : PALETO_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath)) return;
            try
            {
                PaletoParseJson(File.ReadAllText(loadPath));
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                    PaletoSave();
            }
            catch (Exception ex)
            {
                LogException("PaletoLoad", ex);
                string backup = PALETO_SAVE_PATH + ".bak";
                if (loadPath == PALETO_SAVE_PATH && File.Exists(backup))
                {
                    try { PaletoParseJson(File.ReadAllText(backup)); }
                    catch (Exception backupEx)
                    {
                        LogException("PaletoLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool PaletoSave()
        {
            return StageOrWriteVehicleSave(
                PALETO_SAVE_PATH, PaletoBuildJson, "PaletoSave");
        }

        private static string PaletoBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");
            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");
                if (_paletoStored.TryGetValue(key, out var list) && list.Count > 0)
                {
                    sb.AppendLine();
                    for (int i = 0; i < list.Count; i++)
                    {
                        AppendDavisVehicleJson(sb, list[i]);
                        sb.AppendLine(i < list.Count - 1 ? "," : "");
                    }
                    sb.Append("  ]");
                }
                else sb.Append("]");
                sb.AppendLine(k < keys.Length - 1 ? "," : "");
            }
            sb.AppendLine("}");
            return sb.ToString();
        }

        private static void PaletoParseJson(string json)
        {
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR },
                PALETO_SLOT_COUNT);
            foreach (var entry in parsed)
                _paletoStored[entry.Key] = entry.Value;
        }
    }
}
