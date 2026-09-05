using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Mono.Cecil;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class ReactorBridgeBinaryCompatibilityTests
    {
        [Fact]
        public void PackagedBridgeAllin1ReferencesResolveAgainstPackagedCore()
        {
            string pairDirectory = Path.Combine(
                AppContext.BaseDirectory, "reactor-dist-pair");
            string corePath = Path.Combine(pairDirectory, "ALLIN1.dll");
            string bridgePath = Path.Combine(
                pairDirectory, "ALLIN1.ReactorBridge.plugin");
            Assert.True(File.Exists(corePath), "Packaged ALLIN1.dll was not staged.");
            Assert.True(File.Exists(bridgePath), "Packaged bridge was not staged.");

            var resolver = new DefaultAssemblyResolver();
            resolver.AddSearchDirectory(pairDirectory);
            resolver.AddSearchDirectory(Path.GetDirectoryName(typeof(object).Assembly.Location));
            var parameters = new ReaderParameters { AssemblyResolver = resolver };
            using (AssemblyDefinition bridge = AssemblyDefinition.ReadAssembly(
                bridgePath, parameters))
            {
                var unresolved = new List<string>();
                foreach (TypeReference reference in bridge.MainModule
                    .GetTypeReferences()
                    .Where(IsAllin1Reference))
                {
                    try
                    {
                        if (reference.Resolve() == null)
                            unresolved.Add(reference.FullName);
                    }
                    catch (Exception ex)
                    {
                        unresolved.Add(reference.FullName + " (" + ex.Message + ")");
                    }
                }

                MemberReference[] allin1MemberReferences = bridge.MainModule
                    .GetMemberReferences()
                    .Where(value => IsAllin1Reference(value.DeclaringType))
                    .ToArray();
                Assert.NotEmpty(allin1MemberReferences);
                Assert.Contains(allin1MemberReferences, reference =>
                    reference.Name == "get_RuntimeLogPath" &&
                    reference.DeclaringType.FullName ==
                        "ALLIN1.Allin1GbaySnapshot");
                foreach (MemberReference reference in allin1MemberReferences)
                {
                    try
                    {
                        if (Resolve(reference) == null)
                            unresolved.Add(reference.FullName);
                    }
                    catch (Exception ex)
                    {
                        unresolved.Add(reference.FullName + " (" + ex.Message + ")");
                    }
                }

                Assert.True(
                    unresolved.Count == 0,
                    "The packaged Reactor bridge references members absent from " +
                    "the packaged ALLIN1.dll:\n" + string.Join("\n", unresolved));
            }
        }

        [Fact]
        public void PackagedBridgeDoesNotStaticallyReferenceOptionalReadinessInterface()
        {
            string bridgePath = Path.Combine(
                AppContext.BaseDirectory,
                "reactor-dist-pair",
                "ALLIN1.ReactorBridge.plugin");
            Assert.True(File.Exists(bridgePath), "Packaged bridge was not staged.");

            using (AssemblyDefinition bridge = AssemblyDefinition.ReadAssembly(
                bridgePath))
            {
                const string optionalType =
                    "ReactorV.Integration.IReactorMenuPresentationStateHandle";
                Assert.DoesNotContain(
                    bridge.MainModule.GetTypeReferences(),
                    reference => reference.FullName == optionalType);
                Assert.DoesNotContain(
                    bridge.MainModule.GetMemberReferences(),
                    reference => reference.DeclaringType.FullName == optionalType);
            }
        }

        private static bool IsAllin1Reference(TypeReference reference)
        {
            return reference?.Scope is AssemblyNameReference assembly &&
                string.Equals(assembly.Name, "ALLIN1", StringComparison.Ordinal);
        }

        private static IMemberDefinition Resolve(MemberReference reference)
        {
            if (reference is MethodReference method)
                return method.Resolve();
            if (reference is FieldReference field)
                return field.Resolve();
            return null;
        }
    }
}
