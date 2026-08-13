using System;

namespace ALLIN1
{
    /// <summary>
    /// Pure placement math shared by every garage.  A garage owns a floor
    /// anchor; the spawned model owns the distance from its origin to its
    /// lowest bound.  Keeping those inputs separate avoids per-class Z tables.
    /// </summary>
    internal static class VehiclePlacementMath
    {
        internal const float DefaultGroundClearance = 0.015f;
        internal const float MaximumNativeRootCorrection = 2.5f;
        internal const float MinimumMeasuredRootOffset = -2.5f;
        internal const float MaximumMeasuredRootOffset = 5.0f;

        internal static bool IsFinite(float value)
        {
            return !float.IsNaN(value) && !float.IsInfinity(value);
        }

        internal static bool HasUsableBounds(float minimumZ, float maximumZ)
        {
            return IsFinite(minimumZ) && IsFinite(maximumZ)
                && maximumZ > minimumZ
                && minimumZ > -10f && maximumZ < 15f;
        }

        internal static float CalculateRootZ(
            float floorZ,
            float minimumModelZ,
            float nativeRootZ,
            float clearance = DefaultGroundClearance)
        {
            if (!IsFinite(floorZ) || !IsFinite(minimumModelZ)
                || !IsFinite(nativeRootZ))
                return nativeRootZ;

            float calculated = floorZ - minimumModelZ + clearance;
            if (!IsFinite(calculated)) return nativeRootZ;

            // Bad collision bounds should not launch a vehicle into the roof
            // or bury it under the interior.  The native root remains the
            // deterministic fallback for unusual/add-on models.
            float correction = calculated - nativeRootZ;
            if (Math.Abs(correction) > MaximumNativeRootCorrection)
                return nativeRootZ;
            return calculated;
        }

        internal static bool IsUsableMeasuredRootOffset(float rootOffset)
        {
            return IsFinite(rootOffset)
                && rootOffset >= MinimumMeasuredRootOffset
                && rootOffset <= MaximumMeasuredRootOffset;
        }

        internal static float CalculateMeasuredRootZ(
            float floorZ, float measuredRootOffset, float nativeRootZ)
        {
            if (!IsFinite(floorZ)
                || !IsUsableMeasuredRootOffset(measuredRootOffset)
                || !IsFinite(nativeRootZ))
                return nativeRootZ;

            float calculated = floorZ + measuredRootOffset;
            if (!IsFinite(calculated)
                || Math.Abs(calculated - nativeRootZ)
                    > MaximumNativeRootCorrection)
                return nativeRootZ;
            return calculated;
        }

    }
}
