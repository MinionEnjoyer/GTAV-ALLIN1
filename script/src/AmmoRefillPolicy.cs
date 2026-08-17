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
    }
}
