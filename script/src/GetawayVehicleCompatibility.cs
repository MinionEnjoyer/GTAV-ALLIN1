using System;
using System.Collections.Generic;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal enum StoryGetawayMission
    {
        None,
        Agency,
        FbiBlitz,
        Finale,
    }

    internal enum GetawayVehicleDenial
    {
        None,
        Missing,
        Dead,
        NotDriveable,
        OnFire,
        ExcludedTransportType,
        PoliceVehicle,
        TaxiPassenger,
        ExistingVanillaRejection,
        BlacklistedModel,
        StoryPersonalVehicle,
        Damaged,
        AccelerationTooLow,
        TopSpeedTooLow,
        InsufficientSeats,
    }

    internal readonly struct GetawayVehicleFacts
    {
        internal GetawayVehicleFacts(
            bool exists,
            bool dead,
            bool driveable,
            bool onFire,
            bool excludedTransportType,
            bool policeVehicle,
            bool taxiPassenger,
            bool blacklistedModel,
            bool storyPersonalVehicle,
            int entityHealth,
            float engineHealth,
            float acceleration,
            float estimatedMaxSpeed,
            int maximumPassengers)
        {
            Exists = exists;
            Dead = dead;
            Driveable = driveable;
            OnFire = onFire;
            ExcludedTransportType = excludedTransportType;
            PoliceVehicle = policeVehicle;
            TaxiPassenger = taxiPassenger;
            BlacklistedModel = blacklistedModel;
            StoryPersonalVehicle = storyPersonalVehicle;
            EntityHealth = entityHealth;
            EngineHealth = engineHealth;
            Acceleration = acceleration;
            EstimatedMaxSpeed = estimatedMaxSpeed;
            MaximumPassengers = maximumPassengers;
        }

        internal bool Exists { get; }
        internal bool Dead { get; }
        internal bool Driveable { get; }
        internal bool OnFire { get; }
        internal bool ExcludedTransportType { get; }
        internal bool PoliceVehicle { get; }
        internal bool TaxiPassenger { get; }
        internal bool BlacklistedModel { get; }
        internal bool StoryPersonalVehicle { get; }
        internal int EntityHealth { get; }
        internal float EngineHealth { get; }
        internal float Acceleration { get; }
        internal float EstimatedMaxSpeed { get; }
        internal int MaximumPassengers { get; }
    }

    /// <summary>
    /// The eligibility checks used by Rockstar's three Story Mode getaway-car
    /// preparation scripts.  Keeping this policy free of native calls makes the
    /// strict thresholds and the mission-specific seating rule testable.
    /// </summary>
    internal static class GetawayVehiclePolicy
    {
        internal const int MinimumHealth = 300;
        internal const float MinimumAccelerationExclusive = 0.165f;
        internal const float MinimumEstimatedMaxSpeedExclusive = 31f;
        internal const int MinimumPassengersForFourSeatMission = 3;

        internal static bool RequiresFourSeats(StoryGetawayMission mission)
        {
            return mission == StoryGetawayMission.Agency ||
                mission == StoryGetawayMission.Finale;
        }

        internal static GetawayVehicleDenial Evaluate(
            StoryGetawayMission mission, GetawayVehicleFacts facts)
        {
            if (!facts.Exists) return GetawayVehicleDenial.Missing;
            if (facts.Dead) return GetawayVehicleDenial.Dead;
            if (!facts.Driveable) return GetawayVehicleDenial.NotDriveable;
            if (facts.OnFire) return GetawayVehicleDenial.OnFire;
            if (facts.ExcludedTransportType)
                return GetawayVehicleDenial.ExcludedTransportType;
            if (facts.PoliceVehicle)
                return GetawayVehicleDenial.PoliceVehicle;
            if (facts.TaxiPassenger)
                return GetawayVehicleDenial.TaxiPassenger;
            if (facts.BlacklistedModel)
                return GetawayVehicleDenial.BlacklistedModel;
            if (facts.Acceleration <= MinimumAccelerationExclusive)
                return GetawayVehicleDenial.AccelerationTooLow;
            if (facts.EstimatedMaxSpeed <=
                MinimumEstimatedMaxSpeedExclusive)
                return GetawayVehicleDenial.TopSpeedTooLow;
            if (facts.StoryPersonalVehicle)
                return GetawayVehicleDenial.StoryPersonalVehicle;
            if (facts.EntityHealth < MinimumHealth ||
                facts.EngineHealth < MinimumHealth)
                return GetawayVehicleDenial.Damaged;
            if (RequiresFourSeats(mission) &&
                facts.MaximumPassengers <
                MinimumPassengersForFourSeatMission)
                return GetawayVehicleDenial.InsufficientSeats;
            return GetawayVehicleDenial.None;
        }
    }

    /// <summary>
    /// Lets persistent ALLIN1 DLC vehicles take Rockstar's existing decorated
    /// getaway-vehicle path.  Vanilla otherwise rejects these cars solely
    /// because ALLIN1 keeps delivered and replacement traffic mission-owned.
    /// No decorator is added until every vanilla eligibility check passes.
    /// </summary>
    public sealed class GetawayVehicleCompatibility : Script
    {
        private const string ValidDecorator = "GetawayVehicleValid";
        private static readonly int AgencyScript =
            ModelHash("agency_prep2amb");
        private static readonly int FbiBlitzScript =
            ModelHash("fbi4_prep3amb");
        private static readonly int FinaleScript =
            ModelHash("finale_heist_prepeamb");

        private static readonly HashSet<int> DlcModelHashes =
            BuildDlcModelHashes();
        private static readonly Dictionary<int, string> DlcModelNames =
            BuildDlcModelNames();
        private static readonly HashSet<int> BlacklistedModelHashes =
            new HashSet<int>
            {
                ModelHash("trash"),
                ModelHash("towtruck"),
                ModelHash("ambulance"),
                ModelHash("barracks2"),
                ModelHash("stretch"),
                ModelHash("phantom"),
                ModelHash("packer"),
                ModelHash("blazer"),
                ModelHash("blazer2"),
                ModelHash("sentinel2"),
            };

        private StoryGetawayMission _lastMission;
        private int _lastVehicleHandle;
        private GetawayVehicleDenial _lastDenial;
        private bool _lastDecoratorPresent;

        public GetawayVehicleCompatibility()
        {
            Tick += OnTick;
            Interval = 100;
        }

        internal static bool IsAllIn1DlcModel(int modelHash)
        {
            return DlcModelHashes.Contains(modelHash);
        }

        internal static int ModelHash(string value)
        {
            // Rockstar's case-insensitive Jenkins one-at-a-time hash.  Keeping
            // this managed avoids a native dependency during unit tests.
            uint hash = 0;
            foreach (char raw in value ?? string.Empty)
            {
                hash += char.ToLowerInvariant(raw);
                hash += hash << 10;
                hash ^= hash >> 6;
            }
            hash += hash << 3;
            hash ^= hash >> 11;
            hash += hash << 15;
            return unchecked((int)hash);
        }

        private static HashSet<int> BuildDlcModelHashes()
        {
            var result = new HashSet<int>();
            foreach (string model in VehicleList.All)
                result.Add(ModelHash(model));
            return result;
        }

        private static Dictionary<int, string> BuildDlcModelNames()
        {
            var result = new Dictionary<int, string>();
            foreach (string model in VehicleList.All)
            {
                int hash = ModelHash(model);
                if (!result.ContainsKey(hash)) result.Add(hash, model);
            }
            return result;
        }

        private void OnTick(object sender, EventArgs args)
        {
            try
            {
                StoryGetawayMission mission = DetectMission();
                if (mission == StoryGetawayMission.None)
                {
                    ResetObservation();
                    return;
                }

                Ped player = Game.Player.Character;
                if (player == null || !player.Exists() || player.IsDead ||
                    !player.IsInVehicle())
                {
                    Observe(mission, 0, GetawayVehicleDenial.Missing, false,
                        "");
                    return;
                }

                Vehicle vehicle = player.CurrentVehicle;
                if (vehicle == null || !vehicle.Exists()) return;

                int modelHash = vehicle.Model.Hash;
                if (!DlcModelHashes.Contains(modelHash))
                {
                    ResetVehicleObservation(mission);
                    return;
                }

                string modelName = DlcModelNames.TryGetValue(modelHash,
                    out string resolvedName) ? resolvedName :
                    modelHash.ToString("X8");
                bool decoratorPresent = Function.Call<bool>(
                    Hash.DECOR_EXIST_ON, vehicle.Handle, ValidDecorator);
                if (decoratorPresent)
                {
                    bool decoratorValid = Function.Call<bool>(
                        Hash.DECOR_GET_BOOL, vehicle.Handle, ValidDecorator);
                    Observe(mission, vehicle.Handle,
                        decoratorValid ? GetawayVehicleDenial.None :
                            GetawayVehicleDenial.ExistingVanillaRejection,
                        true, modelName);
                    return;
                }

                GetawayVehicleFacts facts = CaptureFacts(
                    player, vehicle, modelHash);
                GetawayVehicleDenial denial =
                    GetawayVehiclePolicy.Evaluate(mission, facts);
                Observe(mission, vehicle.Handle, denial, false, modelName);
                if (denial != GetawayVehicleDenial.None) return;

                bool decorated = Function.Call<bool>(Hash.DECOR_SET_BOOL,
                    vehicle.Handle, ValidDecorator, true);
                if (decorated)
                {
                    _lastDecoratorPresent = true;
                    ClientLog.Info("GetawayVehicle", "dlc_vehicle_approved",
                        BuildLogFields(mission, vehicle, modelName, facts,
                            GetawayVehicleDenial.None));
                }
                else
                {
                    ClientLog.Warn("GetawayVehicle",
                        "decorator_write_failed",
                        BuildLogFields(mission, vehicle, modelName, facts,
                            GetawayVehicleDenial.None));
                }
            }
            catch (Exception ex)
            {
                ClientLog.Error("GetawayVehicle", "compatibility_tick_failed",
                    ex);
            }
        }

        private static StoryGetawayMission DetectMission()
        {
            // If scripts overlap during a transition, retain the stricter
            // four-seat requirement used by Agency and Finale.
            if (IsScriptRunning(AgencyScript))
                return StoryGetawayMission.Agency;
            if (IsScriptRunning(FinaleScript))
                return StoryGetawayMission.Finale;
            if (IsScriptRunning(FbiBlitzScript))
                return StoryGetawayMission.FbiBlitz;
            return StoryGetawayMission.None;
        }

        private static bool IsScriptRunning(int scriptHash)
        {
            return Function.Call<int>(
                Hash.GET_NUMBER_OF_THREADS_RUNNING_THE_SCRIPT_WITH_THIS_HASH,
                scriptHash) > 0;
        }

        private static GetawayVehicleFacts CaptureFacts(
            Ped player, Vehicle vehicle, int modelHash)
        {
            bool excludedTransport =
                Function.Call<bool>(Hash.IS_THIS_MODEL_A_BOAT, modelHash) ||
                Function.Call<bool>(Hash.IS_THIS_MODEL_A_HELI, modelHash) ||
                Function.Call<bool>(Hash.IS_THIS_MODEL_A_PLANE, modelHash) ||
                Function.Call<bool>(Hash.IS_THIS_MODEL_A_TRAIN, modelHash);
            bool policeVehicle = Function.Call<bool>(
                Hash.IS_PED_IN_ANY_POLICE_VEHICLE, player.Handle);
            bool taxiPassenger = IsTaxiPassenger(player, vehicle);
            float acceleration = Function.Call<float>(
                Hash.GET_VEHICLE_MODEL_ACCELERATION, modelHash);
            float maxSpeed = Function.Call<float>(
                Hash.GET_VEHICLE_MODEL_ESTIMATED_MAX_SPEED, modelHash);
            int maximumPassengers = Function.Call<int>(
                Hash.GET_VEHICLE_MAX_NUMBER_OF_PASSENGERS, vehicle.Handle);

            return new GetawayVehicleFacts(
                vehicle.Exists(),
                vehicle.IsDead,
                vehicle.IsDriveable,
                vehicle.IsOnFire,
                excludedTransport,
                policeVehicle,
                taxiPassenger,
                BlacklistedModelHashes.Contains(modelHash),
                GarageManager.IsStoryPersonalVehicle(vehicle),
                vehicle.Health,
                vehicle.EngineHealth,
                acceleration,
                maxSpeed,
                maximumPassengers);
        }

        private static bool IsTaxiPassenger(Ped player, Vehicle vehicle)
        {
            if (!Function.Call<bool>(Hash.IS_PED_IN_ANY_TAXI, player.Handle))
                return false;
            for (int seat = 0; seat <= 2; seat++)
            {
                int occupant = Function.Call<int>(Hash.GET_PED_IN_VEHICLE_SEAT,
                    vehicle.Handle, seat, false);
                if (occupant == player.Handle) return true;
            }
            return false;
        }

        private void Observe(
            StoryGetawayMission mission,
            int vehicleHandle,
            GetawayVehicleDenial denial,
            bool decoratorPresent,
            string modelName)
        {
            if (_lastMission == mission &&
                _lastVehicleHandle == vehicleHandle &&
                _lastDenial == denial &&
                _lastDecoratorPresent == decoratorPresent)
                return;

            _lastMission = mission;
            _lastVehicleHandle = vehicleHandle;
            _lastDenial = denial;
            _lastDecoratorPresent = decoratorPresent;

            if (vehicleHandle == 0) return;
            ClientLog.Info("GetawayVehicle", "dlc_vehicle_evaluated",
                new Dictionary<string, object>
                {
                    { "mission", mission.ToString() },
                    { "vehicle", vehicleHandle },
                    { "model", modelName },
                    { "denial", denial.ToString() },
                    { "decorator_present", decoratorPresent },
                    { "requires_four_seats",
                        GetawayVehiclePolicy.RequiresFourSeats(mission) },
                });
        }

        private static Dictionary<string, object> BuildLogFields(
            StoryGetawayMission mission,
            Vehicle vehicle,
            string modelName,
            GetawayVehicleFacts facts,
            GetawayVehicleDenial denial)
        {
            return new Dictionary<string, object>
            {
                { "mission", mission.ToString() },
                { "vehicle", vehicle.Handle },
                { "model", modelName },
                { "denial", denial.ToString() },
                { "entity_health", facts.EntityHealth },
                { "engine_health", facts.EngineHealth },
                { "acceleration", facts.Acceleration },
                { "estimated_max_speed", facts.EstimatedMaxSpeed },
                { "maximum_passengers", facts.MaximumPassengers },
                { "requires_four_seats",
                    GetawayVehiclePolicy.RequiresFourSeats(mission) },
            };
        }

        private void ResetObservation()
        {
            _lastMission = StoryGetawayMission.None;
            _lastVehicleHandle = 0;
            _lastDenial = GetawayVehicleDenial.None;
            _lastDecoratorPresent = false;
        }

        private void ResetVehicleObservation(StoryGetawayMission mission)
        {
            _lastMission = mission;
            _lastVehicleHandle = 0;
            _lastDenial = GetawayVehicleDenial.None;
            _lastDecoratorPresent = false;
        }
    }
}
