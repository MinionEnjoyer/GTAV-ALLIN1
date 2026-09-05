namespace ALLIN1
{
    internal enum AmmoCapacityStatus
    {
        Unavailable,
        NotApplicable,
        FullyStocked,
        NeedsRefill,
    }

    internal readonly struct AmmoCapacityResult
    {
        internal AmmoCapacityStatus Status { get; }
        internal int RoundsNeeded { get; }

        internal AmmoCapacityResult(AmmoCapacityStatus status, int roundsNeeded)
        {
            Status = status;
            RoundsNeeded = roundsNeeded;
        }
    }

    internal static class AmmoRefillPolicy
    {
        internal static int Price(int rounds, int unitPrice, bool freeMode) =>
            freeMode ? 0 : (int)System.Math.Min(int.MaxValue,
                (long)System.Math.Max(0, rounds) * System.Math.Max(1, unitPrice));

        private const int RefillMagazineCount = 10;
        private const int AbsoluteRefillLimit = 600;

        internal static int ResolveRefillTarget(
            bool capacityResolved, int nativeMaxAmmo, int maxClipAmmo)
        {
            if (!capacityResolved || nativeMaxAmmo <= 0)
                return nativeMaxAmmo;

            int boundedTarget = AbsoluteRefillLimit;
            if (maxClipAmmo > 0)
            {
                long magazineTarget = (long)maxClipAmmo * RefillMagazineCount;
                boundedTarget = (int)System.Math.Min(
                    AbsoluteRefillLimit, magazineTarget);
            }
            return System.Math.Min(nativeMaxAmmo, boundedTarget);
        }

        internal static AmmoCapacityResult Evaluate(
            bool capacityResolved, int currentAmmo, int maxAmmo)
        {
            if (!capacityResolved)
                return new AmmoCapacityResult(AmmoCapacityStatus.Unavailable, 0);
            if (maxAmmo <= 0)
                return new AmmoCapacityResult(AmmoCapacityStatus.NotApplicable, 0);
            int needed = maxAmmo - currentAmmo;
            return needed <= 0
                ? new AmmoCapacityResult(AmmoCapacityStatus.FullyStocked, 0)
                : new AmmoCapacityResult(AmmoCapacityStatus.NeedsRefill, needed);
        }

        internal static int ClampPreservedAmmo(
            int ammoBeforeComponents, bool capacityResolved,
            int maxAmmoAfterComponents)
        {
            int preserved = System.Math.Max(0, ammoBeforeComponents);
            if (!capacityResolved || maxAmmoAfterComponents <= 0)
                return preserved;
            return System.Math.Min(preserved, maxAmmoAfterComponents);
        }
    }
}
