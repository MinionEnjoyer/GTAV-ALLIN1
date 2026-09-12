using System.IO;
using System;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class CharacterInventoryPersistenceTests
    {
        [Fact]
        public void DecodeState_builds_a_complete_canonical_ledger()
        {
            const string json = @"{
                ""Michael"": { ""schema_version"": 10,
                    ""weapons"": [""WEAPON_PISTOL""],
                    ""weapon_ammo"": { ""WEAPON_PISTOL"": 42 } }
            }";

            var state = CharacterInventory.DecodeState(json, out bool migrated);

            Assert.True(migrated);
            Assert.Equal(3, state.Count);
            Assert.Equal(new[] { "WEAPON_PISTOL" }, state["michael"].weapons);
            Assert.Equal(42, state["michael"].weapon_ammo["WEAPON_PISTOL"]);
            Assert.NotNull(state["franklin"]);
            Assert.NotNull(state["trevor"]);
        }

        [Theory]
        [InlineData("")]
        [InlineData("[]")]
        [InlineData("{\"michael\":")]
        [InlineData("{\"michael\":null}")]
        [InlineData("{\"Michael\":{},\"michael\":{}}")]
        [InlineData("{\"not_a_character\":{}}")]
        public void DecodeState_rejects_documents_that_cannot_safely_replace_live_state(
            string json)
        {
            Assert.Throws<InvalidDataException>(() =>
                CharacterInventory.DecodeState(json, out _));
        }

        [Fact]
        public void Reload_keeps_unsaved_staged_state_when_primary_and_backup_disagree()
        {
            string directory = Path.Combine(Path.GetTempPath(),
                "allin1-character-reload-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            string primary = Path.Combine(directory, "characters.json");
            const string backup = @"{
                ""michael"": { ""weapons"": [""WEAPON_PISTOL""],
                    ""weapon_ammo"": { ""WEAPON_PISTOL"": 42 } }
            }";
            try
            {
                var staged = CharacterInventory.DecodeState(backup,
                    out _);
                staged["michael"].weapons.Clear();
                staged["michael"].weapons.Add("WEAPON_CARBINERIFLE");
                staged["michael"].weapon_ammo.Clear();
                staged["michael"].weapon_ammo["WEAPON_CARBINERIFLE"] = 100;
                File.WriteAllText(primary, "{\"not_a_character\":{}}");
                File.WriteAllText(primary + ".bak", backup);

                using (CharacterInventory.UsePersistenceForTests(
                    primary, staged, dirty: true))
                {
                    CharacterInventory.ReloadForTests();
                    var current = CharacterInventory.StateForTests()["michael"];
                    Assert.Contains("WEAPON_CARBINERIFLE", current.weapons);
                    Assert.DoesNotContain("WEAPON_PISTOL", current.weapons);
                }
            }
            finally
            {
                if (Directory.Exists(directory)) Directory.Delete(directory, true);
            }
        }

        [Fact]
        public void Reload_recovers_valid_backup_when_no_staged_state_exists()
        {
            string directory = Path.Combine(Path.GetTempPath(),
                "allin1-character-recovery-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            string primary = Path.Combine(directory, "characters.json");
            const string backup = @"{
                ""michael"": { ""weapons"": [""WEAPON_PISTOL""],
                    ""weapon_ammo"": { ""WEAPON_PISTOL"": 42 } }
            }";
            try
            {
                File.WriteAllText(primary, "{\"not_a_character\":{}}");
                File.WriteAllText(primary + ".bak", backup);
                using (CharacterInventory.UsePersistenceForTests(
                    primary, null, dirty: false))
                {
                    CharacterInventory.ReloadForTests();
                    var current = CharacterInventory.StateForTests()["michael"];
                    Assert.Contains("WEAPON_PISTOL", current.weapons);
                    Assert.Equal(42, current.weapon_ammo["WEAPON_PISTOL"]);
                    Assert.Contains("WEAPON_PISTOL", CharacterInventory.
                        DecodeState(File.ReadAllText(primary), out _)["michael"].weapons);
                }
            }
            finally
            {
                if (Directory.Exists(directory)) Directory.Delete(directory, true);
            }
        }

        [Fact]
        public void Reload_keeps_unsaved_staged_state_when_primary_is_missing()
        {
            string directory = Path.Combine(Path.GetTempPath(),
                "allin1-character-missing-primary-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            string primary = Path.Combine(directory, "characters.json");
            const string backup = @"{
                ""michael"": { ""weapons"": [""WEAPON_PISTOL""] }
            }";
            try
            {
                var staged = CharacterInventory.DecodeState(backup, out _);
                staged["michael"].weapons.Clear();
                staged["michael"].weapons.Add("WEAPON_CARBINERIFLE");
                File.WriteAllText(primary + ".bak", backup);

                using (CharacterInventory.UsePersistenceForTests(
                    primary, staged, dirty: true))
                {
                    CharacterInventory.ReloadForTests();
                    var current = CharacterInventory.StateForTests()["michael"];
                    Assert.Contains("WEAPON_CARBINERIFLE", current.weapons);
                    Assert.DoesNotContain("WEAPON_PISTOL", current.weapons);
                    Assert.Equal(backup, File.ReadAllText(primary + ".bak"));
                }
            }
            finally
            {
                if (Directory.Exists(directory)) Directory.Delete(directory, true);
            }
        }

        [Fact]
        public void Reload_for_explicit_story_load_discards_staged_state_for_primary()
        {
            string directory = Path.Combine(Path.GetTempPath(),
                "allin1-character-story-discard-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            string primary = Path.Combine(directory, "characters.json");
            const string persisted = @"{
                ""michael"": { ""weapons"": [""WEAPON_PISTOL""] }
            }";
            try
            {
                File.WriteAllText(primary, persisted);
                var staged = CharacterInventory.DecodeState(persisted, out _);
                staged["michael"].weapons.Clear();
                staged["michael"].weapons.Add("WEAPON_CARBINERIFLE");

                using (CharacterInventory.UsePersistenceForTests(
                    primary, staged, dirty: true))
                {
                    CharacterInventory.ReloadForTests(discardStaged: true);
                    var current = CharacterInventory.StateForTests()["michael"];
                    Assert.Contains("WEAPON_PISTOL", current.weapons);
                    Assert.DoesNotContain("WEAPON_CARBINERIFLE", current.weapons);
                    Assert.Contains("WEAPON_PISTOL", CharacterInventory.
                        DecodeState(File.ReadAllText(primary), out _)["michael"].weapons);
                }
            }
            finally
            {
                if (Directory.Exists(directory)) Directory.Delete(directory, true);
            }
        }

        [Fact]
        public void Reload_recovers_valid_backup_when_primary_is_missing()
        {
            string directory = Path.Combine(Path.GetTempPath(),
                "allin1-character-missing-recovery-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(directory);
            string primary = Path.Combine(directory, "characters.json");
            const string backup = @"{
                ""michael"": { ""weapons"": [""WEAPON_PISTOL""],
                    ""weapon_ammo"": { ""WEAPON_PISTOL"": 42 } }
            }";
            try
            {
                File.WriteAllText(primary + ".bak", backup);
                using (CharacterInventory.UsePersistenceForTests(
                    primary, null, dirty: false))
                {
                    CharacterInventory.ReloadForTests();
                    var current = CharacterInventory.StateForTests()["michael"];
                    Assert.Contains("WEAPON_PISTOL", current.weapons);
                    Assert.Equal(42, current.weapon_ammo["WEAPON_PISTOL"]);
                    Assert.Contains("WEAPON_PISTOL", CharacterInventory.
                        DecodeState(File.ReadAllText(primary), out _)["michael"].weapons);
                    Assert.Equal(backup, File.ReadAllText(primary + ".bak"));
                }
            }
            finally
            {
                if (Directory.Exists(directory)) Directory.Delete(directory, true);
            }
        }
    }
}
