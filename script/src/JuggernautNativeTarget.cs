using System;
using System.Collections.Generic;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    internal sealed class JuggernautVariation
    {
        internal readonly bool Prop;
        internal readonly int Slot, Drawable, Texture, Palette;
        internal JuggernautVariation(int slot, int drawable, int texture,
            bool prop = false, int palette = 0)
        { Slot = slot; Drawable = drawable; Texture = texture; Prop = prop; Palette = palette; }

        internal static bool ValidIndices(int drawable, int texture,
            int drawableCount, int textureCount) =>
            drawable >= 0 && texture >= 0 && drawableCount > 0 &&
            textureCount > 0 && drawable < drawableCount && texture < textureCount;

        internal static JuggernautVariation[] ForCharacter(PedHash character)
        {
            // Paleto Score variants, with Franklin's unavailable torso/helmet omitted.
            if (character == PedHash.Franklin) return new[] {
                new JuggernautVariation(4, 4, 0), new JuggernautVariation(5, 4, 0),
                new JuggernautVariation(9, 3, 0) };
            if (character == PedHash.Michael) return new[] {
                new JuggernautVariation(3, 5, 1), new JuggernautVariation(4, 5, 1),
                new JuggernautVariation(5, 1, 1), new JuggernautVariation(6, 1, 1),
                new JuggernautVariation(8, 5, 2), new JuggernautVariation(9, 1, 2),
                new JuggernautVariation(11, 0, 1), new JuggernautVariation(0, 26, 1, true),
                new JuggernautVariation(2, 0, 1, true) };
            if (character == PedHash.Trevor) return new[] {
                new JuggernautVariation(3, 2, 1), new JuggernautVariation(4, 2, 1),
                new JuggernautVariation(5, 1, 1), new JuggernautVariation(6, 1, 1),
                new JuggernautVariation(8, 2, 1), new JuggernautVariation(9, 1, 4),
                new JuggernautVariation(11, 0, 0), new JuggernautVariation(0, 24, 1, true) };
            return Array.Empty<JuggernautVariation>();
        }
    }

    // All operations run on SHVDN ticks. No native ped survives a wait without
    // its current player handle AND model being checked again.
    internal sealed class JuggernautNativeTarget : IJuggernautEquipTarget
    {
        private const string Clipset = "ANIM_GROUP_MOVE_BALLISTIC";
        private readonly int _handle, _model;
        private readonly PedHash _character;
        private readonly string _operation;
        private readonly Func<bool> _canCommit;
        private readonly Action _commit;
        private JuggernautVariation[] _plan, _saved;
        private int _health, _maxHealth, _armor;
        private bool _criticalHits;
        private int _lastHealth;

        internal JuggernautNativeTarget(Ped player, string operation,
            Func<bool> canCommit, Action commit)
        {
            _handle = player.Handle; _model = player.Model.Hash;
            if (!GbayShop.TryResolveProtagonist(_model, out _character))
                throw new InvalidOperationException("unsupported_player_model");
            _operation = operation; _canCommit = canCommit; _commit = commit;
        }

        public bool IsSamePlayer
        {
            get
            {
                Ped player = Game.Player.Character;
                return player != null && player.Exists() && !player.IsDead &&
                    player.Handle == _handle && player.Model.Hash == _model;
            }
        }
        public bool IsSafe => IsSamePlayer && GbayShop.IsGearPlayerReady(Game.Player.Character);
        public bool AnimationLoaded => Function.Call<bool>(Hash.HAS_ANIM_SET_LOADED, Clipset);
        public bool CanCommit => IsSafe && (_canCommit?.Invoke() ?? true);

        private Ped Player()
        {
            if (!IsSafe) throw new InvalidOperationException("player_or_world_changed");
            return Game.Player.Character;
        }

        private void Validate(JuggernautVariation item, bool restoring)
        {
            Ped player = Player();
            if (item.Prop && restoring && item.Drawable == -1) return;
            int drawables = Function.Call<int>(item.Prop
                ? Hash.GET_NUMBER_OF_PED_PROP_DRAWABLE_VARIATIONS
                : Hash.GET_NUMBER_OF_PED_DRAWABLE_VARIATIONS, player, item.Slot);
            // Never query textures for an invalid drawable.
            int textures = item.Drawable >= 0 && item.Drawable < drawables
                ? Function.Call<int>(item.Prop
                    ? Hash.GET_NUMBER_OF_PED_PROP_TEXTURE_VARIATIONS
                    : Hash.GET_NUMBER_OF_PED_TEXTURE_VARIATIONS,
                    player, item.Slot, item.Drawable) : 0;
            bool valid = JuggernautVariation.ValidIndices(
                item.Drawable, item.Texture, drawables, textures);
            if (!item.Prop && (item.Palette < 0 || item.Palette > 3)) valid = false;
            if (valid && !item.Prop)
                valid = Function.Call<bool>(Hash.IS_PED_COMPONENT_VARIATION_VALID,
                    player, item.Slot, item.Drawable, item.Texture);
            Trace("variation_validate", Describe(item) + ";drawables=" + drawables +
                ";textures=" + textures + ";valid=" + valid + ";restore=" + restoring);
            if (!valid) throw new InvalidOperationException("invalid_variation:" + Describe(item));
        }

        public void PreflightAndCapture()
        {
            Ped player = Player();
            _plan = JuggernautVariation.ForCharacter(_character);
            if (_plan.Length == 0) throw new InvalidOperationException("empty_outfit_plan");
            var saved = new List<JuggernautVariation>();
            foreach (JuggernautVariation item in _plan)
            {
                Validate(item, false);
                int drawable = Function.Call<int>(item.Prop ? Hash.GET_PED_PROP_INDEX
                    : Hash.GET_PED_DRAWABLE_VARIATION, player, item.Slot);
                int texture = Function.Call<int>(item.Prop ? Hash.GET_PED_PROP_TEXTURE_INDEX
                    : Hash.GET_PED_TEXTURE_VARIATION, player, item.Slot);
                int palette = item.Prop ? 0 : Function.Call<int>(
                    Hash.GET_PED_PALETTE_VARIATION, player, item.Slot);
                var previous = new JuggernautVariation(item.Slot, drawable, texture, item.Prop, palette);
                Validate(previous, true);
                saved.Add(previous);
            }
            _health = player.Health; _maxHealth = player.MaxHealth;
            _armor = player.Armor; _criticalHits = player.CanSufferCriticalHits;
            _saved = saved.ToArray();
        }

        public void RequestAnimation()
        {
            Player();
            Function.Call(Hash.REQUEST_ANIM_SET, Clipset);
        }

        private static string Describe(JuggernautVariation item) =>
            (item.Prop ? "prop=" : "component=") + item.Slot +
            ";drawable=" + item.Drawable + ";texture=" + item.Texture;

        private void SetVariation(JuggernautVariation item, bool restoring)
        {
            Validate(item, restoring);
            Ped player = Player();
            // Written before the native: a native engine crash cannot be caught by C#.
            Trace("variation_begin", Describe(item) + ";restore=" + restoring);
            if (item.Prop)
            {
                if (item.Drawable == -1) Function.Call(Hash.CLEAR_PED_PROP, player, item.Slot);
                else Function.Call(Hash.SET_PED_PROP_INDEX, player, item.Slot,
                    item.Drawable, item.Texture, true);
            }
            else Function.Call(Hash.SET_PED_COMPONENT_VARIATION, player, item.Slot,
                item.Drawable, item.Texture, item.Palette);
            player = Player();
            int actualDrawable = Function.Call<int>(item.Prop ? Hash.GET_PED_PROP_INDEX
                : Hash.GET_PED_DRAWABLE_VARIATION, player, item.Slot);
            int actualTexture = item.Prop && item.Drawable == -1 ? item.Texture
                : Function.Call<int>(item.Prop ? Hash.GET_PED_PROP_TEXTURE_INDEX
                    : Hash.GET_PED_TEXTURE_VARIATION, player, item.Slot);
            if (actualDrawable != item.Drawable || actualTexture != item.Texture)
                throw new InvalidOperationException("variation_not_confirmed:" + Describe(item));
            Trace("variation_complete", Describe(item));
        }

        public void ApplyOutfit()
        {
            if (_saved == null) throw new InvalidOperationException("missing_outfit_snapshot");
            foreach (JuggernautVariation item in _plan) SetVariation(item, false);
        }

        public void ApplyEffects()
        {
            Ped player = Player();
            // Check at the setter too, not only in the transaction's polling stage.
            if (!AnimationLoaded) throw new InvalidOperationException("animation_unloaded_before_apply");
            Trace("movement_begin", Clipset);
            Function.Call(Hash.SET_PED_MOVEMENT_CLIPSET, player, Clipset, 0.25f);
            Trace("movement_complete", Clipset);
            Trace("health_begin", "max=1000");
            player.MaxHealth = 1000; player.Health = 1000; player.Armor = 0;
            player.CanSufferCriticalHits = false;
            player = Player();
            if (player.MaxHealth != 1000 || player.Health != 1000 || player.Armor != 0 ||
                player.CanSufferCriticalHits)
                throw new InvalidOperationException("health_effects_not_confirmed");
            _lastHealth = player.Health;
            Trace("health_complete", "max=1000");
        }

        public void Restore(bool rollback)
        {
            Ped player = Player();
            if (_saved == null) return;
            // Preflight the entire restore before its first setter as well.
            foreach (JuggernautVariation item in _saved) Validate(item, true);
            foreach (JuggernautVariation item in _saved) SetVariation(item, true);
            player = Player();
            player.MaxHealth = _maxHealth;
            player.Health = rollback ? _health : Math.Min(player.Health, _maxHealth);
            if (rollback) player.Armor = _armor;
            player.CanSufferCriticalHits = _criticalHits;
            Function.Call(Hash.RESET_PED_MOVEMENT_CLIPSET, player, 0.25f);
        }

        public void Commit()
        {
            if (!CanCommit) throw new InvalidOperationException("purchase_or_player_changed");
            _commit?.Invoke();
        }
        public void ReleaseAnimation() => Function.Call(Hash.REMOVE_ANIM_SET, Clipset);
        public void Trace(string stage, string detail) => ClientLog.Info("GBAY", "juggernaut_" + stage,
            new Dictionary<string, object> { { "handle", _handle }, { "model", _model },
                { "character", _character.ToString() }, { "operation", _operation }, { "detail", detail } });

        internal void TickDamageReduction()
        {
            if (!IsSafe) return;
            Ped player = Player();
            int health = player.Health;
            if (health > 0 && health < _lastHealth)
            {
                health = Math.Min(player.MaxHealth, health + (int)((_lastHealth - health) * 0.80f));
                player.Health = health;
            }
            _lastHealth = health;
        }
    }
}
