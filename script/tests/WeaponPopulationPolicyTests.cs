using GTA;
using System;
using System.Linq;
using Mono.Cecil;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class WeaponPopulationPolicyTests
    {
        [Theory]
        [InlineData(0, 200d, false, false)]
        [InlineData(1, 2d, false, true)]
        [InlineData(1, 1.99d, false, false)]
        [InlineData(6, 0d, true, true)]
        [InlineData(6, 0d, false, false)]
        [InlineData(12, 0d, false, true)]
        public void Scan_budget_yields_without_starving_after_an_expensive_query(
            int inspected, double elapsed, bool throttled, bool expected)
        {
            Assert.Equal(expected,
                WeaponPopulationPolicy.ShouldStopScan(inspected, elapsed, throttled));
        }

        [Theory]
        [InlineData("pistols", true)]
        [InlineData("smgs", true)]
        [InlineData("shotguns", true)]
        [InlineData("rifles", true)]
        [InlineData("heavy", false)]
        [InlineData("machineguns", false)]
        public void Only_common_firearm_tiers_are_replaceable(string category,
            bool expected)
        {
            Assert.Equal(expected, WeaponPopulationPolicy.IsReplaceableCategory(category));
        }

        [Theory]
        [InlineData(0.499999, true)]
        [InlineData(0.5, false)]
        [InlineData(0.999999, false)]
        public void Replacement_chance_is_one_per_candidate(double roll,
            bool expected)
        {
            Assert.Equal(expected, WeaponPopulationPolicy.ShouldReplaceCandidate(0.5f,
                () => roll));
        }

        [Fact]
        public void Replacement_chance_endpoints_do_not_consume_randomness()
        {
            int calls = 0;
            Func<double> unexpectedRoll = () => { calls++; return 0d; };
            Assert.False(WeaponPopulationPolicy.ShouldReplaceCandidate(0f,
                unexpectedRoll));
            Assert.True(WeaponPopulationPolicy.ShouldReplaceCandidate(1f,
                unexpectedRoll));
            Assert.Equal(0, calls);
        }

        [Fact]
        public void Scripted_scenario_tasks_are_not_ambient_candidates()
        {
            Assert.False(WeaponPopulationPolicy.IsAmbientCandidate(false, false,
                false, false, false, false, false, false, false, false, false,
                false, 1, true));
        }

        [Theory]
        [InlineData(true, true, true, true, true, true)]
        [InlineData(false, true, true, true, true, false)]
        [InlineData(true, false, true, true, true, false)]
        [InlineData(true, true, false, true, true, false)]
        [InlineData(true, true, true, false, true, false)]
        [InlineData(true, true, true, true, false, false)]
        public void Old_weapon_is_kept_until_new_owned_same_tier_weapon_is_proven(
            bool ambient, bool armed, bool sameCategory, bool valid, bool owned,
            bool expected)
        {
            Assert.Equal(expected, WeaponPopulationPolicy.CanReplace(ambient, armed,
                sameCategory, valid, owned));
        }

        [Theory]
        [InlineData(true, true, true, true, true, true, true)]
        [InlineData(true, true, true, true, true, false, false)]
        [InlineData(true, true, false, true, true, true, false)]
        public void Old_weapon_is_not_removed_until_new_weapon_is_selected(
            bool ambient, bool armed, bool sameCategory, bool valid, bool owned,
            bool selected, bool expected)
        {
            Assert.Equal(expected,
                WeaponPopulationPolicy.CanCommitSelectedReplacement(ambient,
                    armed, sameCategory, valid, owned, selected));
        }

        [Fact]
        public void Native_groups_must_match_the_expected_civilian_tier()
        {
            Assert.True(WeaponPopulationPolicy.NativeGroupsMatchCategory("pistols",
                (uint)WeaponGroup.Pistol, (uint)WeaponGroup.Pistol));
            Assert.True(WeaponPopulationPolicy.NativeGroupsMatchCategory("smgs",
                (uint)WeaponGroup.SMG, (uint)WeaponGroup.SMG));
            Assert.True(WeaponPopulationPolicy.NativeGroupsMatchCategory("shotguns",
                (uint)WeaponGroup.Shotgun, (uint)WeaponGroup.Shotgun));
            Assert.True(WeaponPopulationPolicy.NativeGroupsMatchCategory("rifles",
                (uint)WeaponGroup.AssaultRifle, (uint)WeaponGroup.AssaultRifle));
            Assert.False(WeaponPopulationPolicy.NativeGroupsMatchCategory("rifles",
                (uint)WeaponGroup.SMG, (uint)WeaponGroup.SMG));
            Assert.False(WeaponPopulationPolicy.NativeGroupsMatchCategory("smgs",
                (uint)WeaponGroup.SMG, (uint)WeaponGroup.AssaultRifle));
        }

        [Theory]
        [InlineData(0, 1)]
        [InlineData(25, 25)]
        [InlineData(1000, 999)]
        public void Replacement_ammo_is_bounded_without_unarmed_output(int ammo,
            int expected)
        {
            Assert.Equal(expected, WeaponPopulationPolicy.BoundedAmmo(ammo));
        }

        [Theory]
        [InlineData(false, true, false, false, false, false, false, false)]
        [InlineData(true, true, false, false, false, false, false, true)]
        [InlineData(false, false, false, false, false, false, false, true)]
        [InlineData(false, true, true, false, false, false, false, true)]
        [InlineData(false, true, false, true, false, false, false, true)]
        [InlineData(false, true, false, false, true, false, false, true)]
        [InlineData(false, true, false, false, false, true, false, true)]
        [InlineData(false, true, false, false, false, false, true, true)]
        public void Unsafe_global_states_suppress_injection(bool loading, bool player,
            bool mission, bool cutscene, bool switching, bool interior,
            bool garage, bool expected)
        {
            Assert.Equal(expected, WeaponPopulationPolicy.IsSuppressed(loading,
                player, mission, cutscene, switching, interior, garage));
        }

        [Theory]
        [InlineData(true, true, false, false, false, false, false,
            "game loading")]
        [InlineData(false, false, false, false, false, false, false,
            "player unavailable")]
        [InlineData(false, true, true, false, false, false, false,
            "mission active")]
        [InlineData(false, true, false, true, false, false, false,
            "cutscene active")]
        [InlineData(false, true, false, false, true, false, false,
            "player switch in progress")]
        [InlineData(false, true, false, false, false, true, false,
            "player is indoors")]
        [InlineData(false, true, false, false, false, false, true,
            "garage transition in progress")]
        [InlineData(false, true, false, false, false, false, false,
            "")]
        public void Suppression_reason_matches_the_conservative_gate(bool loading,
            bool player, bool mission, bool cutscene, bool switching,
            bool interior, bool garage, string expected)
        {
            Assert.Equal(expected, WeaponPopulationPolicy.SuppressionReason(loading,
                player, mission, cutscene, switching, interior, garage));
            Assert.Equal(!string.IsNullOrEmpty(expected),
                WeaponPopulationPolicy.IsSuppressed(loading, player,
                    mission, cutscene, switching, interior, garage));
        }

        [Fact]
        public void Mission_preference_only_bypasses_the_global_mission_pause()
        {
            // Every combination of the other safety states must behave the
            // same with mission activity enabled as it would outside a mission.
            for (int mask = 0; mask < 64; mask++)
            {
                bool loading = (mask & 1) != 0, available = (mask & 2) == 0,
                    cutscene = (mask & 4) != 0, switching = (mask & 8) != 0,
                    interior = (mask & 16) != 0, garage = (mask & 32) != 0;
                string ordinary = WeaponPopulationPolicy.SuppressionReason(loading,
                    available, false, cutscene, switching, interior, garage);
                string duringMission = WeaponPopulationPolicy.SuppressionReason(loading,
                    available, true, cutscene, switching, interior, garage, true);
                Assert.Equal(ordinary, duringMission);
                Assert.Equal(!string.IsNullOrEmpty(ordinary),
                    WeaponPopulationPolicy.IsSuppressed(loading, available, true,
                        cutscene, switching, interior, garage, true));
                Assert.True(WeaponPopulationPolicy.IsSuppressed(loading, available,
                    true, cutscene, switching, interior, garage, false));
            }
            Assert.False(WeaponPopulationPolicy.IsSuppressed(false, true, true,
                false, false, false, false, true));
        }

        [Theory]
        [InlineData(true, false, false)]
        [InlineData(false, true, false)]
        [InlineData(false, false, true)]
        public void Mission_preference_does_not_make_protected_peds_eligible(
            bool missionEntity, bool scriptedTask, bool combat)
        {
            Assert.False(WeaponPopulationPolicy.IsSuppressed(false, true, true,
                false, false, false, false, true));
            Assert.False(WeaponPopulationPolicy.IsAmbientCandidate(false, false,
                missionEntity, false, combat, false, false, false, false, false,
                false, false, 1, scriptedTask));
        }

        [Fact]
        public void Runtime_reads_and_uses_the_mission_preference_without_replacing_the_master_gate()
        {
            using (var assembly = AssemblyDefinition.ReadAssembly(
                typeof(WeaponPopulationInjector).Assembly.Location))
            {
                var injector = assembly.MainModule.Types.Single(t =>
                    t.Name == nameof(WeaponPopulationInjector));
                var refresh = injector.Methods.Single(m => m.Name == "RefreshConfiguration");
                Assert.Contains(refresh.Body.Instructions, i =>
                    i.OpCode.Code == Mono.Cecil.Cil.Code.Stfld &&
                    (i.Operand as FieldReference)?.Name == "_activeDuringMissions");
                Assert.Contains(refresh.Body.Instructions.Select(i => i.Operand)
                    .OfType<MethodReference>(), m => m.Name == "OptionalBoolean");
                var pause = injector.Methods.Single(m => m.Name == "GlobalPauseReason");
                Assert.Contains(pause.Body.Instructions, i =>
                    i.OpCode.Code == Mono.Cecil.Cil.Code.Ldfld &&
                    (i.Operand as FieldReference)?.Name == "_activeDuringMissions");

                var tick = injector.Methods.Single(m => m.Name == "OnTick").Body.Instructions;
                int master = tick.ToList().FindIndex(i =>
                    i.OpCode.Code == Mono.Cecil.Cil.Code.Ldfld &&
                    (i.Operand as FieldReference)?.Name == "_enabled");
                int missionGate = tick.ToList().FindIndex(i =>
                    (i.Operand as MethodReference)?.Name == "GlobalPauseReason");
                Assert.True(master >= 0 && missionGate > master);
                Assert.Contains(tick.Skip(master).Take(missionGate - master),
                    i => i.OpCode.Code == Mono.Cecil.Cil.Code.Ret);
            }
        }

        [Fact]
        public void Wanted_level_cannot_pause_weapon_scans_or_commit_validation()
        {
            using (var assembly = AssemblyDefinition.ReadAssembly(
                typeof(WeaponPopulationInjector).Assembly.Location))
            {
                var injector = assembly.MainModule.Types.Single(t =>
                    t.Name == nameof(WeaponPopulationInjector));
                var calls = injector.Methods.Where(m => m.HasBody)
                    .SelectMany(m => m.Body.Instructions)
                    .Select(i => i.Operand).OfType<MethodReference>();
                Assert.DoesNotContain(calls, m => m.Name == "get_WantedLevel");

                // Both scan entry and per-ped revalidation keep the remaining
                // shared pause policy, without a separate wanted-level gate.
                foreach (string name in new[] { "OnTick", "IsGloballySuppressed" })
                    Assert.Contains(injector.Methods.Single(m => m.Name == name)
                        .Body.Instructions.Select(i => i.Operand)
                        .OfType<MethodReference>(), m => m.Name == "GlobalPauseReason");
                Assert.Contains(injector.Methods.Single(m => m.Name == "GlobalPauseReason")
                    .Body.Instructions.Select(i => i.Operand).OfType<MethodReference>(),
                    m => m.DeclaringType.Name == nameof(WeaponPopulationPolicy) &&
                        m.Name == "SuppressionReason");
            }
        }
    }
}
