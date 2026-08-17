using System;

namespace ALLIN1
{
    internal enum WeaponPurchaseStatus
    {
        Available,
        CapacityUnavailable,
    }

    internal readonly struct WeaponPurchaseQuote
    {
        internal WeaponPurchaseStatus Status { get; }
        internal int UnitPrice { get; }
        internal int Quantity { get; }
        internal int GrantAmmo { get; }
        internal int TotalPrice { get; }
        internal bool QuantityPriced { get; }

        internal WeaponPurchaseQuote(
            WeaponPurchaseStatus status, int unitPrice, int quantity,
            int grantAmmo, int totalPrice, bool quantityPriced)
        {
            Status = status;
            UnitPrice = unitPrice;
            Quantity = quantity;
            GrantAmmo = grantAmmo;
            TotalPrice = totalPrice;
            QuantityPriced = quantityPriced;
        }
    }

    internal static class WeaponPurchasePolicy
    {
        internal static bool IsQuantityPriced(string category)
        {
            return string.Equals(category, "Throwables",
                StringComparison.OrdinalIgnoreCase);
        }

        internal static WeaponPurchaseQuote Quote(
            int unitPrice, string category, int configuredQuantity,
            bool freeMode)
        {
            int normalizedUnitPrice = Math.Max(0, unitPrice);
            bool quantityPriced = IsQuantityPriced(category);
            if (quantityPriced && configuredQuantity <= 0)
            {
                return new WeaponPurchaseQuote(
                    WeaponPurchaseStatus.CapacityUnavailable,
                    normalizedUnitPrice, 0, 0, 0, true);
            }

            // Keep the established full-ammo first grant for firearms. Only
            // explicit quantity-priced bundles replace that legacy behavior.
            int grantAmmo = quantityPriced ? configuredQuantity : 9999;
            int quantity = quantityPriced ? configuredQuantity : 1;
            int total = freeMode ? 0 : SafeMultiply(normalizedUnitPrice, quantity);
            return new WeaponPurchaseQuote(
                WeaponPurchaseStatus.Available, normalizedUnitPrice,
                quantity, grantAmmo, total, quantityPriced);
        }

        internal static int RefillUnitPrice(
            string category, int catalogUnitPrice, int fallbackAmmoPrice)
        {
            return IsQuantityPriced(category)
                ? Math.Max(0, catalogUnitPrice)
                : Math.Max(0, fallbackAmmoPrice);
        }

        internal static int PriceActualQuantity(
            WeaponPurchaseQuote quote, int actualQuantity, bool freeMode)
        {
            if (freeMode) return 0;
            if (!quote.QuantityPriced) return quote.TotalPrice;
            return SafeMultiply(quote.UnitPrice, Math.Max(0, actualQuantity));
        }

        private static int SafeMultiply(int price, int quantity)
        {
            long total = (long)Math.Max(0, price) * Math.Max(0, quantity);
            return total >= int.MaxValue ? int.MaxValue : (int)total;
        }
    }
}
