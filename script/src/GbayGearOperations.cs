using System;
using System.Collections.Generic;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    // Pure ordering primitive: native work must succeed before bookkeeping;
    // any failed bookkeeping path invokes the supplied native rollback once.
    internal static class GearOperationTransaction
    {
        internal static bool Run(Func<bool> apply, Func<bool> persist,
            Action rollback)
        {
            bool enteredApply = false;
            bool applied = false;
            try
            {
                enteredApply = true;
                applied = apply != null && apply();
                if (applied && persist != null && persist()) return true;
            }
            catch { }
            if (enteredApply)
            {
                try { rollback?.Invoke(); }
                catch { }
            }
            return false;
        }
    }

    // Native gear changes are deliberately synchronous and verified before
    // inventory or money is changed.  The staged Juggernaut controller owns
    // its own deferred native transaction.
    public partial class GbayShop
    {
        internal string GearActionCode { get; private set; } = "";
        internal string GearActionMessage { get; private set; } = "";

        internal static bool IsGearPlayerReady(Ped player)
        {
            return player != null && player.Exists() && !player.IsDead &&
                !Game.IsLoading && !GarageManager.IsTransitionInProgress &&
                !Function.Call<bool>(Hash.IS_PLAYER_SWITCH_IN_PROGRESS) &&
                TryResolveProtagonist(player.Model.Hash, out PedHash ignored) &&
                Game.Player.Character != null &&
                Game.Player.Character.Handle == player.Handle &&
                Game.Player.Character.Model.Hash == player.Model.Hash;
        }

        internal bool GiveGearValidated(string gearId, int suppliedPrice)
        {
            // Prices are always re-resolved from GearList below; callers may
            // only supply an old quote for compatibility with the legacy UI.
            _ = suppliedPrice;
            gearId = (gearId ?? "").Trim().ToUpperInvariant();
            BeginGearAction("purchase");
            if (!TryPrepare(gearId, suppliedPrice, out GearPlayerIdentity identity,
                    out int price)) return false;
            if (IsGearOwned(gearId)) return Fail("already_owned", "That gear is already owned.");
            if (!_freeMode && Game.Player.Money < price)
                return Fail("insufficient_funds", "You no longer have enough money.");
            if (string.Equals(gearId, GearList.ARMOR_JUGGERNAUT,
                    StringComparison.OrdinalIgnoreCase))
                return QueueJuggernaut(identity, "purchase", gearId, price);

            CharacterInventory.GearInventorySnapshot snapshot =
                CharacterInventory.CaptureGearSnapshot();
            RuntimeGearSnapshot runtime = RuntimeGearSnapshot.Capture(identity,
                gearId);
            int moneyBefore = Game.Player.Money;
            if (snapshot == null) return Fail("save_rejected", "The gear purchase could not be saved.");
            bool completed = GearOperationTransaction.Run(
                () => ApplyGear(identity, gearId), () =>
                {
                    if (!identity.IsCurrent) return false;
                    CharacterInventory.RecordOwned(gearId, true);
                    if (!CharacterInventory.IsOwned(gearId, true) ||
                        !CharacterInventory.IsGearEquipped(gearId)) return false;
                    Charge(price); return true;
                }, () => RollbackAppliedGear(identity, snapshot, runtime, moneyBefore));
            return completed ? Succeed("gear_purchased", "Gear purchase completed.")
                : Fail("save_rejected", "The gear purchase could not be saved.");
        }

        internal bool EquipGearValidated(string gearId)
        {
            gearId = (gearId ?? "").Trim().ToUpperInvariant();
            BeginGearAction("equip");
            if (!TryPrepare(gearId, null, out GearPlayerIdentity identity,
                    out int ignoredPrice)) return false;
            if (!IsGearOwned(gearId)) return Fail("not_owned", "Purchase this gear first.");
            if (IsGearEquipped(gearId)) return Fail("already_equipped", "That gear is already equipped.");
            if (string.Equals(gearId, GearList.ARMOR_JUGGERNAUT,
                    StringComparison.OrdinalIgnoreCase))
                return QueueJuggernaut(identity, "equip", gearId, 0);

            CharacterInventory.GearInventorySnapshot snapshot =
                CharacterInventory.CaptureGearSnapshot();
            RuntimeGearSnapshot runtime = RuntimeGearSnapshot.Capture(identity,
                gearId);
            if (snapshot == null) return Fail("save_rejected", "The gear change could not be saved.");
            bool completed = GearOperationTransaction.Run(
                () => ApplyGear(identity, gearId), () =>
                {
                    if (!identity.IsCurrent) return false;
                    CharacterInventory.SetGearEquipped(gearId, true);
                    return CharacterInventory.IsGearEquipped(gearId);
                }, () => RollbackAppliedGear(identity, snapshot, runtime,
                    Game.Player.Money));
            return completed ? Succeed("gear_equipped", "Gear equipped.")
                : Fail("save_rejected", "The gear change could not be saved.");
        }

        internal bool UnequipGearValidated(string gearId)
        {
            gearId = (gearId ?? "").Trim().ToUpperInvariant();
            BeginGearAction("unequip");
            if (!TryPrepare(gearId, null, out GearPlayerIdentity identity,
                    out int ignoredPrice)) return false;
            if (!IsGearEquipped(gearId)) return Fail("not_equipped", "That gear is not equipped.");

            // This also cancels a staged juggernaut transaction; the root
            // controller makes that safe even before its Active flag is set.
            CharacterInventory.GearInventorySnapshot snapshot =
                CharacterInventory.CaptureGearSnapshot();
            RuntimeGearSnapshot runtime = RuntimeGearSnapshot.Capture(identity,
                gearId);
            if (snapshot == null) return Fail("save_rejected", "The gear removal could not be saved.");
            bool completed = GearOperationTransaction.Run(
                () => (!GearList.IsArmor(gearId) || RemoveJuggernaut(identity.Player)) &&
                    RemoveGear(identity, gearId), () =>
                {
                    if (!identity.IsCurrent) return false;
                    CharacterInventory.RemoveOwnedGear(gearId);
                    return !CharacterInventory.IsOwned(gearId, true) &&
                        !CharacterInventory.IsGearEquipped(gearId);
                }, () => RollbackAppliedGear(identity, snapshot, runtime,
                    Game.Player.Money));
            return completed ? Succeed("gear_unequipped", "Gear unequipped.")
                : Fail("save_rejected", "The gear removal could not be saved.");
        }

        private bool TryPrepare(string gearId, int? quotedPrice,
            out GearPlayerIdentity identity, out int price)
        {
            identity = default;
            price = 0;
            if (!KnownGear(gearId)) return Fail("invalid_gear", "That item is not in the GBAY gear catalog.");
            Ped player = Game.Player.Character;
            if (!IsGearPlayerReady(player)) return Fail("gear_unavailable", "Gear is unavailable while the player is changing.");
            identity = new GearPlayerIdentity(player);
            if (!identity.IsCurrent) return Fail("player_changed", "The player changed before gear could be applied.");
            price = _freeMode ? 0 : GearList.Prices[gearId];
            if (price < 0) return Fail("invalid_price", "The current gear price is invalid.");
            if (quotedPrice.HasValue && quotedPrice.Value != price)
                return Fail("listing_changed", "The gear price changed. Choose it again.");
            if (!OnlineContentEnabled)
                return Fail("content_unavailable", "ALLIN1 Online Content is not enabled.");
            if (!GearList.IsArmor(gearId) && !string.Equals(gearId,
                    "WEAPON_NIGHTVISION", StringComparison.OrdinalIgnoreCase) &&
                !Function.Call<bool>(Hash.IS_WEAPON_VALID,
                    Game.GenerateHash(gearId)))
                return Fail("invalid_gear", "This GTA build does not support that gear.");
            return true;
        }

        private bool ApplyGear(GearPlayerIdentity identity, string gearId)
        {
            Trace("apply_before", gearId);
            int previousArmor = -1;
            int grantedWeapon = 0;
            bool hadWeapon = false;
            int previousAmmo = 0;
            bool nightVisionTouched = false;
            bool previousNightVisionOwned = false;
            bool previousNightVisionActive = false;
            try
            {
                if (!identity.IsCurrent) return Fail("player_changed", "The player changed before gear could be applied.");
                Ped player = identity.Player;
                if (GearList.IsArmor(gearId))
                {
                    if (!RemoveJuggernaut(player))
                        return Fail("apply_rejected",
                            "Juggernaut armor could not be removed safely.");
                    if (JuggernautPending) return Fail("gear_pending", "Preparing armor; no charge until equipped.");
                    int before = player.Armor;
                    previousArmor = before;
                    int target = GearList.ArmorValues[gearId];
                    if (target < 0 || target > 100) return Fail("invalid_gear", "The armor value is invalid.");
                    if (!identity.IsCurrent) return Fail("player_changed", "The player changed before armor could be applied.");
                    player.Armor = target;
                    if (player.Armor != target)
                    {
                        if (identity.IsCurrent) identity.Player.Armor = before;
                        return Fail("apply_rejected", "GTA did not confirm the armor change.");
                    }
                }
                else if (string.Equals(gearId, "WEAPON_NIGHTVISION",
                    StringComparison.OrdinalIgnoreCase))
                {
                    previousNightVisionOwned = NightVisionOwned;
                    previousNightVisionActive = _nightVisionActive;
                    nightVisionTouched = true;
                    if (!identity.IsCurrent) return Fail("player_changed", "The player changed before night vision could be applied.");
                    NightVisionOwned = true;
                    _nightVisionActive = false;
                    Function.Call(Hash.SET_NIGHTVISION, false);
                    if (Function.Call<bool>(Hash.GET_USINGNIGHTVISION))
                    {
                        RollbackNightVision(identity, previousNightVisionOwned,
                            previousNightVisionActive);
                        return Fail("apply_rejected", "GTA did not confirm night vision.");
                    }
                }
                else
                {
                    int hash = Game.GenerateHash(gearId);
                    if (!Function.Call<bool>(Hash.IS_WEAPON_VALID, hash))
                        return Fail("invalid_gear", "This GTA build does not support that gear.");
                    hadWeapon = Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                        player.Handle, hash, false);
                    previousAmmo = hadWeapon ? Function.Call<int>(
                        Hash.GET_AMMO_IN_PED_WEAPON, player.Handle, hash) : 0;
                    grantedWeapon = hash;
                    if (!identity.IsCurrent) return Fail("player_changed", "The player changed before gear could be applied.");
                    player.Weapons.Give((WeaponHash)hash, 1, false, true);
                    if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                        player.Handle, hash, false))
                    {
                        RollbackWeaponGrant(identity, hash, hadWeapon, previousAmmo);
                        return Fail("apply_rejected", "GTA did not confirm the gear item.");
                    }
                }
                Trace("apply_confirmed", gearId);
                return true;
            }
            catch (Exception ex)
            {
                try
                {
                    if (previousArmor >= 0 && identity.IsCurrent)
                        identity.Player.Armor = previousArmor;
                    if (grantedWeapon != 0)
                        RollbackWeaponGrant(identity, grantedWeapon, hadWeapon,
                            previousAmmo);
                    if (nightVisionTouched)
                        RollbackNightVision(identity, previousNightVisionOwned,
                            previousNightVisionActive);
                }
                catch { }
                Trace("apply_failed", gearId + ": " + ex.GetType().Name);
                return Fail("apply_rejected", "GTA could not apply that gear.");
            }
        }

        private bool RemoveGear(GearPlayerIdentity identity, string gearId)
        {
            Trace("remove_before", gearId);
            int removedWeapon = 0;
            int removedAmmo = 0;
            int previousArmor = -1;
            bool nightVisionTouched = false;
            bool previousNightVisionOwned = false;
            bool previousNightVisionActive = false;
            try
            {
                if (!identity.IsCurrent) return Fail("player_changed", "The player changed before gear could be removed.");
                Ped player = identity.Player;
                if (GearList.IsArmor(gearId))
                {
                    int before = player.Armor;
                    previousArmor = before;
                    if (!identity.IsCurrent) return Fail("player_changed", "The player changed before armor could be removed.");
                    player.Armor = 0;
                    if (player.Armor != 0)
                    {
                        if (identity.IsCurrent) identity.Player.Armor = before;
                        return Fail("remove_rejected", "GTA did not confirm the armor removal.");
                    }
                }
                else if (string.Equals(gearId, "WEAPON_NIGHTVISION",
                    StringComparison.OrdinalIgnoreCase))
                {
                    previousNightVisionOwned = NightVisionOwned;
                    previousNightVisionActive = _nightVisionActive;
                    nightVisionTouched = true;
                    if (!identity.IsCurrent) return Fail("player_changed", "The player changed before night vision could be removed.");
                    NightVisionOwned = false;
                    _nightVisionActive = false;
                    Function.Call(Hash.SET_NIGHTVISION, false);
                    if (Function.Call<bool>(Hash.GET_USINGNIGHTVISION))
                    {
                        RollbackNightVision(identity, previousNightVisionOwned,
                            previousNightVisionActive);
                        return Fail("remove_rejected", "GTA did not confirm night vision removal.");
                    }
                }
                else
                {
                    int hash = Game.GenerateHash(gearId);
                    removedWeapon = hash;
                    removedAmmo = Function.Call<int>(Hash.GET_AMMO_IN_PED_WEAPON,
                        player.Handle, hash);
                    if (!identity.IsCurrent) return Fail("player_changed", "The player changed before gear could be removed.");
                    Function.Call(Hash.REMOVE_WEAPON_FROM_PED, player.Handle, hash);
                    if (Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                        player.Handle, hash, false))
                        return Fail("remove_rejected", "GTA did not confirm the gear removal.");
                }
                Trace("remove_confirmed", gearId);
                return true;
            }
            catch (Exception ex)
            {
                try
                {
                    if (previousArmor >= 0 && identity.IsCurrent)
                        identity.Player.Armor = previousArmor;
                    if (removedWeapon != 0) RollbackWeaponRemoval(identity,
                        removedWeapon, removedAmmo);
                    if (nightVisionTouched) RollbackNightVision(identity,
                        previousNightVisionOwned, previousNightVisionActive);
                }
                catch { }
                Trace("remove_failed", gearId + ": " + ex.GetType().Name);
                return Fail("remove_rejected", "GTA could not remove that gear.");
            }
        }

        private bool QueueJuggernaut(GearPlayerIdentity identity, string operation,
            string gearId, int price)
        {
            if (JuggernautPending)
                return Fail("gear_pending", "Preparing armor; no charge until equipped.");
            bool queued = BeginJuggernaut(identity.Player, operation,
                () => identity.IsCurrent &&
                    (operation == "purchase"
                        ? !IsGearOwned(gearId) && CurrentPrice(gearId) == price &&
                            (_freeMode || Game.Player.Money >= price)
                        : IsGearOwned(gearId) && !IsGearEquipped(gearId)),
                () =>
                {
                    CharacterInventory.GearInventorySnapshot snapshot =
                        CharacterInventory.CaptureGearSnapshot();
                    if (snapshot == null) throw new InvalidOperationException(
                        "gear_snapshot_unavailable");
                    int moneyBefore = Game.Player.Money;
                    try
                    {
                        if (operation == "purchase")
                        {
                            if (CurrentPrice(gearId) != price)
                                throw new InvalidOperationException("gear_price_changed");
                            CharacterInventory.RecordOwned(gearId, true);
                            if (!CharacterInventory.IsOwned(gearId, true) ||
                                !CharacterInventory.IsGearEquipped(gearId))
                                throw new InvalidOperationException("gear_save_rejected");
                            Charge(price);
                            GTA.UI.Screen.ShowSubtitle(
                                "~g~Juggernaut Armor~w~ purchased and equipped.",
                                4000);
                        }
                        else
                        {
                            CharacterInventory.SetGearEquipped(gearId, true);
                            if (!CharacterInventory.IsGearEquipped(gearId))
                                throw new InvalidOperationException("gear_save_rejected");
                            GTA.UI.Screen.ShowSubtitle(
                                "~g~Juggernaut Armor~w~ equipped.", 4000);
                        }
                        Trace("juggernaut_committed", operation);
                    }
                    catch
                    {
                        if (identity.IsCurrent) Game.Player.Money = moneyBefore;
                        CharacterInventory.RestoreGearSnapshot(snapshot);
                        throw;
                    }
                });
            if (!queued) return Fail("gear_rejected",
                "Juggernaut armor could not be prepared.");
            GearActionCode = "gear_pending";
            GearActionMessage = "Preparing armor; no charge until equipped.";
            Trace("operation_pending", operation);
            return true;
        }

        // CharacterInventory invokes this once while restoring each saved
        // item. It intentionally never changes money or persistence and does
        // not retry a failed native grant in a loop.
        internal static bool RestoreGearValidated(Ped player, string gearId)
        {
            gearId = (gearId ?? "").Trim().ToUpperInvariant();
            if (!KnownGear(gearId) || !IsGearPlayerReady(player)) return false;
            var identity = new GearPlayerIdentity(player);
            if (!identity.IsCurrent) return false;
            RuntimeGearSnapshot runtime = RuntimeGearSnapshot.Capture(identity,
                gearId);
            try
            {
                Trace("restore_before", gearId);
                player = identity.Player;
                if (string.Equals(gearId, GearList.ARMOR_JUGGERNAUT,
                        StringComparison.OrdinalIgnoreCase))
                {
                    ApplyJuggernaut(player);
                    return JuggernautActive || JuggernautPending;
                }
                if (GearList.IsArmor(gearId))
                {
                    // A normal armor restore must cancel a staged ballistic
                    // transition even if it has not become Active yet.
                    if (!identity.IsCurrent || !RemoveJuggernaut(player)) return false;
                    if (JuggernautPending) return false;
                    int target = GearList.ArmorValues[gearId];
                    if (target < 0 || target > 100) return false;
                    if (!identity.IsCurrent) return false;
                    player.Armor = target;
                    if (player.Armor == target) return true;
                    runtime.Restore(identity);
                    return false;
                }
                if (string.Equals(gearId, "WEAPON_NIGHTVISION",
                        StringComparison.OrdinalIgnoreCase))
                {
                    if (!identity.IsCurrent) return false;
                    NightVisionOwned = true;
                    _nightVisionActive = false;
                    Function.Call(Hash.SET_NIGHTVISION, false);
                    if (!Function.Call<bool>(Hash.GET_USINGNIGHTVISION)) return true;
                    runtime.Restore(identity);
                    return false;
                }
                int hash = Game.GenerateHash(gearId);
                if (!Function.Call<bool>(Hash.IS_WEAPON_VALID, hash)) return false;
                if (!identity.IsCurrent) return false;
                player.Weapons.Give((WeaponHash)hash, 1, false, false);
                if (Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                        player.Handle, hash, false)) return true;
                runtime.Restore(identity);
                return false;
            }
            catch (Exception ex)
            {
                try { runtime.Restore(identity); } catch { }
                Trace("restore_failed", gearId + ": " + ex.GetType().Name);
                return false;
            }
        }

        private static bool KnownGear(string gearId)
        {
            if (string.IsNullOrWhiteSpace(gearId) ||
                !GearList.Prices.ContainsKey(gearId)) return false;
            foreach (string value in GearList.All)
                if (string.Equals(value, gearId, StringComparison.OrdinalIgnoreCase))
                    return true;
            return false;
        }

        private int CurrentPrice(string gearId) => _freeMode ? 0 :
            GearList.Prices.TryGetValue(gearId, out int price) ? price : -1;

        private void RollbackAppliedGear(GearPlayerIdentity identity,
            CharacterInventory.GearInventorySnapshot snapshot,
            RuntimeGearSnapshot runtime, int moneyBefore)
        {
            CharacterInventory.RestoreGearSnapshot(snapshot);
            try
            {
                if (identity.IsCurrent)
                {
                    runtime.Restore(identity);
                    Game.Player.Money = moneyBefore;
                    if (runtime.WasJuggernaut && !JuggernautActive)
                        ApplyJuggernaut(identity.Player);
                }
            }
            catch { }
        }

        private readonly struct RuntimeGearSnapshot
        {
            private readonly int _armor, _weapon, _ammo;
            private readonly bool _hadWeapon, _nightOwned, _nightActive;
            private readonly bool _armorTouched, _nightTouched;
            internal readonly bool WasJuggernaut;
            private RuntimeGearSnapshot(int armor, int weapon, int ammo,
                bool hadWeapon, bool nightOwned, bool nightActive, bool armorTouched,
                bool nightTouched, bool wasJuggernaut)
            {
                _armor = armor; _weapon = weapon; _ammo = ammo;
                _hadWeapon = hadWeapon; _nightOwned = nightOwned;
                _nightActive = nightActive;
                _armorTouched = armorTouched; _nightTouched = nightTouched;
                WasJuggernaut = wasJuggernaut;
            }
            internal static RuntimeGearSnapshot Capture(GearPlayerIdentity id,
                string gearId)
            {
                if (!id.IsCurrent) throw new InvalidOperationException("player_changed_before_snapshot");
                Ped player = id.Player;
                int weapon = !GearList.IsArmor(gearId) && gearId != "WEAPON_NIGHTVISION"
                    ? Game.GenerateHash(gearId) : 0;
                bool had = weapon != 0 && Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    player.Handle, weapon, false);
                int ammo = had ? Function.Call<int>(Hash.GET_AMMO_IN_PED_WEAPON,
                    player.Handle, weapon) : 0;
                return new RuntimeGearSnapshot(player.Armor, weapon, ammo, had,
                    NightVisionOwned, _nightVisionActive, GearList.IsArmor(gearId),
                    gearId == "WEAPON_NIGHTVISION", GearList.IsArmor(gearId) && JuggernautActive);
            }
            internal void Restore(GearPlayerIdentity id)
            {
                if (!id.IsCurrent) return;
                Ped player = id.Player;
                if (_armorTouched) player.Armor = _armor;
                if (_nightTouched)
                {
                    NightVisionOwned = _nightOwned;
                    _nightVisionActive = _nightActive;
                    Function.Call(Hash.SET_NIGHTVISION, _nightActive);
                }
                if (_weapon == 0) return;
                if (_hadWeapon)
                {
                    Function.Call(Hash.GIVE_WEAPON_TO_PED, player.Handle, _weapon,
                        0, false, false);
                    Function.Call(Hash.SET_PED_AMMO, player.Handle, _weapon, _ammo);
                }
                else Function.Call(Hash.REMOVE_WEAPON_FROM_PED, player.Handle,
                    _weapon);
            }
        }

        private static void RollbackWeaponGrant(GearPlayerIdentity identity,
            int hash, bool hadWeapon, int ammo)
        {
            if (!identity.IsCurrent) return;
            Ped player = identity.Player;
            if (hadWeapon)
            {
                if (!Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON, player.Handle, hash, false))
                    Function.Call(Hash.GIVE_WEAPON_TO_PED, player.Handle, hash, 0, false, false);
                Function.Call(Hash.SET_PED_AMMO, player.Handle, hash, ammo);
            }
            else Function.Call(Hash.REMOVE_WEAPON_FROM_PED, player.Handle, hash);
        }

        private static void RollbackWeaponRemoval(GearPlayerIdentity identity,
            int hash, int ammo)
        {
            if (!identity.IsCurrent || Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                    identity.Player.Handle, hash, false)) return;
            Function.Call(Hash.GIVE_WEAPON_TO_PED, identity.Player.Handle, hash,
                0, false, false);
            Function.Call(Hash.SET_PED_AMMO, identity.Player.Handle, hash, ammo);
        }

        private static void RollbackNightVision(GearPlayerIdentity identity,
            bool owned, bool active)
        {
            if (!identity.IsCurrent) return;
            NightVisionOwned = owned;
            _nightVisionActive = active;
            Function.Call(Hash.SET_NIGHTVISION, active);
        }

        private readonly struct GearPlayerIdentity
        {
            internal readonly int Handle;
            internal readonly int Model;
            internal GearPlayerIdentity(Ped player)
            {
                Handle = player.Handle;
                Model = player.Model.Hash;
            }
            internal Ped Player => Game.Player.Character;
            internal bool IsCurrent
            {
                get
                {
                    Ped player = Game.Player.Character;
                    return player != null && player.Exists() &&
                        player.Handle == Handle && player.Model.Hash == Model &&
                        IsGearPlayerReady(player);
                }
            }
        }

        private void Charge(int price)
        {
            if (!_freeMode && price > 0) Game.Player.Money -= price;
        }

        private void BeginGearAction(string operation)
        {
            GearActionCode = "";
            GearActionMessage = "";
            Trace("operation_begin", operation);
        }

        private bool Succeed(string code, string message)
        {
            GearActionCode = code;
            GearActionMessage = message;
            Trace("operation_succeeded", code);
            return true;
        }

        private bool Fail(string code, string message)
        {
            GearActionCode = code;
            GearActionMessage = message;
            Trace("operation_failed", code);
            return false;
        }

        private static void Trace(string stage, string detail)
        {
            ClientLog.Info("GBAY", "gear_operation", new Dictionary<string, object>
            {
                { "stage", stage }, { "detail", detail }
            });
        }
    }
}
