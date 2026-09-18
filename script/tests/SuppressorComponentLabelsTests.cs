using System.IO;
using System.Linq;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class SuppressorComponentLabelsTests
    {
        private const string Valid = "{\"schema_version\":3,\"cans\":{\"can\":{\"display_name\":\"Original Can\"}},\"profiles\":[{\"weapon\":\"WEAPON_PISTOL\",\"component\":\"COMPONENT_RSKC_TEST_PISTOL\",\"can\":\"can\"}]}";
        [Fact] public void Schema_three_can_is_flattened_for_exact_binding() =>
            Assert.Single(SuppressorComponentLabels.ParseForTests(Valid));
        [Fact] public void Profile_display_name_overrides_can_default() =>
            Assert.Contains("Profile Name", SuppressorComponentLabels.ParseForTests(
                Valid.Replace("\"can\"}]", "\"can\",\"display_name\":\"Profile Name\"}]" )).Values);
        [Fact] public void Invalid_json_is_rejected() =>
            Assert.Throws<InvalidDataException>(() => SuppressorComponentLabels.ParseForTests("{"));
        [Fact] public void Duplicate_binding_is_rejected() =>
            Assert.Throws<InvalidDataException>(() => SuppressorComponentLabels.ParseForTests(Valid.Replace("}]}", "},{\"weapon\":\"WEAPON_PISTOL\",\"component\":\"COMPONENT_RSKC_TEST_PISTOL\",\"display_name\":\"Override\"}]}")));
        [Fact] public void Stock_component_is_not_a_label_binding() =>
            Assert.Empty(SuppressorComponentLabels.ParseForTests("{\"schema_version\":3,\"profiles\":[{\"weapon\":\"WEAPON_PISTOL\",\"component\":\"COMPONENT_AT_PI_SUPP\",\"display_name\":\"Nope\"}]}"));
        [Fact] public void Same_component_name_on_different_weapon_does_not_collide() =>
            Assert.Equal(2, SuppressorComponentLabels.ParseForTests("{\"schema_version\":3,\"profiles\":[{\"weapon\":\"WEAPON_PISTOL\",\"component\":\"COMPONENT_RSKC_SHARED\",\"display_name\":\"Pistol\"},{\"weapon\":\"WEAPON_SMG\",\"component\":\"COMPONENT_RSKC_SHARED\",\"display_name\":\"SMG\"}]}").Count);
        [Fact] public void Known_can_fixture_shape_filters_thirteen_native_bindings_and_four_experimental_ones()
        {
            string native = string.Join(",", Enumerable.Range(1, 13).Select(i =>
                "{\"weapon\":\"WEAPON_PISTOL\",\"component\":\"COMPONENT_RSKC_TEST_" + i + "\",\"display_name\":\"Original " + i + "\",\"component_model\":\"w_rs_test_" + i + "\"}"));
            string experimental = string.Join(",", Enumerable.Range(1, 4).Select(i =>
                "{\"weapon\":\"WEAPON_A1_EQ_TEST\",\"component\":\"COMPONENT_A1_EQ_TEST_" + i + "\",\"display_name\":\"Experimental\"}"));
            string json = "{\"schema_version\":3,\"profiles\":[" + native + "," + experimental + "]}";
            var labels = SuppressorComponentLabels.ParseForTests(json);
            Assert.Equal(13, labels.Count);
            Assert.Contains("Original 1", labels.Values);
            Assert.Equal(13, SuppressorComponentLabels.ParseBindingsForTests(json).Count);
        }

        [Fact] public void Exact_binding_flattens_reusable_can_model_and_hashes()
        {
            var binding = Assert.Single(SuppressorComponentLabels.ParseBindingsForTests(
                "{\"schema_version\":3,\"cans\":{\"m45\":{\"display_name\":\"M45\",\"component_model\":\"w_rs_kc_m45_pistol_supp\"}},\"profiles\":[{\"can\":\"m45\",\"weapon\":\"WEAPON_PISTOL\",\"component\":\"COMPONENT_RSKC_M45_PISTOL\"}]}"));
            Assert.Equal("WEAPON_PISTOL", binding.Weapon);
            Assert.Equal("COMPONENT_RSKC_M45_PISTOL", binding.Component);
            Assert.Equal("M45", binding.DisplayName);
            Assert.Equal("w_rs_kc_m45_pistol_supp", binding.ExpectedComponentModel);
            Assert.Equal(unchecked((int)RuntimeWeaponCatalog.WeaponHash(binding.Weapon)), binding.WeaponHash);
            Assert.Equal(1791154987, binding.ComponentHash);
            Assert.Equal(unchecked((int)RuntimeWeaponCatalog.WeaponHash(binding.ExpectedComponentModel)), binding.ExpectedComponentModelHash);
        }

        [Fact] public void Exact_binding_requires_a_component_model()
        {
            Assert.Empty(SuppressorComponentLabels.ParseBindingsForTests(Valid));
        }

        [Fact] public void Probe_gate_requires_native_compatibility_and_exact_model_match()
        {
            Assert.True(SuppressorComponentLabels.AcceptsExpectedComponentModel(true, 42, 42));
            Assert.False(SuppressorComponentLabels.AcceptsExpectedComponentModel(false, 42, 42));
            Assert.False(SuppressorComponentLabels.AcceptsExpectedComponentModel(true, 42, 43));
            Assert.False(SuppressorComponentLabels.AcceptsExpectedComponentModel(true, 0, 0));
        }
    }
}
