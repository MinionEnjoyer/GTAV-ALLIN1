// Conservative ambient-NPC firearm replacement.  Never touches the player,
// saves, mission/scripted entities, vehicles, or visible/nearby/interacting peds.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using GTA;
using GTA.Native;

namespace ALLIN1
{
    public sealed class WeaponPopulationInjector : Script
    {
        private const int RefreshMilliseconds = 5000;
        private const int MaximumDocumentBytes = 1024 * 1024;
        private const int SeenTtlMilliseconds = 90000;
        private const int MaximumSeen = 256;
        private const float ScanRadius = 200f;
        private const float MinimumDistance = 60f;

        private sealed class Selection
        {
            internal RuntimeWeaponEntry Entry;
            internal int Weight;
        }

        private readonly List<Selection> _selections = new List<Selection>();
        private readonly HashSet<int> _seen = new HashSet<int>();
        private readonly Queue<KeyValuePair<int, int>> _seenOrder =
            new Queue<KeyValuePair<int, int>>();
        private readonly Random _random = new Random();
        private static volatile PopulationRuntimeDiagnostics _diagnostics =
            new PopulationRuntimeDiagnostics();
        private bool _enabled;
        private bool _activeDuringMissions;
        private float _replacementChance;
        private int _lastRefresh = int.MinValue;
        private int _lastWork;
        private int _lastTelemetry;
        private float _smoothedFps = 60f;
        private string _configurationDigest = "";
        private int _attempted;
        private int _skipped;
        private int _swapped;
        private int _configuredChoices;
        private long _diagnosticScanned;
        private long _diagnosticAttempted;
        private long _diagnosticSwapped;
        private long _diagnosticRejected;
        private string _configurationState = "starting";
        private string _configurationDetail = "Waiting for weapon population configuration";
        private string _lastError = "";
        private bool _lastErrorIsTransientScanFailure;
        private string _lastScanDetail = "Waiting for the first bounded ambient scan";
        private double _scanMilliseconds;
        private double _maximumScanMilliseconds;
        private double _refreshMilliseconds;
        private double _maximumRefreshMilliseconds;
        private int _scans;
        private int _refreshes;

        internal static PopulationRuntimeDiagnostics Diagnostics => _diagnostics;

        public WeaponPopulationInjector()
        {
            Interval = 100;
            Tick += OnTick;
        }

        private void OnTick(object sender, EventArgs args)
        {
            int now = Game.GameTime;
            UpdatePerformance();
            ReportTelemetry(now);
            if (unchecked((uint)(now - _lastRefresh)) >= (uint)RefreshMilliseconds)
            {
                _lastRefresh = now;
                Stopwatch refresh = Stopwatch.StartNew();
                try { RefreshConfiguration(); }
                finally
                {
                    double elapsed = refresh.Elapsed.TotalMilliseconds;
                    _refreshMilliseconds += elapsed;
                    _maximumRefreshMilliseconds = Math.Max(_maximumRefreshMilliseconds, elapsed);
                    _refreshes++;
                }
            }
            Ped player = Game.Player.Character;
            if (!_enabled)
            {
                PublishDiagnostics(_configurationState, _configurationDetail, false);
                return;
            }
            string pauseReason = GlobalPauseReason(player);
            if (!string.IsNullOrEmpty(pauseReason))
            {
                PublishDiagnostics("paused", pauseReason, false);
                return;
            }
            if (_selections.Count == 0)
            {
                PublishDiagnostics("waiting", "No eligible authorized civilian weapon choices", false);
                return;
            }
            if (_replacementChance <= 0f)
            {
                PublishDiagnostics("active", "Replacement chance is 0%; no scans needed", false);
                return;
            }
            bool throttled = _smoothedFps < 40f;
            if (!WeaponPopulationPolicy.IsWorkDue(now, _lastWork, throttled))
            {
                // The scan result is the useful diagnostic.  Do not overwrite
                // it on the next 100 ms tick merely because the bounded work
                // interval has not elapsed yet.
                PublishDiagnostics("active", _lastScanDetail, throttled);
                return;
            }
            _lastWork = now;
            PruneSeen(now);
            _lastScanDetail = TryReplaceOne(player, throttled, now);
            PublishDiagnostics("active", _lastScanDetail, throttled);
        }

        private void RefreshConfiguration()
        {
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory,
                ".allin1", "weapon-population.json");
            try
            {
                if (!File.Exists(path))
                {
                    if (_configurationDigest == "missing") return;
                    _configurationDigest = "missing";
                    _selections.Clear(); _enabled = false; _activeDuringMissions = false;
                    _configuredChoices = 0;
                    _configurationState = "unconfigured";
                    _configurationDetail = "No weapon population configuration was found";
                    _lastError = "";
                    _lastErrorIsTransientScanFailure = false;
                    return;
                }
                byte[] bytes = ReadBoundedConfiguration(path);
                string digest;
                using (SHA256 hash = SHA256.Create())
                    digest = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "");
                if (string.Equals(digest, _configurationDigest,
                        StringComparison.Ordinal))
                {
                    if (_enabled && RuntimeWeaponCatalog.RefreshIfChanged())
                        RevalidateSelections();
                    return;
                }
                _configurationDigest = digest;
                _selections.Clear(); _enabled = false; _activeDuringMissions = false;
                _configuredChoices = 0;
                string text = new UTF8Encoding(false, true).GetString(bytes);
                Dictionary<string, object> root = Object(PortableJsonParser.Parse(text));
                ExactFields(root, new[] { "schema_version", "enabled",
                    "replacement_chance", "entries" }, new[] { "active_during_missions" });
                if (Integer(root, "schema_version") != 1)
                    throw new InvalidDataException("Unsupported weapon population schema version");
                _enabled = Boolean(root, "enabled");
                _activeDuringMissions = OptionalBoolean(root, "active_during_missions");
                _replacementChance = (float)Number(root, "replacement_chance", 0d, 1d);
                object[] rows = Array(root, "entries");
                _configuredChoices = rows.Length;
                if (rows.Length > 512) throw new InvalidDataException("weapon population has too many entries");
                // A disabled document cannot alter a ped, so avoid rebuilding
                // every receipt-hashed catalog merely to observe its default.
                if (!_enabled)
                {
                    _configurationState = "disabled";
                    _configurationDetail = "Weapon population is disabled in its configuration";
                    _lastError = "";
                    _lastErrorIsTransientScanFailure = false;
                    return;
                }
                RuntimeWeaponCatalog.RefreshIfChanged();
                var selected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (object raw in rows)
                {
                    Dictionary<string, object> row = Object(raw);
                    ExactFields(row, new[] { "package_id", "weapon", "enabled", "weight" });
                    string packageId = Identifier(Text(row, "package_id"));
                    string weapon = Weapon(Text(row, "weapon"));
                    string key = packageId + "/" + weapon;
                    if (!selected.Add(key)) throw new InvalidDataException("weapon population repeats a selection");
                    bool included = Boolean(row, "enabled");
                    int weight = Integer(row, "weight");
                    if (weight < 1 || weight > 100)
                        throw new InvalidDataException("weapon population weight must be 1 to 100");
                    RuntimeWeaponEntry entry;
                    if (!RuntimeWeaponCatalog.TryGetPopulationEntry(packageId, weapon, out entry))
                        throw new InvalidDataException("weapon selection is not receipt-authorized: " + key);
                    if (!WeaponPopulationPolicy.IsReplaceableCategory(entry.Category))
                        throw new InvalidDataException("weapon population category is not civilian-safe");
                    if (included) _selections.Add(new Selection { Entry = entry, Weight = weight });
                }
                ClientLog.Info("WeaponPopulation", "configuration_loaded",
                    new Dictionary<string, object> { { "enabled", _enabled },
                        { "active_during_missions", _activeDuringMissions },
                        { "selections", _selections.Count } });
                _configurationState = _selections.Count == 0 ? "waiting" : "active";
                _configurationDetail = _selections.Count == 0
                    ? "No enabled authorized civilian weapon choices"
                    : "Configuration loaded";
                _lastError = "";
                _lastErrorIsTransientScanFailure = false;
            }
            catch (Exception ex) when (ex is IOException || ex is UnauthorizedAccessException ||
                ex is InvalidDataException || ex is FormatException || ex is ArgumentException)
            {
                _enabled = false;
                _activeDuringMissions = false;
                _selections.Clear();
                _configurationState = "configuration_error";
                _configurationDetail = ex.Message;
                _lastError = ex.Message;
                _lastErrorIsTransientScanFailure = false;
                ClientLog.Warn("WeaponPopulation", "configuration_rejected",
                    new Dictionary<string, object> { { "reason", ex.Message } });
            }
        }

        private string TryReplaceOne(Ped player, bool throttled, int now)
        {
            Stopwatch scan = Stopwatch.StartNew();
            try { return TryReplaceOneCore(player, throttled, now, scan); }
            finally
            {
                double elapsed = scan.Elapsed.TotalMilliseconds;
                _scanMilliseconds += elapsed;
                _maximumScanMilliseconds = Math.Max(_maximumScanMilliseconds, elapsed);
                _scans++;
            }
        }

        private string TryReplaceOneCore(Ped player, bool throttled, int now,
            Stopwatch scan)
        {
            if (_selections.Count == 0) return "No eligible authorized civilian weapon choices";
            Ped[] nearby;
            try { nearby = World.GetNearbyPeds(player, ScanRadius); }
            catch
            {
                _lastError = "Nearby pedestrian scan failed";
                _lastErrorIsTransientScanFailure = true;
                return _lastError;
            }
            if (nearby == null) return "Waiting for nearby ambient pedestrians";
            if (_lastErrorIsTransientScanFailure)
            {
                _lastError = "";
                _lastErrorIsTransientScanFailure = false;
            }
            int inspected = 0;
            foreach (Ped ped in nearby)
            {
                if (WeaponPopulationPolicy.ShouldStopScan(inspected,
                        scan.Elapsed.TotalMilliseconds, throttled))
                    return "No suitable armed NPC found in the bounded scan";
                if (ped == null || !ped.Exists() || _seen.Contains(ped.Handle)) continue;
                Remember(ped.Handle, now); inspected++; _diagnosticScanned++;
                if (!IsAmbientCandidate(ped, player))
                {
                    _diagnosticRejected++;
                    continue;
                }
                int oldWeapon = Function.Call<int>(Hash.GET_SELECTED_PED_WEAPON, ped.Handle);
                string category = CategoryFor(oldWeapon);
                if (!WeaponPopulationPolicy.IsReplaceableCategory(category))
                {
                    _diagnosticRejected++;
                    continue;
                }
                // This encounter is already remembered above for the seen
                // TTL. A declined roll is not a temporary scan throttle.
                if (!WeaponPopulationPolicy.ShouldReplaceCandidate(
                        _replacementChance, _random.NextDouble))
                {
                    _skipped++; _diagnosticRejected++;
                    return "Eligible NPC declined by replacement chance";
                }
                Selection selection = Pick(category);
                if (selection != null)
                {
                    _attempted++; _diagnosticAttempted++;
                    if (Replace(ped, player, oldWeapon, ped.Model.Hash,
                            category, selection))
                    {
                        _swapped++; _diagnosticSwapped++;
                        return "Weapon replacement committed";
                    }
                    _skipped++; _diagnosticRejected++;
                    return "Replacement rejected by a protected native safety check";
                }
                _diagnosticRejected++;
                return "No configured choice matches the NPC weapon category";
            }
            return inspected == 0 ? "Waiting for unexamined ambient pedestrians" :
                "No suitable armed NPC found in the bounded scan";
        }

        private bool Replace(Ped ped, Ped player, int oldWeapon, int sourceModel,
            string category,
            Selection selection)
        {
            int newWeapon = Game.GenerateHash(selection.Entry.Weapon);
            bool hadOld = oldWeapon != Game.GenerateHash("WEAPON_UNARMED") &&
                Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON, ped.Handle, oldWeapon, false);
            bool newValid = newWeapon != 0 && Function.Call<bool>(Hash.IS_WEAPON_VALID, newWeapon);
            bool alreadyHasNew = Function.Call<bool>(Hash.HAS_PED_GOT_WEAPON,
                ped.Handle, newWeapon, false);
            if (newWeapon == oldWeapon || alreadyHasNew || !WeaponPopulationPolicy.CanReplace(
                    IsSafeSource(ped, player, oldWeapon, sourceModel), hadOld,
                    string.Equals(category, selection.Entry.Category,
                        StringComparison.Ordinal) && NativeGroupsMatch(category,
                            oldWeapon, newWeapon), newValid, true)) return false;
            int ammo = WeaponPopulationPolicy.BoundedAmmo(Function.Call<int>(
                Hash.GET_AMMO_IN_PED_WEAPON, ped.Handle, oldWeapon));
            // Stage and prove ownership before deleting the old firearm.
            Function.Call(Hash.GIVE_WEAPON_TO_PED, ped.Handle, newWeapon, ammo, false, false);
            bool staged = HasWeapon(ped, newWeapon);
            if (!IsSafeSource(ped, player, oldWeapon, sourceModel) || !staged)
            {
                RollbackNewWeapon(ped, player, sourceModel, oldWeapon, newWeapon);
                return false;
            }
            // Make the staged weapon current while the old firearm remains
            // intact. A failure therefore restores the exact prior selection.
            Function.Call(Hash.SET_CURRENT_PED_WEAPON, ped.Handle, newWeapon, true);
            bool equipped = Function.Call<int>(Hash.GET_SELECTED_PED_WEAPON,
                ped.Handle) == newWeapon;
            if (!WeaponPopulationPolicy.CanCommitSelectedReplacement(
                    IsSafePed(ped, player, sourceModel), HasWeapon(ped, oldWeapon),
                    string.Equals(category, selection.Entry.Category,
                        StringComparison.Ordinal) && NativeGroupsMatch(category,
                            oldWeapon, newWeapon), newValid, staged, equipped))
            {
                RollbackNewWeapon(ped, player, sourceModel, oldWeapon, newWeapon);
                return false;
            }
            Function.Call(Hash.REMOVE_WEAPON_FROM_PED, ped.Handle, oldWeapon);
            if (HasWeapon(ped, oldWeapon))
            {
                RollbackNewWeapon(ped, player, sourceModel, oldWeapon, newWeapon);
                return false;
            }
            // One final native check avoids reporting success if another
            // script changed the selected firearm during removal.
            Function.Call(Hash.SET_CURRENT_PED_WEAPON, ped.Handle, newWeapon, true);
            bool committed = IsSafePed(ped, player, sourceModel) && HasWeapon(ped, newWeapon) &&
                Function.Call<int>(Hash.GET_SELECTED_PED_WEAPON, ped.Handle) == newWeapon;
            if (!committed)
                RestoreOldAfterRemoval(ped, player, sourceModel, oldWeapon, newWeapon, ammo);
            return committed;
        }

        private void RevalidateSelections()
        {
            foreach (Selection selection in _selections)
            {
                RuntimeWeaponEntry current;
                if (selection.Entry == null || !RuntimeWeaponCatalog.TryGetPopulationEntry(
                        selection.Entry.PackageId, selection.Entry.Weapon,
                        out current) || !WeaponPopulationPolicy.IsReplaceableCategory(
                            current.Category))
                {
                    _enabled = false;
                    _selections.Clear();
                    _configurationState = "authorization_expired";
                    _configurationDetail = "A configured weapon is no longer receipt-authorized";
                    _lastError = _configurationDetail;
                    _lastErrorIsTransientScanFailure = false;
                    ClientLog.Warn("WeaponPopulation", "authorization_expired");
                    return;
                }
                selection.Entry = current;
            }
        }

        private Selection Pick(string category)
        {
            int total = 0;
            foreach (Selection choice in _selections)
                if (choice.Entry.Category == category) total += choice.Weight;
            if (total <= 0) return null;
            int pick = _random.Next(total);
            foreach (Selection choice in _selections)
                if (choice.Entry.Category == category && (pick -= choice.Weight) < 0)
                    return choice;
            return null;
        }

        private static string CategoryFor(int weapon)
        {
            foreach (KeyValuePair<string, string> item in RuntimeWeaponCatalog.CategoryNames)
                if (Game.GenerateHash(item.Key) == weapon)
                    switch (item.Value)
                    {
                        case "Pistols": return "pistols";
                        case "SMGs": return "smgs";
                        case "Shotguns": return "shotguns";
                        case "Assault Rifles": return "rifles";
                    }
            return "";
        }

        private static bool IsAmbientCandidate(Ped ped, Ped player)
        {
            try
            {
                // Most nearby entities are visible or too close. Reject those
                // before evaluating the full set of native safety predicates.
                if (ped == null || player == null || !ped.Exists() || !player.Exists() ||
                    ped == player || ped.IsOnScreen || ped.IsPersistent ||
                    ped.Position.DistanceTo(player.Position) < MinimumDistance ||
                    Function.Call<bool>(Hash.IS_PED_A_PLAYER, ped.Handle)) return false;
                return WeaponPopulationPolicy.IsAmbientCandidate(
                    false, false, Function.Call<bool>(Hash.IS_ENTITY_A_MISSION_ENTITY, ped.Handle),
                    ped.CurrentVehicle != null, ped.IsInCombat, ped.IsDead, ped.IsInjured,
                    ped.IsRagdoll, ped.IsFleeing, ped.IsShooting, false, false,
                    Function.Call<int>(Hash.GET_ENTITY_POPULATION_TYPE, ped.Handle),
                    Function.Call<bool>(Hash.IS_PED_USING_ANY_SCENARIO, ped.Handle));
            }
            catch { return false; }
        }

        private static bool HasWeapon(Ped ped, int weaponHash)
        {
            return ped != null && ped.Exists() && Function.Call<bool>(
                Hash.HAS_PED_GOT_WEAPON, ped.Handle, weaponHash, false);
        }

        private static bool StillHasSource(Ped ped, int sourceHash)
        {
            return HasWeapon(ped, sourceHash) &&
                Function.Call<int>(Hash.GET_SELECTED_PED_WEAPON, ped.Handle) == sourceHash;
        }

        private void RollbackNewWeapon(Ped ped, Ped player, int sourceModel,
            int oldWeapon, int newWeapon)
        {
            // Revalidation may have failed because this NPC became protected
            // or its handle was reused. Do not mutate that entity to clean up.
            if (!IsSafePed(ped, player, sourceModel)) return;
            if (HasWeapon(ped, oldWeapon))
                Function.Call(Hash.SET_CURRENT_PED_WEAPON, ped.Handle, oldWeapon, true);
            if (IsSafePed(ped, player, sourceModel) && HasWeapon(ped, newWeapon))
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED, ped.Handle, newWeapon);
        }

        // Do not try to repair a player, mission, or reused entity handle.
        // For the same still-ambient source, restore a usable old weapon before
        // dropping the staged add-on after a post-removal verification failure.
        private void RestoreOldAfterRemoval(Ped ped, Ped player, int sourceModel,
            int oldWeapon, int newWeapon, int ammo)
        {
            if (!IsSafePed(ped, player, sourceModel)) return;
            Function.Call(Hash.GIVE_WEAPON_TO_PED, ped.Handle, oldWeapon, ammo, false, false);
            if (!IsSafePed(ped, player, sourceModel) || !HasWeapon(ped, oldWeapon)) return;
            Function.Call(Hash.SET_CURRENT_PED_WEAPON, ped.Handle, oldWeapon, true);
            if (Function.Call<int>(Hash.GET_SELECTED_PED_WEAPON, ped.Handle) == oldWeapon &&
                HasWeapon(ped, newWeapon))
                Function.Call(Hash.REMOVE_WEAPON_FROM_PED, ped.Handle, newWeapon);
        }

        private static bool NativeGroupsMatch(string category, int sourceWeapon,
            int targetWeapon)
        {
            try
            {
                uint sourceGroup = Function.Call<uint>(Hash.GET_WEAPONTYPE_GROUP,
                    sourceWeapon);
                uint targetGroup = Function.Call<uint>(Hash.GET_WEAPONTYPE_GROUP,
                    targetWeapon);
                return WeaponPopulationPolicy.NativeGroupsMatchCategory(category,
                    sourceGroup, targetGroup);
            }
            catch { return false; }
        }

        private static byte[] ReadBoundedConfiguration(string path)
        {
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                FileShare.Read))
            {
                if (stream.Length < 2 || stream.Length > MaximumDocumentBytes)
                    throw new InvalidDataException("weapon population document exceeds 1 MiB");
                byte[] bytes = new byte[(int)stream.Length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    int read = stream.Read(bytes, offset, bytes.Length - offset);
                    if (read == 0) throw new EndOfStreamException("weapon population document ended early");
                    offset += read;
                }
                return bytes;
            }
        }

        private bool IsSafeSource(Ped ped, Ped player, int sourceHash,
            int sourceModel)
        {
            return IsSafePed(ped, player, sourceModel) &&
                StillHasSource(ped, sourceHash);
        }

        private bool IsSafePed(Ped ped, Ped player, int sourceModel)
        {
            return player != null && player.Exists() && !IsGloballySuppressed(player) &&
                ped != null && ped.Exists() && ped.Model.Hash == sourceModel &&
                IsAmbientCandidate(ped, player);
        }

        private bool IsGloballySuppressed(Ped player)
        {
            return !string.IsNullOrEmpty(GlobalPauseReason(player));
        }

        private string GlobalPauseReason(Ped player)
        {
            bool available = player != null && player.Exists() && !player.IsDead;
            return WeaponPopulationPolicy.SuppressionReason(Game.IsLoading, available,
                Function.Call<bool>(Hash.GET_MISSION_FLAG),
                Function.Call<bool>(Hash.IS_CUTSCENE_ACTIVE),
                Function.Call<bool>(Hash.IS_PLAYER_SWITCH_IN_PROGRESS), available &&
                Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY, player.Handle) != 0,
                GarageManager.TransitionInProgress, _activeDuringMissions);
        }

        private void PublishDiagnostics(string state, string detail, bool throttled)
        {
            double fps = Math.Round(_smoothedFps);
            PopulationRuntimeDiagnostics previous = _diagnostics;
            if (previous.Enabled == _enabled && previous.State == state &&
                previous.Detail == detail && previous.Selections == _selections.Count &&
                previous.Scanned == _diagnosticScanned && previous.Attempted == _diagnosticAttempted &&
                previous.Replaced == _diagnosticSwapped && previous.Rejected == _diagnosticRejected &&
                previous.ReplacementChance == _replacementChance && previous.LastError == _lastError &&
                previous.Throttled == throttled && previous.Configured == _configuredChoices &&
                previous.SmoothedFps == fps) return;
            _diagnostics = new PopulationRuntimeDiagnostics(enabled: _enabled,
                state: state, detail: detail, selections: _selections.Count,
                scanned: _diagnosticScanned, attempted: _diagnosticAttempted,
                replaced: _diagnosticSwapped, rejected: _diagnosticRejected,
                replacementChance: _replacementChance, lastError: _lastError,
                throttled: throttled, configured: _configuredChoices, smoothedFps: fps);
        }

        private void Remember(int handle, int now)
        {
            if (_seen.Add(handle)) _seenOrder.Enqueue(new KeyValuePair<int, int>(handle, now));
        }

        private void PruneSeen(int now)
        {
            while (_seenOrder.Count > 0 && (unchecked((uint)(now - _seenOrder.Peek().Value)) >
                (uint)SeenTtlMilliseconds || _seenOrder.Count > MaximumSeen))
                _seen.Remove(_seenOrder.Dequeue().Key);
        }

        private void UpdatePerformance()
        {
            float frame = Function.Call<float>(Hash.GET_FRAME_TIME);
            if (frame > 0.0001f) _smoothedFps = _smoothedFps * 0.92f + (1f / frame) * 0.08f;
        }

        private void ReportTelemetry(int now)
        {
            if (_lastTelemetry == 0)
            {
                _lastTelemetry = now;
                return;
            }
            if (unchecked((uint)(now - _lastTelemetry)) < 60000U) return;
            _lastTelemetry = now;
            ClientLog.Info("WeaponPopulation", "minute_summary",
                new Dictionary<string, object> { { "attempted", _attempted },
                    { "enabled", _enabled },
                    { "active_during_missions", _activeDuringMissions },
                    { "skipped", _skipped }, { "swapped", _swapped },
                    { "state", _diagnostics.State },
                    { "detail", _diagnostics.Detail },
                    { "cumulative_scanned", _diagnosticScanned },
                    { "cumulative_attempted", _diagnosticAttempted },
                    { "cumulative_swapped", _diagnosticSwapped },
                    { "cumulative_rejected", _diagnosticRejected },
                    { "fps", Math.Round(_smoothedFps) },
                    { "scans", _scans },
                    { "scan_ms", Math.Round(_scanMilliseconds, 3) },
                    { "max_scan_ms", Math.Round(_maximumScanMilliseconds, 3) },
                    { "refreshes", _refreshes },
                    { "refresh_ms", Math.Round(_refreshMilliseconds, 3) },
                    { "max_refresh_ms", Math.Round(_maximumRefreshMilliseconds, 3) } });
            _attempted = 0; _skipped = 0; _swapped = 0;
            _scans = 0; _refreshes = 0;
            _scanMilliseconds = 0; _maximumScanMilliseconds = 0;
            _refreshMilliseconds = 0; _maximumRefreshMilliseconds = 0;
        }

        private static Dictionary<string, object> Object(object value)
        {
            var result = value as Dictionary<string, object>;
            if (result == null) throw new InvalidDataException("weapon population object expected");
            return result;
        }
        private static object[] Array(Dictionary<string, object> value, string key)
        {
            object raw; if (!value.TryGetValue(key, out raw) || !(raw is object[] result))
                throw new InvalidDataException(key + " must be an array");
            return result;
        }
        private static string Text(Dictionary<string, object> value, string key)
        {
            object raw; if (!value.TryGetValue(key, out raw) || !(raw is string result) ||
                string.IsNullOrWhiteSpace(result)) throw new InvalidDataException(key + " must be text");
            return result;
        }
        private static bool Boolean(Dictionary<string, object> value, string key)
        {
            object raw; if (!value.TryGetValue(key, out raw) || !(raw is bool result))
                throw new InvalidDataException(key + " must be a boolean");
            return result;
        }
        private static bool OptionalBoolean(Dictionary<string, object> value, string key)
        {
            // Legacy schema-v1 policies retain their mission pause. Explicit
            // null, strings and numbers are invalid rather than silently false.
            return value.ContainsKey(key) && Boolean(value, key);
        }
        private static int Integer(Dictionary<string, object> value, string key)
        {
            object raw; if (!value.TryGetValue(key, out raw) || raw is bool || !(raw is int result))
                throw new InvalidDataException(key + " must be an integer");
            return result;
        }
        private static double Number(Dictionary<string, object> value, string key, double minimum, double maximum)
        {
            object raw;
            if (!value.TryGetValue(key, out raw))
                throw new InvalidDataException(key + " must be numeric");
            // PortableJsonParser intentionally prefers decimal for JSON
            // fractions. Accept its numeric outputs without coercing text or
            // booleans; the launcher serializes 50% as the JSON number 0.5.
            double result;
            if (raw is int integer) result = integer;
            else if (raw is long longInteger) result = longInteger;
            else if (raw is decimal decimalNumber) result = (double)decimalNumber;
            else if (raw is double doubleNumber) result = doubleNumber;
            else throw new InvalidDataException(key + " must be numeric");
            if (double.IsNaN(result) || double.IsInfinity(result) || result < minimum || result > maximum)
                throw new InvalidDataException(key + " is outside bounds");
            return result;
        }
        private static void ExactFields(Dictionary<string, object> value, string[] fields,
            string[] optionalFields = null)
        {
            foreach (string field in fields) if (!value.ContainsKey(field))
                throw new InvalidDataException("weapon population has missing fields");
            var allowed = new HashSet<string>(fields, StringComparer.Ordinal);
            if (optionalFields != null) allowed.UnionWith(optionalFields);
            foreach (string field in value.Keys) if (!allowed.Contains(field))
                throw new InvalidDataException("weapon population has unsupported fields");
        }
        private static string Identifier(string value)
        {
            string result = (value ?? "").Trim().ToLowerInvariant();
            if (!System.Text.RegularExpressions.Regex.IsMatch(result, "^[a-z][a-z0-9._-]{1,95}$"))
                throw new InvalidDataException("invalid weapon package id");
            return result;
        }
        private static string Weapon(string value)
        {
            string result = value ?? "";
            if (result != result.Trim() || result != result.ToUpperInvariant() ||
                !System.Text.RegularExpressions.Regex.IsMatch(result, "^WEAPON_[A-Z0-9_]{1,56}$"))
                throw new InvalidDataException("invalid weapon id");
            return result;
        }
    }
}
