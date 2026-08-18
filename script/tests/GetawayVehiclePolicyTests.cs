using System.Collections.Generic;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GetawayVehiclePolicyTests
    {
        private static GetawayVehicleFacts ValidFacts(
            int maximumPassengers = 3,
            int health = 1000,
            float engineHealth = 1000f,
            float acceleration = 0.2f,
            float topSpeed = 40f,
            bool exists = true,
            bool dead = false,
            bool driveable = true,
            bool onFire = false,
            bool excludedTransport = false,
            bool police = false,
            bool taxiPassenger = false,
            bool blacklisted = false,
            bool personal = false)
        {
            return new GetawayVehicleFacts(
                exists, dead, driveable, onFire, excludedTransport, police,
                taxiPassenger, blacklisted, personal, health, engineHealth,
                acceleration, topSpeed, maximumPassengers);
        }

        [Theory]
        [InlineData((int)StoryGetawayMission.Agency, true)]
        [InlineData((int)StoryGetawayMission.Finale, true)]
        [InlineData((int)StoryGetawayMission.FbiBlitz, false)]
        [InlineData((int)StoryGetawayMission.None, false)]
        public void Four_seat_requirement_matches_the_story_script(
            int missionValue, bool expected)
        {
            Assert.Equal(expected,
                GetawayVehiclePolicy.RequiresFourSeats(
                    (StoryGetawayMission)missionValue));
        }

        [Theory]
        [InlineData((int)StoryGetawayMission.Agency, 2,
            (int)GetawayVehicleDenial.InsufficientSeats)]
        [InlineData((int)StoryGetawayMission.Finale, 2,
            (int)GetawayVehicleDenial.InsufficientSeats)]
        [InlineData((int)StoryGetawayMission.FbiBlitz, 0,
            (int)GetawayVehicleDenial.None)]
        [InlineData((int)StoryGetawayMission.Agency, 3,
            (int)GetawayVehicleDenial.None)]
        public void Passenger_capacity_is_mission_specific(
            int missionValue,
            int maximumPassengers,
            int expectedValue)
        {
            Assert.Equal((GetawayVehicleDenial)expectedValue,
                GetawayVehiclePolicy.Evaluate(
                    (StoryGetawayMission)missionValue,
                    ValidFacts(maximumPassengers)));
        }

        [Theory]
        [InlineData(299, 1000f, (int)GetawayVehicleDenial.Damaged)]
        [InlineData(300, 299.99f, (int)GetawayVehicleDenial.Damaged)]
        [InlineData(300, 300f, (int)GetawayVehicleDenial.None)]
        public void Health_threshold_is_inclusive_at_300(
            int health, float engineHealth, int expectedValue)
        {
            Assert.Equal((GetawayVehicleDenial)expectedValue,
                GetawayVehiclePolicy.Evaluate(
                StoryGetawayMission.FbiBlitz,
                ValidFacts(health: health, engineHealth: engineHealth)));
        }

        [Theory]
        [InlineData(0.1649f, 40f,
            (int)GetawayVehicleDenial.AccelerationTooLow)]
        [InlineData(0.165f, 40f,
            (int)GetawayVehicleDenial.AccelerationTooLow)]
        [InlineData(0.1651f, 31f,
            (int)GetawayVehicleDenial.TopSpeedTooLow)]
        [InlineData(0.1651f, 31.01f,
            (int)GetawayVehicleDenial.None)]
        public void Performance_thresholds_are_strictly_greater_than_vanilla_limits(
            float acceleration, float topSpeed, int expectedValue)
        {
            Assert.Equal((GetawayVehicleDenial)expectedValue,
                GetawayVehiclePolicy.Evaluate(
                StoryGetawayMission.FbiBlitz,
                ValidFacts(acceleration: acceleration, topSpeed: topSpeed)));
        }

        [Fact]
        public void Non_road_and_restricted_vehicles_are_rejected()
        {
            Assert.Equal(GetawayVehicleDenial.ExcludedTransportType,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(excludedTransport: true)));
            Assert.Equal(GetawayVehicleDenial.PoliceVehicle,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(police: true)));
            Assert.Equal(GetawayVehicleDenial.TaxiPassenger,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(taxiPassenger: true)));
            Assert.Equal(GetawayVehicleDenial.BlacklistedModel,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(blacklisted: true)));
            Assert.Equal(GetawayVehicleDenial.StoryPersonalVehicle,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(personal: true)));
        }

        [Fact]
        public void Broken_burning_and_dead_vehicles_are_rejected_before_performance()
        {
            Assert.Equal(GetawayVehicleDenial.Dead,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(dead: true, acceleration: 0f)));
            Assert.Equal(GetawayVehicleDenial.NotDriveable,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(driveable: false)));
            Assert.Equal(GetawayVehicleDenial.OnFire,
                GetawayVehiclePolicy.Evaluate(
                    StoryGetawayMission.FbiBlitz,
                    ValidFacts(onFire: true)));
        }

        [Fact]
        public void Generated_catalog_models_are_recognized_by_the_bridge()
        {
            Assert.True(GetawayVehicleCompatibility.IsAllIn1DlcModel(
                GetawayVehicleCompatibility.ModelHash("deity")));
            Assert.True(GetawayVehicleCompatibility.IsAllIn1DlcModel(
                GetawayVehicleCompatibility.ModelHash("buffalo4")));
            Assert.False(GetawayVehicleCompatibility.IsAllIn1DlcModel(
                GetawayVehicleCompatibility.ModelHash("tailgater")));
        }

        [Fact]
        public void Every_generated_DLC_vehicle_is_covered_without_hash_collisions()
        {
            var hashes = new HashSet<int>();
            foreach (string model in VehicleList.All)
            {
                int hash = GetawayVehicleCompatibility.ModelHash(model);
                Assert.True(hashes.Add(hash),
                    $"Duplicate model hash for {model}");
                Assert.True(
                    GetawayVehicleCompatibility.IsAllIn1DlcModel(hash),
                    $"Missing getaway coverage for {model}");
            }
            Assert.Equal(VehicleList.All.Length, hashes.Count);
        }

        [Theory]
        [InlineData("adder", -1216765807)]
        [InlineData("akula", 1181327175)]
        [InlineData("tailgater", -1008861746)]
        public void Managed_joaat_matches_known_Rockstar_model_hashes(
            string model, int expected)
        {
            Assert.Equal(expected,
                GetawayVehicleCompatibility.ModelHash(model));
            Assert.Equal(expected,
                GetawayVehicleCompatibility.ModelHash(model.ToUpperInvariant()));
        }
    }
}
