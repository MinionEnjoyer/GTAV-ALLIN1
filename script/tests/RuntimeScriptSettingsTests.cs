using System;
using System.IO;
using System.Text;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class RuntimeScriptSettingsTests
    {
        [Fact]
        public void Bounded_reader_reads_only_the_script_boolean_from_a_real_file()
        {
            string path = Path.Combine(Path.GetTempPath(),
                "allin1-runtime-settings-" + Guid.NewGuid().ToString("N") + ".toml");
            try
            {
                File.WriteAllText(path, "[general]\nenhanced_smoke_effects = false\n" +
                    "[script]\nenhanced_smoke_effects = true # enabled\n");
                Assert.True(RuntimeScriptSettings.ReadBooleanFile(path,
                    "enhanced_smoke_effects", false));
            }
            finally
            {
                File.Delete(path);
            }
        }

        [Fact]
        public void Utf8_bom_script_file_enables_the_smoke_setting()
        {
            string path = Path.Combine(Path.GetTempPath(),
                "allin1-runtime-settings-" + Guid.NewGuid().ToString("N") + ".toml");
            try
            {
                File.WriteAllText(path, "[script]\nenhanced_smoke_effects = true\n",
                    new UTF8Encoding(true));

                Assert.True(RuntimeScriptSettings.ReadBooleanFile(path,
                    "enhanced_smoke_effects", false));
            }
            finally
            {
                File.Delete(path);
            }
        }

        [Fact]
        public void Smoke_setting_defaults_off_when_the_script_key_is_absent()
        {
            Assert.False(RuntimeScriptSettings.ParseBoolean(
                "[script]\nother_setting = true\n", "enhanced_smoke_effects", false));
        }

        [Theory]
        [InlineData("[script]\nenhanced_smoke_effects = true", true)]
        [InlineData("[script]\nenhanced_smoke_effects = false", false)]
        [InlineData("[other]\nenhanced_smoke_effects = true", false)]
        [InlineData("[script]\nother = true", false)]
        public void Parser_requires_an_exact_script_key(string document,
            bool expected)
        {
            Assert.Equal(expected, RuntimeScriptSettings.ParseBoolean(document,
                "enhanced_smoke_effects", false));
        }

        [Fact]
        public void Oversized_configuration_falls_back_without_parsing()
        {
            string path = Path.Combine(Path.GetTempPath(),
                "allin1-runtime-settings-" + Guid.NewGuid().ToString("N") + ".toml");
            try
            {
                File.WriteAllText(path, new string('x',
                    RuntimeScriptSettings.MaximumConfigurationBytes + 1));
                Assert.False(RuntimeScriptSettings.ReadBooleanFile(path,
                    "enhanced_smoke_effects", false));
            }
            finally
            {
                File.Delete(path);
            }
        }
    }
}
