using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Xunit;

namespace RealisticSuppressors.Tests
{
    public sealed class SuppressorProfileDiscoveryTests
    {
        internal static string VectorJson => File.ReadAllText(Path.Combine(
            AppDomain.CurrentDomain.BaseDirectory, "TestData", "suppressor-profile.json"));

        internal static string EditProfile(Action<Dictionary<string, object>> edit)
        {
            var root = PortableJson.ParseObject(VectorJson);
            edit((Dictionary<string, object>)((object[])root["profiles"])[0]);
            return PortableJson.Serialize(root);
        }

        internal sealed class Fixture : IDisposable
        {
            internal string Root { get; } = Path.Combine(Path.GetTempPath(), "suppressor-profile-tests-" + Guid.NewGuid().ToString("N"));
            internal string Profiles => Path.Combine(Root, "scripts", "RealisticSuppressors", "profiles");
            internal string Receipts => Path.Combine(Root, "scripts", ".allin1", "mods");
            internal Fixture()
            {
                Directory.CreateDirectory(Profiles);
                Directory.CreateDirectory(Receipts);
            }
            internal string Write(string relative, string content)
            {
                string path = Path.Combine(Root, relative);
                Directory.CreateDirectory(Path.GetDirectoryName(path));
                File.WriteAllText(path, content, new UTF8Encoding(false));
                return path;
            }
            internal void Standalone(string name = "vector.json", string json = null) =>
                Write("scripts/RealisticSuppressors/profiles/" + name, json ?? VectorJson);
            internal void Managed(string id = "a1.krissvector", bool enabled = true, string json = null,
                string destination = null, string checksum = null)
            {
                string relative = destination ?? "scripts/ALLIN1/Weapons/" + id + "/suppressor-profile.json";
                string path = Write("scripts/ALLIN1/Weapons/" + id + "/suppressor-profile.json", json ?? VectorJson);
                using (var hash = SHA256.Create())
                    checksum = checksum ?? BitConverter.ToString(hash.ComputeHash(File.ReadAllBytes(path))).Replace("-", "").ToLowerInvariant();
                Write("scripts/.allin1/mods/" + id + ".json", PortableJson.Serialize(new Dictionary<string, object>
                {
                    { "schema_version", 2 }, { "id", id }, { "enabled", enabled },
                    { "files", new object[] { new Dictionary<string, object> { { "destination", relative }, { "sha256", checksum } } } }
                }));
            }
            internal SuppressorProfileCatalog Load(bool hosted = false, Func<string, bool> enabled = null) =>
                hosted ? SuppressorProfileDiscovery.Load(Root, null, enabled ?? (_ => true))
                    : SuppressorProfileDiscovery.Load(null, Profiles);
            public void Dispose()
            {
                // This fixture creates one unique directory under TEMP only.
                if (!Root.StartsWith(Path.Combine(Path.GetTempPath(), "suppressor-profile-tests-"), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Unexpected fixture root.");
                Directory.Delete(Root, true);
            }
        }

        [Fact]
        public void Json_only_vector_resolves_without_a_compiled_entry_and_lifecycle_uses_the_same_catalog()
        {
            Assert.False(SuppressorThermalProfiles.TryGet(0xCDA264A5, out _));
            using (var files = new Fixture())
            {
                files.Managed();
                var result = files.Load(true);
                Assert.Empty(result.Diagnostics);
                Assert.Equal(40, result.All.Count);
                Assert.Equal(1, result.CustomCount);
                Assert.True(result.TryGet(0xCDA264A5, out var vector));
                Assert.Equal(0xC304849Au, vector.ComponentHash);
                Assert.Equal(SuppressorWeaponClass.SubmachineGun, vector.WeaponClass);
                Assert.Equal("A1V45", vector.ProfileCode);
                Assert.Equal(2.3f, vector.HeatPerShotCelsius);
                Assert.StartsWith("package:a1.krissvector/", result.Sources[vector.WeaponHash]);
                Assert.True(result.TryGetLifecycle(" weapon_a1_kriss_vector ", unchecked((int)vector.ComponentHash), out var lifecycle));
                Assert.Same(vector, lifecycle);
                Assert.False(result.TryGetLifecycle(vector.WeaponName, 123, out var wrongComponent));
                Assert.Null(wrongComponent);
                Assert.False(result.TryGetLifecycle("WEAPON_OTHER", unchecked((int)vector.ComponentHash), out _));
                Assert.False(new SuppressorProfileCatalog().TryGet(vector.WeaponHash, out _));
            }
        }

        [Fact]
        public void Standalone_profiles_need_no_launcher_and_do_not_scan_nested_folders()
        {
            using (var files = new Fixture())
            {
                files.Standalone();
                files.Standalone("nested/ignored.json", "broken");
                var result = files.Load();
                Assert.Empty(result.Diagnostics);
                Assert.Equal(1, result.CustomCount);
                Assert.StartsWith("standalone:", result.Sources.Values.Single());
            }
        }

        [Fact]
        public void Hosted_mode_ignores_loose_profiles_disabled_packages_and_disabled_receipts()
        {
            using (var files = new Fixture())
            {
                files.Standalone();
                files.Managed(enabled: false);
                Assert.Equal(0, files.Load(true).CustomCount);
                files.Managed();
                Assert.Equal(0, files.Load(true, _ => false).CustomCount);
                File.Delete(Path.Combine(files.Receipts, "a1.krissvector.json"));
                Assert.Equal(0, files.Load(true).CustomCount);
            }
        }

        [Fact]
        public void Changed_owned_json_is_rejected_until_managed_reinstall()
        {
            using (var files = new Fixture())
            {
                files.Managed();
                File.AppendAllText(Path.Combine(files.Root, "scripts/ALLIN1/Weapons/a1.krissvector/suppressor-profile.json"), " ");
                var result = files.Load(true);
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("SHA-256 mismatch"));
                files.Managed();
                Assert.Equal(1, files.Load(true).CustomCount);
            }
        }

        [Theory]
        [InlineData("scripts/../outside/suppressor-profile.json")]
        [InlineData("scripts/link/../../outside/suppressor-profile.json")]
        [InlineData("C:/elsewhere/suppressor-profile.json")]
        [InlineData("//server/share/suppressor-profile.json")]
        [InlineData("scripts/ads:stream/suppressor-profile.json")]
        [InlineData("scripts/folder./suppressor-profile.json")]
        [InlineData("scripts//suppressor-profile.json")]
        [InlineData("scripts/folder /suppressor-profile.json")]
        [InlineData("mods/profiles/suppressor-profile.json")]
        [InlineData("scripts\\folder\\suppressor-profile.json")]
        public void Unsafe_receipt_paths_never_load(string destination)
        {
            using (var files = new Fixture())
            {
                files.Managed(destination: destination);
                var result = files.Load(true);
                Assert.Equal(0, result.CustomCount);
                Assert.NotEmpty(result.Diagnostics);
            }
        }

        [Fact]
        public void Reparse_point_profile_directory_is_rejected()
        {
            using (var files = new Fixture())
            {
                string outside = Path.Combine(files.Root, "outside");
                Directory.CreateDirectory(outside);
                File.WriteAllText(Path.Combine(outside, "vector.json"), VectorJson);
                string link = Path.Combine(files.Profiles, "redirect");
                using (var process = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(
                    "cmd.exe", "/c mklink /J \"" + link + "\" \"" + outside + "\"")
                    { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true }))
                {
                    process.WaitForExit();
                    Assert.Equal(0, process.ExitCode);
                }
                try
                {
                    var result = SuppressorProfileDiscovery.Load(null, link);
                    Assert.Equal(0, result.CustomCount);
                    Assert.Contains(result.Diagnostics, d => d.Contains("Redirected"));
                }
                finally { Directory.Delete(link); }
            }
        }

        [Fact]
        public void Conflicts_reject_every_definition_regardless_of_filename_order()
        {
            using (var files = new Fixture())
            {
                files.Standalone("a.json");
                files.Standalone("z.json", EditProfile(p => p["heat_per_shot_c"] = 5));
                var result = files.Load();
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("Conflicting") && d.Contains("a.json") && d.Contains("z.json"));
            }
        }

        [Fact]
        public void Cross_package_conflicts_and_builtin_overrides_are_not_last_writer_wins()
        {
            using (var files = new Fixture())
            {
                files.Managed("author.one");
                files.Managed("author.two");
                files.Managed("stock.override", json: EditProfile(p => p["weapon"] = "WEAPON_SMG"));
                var result = files.Load(true);
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("Conflicting"));
                Assert.Contains(result.Diagnostics, d => d.Contains("Built-in"));
                Assert.True(result.TryGet(0x2BE6766B, out var smg));
                Assert.Equal(2f, smg.HeatPerShotCelsius);
            }
        }

        [Fact]
        public void Missing_malformed_and_oversized_files_report_diagnostics_but_keep_valid_profiles()
        {
            using (var files = new Fixture())
            {
                files.Standalone();
                files.Standalone("broken.json", "{");
                files.Standalone("huge.json", new string(' ', SuppressorProfileDiscovery.MaxFileBytes + 1));
                var result = files.Load();
                Assert.Equal(1, result.CustomCount);
                Assert.Equal(2, result.Diagnostics.Count);
                files.Managed();
                File.Delete(Path.Combine(files.Root, "scripts/ALLIN1/Weapons/a1.krissvector/suppressor-profile.json"));
                Assert.Equal(0, files.Load(true).CustomCount);
                Assert.NotEmpty(files.Load(true).Diagnostics);
            }
        }

        [Fact]
        public void Byte_order_mark_is_supported_and_invalid_utf8_is_not()
        {
            using (var files = new Fixture())
            {
                files.Standalone();
                File.WriteAllText(Path.Combine(files.Profiles, "vector.json"), VectorJson, new UTF8Encoding(true));
                Assert.Equal(1, files.Load().CustomCount);
                File.WriteAllBytes(Path.Combine(files.Profiles, "vector.json"), new byte[] { 0xFF, 0xFE, 0x7B });
                Assert.Equal(0, files.Load().CustomCount);
                Assert.NotEmpty(files.Load().Diagnostics);
            }
        }

        [Theory]
        [InlineData("pistol_9mm")]
        [InlineData("smg_9mm")]
        [InlineData("smg_45")]
        [InlineData("rifle_556")]
        [InlineData("rifle_762")]
        [InlineData("shotgun_12g")]
        [InlineData("sniper_magnum")]
        public void Presets_allow_bounded_numeric_overrides(string preset)
        {
            var profile = SuppressorProfileDiscovery.Parse(EditProfile(p =>
            {
                p["preset"] = preset; p["heat_per_shot_c"] = 3.5;
                p["cooling_half_life_s"] = 300; p["rated_life_rounds"] = 9000;
            })).Single();
            Assert.Equal(3.5f, profile.HeatPerShotCelsius);
            Assert.Equal(300f, profile.CoolingHalfLifeSeconds);
            Assert.Equal(9000, profile.RatedLifeRounds);
        }

        [Fact]
        public void Fully_explicit_profile_is_valid_without_a_preset()
        {
            var profile = SuppressorProfileDiscovery.Parse(EditProfile(p =>
            {
                p.Remove("preset"); p["weapon_class"] = "smg";
                p["heat_per_shot_c"] = 2.3; p["cooling_half_life_s"] = 240;
                p["damage_onset_c"] = 325; p["critical_c"] = 650; p["rated_life_rounds"] = 8000;
            })).Single();
            Assert.Equal(8000, profile.RatedLifeRounds);
            Assert.Equal(SuppressorWeaponClass.SubmachineGun, profile.WeaponClass);
        }

        [Theory]
        [InlineData("heat_per_shot_c", 0)]
        [InlineData("heat_per_shot_c", 101)]
        [InlineData("cooling_half_life_s", 0)]
        [InlineData("cooling_half_life_s", 3601)]
        [InlineData("damage_onset_c", 20)]
        [InlineData("damage_onset_c", 651)]
        [InlineData("critical_c", 525)]
        [InlineData("critical_c", 1601)]
        [InlineData("rated_life_rounds", 0)]
        [InlineData("rated_life_rounds", 1000001)]
        [InlineData("rated_life_rounds", 1.5)]
        public void Out_of_range_values_are_rejected(string key, double value) =>
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(EditProfile(p => p[key] = value)));

        [Theory]
        [InlineData("preset", "invented")]
        [InlineData("weapon_class", "invalid")]
        [InlineData("weapon", "../WEAPON_VECTOR")]
        [InlineData("component", "COMPONENT_AT_MUZZLE_01")]
        [InlineData("heat_per_shot_c", "2.3")]
        [InlineData("profile_code", "too long and not a code")]
        [InlineData("heat_per_shoot_c", "typo")]
        public void Invalid_fields_are_not_silently_ignored(string key, string value) =>
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(EditProfile(p => p[key] = value)));

        [Fact]
        public void Booleans_nonfinite_values_duplicate_keys_versions_and_partial_explicit_profiles_fail()
        {
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(EditProfile(p => p["heat_per_shot_c"] = true)));
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(VectorJson.Replace("\"schema_version\": 1", "\"schema_version\": 2")));
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(VectorJson.Replace("\"schema_version\": 1", "\"schema_version\": 1, \"schema_version\": 1")));
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(VectorJson.Replace("\"preset\": \"smg_45\"", "\"preset\": \"smg_45\", \"heat_per_shot_c\": 1e999")));
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(EditProfile(p => p.Remove("preset"))));
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse("{\"schema_version\":1,\"profiles\":[]}"));
        }

        [Fact]
        public void File_count_and_aggregate_profile_count_fail_closed()
        {
            using (var files = new Fixture())
            {
                for (int i = 0; i <= SuppressorProfileDiscovery.MaxFiles; i++) files.Standalone(i + ".json");
                var result = files.Load();
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("file count"));
            }
            using (var files = new Fixture())
            {
                var root = PortableJson.ParseObject(VectorJson);
                var row = ((object[])root["profiles"])[0];
                root["profiles"] = Enumerable.Repeat(row, 64).ToArray();
                for (int i = 0; i < 5; i++) files.Standalone(i + ".json", PortableJson.Serialize(root));
                var result = files.Load();
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("Aggregate"));
            }
        }

        [Fact]
        public void Receipt_identity_and_duplicate_destinations_are_validated()
        {
            using (var files = new Fixture())
            {
                files.Managed();
                string path = Path.Combine(files.Receipts, "a1.krissvector.json");
                var receipt = PortableJson.ParseObject(File.ReadAllText(path));
                receipt["id"] = "somebody.else";
                File.WriteAllText(path, PortableJson.Serialize(receipt));
                Assert.Equal(0, files.Load(true).CustomCount);
                Assert.Contains(files.Load(true).Diagnostics, d => d.Contains("identifier"));
                receipt["id"] = "a1.krissvector";
                receipt["files"] = new object[] { ((object[])receipt["files"])[0], ((object[])receipt["files"])[0] };
                File.WriteAllText(path, PortableJson.Serialize(receipt));
                Assert.Equal(0, files.Load(true).CustomCount);
                Assert.Contains(files.Load(true).Diagnostics, d => d.Contains("Duplicate"));
            }
        }

        [Fact]
        public void Configured_vector_retains_existing_saved_durability()
        {
            using (var files = new Fixture())
            {
                string statePath = Path.Combine(files.Root, "condition.json");
                var previous = new SuppressorStateStore(statePath);
                previous.SetDurability("Michael", "WEAPON_A1_KRISS_VECTOR", 0xC304849A, .42f);
                previous.Commit();
                files.Standalone();
                var result = files.Load();
                Assert.True(result.TryGet(0xCDA264A5, out var vector));
                var current = new SuppressorStateStore(statePath);
                Assert.Equal(.42f, current.GetDurability("Michael", vector.WeaponName, vector.ComponentHash), 3);
                Assert.Equal(1f, current.GetDurability("Michael", "WEAPON_SMG", vector.ComponentHash), 3);
            }
        }

        [Fact]
        public void Aggregate_receipt_budget_and_receipt_count_are_bounded()
        {
            using (var files = new Fixture())
            {
                for (int i = 0; i < 9; i++)
                {
                    string id = "package." + i;
                    files.Managed(id);
                    string path = Path.Combine(files.Receipts, id + ".json");
                    string receipt = File.ReadAllText(path);
                    File.WriteAllText(path, receipt.PadRight(1024 * 1024, ' '), new UTF8Encoding(false));
                }
                var result = files.Load(true);
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("Aggregate"));
            }
            using (var files = new Fixture())
            {
                for (int i = 0; i <= SuppressorProfileDiscovery.MaxReceipts; i++)
                    files.Write("scripts/.allin1/mods/package." + i + ".json", "{}");
                var result = files.Load(true);
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("file count"));
            }
        }

        [Fact]
        public void Oversized_receipt_and_unknown_top_level_fields_are_rejected()
        {
            using (var files = new Fixture())
            {
                files.Managed();
                string path = Path.Combine(files.Receipts, "a1.krissvector.json");
                File.WriteAllText(path, new string(' ', 1024 * 1024 + 1), new UTF8Encoding(false));
                var result = files.Load(true);
                Assert.Equal(0, result.CustomCount);
                Assert.Contains(result.Diagnostics, d => d.Contains("byte limit"));
            }
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(
                VectorJson.Replace("\"schema_version\": 1", "\"schema_version\": 1, \"include\": \"other.json\"")));
            var root = PortableJson.ParseObject(VectorJson);
            root["profiles"] = Enumerable.Repeat(((object[])root["profiles"])[0], 65).ToArray();
            Assert.Throws<InvalidDataException>(() => SuppressorProfileDiscovery.Parse(PortableJson.Serialize(root)));
        }

        [Fact]
        public void Missing_directories_are_normal_and_root_resolution_ignores_shadow_copy()
        {
            using (var files = new Fixture())
            {
                Assert.Equal(Path.GetPathRoot(files.Root), SuppressorProfileDiscovery.SafeRoot(Path.GetPathRoot(files.Root)));
                Assert.Empty(files.Load().Diagnostics);
                Assert.Equal(39, files.Load().All.Count);
                File.WriteAllText(Path.Combine(files.Root, "GTA5_Enhanced.exe"), "");
                Assert.Equal(files.Root, SuppressorProfileDiscovery.ResolveGameRoot("C:/cache/shadow/mod.dll", files.Root));
                Assert.Equal(files.Root, SuppressorProfileDiscovery.ResolveGameRoot(
                    Path.Combine(files.Root, "scripts/RealisticSuppressors/RealisticSuppressors.dll"), "C:/cache/shadow"));
            }
        }
    }
}
