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
