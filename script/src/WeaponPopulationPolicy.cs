// Narrow, testable safety policy for ambient NPC firearm replacement.
using System;
using GTA;

namespace ALLIN1
{
    internal static class WeaponPopulationPolicy
    {
        internal static bool IsSuppressed(bool loading, bool playerAvailable,
            bool mission, bool cutscene, bool switching,
            bool interior, bool garageTransition, bool activeDuringMissions = false)
        {
            return !string.IsNullOrEmpty(SuppressionReason(loading,
                playerAvailable, mission, cutscene, switching, interior,
                garageTransition, activeDuringMissions));
        }

        // Keep the safety gate and the user-visible diagnosis coupled.  This
        // is deliberately descriptive only: callers must not relax a gate
        // based on this text. Wanted level deliberately is not an input:
        // weapon replacement continues during pursuits, while the per-ped
        // candidate checks still protect active encounters and scripted NPCs.
        internal static string SuppressionReason(bool loading,
            bool playerAvailable, bool mission, bool cutscene,
            bool switching, bool interior, bool garageTransition,
            bool activeDuringMissions = false)
        {
            if (loading) return "game loading";
            if (!playerAvailable) return "player unavailable";
            if (mission && !activeDuringMissions) return "mission active";
            if (cutscene) return "cutscene active";
            if (switching) return "player switch in progress";
            if (interior) return "player is indoors";
            if (garageTransition) return "garage transition in progress";
            return "";
        }

        internal static bool IsAmbientCandidate(bool isPlayer, bool persistent,
            bool missionEntity, bool inVehicle, bool combat, bool dead,
            bool injured, bool ragdoll, bool fleeing, bool shooting,
            bool onScreen, bool tooNear, int populationType)
        {
            return IsAmbientCandidate(isPlayer, persistent, missionEntity,
                inVehicle, combat, dead, injured, ragdoll, fleeing, shooting,
                onScreen, tooNear, populationType, false);
        }

        internal static bool IsAmbientCandidate(bool isPlayer, bool persistent,
            bool missionEntity, bool inVehicle, bool combat, bool dead,
            bool injured, bool ragdoll, bool fleeing, bool shooting,
            bool onScreen, bool tooNear, int populationType, bool scriptedTask)
        {
            return !isPlayer && !persistent && !missionEntity && !inVehicle &&
                !combat && !dead && !injured && !ragdoll && !fleeing &&
                !shooting && !onScreen && !tooNear && !scriptedTask &&
                populationType >= 1 && populationType <= 5;
        }

        // Population v1 intentionally stays in common civilian firearm tiers.
        // It never changes an SMG into a rifle (or any other category).
        internal static bool IsReplaceableCategory(string category)
        {
            switch (category ?? "")
            {
                case "pistols": case "smgs": case "shotguns": case "rifles":
                    return true;
                default: return false;
            }
        }

        // Decide once for an eligible encounter, rather than per scan
        // interval. Callers remember that encounter for their bounded seen
        // TTL before asking. Explicit endpoints do not consume randomness.
        internal static bool ShouldReplaceCandidate(float chance,
            Func<double> nextRoll)
        {
            if (chance <= 0f) return false;
            if (chance >= 1f) return true;
            if (nextRoll == null) throw new ArgumentNullException("nextRoll");
            double roll = nextRoll();
            return roll >= 0d && roll < chance;
        }

        // Catalog labels express author intent, but the game is authoritative
        // about what a weapon actually is. Both donor and replacement must be
        // in the one expected native group; this prevents a mislabeled add-on
        // from crossing a civilian tier.
        internal static bool NativeGroupsMatchCategory(string category,
            uint sourceGroup, uint targetGroup)
        {
            uint expected;
            return ExpectedNativeGroup(category, out expected) &&
                sourceGroup == expected && targetGroup == expected;
        }

        private static bool ExpectedNativeGroup(string category, out uint group)
        {
            switch (category ?? "")
            {
                case "pistols": group = (uint)WeaponGroup.Pistol; return true;
                case "smgs": group = (uint)WeaponGroup.SMG; return true;
                case "shotguns": group = (uint)WeaponGroup.Shotgun; return true;
                case "rifles": group = (uint)WeaponGroup.AssaultRifle; return true;
                default: group = 0; return false;
            }
        }

        internal static bool CanReplace(bool candidateStillAmbient,
            bool oldWeaponArmed, bool categoryMatches, bool newWeaponValid,
            bool newWeaponOwned)
        {
            return candidateStillAmbient && oldWeaponArmed && categoryMatches &&
                newWeaponValid && newWeaponOwned;
        }

        internal static bool CanCommitSelectedReplacement(
            bool candidateStillAmbient, bool oldWeaponArmed,
            bool categoryMatches, bool newWeaponValid, bool newWeaponOwned,
            bool newWeaponSelected)
        {
            return CanReplace(candidateStillAmbient, oldWeaponArmed,
                categoryMatches, newWeaponValid, newWeaponOwned) &&
                newWeaponSelected;
        }

        internal static int BoundedAmmo(int ammo)
        {
            return Math.Max(1, Math.Min(999, ammo));
        }

        internal static int CandidateBudget(bool throttled)
        {
            return throttled ? 6 : 12;
        }

        internal static bool ShouldStopScan(int inspected, double elapsedMilliseconds,
            bool throttled)
        {
            // One native nearby query can itself exceed the soft budget. Still
            // inspect one unseen candidate so that expensive queries cannot
            // indefinitely starve the injector. Native calls cannot be preempted.
            return inspected >= CandidateBudget(throttled) ||
                (inspected > 0 && elapsedMilliseconds >= 2d);
        }

        internal static bool IsWorkDue(int now, int lastWork, bool throttled)
        {
            int interval = throttled ? 30000 : 15000;
            return unchecked((uint)(now - lastWork)) >= (uint)interval;
        }
    }
}
