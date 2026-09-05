// GarageManager.Davis.cs -- Davis 10-car garage using the Tuners Auto Shop.

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
        private const int DAVIS_SLOT_COUNT = 10;
        private static readonly GarageDefinition DAVIS_GARAGE =
            GarageDefinitions.Davis;

        // Exterior anchors surveyed in Davis.
        internal static Vector3 DAVIS_VEHICLE_ENTRANCE_POS =
            new Vector3(204.0661f, -1466.4750f, 29.1437f);
        private static float DAVIS_VEHICLE_ENTRANCE_HEADING = 43.97f;
        internal static Vector3 DAVIS_PED_ENTRANCE_POS =
            new Vector3(215.0502f, -1461.0250f, 29.1847f);
        private static float DAVIS_PED_ENTRANCE_HEADING = 49.38f;

        // Shared Los Santos Tuners Auto Shop interior.
        private static Vector3 DAVIS_INTERIOR_PED =
            new Vector3(-1357.6240f, 153.2929f, -99.1942f);
        private static float DAVIS_INTERIOR_PED_HEADING = 0f;

        // This is the actual Auto Shop MILO placement name in mptuner's
        // int_placement_tr.rpf. The five tr_tuner_shop_* names are exterior
        // location aliases and never become active for this shared interior.
        private static string[] DAVIS_AUTO_SHOP_IPLS =
        {
            "tr_int_placement_tr_interior_0_tuner_mod_garage_milo_",
        };
        private static Vector3 DAVIS_INTERIOR_CENTER =
            new Vector3(-1350f, 160f, -100f);
        private const int DAVIS_INTERIOR_LOAD_TIMEOUT_MS = 5000;
        private const int DAVIS_INTERIOR_FALLBACK_SETTLE_MS = 1000;

        // Mission boards and the permanent shop fixtures are kept active for
        // every layout.  The purchasable/decorative variants below are applied
        // from the player's saved Auto Shop customization instead of being
        // hard-coded on top of one another.
        private static readonly string[] DAVIS_AUTO_SHOP_ENTITY_SETS_FIXED =
        {
            "entity_set_bombs",
            "entity_set_drive",
            "entity_set_ecu",
            "entity_set_IAA",
            "entity_set_jammers",
            "entity_set_laptop",
            "entity_set_lightbox",
            "entity_set_plate",
            "entity_set_scope",
            "entity_set_thermal",
            "entity_set_tints",
            "entity_set_train",
            "entity_set_virus",
        };

        private static readonly string[] DAVIS_AUTO_SHOP_ENTITY_SETS_CONFIGURABLE =
        {
            "entity_set_bedroom",
            "entity_set_bedroom_empty",
            "entity_set_box_clutter",
            "entity_set_cabinets",
            "entity_set_car_lift_cutscene",
            "entity_set_car_lift_default",
            "entity_set_car_lift_purchase",
            "entity_set_chalkboard",
            "entity_set_container",
            "entity_set_cut_seats",
            "entity_set_def_table",
            "entity_set_methLab",
            "entity_set_style_1",
            "entity_set_style_2",
            "entity_set_style_3",
            "entity_set_style_4",
            "entity_set_style_5",
            "entity_set_style_6",
            "entity_set_style_7",
            "entity_set_style_8",
            "entity_set_style_9",
            "entity_set_table",
        };

        internal static readonly string[] DAVIS_CUSTOM_CATEGORY_NAMES =
        {
            "Style", "Tint", "Car Lift", "Personal Quarters",
            "Work Area", "Storage",
        };

        internal static readonly string[][] DAVIS_CUSTOM_OPTION_LABELS =
        {
            new[]
            {
                "Undressed", "Flawless", "Polished", "Concrete Chic",
                "Nostalgia Trip", "Route 68", "Super Chibi", "Wildstyle",
                "Race and Chase",
            },
            new[]
            {
                "Yellow", "White", "Brown", "Green", "Orange",
                "Red", "Pink", "Purple", "Blue",
            },
            new[] { "Standard", "Second Lift" },
            new[] { "Empty", "Furnished" },
            new[] { "Default Bench", "Cabinets", "Workbench", "Planning Board" },
            new[] { "Clear", "Box Clutter", "Container", "Seat Covers" },
        };

        private static readonly string[][] DAVIS_CUSTOM_ENTITY_SETS =
        {
            new[]
            {
                "entity_set_style_1", "entity_set_style_2",
                "entity_set_style_3", "entity_set_style_4",
                "entity_set_style_5", "entity_set_style_6",
                "entity_set_style_7", "entity_set_style_8",
                "entity_set_style_9",
            },
            null, // Tint is the colour variant of entity_set_tints.
            new[] { "entity_set_car_lift_default", "entity_set_car_lift_purchase" },
            new[] { "entity_set_bedroom_empty", "entity_set_bedroom" },
            new[] { "entity_set_def_table", "entity_set_cabinets", "entity_set_table", "entity_set_chalkboard" },
            new[] { null, "entity_set_box_clutter", "entity_set_container", "entity_set_cut_seats" },
        };

        internal const int DAVIS_CUSTOM_CATEGORY_COUNT = 6;
        private static readonly int[] DAVIS_DEFAULT_CUSTOMIZATION =
            { 8, 0, 1, 1, 0, 0 };

        private static readonly Dictionary<string, int[]> _davisCustomization =
            new Dictionary<string, int[]>
            {
                { KEY_MICHAEL,  (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone() },
                { KEY_FRANKLIN, (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone() },
                { KEY_TREVOR,   (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone() },
            };

        // Rockstar's native Auto Shop ten-car arrangement.
        internal static ParkingSlot[] DavisGarageSlots =
        {
            new ParkingSlot(-1341.5f, 156.0f, -99.6944f, 160f, -100.1944f),
            new ParkingSlot(-1337.5f, 156.0f, -99.6944f, 160f, -100.1944f),
            new ParkingSlot(-1333.5f, 156.0f, -99.6944f, 160f, -100.1944f),
            new ParkingSlot(-1329.5f, 156.0f, -99.6944f, 160f, -100.1944f),
            new ParkingSlot(-1326.0f, 149.0f, -99.6944f, 90f, -100.1944f),
            new ParkingSlot(-1325.5f, 142.0f, -99.6944f, 20f, -100.1944f),
            new ParkingSlot(-1329.5f, 142.0f, -99.6944f, 20f, -100.1944f),
            new ParkingSlot(-1333.5f, 142.0f, -99.6944f, 20f, -100.1944f),
            new ParkingSlot(-1337.5f, 142.0f, -99.6944f, 20f, -100.1944f),
            new ParkingSlot(-1341.5f, 142.0f, -99.6944f, 20f, -100.1944f),
        };

        private static ParkingSlot ResolveDavisGarageSlot(
            int slotIndex, string modelName, int modelHash)
        {
            ParkingSlot slot = DavisGarageSlots[slotIndex];
            if (GetGarageSizeTier(modelName, modelHash) > 0) return slot;

            // Rockstar moves ordinary cars toward the center of each bay;
            // the published roots remain unchanged for long/wide vehicles.
            if (slotIndex <= 3) slot.Position.Y += 0.75f;
            else if (slotIndex == 4) slot.Position.X += 0.75f;
            else slot.Position.Y -= 0.75f;
            return slot;
        }

        private static readonly string DAVIS_SAVE_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_davis_garage.json");
        private static readonly string DAVIS_CUSTOMIZATION_PATH =
            Path.Combine(SCRIPTS_DIR, "ALLIN1_davis_customization.json");
        private static readonly Dictionary<string, List<StoredVehicle>> _davisStored =
            new Dictionary<string, List<StoredVehicle>>
            {
                { KEY_MICHAEL,  new List<StoredVehicle>() },
                { KEY_FRANKLIN, new List<StoredVehicle>() },
                { KEY_TREVOR,   new List<StoredVehicle>() },
            };
        private static readonly Vehicle[] _davisHandles =
            new Vehicle[DAVIS_SLOT_COUNT];
        private static bool _isPlayerInDavisGarage;
        private static bool _davisMapLeaseHeld;
        private static bool _davisMapLeaseCreatedForCurrentEntry;
        private static bool _davisInitialized;
        private static int _davisExitCooldownFrames;
        private static Blip _davisVehicleBlip;
        private static Blip _davisPedBlip;

        internal static bool IsPlayerInDavisGarage => _isPlayerInDavisGarage;
        internal static bool IsDavisGarageInitialized => _davisInitialized;

        internal static void InitializeDavisGarage()
        {
            if (_davisInitialized) return;
            try
            {
                DavisLoad();
                DavisCustomizationLoad();
                _davisVehicleBlip = World.CreateBlip(DAVIS_VEHICLE_ENTRANCE_POS);
                _davisVehicleBlip.Sprite = BlipSprite.Garage;
                _davisVehicleBlip.Color = CharacterBlipColor();
                _davisVehicleBlip.Name = "ALLIN1 Davis Auto Shop (Vehicle)";
                _davisVehicleBlip.IsShortRange = true;

                _davisPedBlip = World.CreateBlip(DAVIS_PED_ENTRANCE_POS);
                _davisPedBlip.Sprite = BlipSprite.Garage;
                _davisPedBlip.Color = CharacterBlipColor();
                _davisPedBlip.Name = "ALLIN1 Davis Auto Shop (Pedestrian)";
                _davisPedBlip.IsShortRange = true;

                int count = 0;
                foreach (var list in _davisStored.Values) count += list.Count;
                Log($"Davis Auto Shop initialized ({count} stored vehicles)");
            }
            catch (Exception ex)
            {
                LogException("InitializeDavisGarage", ex);
            }
            _davisInitialized = true;
        }

        internal static int GetDavisGarageUsedSlots()
        {
            return _davisStored.TryGetValue(CharacterKey(), out var list)
                ? list.Count : 0;
        }

        internal static int GetDavisGarageCapacity() => DAVIS_SLOT_COUNT;

        internal static List<StoredVehicle> GetDavisGarageStoredVehicles()
        {
            return _davisStored.TryGetValue(CharacterKey(), out var list)
                ? list : new List<StoredVehicle>();
        }

        internal static int GetDavisCustomizationOptionCount(int category)
        {
            if (category < 0 || category >= DAVIS_CUSTOM_CATEGORY_COUNT) return 0;
            return DAVIS_CUSTOM_OPTION_LABELS[category].Length;
        }

        internal static int GetDavisCustomizationChoice(int category)
        {
            if (category < 0 || category >= DAVIS_CUSTOM_CATEGORY_COUNT) return 0;
            string key = CharacterKey();
            if (key == KEY_UNSUPPORTED) return DAVIS_DEFAULT_CUSTOMIZATION[category];
            if (!_davisCustomization.TryGetValue(key, out int[] choices))
                return DAVIS_DEFAULT_CUSTOMIZATION[category];
            int choice = choices[category];
            int optionCount = GetDavisCustomizationOptionCount(category);
            return choice >= 0 && choice < optionCount
                ? choice : DAVIS_DEFAULT_CUSTOMIZATION[category];
        }

        internal static void SetDavisCustomizationChoice(int category, int option)
        {
            if (category < 0 || category >= DAVIS_CUSTOM_CATEGORY_COUNT) return;
            int optionCount = GetDavisCustomizationOptionCount(category);
            if (option < 0 || option >= optionCount) return;

            string key = CharacterKey();
            if (key == KEY_UNSUPPORTED) return;
            if (!_davisCustomization.TryGetValue(key, out int[] choices))
            {
                choices = (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone();
                _davisCustomization[key] = choices;
            }
            if (choices[category] == option) return;
            choices[category] = option;
            DavisCustomizationSave();

            if (_isPlayerInDavisGarage)
            {
                int interior = Function.Call<int>(
                    Hash.GET_INTERIOR_AT_COORDS, -1350f, 160f, -100f);
                if (interior != 0)
                    ApplyDavisAutoShopCustomization(interior);
            }
            Log($"SetDavisCustomizationChoice: cat={DAVIS_CUSTOM_CATEGORY_NAMES[category]} option={option}");
        }

        internal static bool DeliverToDavisGarage(
            string model, int color1, int color2)
        {
            if (GetGarageSizeTier(model) >= 2) return false;
            if (!_davisStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (list.Count >= DAVIS_SLOT_COUNT) return false;

            int slotIndex = FindEmptyDavisSlot(list);
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

            if (_isPlayerInDavisGarage)
                SpawnDavisVehicle(stored);

            if (!DavisSave())
            {
                list.Remove(stored);
                DeleteDavisHandle(slotIndex);
                return false;
            }
            Log($"DeliverToDavisGarage: {model} -> slot {slotIndex}");
            return true;
        }

        internal static bool RemoveDavisGarageVehicle(int listIndex)
        {
            if (!_davisStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (listIndex < 0 || listIndex >= list.Count) return false;

            StoredVehicle stored = list[listIndex];
            DeleteDavisHandle(stored.Slot);
            list.RemoveAt(listIndex);
            if (!DavisSave())
            {
                list.Insert(listIndex, stored);
                return false;
            }
            Log($"RemoveDavisGarageVehicle: {stored.Model} from slot {stored.Slot}");
            return true;
        }

        internal static void OnDavisGarageTick()
        {
            if (!_davisInitialized || _transitionInProgress) return;
            if (_isPlayerInGarage || _isPlayerInFloorGarage ||
                _isPlayerInGarmentGarage || _isPlayerInRuralGarage ||
                _isPlayerInPaletoGarage) return;
            if (_davisExitCooldownFrames > 0)
            {
                _davisExitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;
            Color markerColor;

            if (!_isPlayerInDavisGarage)
            {
                bool inVehicle = player.IsInVehicle();
                Vector3 activeEntrance = inVehicle
                    ? DAVIS_VEHICLE_ENTRANCE_POS
                    : DAVIS_PED_ENTRANCE_POS;
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
                        DAVIS_VEHICLE_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(2.5f, 2.5f, 1.5f),
                        markerColor);
                    if (player.Position.DistanceTo(DAVIS_VEHICLE_ENTRANCE_POS) <
                        ENTER_RADIUS + 0.5f)
                    {
                        Vehicle vehicle = player.CurrentVehicle;
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            DAVIS_GARAGE, vehicle);
                        if (denial != GarageEntryDenial.None)
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(DAVIS_GARAGE, denial));
                        }
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Davis Auto Shop.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterDavisGarage();
                        }
                    }
                }
                else
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        DAVIS_PED_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(1.5f, 1.5f, 1.2f),
                        markerColor);
                    if (player.Position.DistanceTo(DAVIS_PED_ENTRANCE_POS) < ENTER_RADIUS)
                    {
                        GarageEntryDenial denial = EvaluateGarageEntry(
                            DAVIS_GARAGE);
                        if (denial != GarageEntryDenial.None)
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                GarageEntryMessage(DAVIS_GARAGE, denial));
                        else
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "Press ~INPUT_CONTEXT~ to enter the Davis Auto Shop.");
                            if (Game.IsControlJustPressed(GTA.Control.Context))
                                EnterDavisGarage();
                        }
                    }
                }
                return;
            }

            markerColor = CharacterMarkerColor();
            EnforceDavisVehicleState(player);
            if (player.IsInVehicle())
            {
                GTA.UI.Screen.ShowHelpTextThisFrame(
                    "Press ~INPUT_CONTEXT~ to leave the Davis Auto Shop with your vehicle.");
                if (Game.IsControlJustPressed(GTA.Control.Context))
                    LeaveDavisGarage();
            }
            else
            {
                World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                    DAVIS_INTERIOR_PED - new Vector3(0f, 0f, 1f),
                    Vector3.Zero, Vector3.Zero, new Vector3(1.5f, 1.5f, 1.2f),
                    markerColor);
                if (player.Position.DistanceTo(DAVIS_INTERIOR_PED) < EXIT_RADIUS)
                {
                    GTA.UI.Screen.ShowHelpTextThisFrame(
                        "Press ~INPUT_CONTEXT~ to leave the Davis Auto Shop.");
                    if (Game.IsControlJustPressed(GTA.Control.Context))
                        LeaveDavisGarage();
                }
            }
        }

        private static void EnterDavisGarage()
        {
            if (RejectGarageEntry(DAVIS_GARAGE)) return;
            if (!DeferredMapContentRuntime.CanBeginOfficialGarageEntry(
                    DeferredMapProperty.Davis, out _)) return;
            if (!BeginTransition("EnterDavisGarage")) return;
            _davisMapLeaseCreatedForCurrentEntry = false;
            var transition = CreateDavisEntryStreamingTransition();
            try
            {
                using (ClientLog.Time("Garage", "enter_davis_garage"))
                    EnterDavisGarageCore(transition);
            }
            catch (Exception ex)
            {
                transition.Fail("entry_exception:" + ex.GetType().Name);
                LogException("EnterDavisGarage", ex);
                RecoverTransition("EnterDavisGarage", DAVIS_PED_ENTRANCE_POS,
                    DAVIS_PED_ENTRANCE_HEADING);
                Script.Wait(100);
                UnloadDavisAutoShopInterior(
                    force: _davisMapLeaseCreatedForCurrentEntry);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Davis garage entry failed safely. See ALLIN1_gbay.log.", 4000);
            }
            finally
            {
                transition.Dispose();
                EndTransition("EnterDavisGarage");
            }
        }

        private static OfficialGarageTransitionCoordinator
            CreateDavisEntryStreamingTransition()
        {
            return new OfficialGarageTransitionCoordinator(
                DAVIS_GARAGE.Id,
                "entry",
                () => Environment.TickCount,
                ObserveOfficialGarageTransition,
                () =>
                {
                    _isPlayerInDavisGarage = false;
                    ClearDavisHandles();
                    bool forceRelease =
                        _davisMapLeaseCreatedForCurrentEntry;
                    UnloadDavisAutoShopInterior(
                        force: forceRelease);
                    if (!_davisMapLeaseHeld)
                        _davisMapLeaseCreatedForCurrentEntry = false;
                },
                () => Function.Call(Hash.DO_SCREEN_FADE_IN, 0));
        }

        private static void ObserveOfficialGarageTransition(
            OfficialGarageTransitionEvent observation)
        {
            ClientLog.Info("Garage", "official_garage_transition_phase",
                new Dictionary<string, object>
                {
                    { "transition_id", observation.TransitionId },
                    { "garage", observation.GarageId },
                    { "direction", observation.Direction },
                    { "previous_phase", observation.PreviousPhase.ToString() },
                    { "phase", observation.Phase.ToString() },
                    { "phase_elapsed_ms", observation.PhaseElapsedMilliseconds },
                    { "total_elapsed_ms", observation.TotalElapsedMilliseconds },
                    { "detail", observation.Detail },
                    { "terminal", observation.Terminal },
                });
        }

        private static void EnterDavisGarageCore(
            OfficialGarageTransitionCoordinator transition)
        {
            Log("EnterDavisGarage: START");
            Ped player = Game.Player.Character;
            Vehicle rideInToDelete = null;
            string confirmation = null;
            List<StoredVehicle> storedListDuringEntry = null;
            StoredVehicle storedDuringEntry = null;
            bool storageCommitted = false;

            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
                    string modelName = ResolveDavisVehicleName(rideIn);
                    if (RejectGarageEntry(
                        DAVIS_GARAGE, rideIn, modelName, rideIn.Model.Hash)) return;

                    List<StoredVehicle> list = GetDavisGarageStoredVehicles();
                    if (list.Count >= DAVIS_SLOT_COUNT)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            $"~r~The Davis Auto Shop is full.~w~ ({list.Count}/{DAVIS_SLOT_COUNT})",
                            3000);
                        return;
                    }
                    int slotIndex = FindEmptyDavisSlot(list);
                    if (slotIndex < 0) return;
                    storedListDuringEntry = list;
                    storedDuringEntry = CaptureVehicleState(
                        rideIn, modelName, slotIndex);
                    string display = RuntimeVehicleCatalog.GetDisplayName(modelName);
                    confirmation = $"~g~{display}~w~ stored in the Davis Auto Shop.";
                    rideInToDelete = rideIn;
                }
            }

            // MPTUNER_MAP_UPDATE is a broad Rockstar cache-loader changeset
            // whose own metadata requires a loading screen. Hold and verify
            // black before the Phase-B runtime can execute the fixed group.
            transition.HoldFade(
                () => BeginGarageBlackTransition("EnterDavisGarage"));
            transition.Advance(
                OfficialGarageTransitionPhase.LeaseRequested,
                "davis_map_lease_requested_while_black");
            if (!LoadDavisAutoShopInterior(transition))
            {
                transition.Fail("map_activation_failed");
                GTA.UI.Screen.ShowSubtitle(
                    DeferredMapContentRuntime.GarageUnavailableMessage(
                        "The Davis Auto Shop"), 4000);
                return;
            }

            try
            {
                if (storedDuringEntry != null && storedListDuringEntry != null)
                {
                    storedListDuringEntry.Add(storedDuringEntry);
                    if (!DavisSave())
                    {
                        storedListDuringEntry.Remove(storedDuringEntry);
                        transition.Fail("vehicle_persistence_failed");
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The vehicle could not be saved.", 3000);
                        return;
                    }
                    storageCommitted = true;
                    rideInToDelete.IsPersistent = true;
                }

                ClearDavisHandles();
                _isPlayerInDavisGarage = true;
                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    DAVIS_INTERIOR_PED.X, DAVIS_INTERIOR_PED.Y,
                    DAVIS_INTERIOR_PED.Z, false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player,
                    DAVIS_INTERIOR_PED_HEADING);
                Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
                if (rideInToDelete != null && rideInToDelete.Exists())
                    rideInToDelete.Delete();
                SpawnDavisGarageVehicles();
                player.IsPositionFrozen = false;
                Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
                transition.Complete(
                    OfficialGarageTransitionPhase.Occupied,
                    () => CompleteGarageBlackTransition(
                        "EnterDavisGarage", player, null,
                        () => IsPlayerInReadyInterior(player), _davisHandles),
                    "davis_interior_occupied");
                _davisMapLeaseCreatedForCurrentEntry = false;
                if (!string.IsNullOrEmpty(confirmation))
                    GTA.UI.Screen.ShowSubtitle(confirmation, 4000);
                Log("EnterDavisGarage: COMPLETE");
            }
            catch
            {
                if (storageCommitted && storedDuringEntry != null &&
                    storedListDuringEntry != null)
                {
                    storedListDuringEntry.Remove(storedDuringEntry);
                    if (!DavisSave())
                        Log("EnterDavisGarage: WARNING - entry rollback save failed");
                    Log("EnterDavisGarage: rolled back drive-in storage after transition failure");
                }
                throw;
            }
        }

        private static void LeaveDavisGarage()
        {
            if (!BeginTransition("LeaveDavisGarage")) return;
            try
            {
                using (ClientLog.Time("Garage", "leave_davis_garage"))
                    LeaveDavisGarageCore();
            }
            catch (Exception ex)
            {
                LogException("LeaveDavisGarage", ex);
                RecoverTransition("LeaveDavisGarage", DAVIS_PED_ENTRANCE_POS,
                    DAVIS_PED_ENTRANCE_HEADING);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Davis garage exit recovered safely. See ALLIN1_gbay.log.", 4000);
            }
            finally { EndTransition("LeaveDavisGarage"); }
        }

        private static void LeaveDavisGarageCore()
        {
            Log("LeaveDavisGarage: START");
            DavisUpdateStoredFromLive();
            Ped player = Game.Player.Character;
            Vehicle playerVehicle = null;
            int playerSlot = -1;

            if (player.IsInVehicle())
            {
                Vehicle current = player.CurrentVehicle;
                for (int i = 0; i < _davisHandles.Length; i++)
                {
                    if (_davisHandles[i] != null && _davisHandles[i] == current)
                    {
                        playerVehicle = current;
                        playerSlot = i;
                        _davisHandles[i] = null;
                        break;
                    }
                }
            }

            ClearDavisHandles();
            BeginGarageBlackTransition("LeaveDavisGarage");

            // Keep the player and ride inert while restoring the exterior
            // world. Releasing the MP map after the teleport creates a gap
            // where the vehicle has physics but the street has no collision.
            player.IsPositionFrozen = true;
            if (playerVehicle != null)
                playerVehicle.IsPositionFrozen = true;

            if (playerVehicle != null)
            {
                List<StoredVehicle> list = GetDavisGarageStoredVehicles();
                for (int i = list.Count - 1; i >= 0; i--)
                    if (list[i].Slot == playerSlot) { list.RemoveAt(i); break; }

                playerVehicle.IsPersistent = true;
                ReleaseGarageVehicleForDriving(playerVehicle,
                    DAVIS_VEHICLE_ENTRANCE_POS,
                    DAVIS_VEHICLE_ENTRANCE_HEADING, "Davis");
            }
            else
            {
                player.IsPositionFrozen = true;
                Function.Call(Hash.SET_ENTITY_COORDS, player,
                    DAVIS_PED_ENTRANCE_POS.X, DAVIS_PED_ENTRANCE_POS.Y,
                    DAVIS_PED_ENTRANCE_POS.Z, false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, player,
                    DAVIS_PED_ENTRANCE_HEADING);
                player.IsPositionFrozen = false;
            }

            Script.Wait(100);
            UnloadDavisAutoShopInterior();

            DavisSave();
            _isPlayerInDavisGarage = false;
            _davisExitCooldownFrames = 60;
            CompleteGarageBlackTransition(
                "LeaveDavisGarage", player, playerVehicle,
                () => Function.Call<int>(
                    Hash.GET_INTERIOR_FROM_ENTITY, player) == 0);
            Log("LeaveDavisGarage: COMPLETE");
        }

        private static bool LoadDavisAutoShopInterior(
            OfficialGarageTransitionCoordinator transition = null)
        {
            bool focusSet = false;
            try
            {
                if (!_davisMapLeaseHeld)
                {
                    DeferredMapContentResult activation =
                        DeferredMapContentRuntime.TryAcquireDavisPhaseB(
                            transition, DAVIS_AUTO_SHOP_IPLS,
                            DAVIS_INTERIOR_LOAD_TIMEOUT_MS);
                    if (!activation.Success)
                    {
                        if (DeferredMapContentRuntime
                                .HasDavisPhaseBCleanupPending)
                        {
                            _davisMapLeaseHeld = true;
                            _davisMapLeaseCreatedForCurrentEntry = true;
                        }
                        Log("LoadDavisAutoShopInterior: deferred map unavailable " +
                            $"outcome={activation.Outcome} detail={activation.Detail}");
                        return false;
                    }
                    _davisMapLeaseHeld = true;
                    _davisMapLeaseCreatedForCurrentEntry = true;
                }

                Function.Call(Hash.SET_FOCUS_POS_AND_VEL,
                    DAVIS_INTERIOR_CENTER.X, DAVIS_INTERIOR_CENTER.Y,
                    DAVIS_INTERIOR_CENTER.Z, 0f, 0f, 0f);
                focusSet = true;

                int startedAt = Game.GameTime;
                int interior = 0;
                bool interiorReady = false;
                bool iplActive = false;
                int firstResolvedAt = -1;
                while (Game.GameTime - startedAt < DAVIS_INTERIOR_LOAD_TIMEOUT_MS)
                {
                    foreach (string ipl in DAVIS_AUTO_SHOP_IPLS)
                        Function.Call(Hash.REQUEST_IPL, ipl);
                    Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                        DAVIS_INTERIOR_CENTER.X, DAVIS_INTERIOR_CENTER.Y,
                        DAVIS_INTERIOR_CENTER.Z);

                    interior = Function.Call<int>(Hash.GET_INTERIOR_AT_COORDS,
                        DAVIS_INTERIOR_CENTER.X, DAVIS_INTERIOR_CENTER.Y,
                        DAVIS_INTERIOR_CENTER.Z);
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
                    foreach (string ipl in DAVIS_AUTO_SHOP_IPLS)
                        iplActive &= Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl);
                    if (iplActive && transition != null &&
                        transition.Phase ==
                            OfficialGarageTransitionPhase.LeaseRequested)
                    {
                        transition.Advance(
                            OfficialGarageTransitionPhase.IplReady,
                            "davis_ipls_active");
                    }
                    int resolvedForMs = firstResolvedAt < 0 ? 0
                        : Game.GameTime - firstResolvedAt;
                    if (GarageInteriorReadinessPolicy.IsUsable(
                        interior, true, iplActive, interiorReady,
                        resolvedForMs, DAVIS_INTERIOR_FALLBACK_SETTLE_MS))
                    {
                        ApplyDavisAutoShopCustomization(interior);
                        if (transition != null && transition.Phase ==
                            OfficialGarageTransitionPhase.IplReady)
                        {
                            transition.Advance(
                                OfficialGarageTransitionPhase.InteriorReady,
                                "davis_interior_ready");
                        }
                        Log($"LoadDavisAutoShopInterior: interior={interior} ready " +
                            $"readySignal={interiorReady} iplActive={iplActive} " +
                            $"elapsed={Game.GameTime - startedAt}ms");
                        return true;
                    }
                    Script.Wait(100);
                }

                Log($"LoadDavisAutoShopInterior: FAILED interior={interior} " +
                    $"interiorReady={interiorReady} iplActive={iplActive}");
            }
            catch (Exception ex)
            {
                LogException("LoadDavisAutoShopInterior", ex);
            }
            finally
            {
                if (focusSet) Function.Call(Hash.CLEAR_FOCUS);
            }
            UnloadDavisAutoShopInterior(
                force: _davisMapLeaseCreatedForCurrentEntry);
            return false;
        }

        private static void UnloadDavisAutoShopInterior(bool force = false)
        {
            if (!_davisMapLeaseHeld) return;
            DeferredMapContentResult released =
                DeferredMapContentRuntime.Release(
                    DeferredMapProperty.Davis, DAVIS_AUTO_SHOP_IPLS, force);
            if (released.Outcome == DeferredMapContentOutcome.KeptResident)
            {
                Log("UnloadDavisAutoShopInterior: Phase-B map retained for " +
                    "the Story session");
                return;
            }
            if (released.ReleaseComplete)
            {
                _davisMapLeaseHeld = false;
                _davisMapLeaseCreatedForCurrentEntry = false;
            }
            else
                Log("UnloadDavisAutoShopInterior: map release failed; " +
                    "lease retained " + released.Detail);
        }

        private static void ApplyDavisAutoShopCustomization(int interior)
        {
            foreach (string set in DAVIS_AUTO_SHOP_ENTITY_SETS_CONFIGURABLE)
                Function.Call(Hash.DEACTIVATE_INTERIOR_ENTITY_SET, interior, set);
            foreach (string set in DAVIS_AUTO_SHOP_ENTITY_SETS_FIXED)
                Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, set);

            string key = CharacterKey();
            if (!_davisCustomization.TryGetValue(key, out int[] choices))
            {
                choices = (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone();
                _davisCustomization[key] = choices;
            }

            for (int category = 0; category < DAVIS_CUSTOM_CATEGORY_COUNT; category++)
            {
                if (category == 1) continue;
                int choice = choices[category];
                string[][] groups = DAVIS_CUSTOM_ENTITY_SETS;
                if (choice < 0 || choice >= groups[category].Length)
                    choice = DAVIS_DEFAULT_CUSTOMIZATION[category];
                string set = groups[category][choice];
                if (!string.IsNullOrEmpty(set))
                    Function.Call(Hash.ACTIVATE_INTERIOR_ENTITY_SET, interior, set);
            }

            int tint = choices[1];
            if (tint < 0 || tint >= DAVIS_CUSTOM_OPTION_LABELS[1].Length)
                tint = DAVIS_DEFAULT_CUSTOMIZATION[1];
            // SET_INTERIOR_ENTITY_SET_COLOR is not named by SHVDN 3.6.0.
            Function.Call((Hash)0xC1F1920BAF281317,
                interior, "entity_set_tints", tint);
            Function.Call(Hash.REFRESH_INTERIOR, interior);
        }

        private static void SpawnDavisGarageVehicles()
        {
            ClearDavisHandles();
            foreach (StoredVehicle stored in GetDavisGarageStoredVehicles())
                SpawnDavisVehicle(stored);
        }

        private static void SpawnDavisVehicle(StoredVehicle stored)
        {
            if (stored.Slot < 0 || stored.Slot >= DAVIS_SLOT_COUNT) return;
            try
            {
                ParkingSlot slot = ResolveDavisGarageSlot(
                    stored.Slot, stored.Model, stored.ModelHash);
                Model model = GetStoredModel(stored);
                model.Request(10000);
                if (!model.IsLoaded)
                {
                    Log($"SpawnDavisVehicle: model unavailable {stored.Model}");
                    return;
                }
                Vehicle vehicle = World.CreateVehicle(
                    model, slot.Position, slot.Heading);
                model.MarkAsNoLongerNeeded();
                if (vehicle == null) return;
                ApplyVehicleState(vehicle, stored);
                vehicle.IsPersistent = true;
                vehicle.IsEngineRunning = false;
                PlaceVehicleInParkingSpace(
                    vehicle, slot, stored.Model, "Davis");
                vehicle.IsPositionFrozen = true;
                _davisHandles[stored.Slot] = vehicle;
            }
            catch (Exception ex)
            {
                LogException($"SpawnDavisVehicle({stored.Model})", ex);
            }
        }

        private static void EnforceDavisVehicleState(Ped player)
        {
            for (int i = 0; i < _davisHandles.Length; i++)
            {
                Vehicle vehicle = _davisHandles[i];
                if (vehicle == null || !vehicle.Exists()) continue;
                vehicle.IsPositionFrozen = true;
                vehicle.IsEngineRunning = false;
            }
        }

        private static void ClearDavisHandles()
        {
            for (int i = 0; i < _davisHandles.Length; i++)
                DeleteDavisHandle(i);
        }

        private static void DeleteDavisHandle(int slot)
        {
            if (slot < 0 || slot >= _davisHandles.Length) return;
            Vehicle vehicle = _davisHandles[slot];
            if (vehicle != null && vehicle.Exists())
            {
                vehicle.IsPersistent = true;
                vehicle.Delete();
            }
            _davisHandles[slot] = null;
        }

        private static int FindEmptyDavisSlot(List<StoredVehicle> list)
        {
            var occupied = new HashSet<int>();
            foreach (StoredVehicle stored in list) occupied.Add(stored.Slot);
            for (int i = 0; i < DAVIS_SLOT_COUNT; i++)
                if (!occupied.Contains(i)) return i;
            return -1;
        }

        private static string ResolveDavisVehicleName(Vehicle vehicle)
        {
            int hash = vehicle.Model.Hash;
            if (_hashToSpawnName != null &&
                _hashToSpawnName.TryGetValue(hash, out string spawnName))
                return spawnName;
            string display = Function.Call<string>(
                Hash.GET_DISPLAY_NAME_FROM_VEHICLE_MODEL, (uint)hash);
            return string.IsNullOrEmpty(display)
                ? hash.ToString() : display.ToLowerInvariant();
        }

        private static void DavisUpdateStoredFromLive()
        {
            if (!_isPlayerInDavisGarage) return;
            List<StoredVehicle> list = GetDavisGarageStoredVehicles();
            for (int i = 0; i < list.Count; i++)
            {
                StoredVehicle stored = list[i];
                if (stored.Slot < 0 || stored.Slot >= DAVIS_SLOT_COUNT) continue;
                Vehicle vehicle = _davisHandles[stored.Slot];
                if (vehicle == null || !vehicle.Exists()) continue;
                list[i] = CaptureVehicleState(vehicle, stored.Model, stored.Slot);
            }
            DavisSave();
        }

        private static void DavisCustomizationLoad()
        {
            if (!File.Exists(DAVIS_CUSTOMIZATION_PATH)) return;
            try
            {
                string json = File.ReadAllText(DAVIS_CUSTOMIZATION_PATH);
                string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
                foreach (string key in keys)
                {
                    int keyIndex = json.IndexOf($"\"{key}\"",
                        StringComparison.OrdinalIgnoreCase);
                    if (keyIndex < 0) continue;
                    int start = json.IndexOf('[', keyIndex);
                    int end = start >= 0 ? json.IndexOf(']', start) : -1;
                    if (start < 0 || end < 0) continue;

                    string[] parts = json.Substring(
                        start + 1, end - start - 1).Split(',');
                    int[] choices = (int[])DAVIS_DEFAULT_CUSTOMIZATION.Clone();
                    for (int category = 0;
                        category < Math.Min(parts.Length, DAVIS_CUSTOM_CATEGORY_COUNT);
                        category++)
                    {
                        int optionCount = GetDavisCustomizationOptionCount(category);
                        if (int.TryParse(parts[category].Trim(), out int option) &&
                            option >= 0 && option < optionCount)
                            choices[category] = option;
                    }
                    _davisCustomization[key] = choices;
                }
                Log("DavisCustomizationLoad: loaded Auto Shop customization");
            }
            catch (Exception ex)
            {
                LogException("DavisCustomizationLoad", ex);
            }
        }

        private static void DavisCustomizationSave()
        {
            _garageCustomizationSavesDirty = true;
        }

        private static bool DavisCustomizationWrite()
        {
            try
            {
                var sb = new StringBuilder();
                sb.AppendLine("{");
                string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
                for (int index = 0; index < keys.Length; index++)
                {
                    string key = keys[index];
                    int[] choices = _davisCustomization.TryGetValue(
                        key, out int[] saved)
                        ? saved : DAVIS_DEFAULT_CUSTOMIZATION;
                    sb.Append($"  \"{key}\": [{string.Join(",", choices)}]");
                    sb.AppendLine(index < keys.Length - 1 ? "," : "");
                }
                sb.AppendLine("}");
                AtomicWriteText(DAVIS_CUSTOMIZATION_PATH, sb.ToString());
                return true;
            }
            catch (Exception ex)
            {
                LogException("DavisCustomizationSave", ex);
                return false;
            }
        }

        private static void DavisLoad()
        {
            string loadPath = File.Exists(DAVIS_SAVE_PATH)
                ? DAVIS_SAVE_PATH : DAVIS_SAVE_PATH + ".bak";
            if (!File.Exists(loadPath)) return;
            try
            {
                string json = File.ReadAllText(loadPath);
                DavisParseJson(json);
                if (loadPath.EndsWith(".bak", StringComparison.OrdinalIgnoreCase))
                    DavisSave();
            }
            catch (Exception ex)
            {
                LogException("DavisLoad", ex);
                string backup = DAVIS_SAVE_PATH + ".bak";
                if (loadPath == DAVIS_SAVE_PATH && File.Exists(backup))
                {
                    try
                    {
                        DavisParseJson(File.ReadAllText(backup));
                        Log("DavisLoad: primary save failed; recovered from backup");
                    }
                    catch (Exception backupEx)
                    {
                        LogException("DavisLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool DavisSave()
        {
            return StageOrWriteVehicleSave(
                DAVIS_SAVE_PATH, DavisBuildJson, "DavisSave");
        }

        private static string DavisBuildJson()
        {
            var sb = new StringBuilder();
            sb.AppendLine("{");
            sb.AppendLine("  \"_schema_v2\": [],");
            string[] keys = { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR };
            for (int k = 0; k < keys.Length; k++)
            {
                string key = keys[k];
                sb.Append($"  \"{key}\": [");
                if (_davisStored.TryGetValue(key, out var list) && list.Count > 0)
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

        private static void AppendDavisVehicleJson(
            StringBuilder sb, StoredVehicle stored)
        {
            sb.Append("    { ");
            sb.Append($"\"model\": \"{EscapeJson(stored.Model)}\", ");
            sb.Append($"\"modelHash\": {GetStoredModelHash(stored)}, ");
            sb.Append($"\"slot\": {stored.Slot}, ");
            sb.Append($"\"color1\": {stored.Color1}, ");
            sb.Append($"\"color2\": {stored.Color2}");
            if (stored.PlateText != null)
                sb.Append($", \"plate\": \"{EscapeJson(stored.PlateText)}\"");
            if (stored.PlateStyle != 0)
                sb.Append($", \"plateStyle\": {stored.PlateStyle}");
            if (stored.WheelType != 0)
                sb.Append($", \"wheelType\": {stored.WheelType}");
            if (stored.WindowTint != 0)
                sb.Append($", \"windowTint\": {stored.WindowTint}");
            if (stored.Livery > 0)
                sb.Append($", \"livery\": {stored.Livery}");
            if (stored.PearlescentColor != 0)
                sb.Append($", \"pearlescent\": {stored.PearlescentColor}");
            if (stored.RimColor != 0)
                sb.Append($", \"rimColor\": {stored.RimColor}");
            if (stored.Mods != null)
                sb.Append($", \"mods\": [{string.Join(",", stored.Mods)}]");
            if (stored.ModToggles != null)
                sb.Append($", \"modToggles\": [{string.Join(",", BoolArrayToInts(stored.ModToggles))}]");
            if (stored.NeonEnabled != null)
                sb.Append($", \"neonEnabled\": [{string.Join(",", stored.NeonEnabled)}]");
            if (stored.NeonColor != null)
                sb.Append($", \"neonColor\": [{string.Join(",", stored.NeonColor)}]");
            if (stored.TyreSmokeColor != null)
                sb.Append($", \"tyreSmokeColor\": [{string.Join(",", stored.TyreSmokeColor)}]");
            if (stored.Extras != null)
                sb.Append($", \"extras\": [{string.Join(",", stored.Extras)}]");
            if (stored.CustomPrimaryColor && stored.CustomPrimary != null)
                sb.Append($", \"customPrimary\": [{string.Join(",", stored.CustomPrimary)}]");
            if (stored.CustomSecondaryColor && stored.CustomSecondary != null)
                sb.Append($", \"customSecondary\": [{string.Join(",", stored.CustomSecondary)}]");
            sb.Append(" }");
        }

        private static void DavisParseJson(string json)
        {
            var parsed = GarageSaveCodec.Parse(json,
                new[] { KEY_MICHAEL, KEY_FRANKLIN, KEY_TREVOR }, DAVIS_SLOT_COUNT);
            foreach (var entry in parsed)
                _davisStored[entry.Key] = entry.Value;
        }

        private static void LegacyDavisParseJson(string json)
        {
            string currentKey = null;
            int i = 0;
            while (i < json.Length)
            {
                if (json[i] == '"')
                {
                    int end = json.IndexOf('"', i + 1);
                    if (end < 0) break;
                    string value = json.Substring(i + 1, end - i - 1);
                    i = end + 1;
                    if (currentKey == null)
                    {
                        int peek = SkipWhitespace(json, i);
                        if (peek < json.Length && json[peek] == ':')
                        {
                            currentKey = value;
                            i = peek + 1;
                        }
                    }
                    continue;
                }
                if (json[i] == '[' && currentKey != null)
                {
                    i++;
                    List<StoredVehicle> vehicles = ParseVehicleArray(json, ref i);
                    if (_davisStored.ContainsKey(currentKey))
                        _davisStored[currentKey] = vehicles;
                    currentKey = null;
                    continue;
                }
                i++;
            }
        }
    }
}
