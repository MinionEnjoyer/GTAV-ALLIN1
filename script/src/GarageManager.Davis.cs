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

        // Exterior anchors surveyed in Davis.
        internal static readonly Vector3 DAVIS_VEHICLE_ENTRANCE_POS =
            new Vector3(204.0661f, -1466.4750f, 29.1437f);
        private const float DAVIS_VEHICLE_ENTRANCE_HEADING = 43.97f;
        internal static readonly Vector3 DAVIS_PED_ENTRANCE_POS =
            new Vector3(215.0502f, -1461.0250f, 29.1847f);
        private const float DAVIS_PED_ENTRANCE_HEADING = 49.38f;

        // Shared Los Santos Tuners Auto Shop interior.
        private static readonly Vector3 DAVIS_INTERIOR_PED =
            new Vector3(-1357.6240f, 153.2929f, -99.1942f);
        private const float DAVIS_INTERIOR_PED_HEADING = 0f;

        private static readonly string[] DAVIS_AUTO_SHOP_IPLS =
        {
            "tr_tuner_shop_burton",
            "tr_tuner_shop_mesa",
            "tr_tuner_shop_mission",
            "tr_tuner_shop_rancho",
            "tr_tuner_shop_strawberry",
        };

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
        internal static readonly ParkingSlot[] DavisGarageSlots =
        {
            new ParkingSlot(-1341.5f, 156.0f, -99.6944f, 160f),
            new ParkingSlot(-1337.5f, 156.0f, -99.6944f, 160f),
            new ParkingSlot(-1333.5f, 156.0f, -99.6944f, 160f),
            new ParkingSlot(-1329.5f, 156.0f, -99.6944f, 160f),
            new ParkingSlot(-1326.0f, 149.0f, -99.6944f, 90f),
            new ParkingSlot(-1325.5f, 142.0f, -99.6944f, 20f),
            new ParkingSlot(-1329.5f, 142.0f, -99.6944f, 20f),
            new ParkingSlot(-1333.5f, 142.0f, -99.6944f, 20f),
            new ParkingSlot(-1337.5f, 142.0f, -99.6944f, 20f),
            new ParkingSlot(-1341.5f, 142.0f, -99.6944f, 20f),
        };

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
                _davisVehicleBlip.Color = BlipColor.Green;
                _davisVehicleBlip.Name = "ALLIN1 Davis Auto Shop (Vehicle)";
                _davisVehicleBlip.IsShortRange = true;

                _davisPedBlip = World.CreateBlip(DAVIS_PED_ENTRANCE_POS);
                _davisPedBlip.Sprite = BlipSprite.Garage;
                _davisPedBlip.Color = BlipColor.Green;
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
            if (VehicleList.GetSizeTier(model) == 2) return false;
            if (!_davisStored.TryGetValue(CharacterKey(), out var list)) return false;
            if (list.Count >= DAVIS_SLOT_COUNT) return false;

            int slotIndex = FindEmptyDavisSlot(list);
            if (slotIndex < 0) return false;
            var stored = new StoredVehicle
            {
                Model = model,
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
            if (_isPlayerInGarage || _isPlayerInFloorGarage) return;
            if (_davisExitCooldownFrames > 0)
            {
                _davisExitCooldownFrames--;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || player.IsDead) return;
            Color markerColor = Color.FromArgb(128, 0, 200, 0);

            if (!_isPlayerInDavisGarage)
            {
                if (player.IsInVehicle())
                {
                    World.DrawMarker(GTA.MarkerType.VerticalCylinder,
                        DAVIS_VEHICLE_ENTRANCE_POS - new Vector3(0f, 0f, 1f),
                        Vector3.Zero, Vector3.Zero, new Vector3(2.5f, 2.5f, 1.5f),
                        markerColor);
                    if (player.Position.DistanceTo(DAVIS_VEHICLE_ENTRANCE_POS) <
                        ENTER_RADIUS + 0.5f)
                    {
                        Vehicle vehicle = player.CurrentVehicle;
                        if (vehicle != null && vehicle.Exists() && IsPersonalVehicle(vehicle))
                        {
                            GTA.UI.Screen.ShowHelpTextThisFrame(
                                "You cannot store your personal vehicle in the Davis Auto Shop.");
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
                        GTA.UI.Screen.ShowHelpTextThisFrame(
                            "Press ~INPUT_CONTEXT~ to enter the Davis Auto Shop.");
                        if (Game.IsControlJustPressed(GTA.Control.Context))
                            EnterDavisGarage();
                    }
                }
                return;
            }

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
            if (!BeginTransition("EnterDavisGarage")) return;
            try
            {
                using (ClientLog.Time("Garage", "enter_davis_garage"))
                    EnterDavisGarageCore();
            }
            catch (Exception ex)
            {
                LogException("EnterDavisGarage", ex);
                RecoverTransition("EnterDavisGarage", DAVIS_PED_ENTRANCE_POS,
                    DAVIS_PED_ENTRANCE_HEADING);
                GTA.UI.Screen.ShowSubtitle(
                    "~r~Davis garage entry failed safely. See ALLIN1_gbay.log.", 4000);
            }
            finally { EndTransition("EnterDavisGarage"); }
        }

        private static void EnterDavisGarageCore()
        {
            Log("EnterDavisGarage: START");
            Ped player = Game.Player.Character;
            Vehicle rideInToDelete = null;
            string confirmation = null;

            if (player.IsInVehicle())
            {
                Vehicle rideIn = player.CurrentVehicle;
                if (rideIn != null && rideIn.Exists())
                {
                    if (IsPersonalVehicle(rideIn))
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~You cannot store a personal vehicle here.", 3000);
                        return;
                    }
                    string modelName = ResolveDavisVehicleName(rideIn);
                    if (VehicleList.GetSizeTier(modelName) == 2)
                    {
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~That vehicle is too large for the Auto Shop.", 3000);
                        return;
                    }

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
                    StoredVehicle stored = CaptureVehicleState(
                        rideIn, modelName, slotIndex);
                    list.Add(stored);
                    if (!DavisSave())
                    {
                        list.Remove(stored);
                        GTA.UI.Screen.ShowSubtitle(
                            "~r~The vehicle could not be saved.", 3000);
                        return;
                    }
                    string display = VehicleList.DisplayNames.TryGetValue(
                        modelName, out string displayName) ? displayName : modelName;
                    confirmation = $"~g~{display}~w~ stored in the Davis Auto Shop.";
                    rideIn.IsPersistent = true;
                    rideInToDelete = rideIn;
                }
            }

            LoadDavisAutoShopInterior();
            ClearDavisHandles();
            _isPlayerInDavisGarage = true;
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            Script.Wait(600);

            player.IsPositionFrozen = true;
            Function.Call(Hash.SET_ENTITY_COORDS, player,
                DAVIS_INTERIOR_PED.X, DAVIS_INTERIOR_PED.Y, DAVIS_INTERIOR_PED.Z,
                false, false, false, true);
            Function.Call(Hash.SET_ENTITY_HEADING, player, DAVIS_INTERIOR_PED_HEADING);
            Function.Call(Hash.CLEAR_PED_TASKS_IMMEDIATELY, player);
            if (rideInToDelete != null && rideInToDelete.Exists())
                rideInToDelete.Delete();
            SpawnDavisGarageVehicles();
            player.IsPositionFrozen = false;
            Function.Call(Hash.FREEZE_ENTITY_POSITION, player, false);
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
            if (!string.IsNullOrEmpty(confirmation))
                GTA.UI.Screen.ShowSubtitle(confirmation, 4000);
            Log("EnterDavisGarage: COMPLETE");
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
            Function.Call(Hash.DO_SCREEN_FADE_OUT, 500);
            Script.Wait(600);

            if (playerVehicle != null)
            {
                List<StoredVehicle> list = GetDavisGarageStoredVehicles();
                for (int i = list.Count - 1; i >= 0; i--)
                    if (list[i].Slot == playerSlot) { list.RemoveAt(i); break; }

                playerVehicle.IsPositionFrozen = false;
                playerVehicle.IsPersistent = true;
                Function.Call(Hash.SET_ENTITY_COORDS, playerVehicle,
                    DAVIS_VEHICLE_ENTRANCE_POS.X, DAVIS_VEHICLE_ENTRANCE_POS.Y,
                    DAVIS_VEHICLE_ENTRANCE_POS.Z, false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, playerVehicle,
                    DAVIS_VEHICLE_ENTRANCE_HEADING);
                Function.Call(Hash.SET_VEHICLE_ON_GROUND_PROPERLY, playerVehicle);
                playerVehicle.IsEngineRunning = true;
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

            DavisSave();
            _isPlayerInDavisGarage = false;
            _davisExitCooldownFrames = 60;
            Function.Call(Hash.DO_SCREEN_FADE_IN, 500);
            Log("LeaveDavisGarage: COMPLETE");
        }

        private static void LoadDavisAutoShopInterior()
        {
            Function.Call((Hash)0x0888C3502DBBEEF5, 1); // _LOAD_MP_DLC_MAPS
            Script.Wait(500);
            foreach (string ipl in DAVIS_AUTO_SHOP_IPLS)
                Function.Call(Hash.REQUEST_IPL, ipl);
            Script.Wait(1000);

            int interior = Function.Call<int>(
                Hash.GET_INTERIOR_AT_COORDS, -1350f, 160f, -100f);
            if (interior == 0)
            {
                Log("LoadDavisAutoShopInterior: WARNING - interior not found");
                return;
            }
            ApplyDavisAutoShopCustomization(interior);
            Log($"LoadDavisAutoShopInterior: interior={interior} configured");
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
                ParkingSlot slot = DavisGarageSlots[stored.Slot];
                Model model = new Model(stored.Model);
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
                float deltaZ = VehicleList.GetSpawnDeltaZ(stored.Model);
                Function.Call(Hash.SET_ENTITY_COORDS, vehicle,
                    slot.Position.X, slot.Position.Y, slot.Position.Z + deltaZ,
                    false, false, false, true);
                Function.Call(Hash.SET_ENTITY_HEADING, vehicle, slot.Heading);
                CenterVehicleInParkingSpace(
                    vehicle, slot, deltaZ, stored.Model, "Davis");
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
            }
            catch (Exception ex)
            {
                LogException("DavisCustomizationSave", ex);
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
                if (!IsCompleteJson(json))
                    throw new InvalidDataException("Incomplete Davis garage save");
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
                    try { DavisParseJson(File.ReadAllText(backup)); }
                    catch (Exception backupEx)
                    {
                        LogException("DavisLoad.Backup", backupEx);
                    }
                }
            }
        }

        private static bool DavisSave()
        {
            try
            {
                AtomicWriteText(DAVIS_SAVE_PATH, DavisBuildJson());
                return true;
            }
            catch (Exception ex)
            {
                LogException("DavisSave", ex);
                return false;
            }
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
