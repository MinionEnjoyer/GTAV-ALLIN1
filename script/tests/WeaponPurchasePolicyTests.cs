using Xunit;

namespace ALLIN1.Tests
{
    public sealed class WeaponPurchasePolicyTests
    {
        [Fact]
        public void StickyBombQuote_ChargesEveryGrantedBomb()
        {
            WeaponPurchaseQuote quote = WeaponPurchasePolicy.Quote(
                600, "Throwables", 25, false);

            Assert.Equal(WeaponPurchaseStatus.Available, quote.Status);
            Assert.True(quote.QuantityPriced);
            Assert.Equal(600, quote.UnitPrice);
            Assert.Equal(25, quote.Quantity);
            Assert.Equal(25, quote.GrantAmmo);
            Assert.Equal(15000, quote.TotalPrice);
        }

        [Fact]
        public void FirearmPrice_IsNotMultipliedByItsAmmoCapacity()
        {
            WeaponPurchaseQuote quote = WeaponPurchasePolicy.Quote(
                650000, "Machine Guns", 1, false);

            Assert.False(quote.QuantityPriced);
            Assert.Equal(1, quote.Quantity);
            Assert.Equal(9999, quote.GrantAmmo);
            Assert.Equal(650000, quote.TotalPrice);
        }

        [Fact]
        public void MeleePurchase_UsesOneGrantUnitWithoutAmmoCapacity()
        {
            WeaponPurchaseQuote quote = WeaponPurchasePolicy.Quote(
                50, "Melee", 1, false);

            Assert.Equal(WeaponPurchaseStatus.Available, quote.Status);
            Assert.Equal(1, quote.Quantity);
            Assert.Equal(9999, quote.GrantAmmo);
            Assert.Equal(50, quote.TotalPrice);
        }

        [Fact]
        public void ThrowablePurchase_FailsClosedWhenCapacityIsUnknown()
        {
            WeaponPurchaseQuote quote = WeaponPurchasePolicy.Quote(
                600, "Throwables", 0, false);

            Assert.Equal(WeaponPurchaseStatus.CapacityUnavailable, quote.Status);
            Assert.Equal(0, quote.TotalPrice);
            Assert.Equal(0, quote.GrantAmmo);
        }

        [Fact]
        public void FreeMode_KeepsTheRealQuantityButWaivesTheTotal()
        {
            WeaponPurchaseQuote quote = WeaponPurchasePolicy.Quote(
                600, "Throwables", 25, true);

            Assert.Equal(25, quote.Quantity);
            Assert.Equal(25, quote.GrantAmmo);
            Assert.Equal(0, quote.TotalPrice);
        }

        [Fact]
        public void ThrowableRefill_UsesItsCatalogUnitPrice()
        {
            Assert.Equal(600, WeaponPurchasePolicy.RefillUnitPrice(
                "Throwables", 600, 50));
            Assert.Equal(3, WeaponPurchasePolicy.RefillUnitPrice(
                "Assault Rifles", 95000, 3));
        }

        [Fact]
        public void ActualGrantedQuantity_DeterminesTheFinalCharge()
        {
            WeaponPurchaseQuote quote = WeaponPurchasePolicy.Quote(
                600, "Throwables", 25, false);

            Assert.Equal(12000, WeaponPurchasePolicy.PriceActualQuantity(
                quote, 20, false));
        }
    }
}
