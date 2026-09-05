using System;
using System.IO;
using System.Reflection;
using System.Reflection.Emit;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GtaEditionDetectorTests
    {
        [Fact]
        public void DynamicAssemblyLocationFallsBackToEnhancedProcessIdentity()
        {
            AssemblyName name = new AssemblyName(
                "ALLIN1.DynamicEditionFixture." + Guid.NewGuid().ToString("N"));
            AssemblyBuilder dynamicAssembly = AppDomain.CurrentDomain
                .DefineDynamicAssembly(name, AssemblyBuilderAccess.Run);

            Assert.Equal(string.Empty, SafeAssemblyLocation(dynamicAssembly));
            Assert.Equal("Enhanced", Detect(
                Path.Combine("C:\\Games\\GTAV", "GTA5_Enhanced.exe"),
                SafeAssemblyLocation(dynamicAssembly),
                string.Empty,
                string.Empty,
                string.Empty));
        }

        [Fact]
        public void EmptyAssemblyLocationsFallBackToLegacyRuntimeRoot()
        {
            WithGameRoot("GTA5.exe", gameRoot =>
            {
                string scripts = Path.Combine(gameRoot, "scripts");
                Directory.CreateDirectory(scripts);

                string result = Detect(
                    Path.Combine(gameRoot, "unrelated-test-host.exe"),
                    string.Empty,
                    string.Empty,
                    scripts,
                    string.Empty);

                Assert.Equal("Legacy", result);
                Assert.DoesNotContain(gameRoot, result);
            });
        }

        [Fact]
        public void NestedBridgeLocationFindsEnhancedGameRoot()
        {
            WithGameRoot("GTA5_Enhanced.exe", gameRoot =>
            {
                string plugin = Path.Combine(
                    gameRoot, "scripts", "ReactorV",
                    "ALLIN1.ReactorBridge.plugin");
                Directory.CreateDirectory(Path.GetDirectoryName(plugin));

                Assert.Equal("Enhanced", Detect(
                    Path.Combine(gameRoot, "unrelated-test-host.exe"),
                    string.Empty,
                    plugin,
                    string.Empty,
                    string.Empty));
            });
        }

        private static string Detect(
            string processExecutablePath,
            string contentAssemblyLocation,
            string bridgeAssemblyLocation,
            string runtimeBaseDirectory,
            string currentDirectory)
        {
            Type detector = DetectorType();
            MethodInfo method = detector.GetMethod(
                "Detect", BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(method);
            return Assert.IsType<string>(method.Invoke(null, new object[]
            {
                processExecutablePath,
                contentAssemblyLocation,
                bridgeAssemblyLocation,
                runtimeBaseDirectory,
                currentDirectory,
            }));
        }

        private static string SafeAssemblyLocation(Assembly assembly)
        {
            MethodInfo method = DetectorType().GetMethod(
                "SafeAssemblyLocation",
                BindingFlags.Static | BindingFlags.NonPublic);
            Assert.NotNull(method);
            return Assert.IsType<string>(method.Invoke(
                null, new object[] { assembly }));
        }

        private static Type DetectorType()
        {
            string packageDirectory = Path.Combine(
                AppContext.BaseDirectory,
                "reactor-package", "scripts", "ReactorV");
            Assembly plugin = Assembly.LoadFrom(Path.Combine(
                packageDirectory, "ALLIN1.ReactorBridge.plugin"));
            Type detector = plugin.GetType(
                "ALLIN1.ReactorBridge.GtaEditionDetector");
            Assert.NotNull(detector);
            return detector;
        }

        private static void WithGameRoot(
            string executableName,
            Action<string> action)
        {
            string root = Path.Combine(
                Path.GetTempPath(), "allin1-edition-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            File.WriteAllBytes(Path.Combine(root, executableName), new byte[] { 0 });
            try
            {
                action(root);
            }
            finally
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }
}
