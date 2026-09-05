using System.Collections.Generic;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class WeaponComponentDefaultsTests
    {
        private static readonly int Scope = (int)GTA.WeaponAttachmentPoint.Scope2;
        private static readonly int Supp = (int)GTA.WeaponAttachmentPoint.Supp;
        private static WeaponComponentDefaults.Entry E(int hash, int point, bool value) =>
            new WeaponComponentDefaults.Entry(hash, point, value);

        [Fact]
        public void Default_is_native_metadata_not_label_or_first_entry()
        {
            var entries = new[] { E(10, Scope, false), E(20, Supp, true), E(30, Scope, true) };
            Assert.Equal(30, WeaponComponentDefaults.SelectDefault(entries, Scope));
        }

        [Fact]
        public void Duplicate_story_and_online_records_are_safe()
        {
            Assert.Equal(30, WeaponComponentDefaults.SelectDefault(new[] {
                E(30, Scope, true), E(30, Scope, true) }, Scope));
        }

        [Fact]
        public void Conflicting_defaults_fail_closed()
        {
            Assert.Equal(0, WeaponComponentDefaults.SelectDefault(new[] {
                E(30, Scope, true), E(40, Scope, true) }, Scope));
        }

        [Fact]
        public void Missing_or_zero_default_never_invents_component()
        {
            Assert.Equal(0, WeaponComponentDefaults.SelectDefault(new[] {
                E(0, Scope, true), E(40, Scope, false) }, Scope));
        }

        [Theory]
        [InlineData(0, 30)]
        [InlineData(10, 30)]
        [InlineData(20, 0)]
        [InlineData(30, 0)]
        public void Restore_irons_only_when_scope_slot_is_empty(int equipped, int expected)
        {
            var entries = new[] { E(10, Scope, false), E(20, Scope, false), E(30, Scope, true) };
            Assert.Equal(expected, WeaponComponentDefaults.SelectRestoration(entries, Scope, 10, hash => hash == equipped));
        }

        [Fact]
        public void Other_slots_do_not_block_sight_restoration()
        {
            Assert.Equal(30, WeaponComponentDefaults.SelectRestoration(new[] {
                E(30, Scope, true), E(20, Supp, false) }, Scope, 10, hash => hash == 20));
        }

        [Fact]
        public void Never_restore_the_removed_component_or_a_required_slot()
        {
            Assert.Equal(0, WeaponComponentDefaults.SelectRestoration(new[] {
                E(30, Scope, true) }, Scope, 30, _ => false));
            int clip = unchecked((int)GTA.WeaponAttachmentPoint.Clip);
            Assert.Equal(0, WeaponComponentDefaults.SelectRestoration(new[] {
                E(30, clip, true) }, clip, 10, _ => false));
        }
    }
}
