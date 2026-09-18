using System;
using System.Collections.Generic;
using System.Linq;
using Mono.Cecil;
using Xunit;

namespace ALLIN1.Tests
{
    public sealed class GearRuntimeWiringTests
    {
        private static List<MethodReference> Calls(MethodDefinition method) =>
            method.Body.Instructions.Select(i => i.Operand).OfType<MethodReference>().ToList();

        [Theory]
        [InlineData("ExecuteGiveGear", "GiveGearValidated")]
        [InlineData("ExecuteEquipGear", "EquipGearValidated")]
        [InlineData("ExecuteUnequipGear", "UnequipGearValidated")]
        [InlineData("ExecuteRemoveArmor", "UnequipGearValidated")]
        [InlineData("ExecuteRemoveNightVision", "UnequipGearValidated")]
        public void LegacyEntryPointsCannotBypassGearValidation(string entry, string target)
        {
            using (var assembly = AssemblyDefinition.ReadAssembly(typeof(GbayShop).Assembly.Location))
            {
                var shop = assembly.MainModule.Types.Single(t => t.Name == "GbayShop");
                Assert.Contains(Calls(shop.Methods.Single(m => m.Name == entry)), m => m.Name == target);
            }
        }

        [Fact]
        public void SavedGearUsesTheSameValidationAfterSavedAppearance()
        {
            using (var assembly = AssemblyDefinition.ReadAssembly(typeof(GbayShop).Assembly.Location))
            {
                var inventory = assembly.MainModule.Types.Single(t => t.Name == "CharacterInventory");
                var apply = inventory.Methods.Single(m => m.Name == "Apply");
                var calls = Calls(apply);
                int outfit = calls.FindIndex(m => m.Name == "ApplyOutfit");
                int gear = calls.FindIndex(m => m.Name == "RestoreGearValidated");
                Assert.True(outfit >= 0 && gear > outfit);
                Assert.DoesNotContain(calls, m => m.DeclaringType.Name == "Ped" && m.Name == "set_Armor");
            }
        }

        [Fact]
        public void StagedArmorDoesNotYieldInsideAReactorAction()
        {
            using (var assembly = AssemblyDefinition.ReadAssembly(typeof(GbayShop).Assembly.Location))
            {
                foreach (var type in assembly.MainModule.Types.Where(t =>
                    t.Name == "JuggernautNativeTarget" || t.Name == "JuggernautEquipTransaction"))
                    foreach (var method in type.Methods.Where(m => m.HasBody))
                        Assert.DoesNotContain(Calls(method), m =>
                            m.DeclaringType.FullName == "GTA.Script" && m.Name == "Wait");
            }
        }

        [Fact]
        public void ReactorValidatesPlayerBeforeNativeOwnershipQueries()
        {
            using (var assembly = AssemblyDefinition.ReadAssembly(typeof(GbayShop).Assembly.Location))
            {
                var method = assembly.MainModule.Types.SelectMany(t => t.Methods)
                    .Single(m => m.Name == "ApplyGearAction" && m.HasBody);
                var calls = Calls(method);
                int readiness = calls.FindIndex(m => m.Name == "IsGearPlayerReady");
                int ownership = calls.FindIndex(m => m.Name == "IsGearOwned");
                Assert.True(readiness >= 0 && ownership > readiness);
            }
        }
    }
}
