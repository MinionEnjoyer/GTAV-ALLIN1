using ALLIN1;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class NpcPhysicsExperimentPolicyTests
    {
        [Fact]
        public void Ambient_human_with_fresh_weapon_damage_can_react()
        {
            Assert.True(ShouldReact());
        }

        [Theory]
        [InlineData(false, true, true, true, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, false, true, true, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, false, true, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, false, false, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, true, false, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, true, false, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, true, false, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, false, true, true, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, false, 200, 180, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, true, 200, 200, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, true, 200, 201, 1000)]
        [InlineData(true, true, true, true, false, false, false, false, true, 200, 180, 899)]
        public void Unsafe_or_stale_candidates_are_excluded(
            bool enabled, bool exists, bool human, bool alive, bool player,
            bool mission, bool persistent, bool inVehicle, bool weaponDamage,
            int oldHealth, int newHealth, int elapsed)
        {
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReact(
                enabled, exists, human, alive, player, mission, persistent,
                inVehicle, weaponDamage, oldHealth, newHealth, elapsed));
        }

        [Theory]
        [InlineData(31086, (int)NpcPhysicsBodyRegion.Head)]
        [InlineData(39317, (int)NpcPhysicsBodyRegion.Neck)]
        [InlineData(23553, (int)NpcPhysicsBodyRegion.Gut)]
        [InlineData(18905, (int)NpcPhysicsBodyRegion.Arm)]
        [InlineData(63931, (int)NpcPhysicsBodyRegion.Leg)]
        [InlineData(24817, (int)NpcPhysicsBodyRegion.Torso)]
        public void Damage_bones_map_to_region_specific_reactions(
            int bone, int expected)
        {
            Assert.Equal((NpcPhysicsBodyRegion)expected,
                NpcPhysicsExperimentPolicy.ClassifyBone(bone));
        }

        [Fact]
        public void Fresh_lethal_damage_can_receive_a_death_reaction()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldReactToLethalDamage(
                true, true, false, false, false, false, true,
                100, 0, true, 1000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReactToLethalDamage(
                true, true, false, true, false, false, true,
                100, 0, true, 1000));
        }

        [Fact]
        public void Slow_close_vehicle_contact_can_balance_without_a_shot()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldReactToVehicleBump(
                true, true, true, false, true, true,
                2.5f, 1.5f, 800));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReactToVehicleBump(
                true, true, true, false, true, true,
                0.5f, 1.5f, 800));
        }

        [Fact]
        public void Blast_reaction_requires_fresh_damage_near_an_explosion()
        {
            Assert.True(NpcPhysicsExperimentPolicy.ShouldReactToBlast(
                true, true, true, false, true, true, 1000));
            Assert.False(NpcPhysicsExperimentPolicy.ShouldReactToBlast(
                true, true, true, false, true, false, 1000));
        }

        [Fact]
        public void Trauma_chances_are_repeatable_for_the_same_event()
        {
            bool first = NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 30);
            bool second = NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 30);
            Assert.Equal(first, second);
            Assert.False(NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 0));
            Assert.True(NpcPhysicsExperimentPolicy.DeterministicChance(
                42, 3, 100));
        }

        private static bool ShouldReact()
        {
            return NpcPhysicsExperimentPolicy.ShouldReact(
                enabled: true,
                exists: true,
                isHuman: true,
                isAlive: true,
                isPlayer: false,
                isMissionEntity: false,
                isPersistent: false,
                isInVehicle: false,
                hasWeaponDamage: true,
                previousHealth: 200,
                currentHealth: 180,
                elapsedSinceReactionMs: 1000);
        }
    }
}
