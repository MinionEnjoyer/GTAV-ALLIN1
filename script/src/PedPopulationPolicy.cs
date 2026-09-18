using System;

namespace ALLIN1
{
    internal enum PedPopulationMode
    {
        Disabled,
        Add,
        Replace,
    }

    // Kept native-free so the streaming lifecycle can be exercised in tests.
    internal enum PedPopulationPendingAction
    {
        KeepWaiting,
        Create,
        Cancel,
        Timeout,
    }

    internal enum PedPopulationMetadataAction
    {
        Wait,
        Accept,
        Retry,
        Quarantine,
        Cancel,
    }

    internal static class PedPopulationPolicy
    {
        internal static bool TryParseMode(string value, out PedPopulationMode mode)
        {
            switch ((value ?? "").Trim().ToLowerInvariant())
            {
                case "disabled": mode = PedPopulationMode.Disabled; return true;
                case "add": mode = PedPopulationMode.Add; return true;
                case "replace": mode = PedPopulationMode.Replace; return true;
                default: mode = PedPopulationMode.Disabled; return false;
            }
        }

        internal static bool IsSuppressed(bool loading, bool playerAvailable,
            bool wanted, bool mission, bool cutscene, bool switching,
            bool interior, bool garageTransition)
        {
            return !string.IsNullOrEmpty(SuppressionReason(loading,
                playerAvailable, wanted, mission, cutscene, switching, interior,
                garageTransition));
        }

        // This describes the same closed safety gate used by IsSuppressed;
        // diagnostics never use it to weaken a world-state check.
        internal static string SuppressionReason(bool loading,
            bool playerAvailable, bool wanted, bool mission, bool cutscene,
            bool switching, bool interior, bool garageTransition)
        {
            if (loading) return "game loading";
            if (!playerAvailable) return "player unavailable";
            if (wanted) return "wanted level active";
            if (mission) return "mission active";
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
            return !isPlayer && !persistent && !missionEntity && !inVehicle &&
                !combat && !dead && !injured && !ragdoll && !fleeing &&
                !shooting && !onScreen && !tooNear &&
                populationType >= 1 && populationType <= 5;
        }

        internal static bool IsAmbientCandidate(bool isPlayer, bool persistent,
            bool missionEntity, bool inVehicle, bool combat, bool dead,
            bool injured, bool ragdoll, bool fleeing, bool shooting,
            bool onScreen, bool tooNear, int populationType, bool scriptedTask)
        {
            return IsAmbientCandidate(isPlayer, persistent, missionEntity,
                inVehicle, combat, dead, injured, ragdoll, fleeing, shooting,
                onScreen, tooNear, populationType) && !scriptedTask;
        }

        internal static bool CanCommitReplacement(bool targetReady,
            bool sourceStillEligible, bool sourceOffScreen)
        {
            return targetReady && sourceStillEligible && sourceOffScreen;
        }

        internal static bool CanCreateAfterStreaming(bool worldSafe,
            bool sourceStillEligible, bool destinationFar,
            bool destinationExterior)
        {
            return worldSafe && sourceStillEligible && destinationFar &&
                destinationExterior;
        }

        // A staged ped is deliberately hidden, so entity visibility alone is
        // not evidence that its position is outside the camera frustum.
        internal static bool IsStagedDestinationSafe(bool exists,
            bool entityOffScreen, bool positionOutsideCamera,
            bool destinationSafe, bool exterior)
        {
            return exists && entityOffScreen && positionOutsideCamera &&
                destinationSafe && exterior;
        }

        internal static bool CanReleaseTrackedPed(bool exists,
            bool expectedModel, bool missionEntity)
        {
            return exists && expectedModel && !missionEntity;
        }

        internal static bool CanReleaseTrackedPed(bool exists,
            bool expectedModel)
        {
            return CanReleaseTrackedPed(exists, expectedModel, false);
        }

        // A retained ped may be released only when its native script
        // ownership is still ours.  A mission bit alone is ambiguous because
        // our temporary persistence also uses it.
        internal static bool CanRelinquishOwnedPed(bool exists,
            bool expectedModel, bool belongsToThisScript)
        {
            return exists && expectedModel && belongsToThisScript;
        }

        // Added peds remain owned for a short, bounded period.  Releasing
        // them immediately after creation lets the engine cull the entity
        // before the population cap can observe it.
        internal static bool ShouldRetainTrackedPed(int now, int addedAt,
            int retentionMilliseconds)
        {
            return unchecked((uint)(now - addedAt)) <=
                (uint)Math.Max(0, retentionMilliseconds);
        }

        // Model metadata for streamed add-on peds is not authoritative until
        // the request has completed.  The final ped/human check remains
        // mandatory; this only defines when it may be evaluated.
        internal static bool CanUseLoadedPedModel(bool isLoaded, bool isPed,
            bool isHumanPed)
        {
            return isLoaded && isPed && isHumanPed;
        }

        internal static PedPopulationMetadataAction DecideModelMetadata(
            bool cancelled, bool loaded, bool isPed, bool isHumanPed,
            int priorFailures, int maximumRetries, bool retryDue)
        {
            if (cancelled) return PedPopulationMetadataAction.Cancel;
            if (!loaded || !retryDue) return PedPopulationMetadataAction.Wait;
            if (isPed && isHumanPed) return PedPopulationMetadataAction.Accept;
            return priorFailures >= Math.Max(0, maximumRetries)
                ? PedPopulationMetadataAction.Quarantine
                : PedPopulationMetadataAction.Retry;
        }

        internal static int MetadataRetryDelayMilliseconds(int failureNumber)
        {
            // 100/200/400ms keeps retries tick-based and bounded below the
            // operation's existing three-second streaming timeout.
            int exponent = Math.Min(2, Math.Max(0, failureNumber - 1));
            return 100 << exponent;
        }

        internal static bool IsMetadataRetryDue(int now, int retryNotBefore)
        {
            return retryNotBefore == 0 || unchecked((uint)(now - retryNotBefore))
                < 0x80000000U;
        }

        internal static bool CanAdd(int activeAdded, int maximumAdded)
        {
            return maximumAdded > 0 && activeAdded >= 0 &&
                activeAdded < Math.Min(20, maximumAdded);
        }

        internal static int CandidateBudget(bool throttled)
        {
            return throttled ? 2 : 4;
        }

        internal static bool IsWorkDue(int now, int lastWork,
            bool throttled)
        {
            int interval = throttled ? 6000 : 3000;
            return unchecked((uint)(now - lastWork)) >= (uint)interval;
        }

        internal static bool WithinWorkBudget(long elapsedMilliseconds)
        {
            return elapsedMilliseconds <= 2;
        }

        // A slow nearby query must not turn every population window into a
        // no-op.  The first unseen candidate is always inspected; later work
        // remains bounded by both the candidate and elapsed-time caps.
        internal static bool CanInspectCandidate(int inspected, int budget,
            bool withinWorkBudget)
        {
            return inspected < Math.Max(0, budget) &&
                (inspected == 0 || withinWorkBudget);
        }

        internal static PedPopulationPendingAction AdvancePending(
            bool cancelled, long elapsedMilliseconds, int timeoutMilliseconds,
            bool modelLoaded, bool modelUsable, bool revalidated)
        {
            if (cancelled) return PedPopulationPendingAction.Cancel;
            if (IsModelLoadTimedOut(elapsedMilliseconds, timeoutMilliseconds))
                return PedPopulationPendingAction.Timeout;
            if (!modelLoaded) return PedPopulationPendingAction.KeepWaiting;
            return modelUsable && revalidated
                ? PedPopulationPendingAction.Create
                : PedPopulationPendingAction.Cancel;
        }

        internal static bool CanRevalidatePendingSource(bool sourceExists,
            bool exactModel, bool sourceEligible, bool worldSafe,
            bool destinationFar, bool destinationExterior)
        {
            return sourceExists && exactModel && CanCreateAfterStreaming(worldSafe,
                sourceEligible, destinationFar, destinationExterior);
        }

        internal static bool IsModelLoadTimedOut(long elapsedMilliseconds,
            int timeoutMilliseconds)
        {
            return elapsedMilliseconds >= Math.Max(0, timeoutMilliseconds);
        }
    }
}
