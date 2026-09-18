// Conservative ambient custom-ped population controller. It never changes
// the player, a mission/script ped, or a visible/interactive pedestrian.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public sealed class PedPopulationSpawner : Script
    {
        private const int ConfigurationRefreshMs = 5000;
        private const int ModelLoadTimeoutMs = 3000;
        private const int MaximumModelMetadataRetries = 3;
        private const int SeenHandleTtlMs = 90000;
        private const int MaximumSeenHandles = 256;
        private const float ScanRadius = 200f;
        private const float MinimumDistance = 60f;
        private const int MaximumDocumentBytes = 1024 * 1024;
        private const int MaximumRegistryBytes = 4 * 1024 * 1024;
        private const int TelemetryIntervalMs = 60000;
        private static readonly HashSet<string> VanillaTargets =
            new HashSet<string>(new[] {
                "a_f_m_beach_01", "a_f_m_bevhills_01", "a_f_m_business_02",
                "a_f_m_downtown_01", "a_f_m_eastsa_01", "a_f_m_fatbla_01",
                "a_f_m_fatcult_01", "a_f_m_ktown_01", "a_f_m_tourist_01",
                "a_f_y_beach_01", "a_f_y_bevhills_01", "a_f_y_business_01",
                "a_f_y_eastsa_01", "a_f_y_hipster_01", "a_f_y_tourist_01",
                "a_m_m_beach_01", "a_m_m_business_01", "a_m_m_eastsa_01",
                "a_m_m_genfat_01", "a_m_m_ktown_01", "a_m_m_malibu_01",
                "a_m_m_paparazzi_01", "a_m_m_salton_01", "a_m_m_skidrow_01",
                "a_m_m_socenlat_01", "a_m_m_soucent_01", "a_m_m_tourist_01",
                "a_m_y_beach_01", "a_m_y_bevhills_01", "a_m_y_business_01",
                "a_m_y_business_02", "a_m_y_downtown_01", "a_m_y_eastsa_01",
                "a_m_y_hipster_01", "a_m_y_ktown_01", "a_m_y_tourist_01",
            }, StringComparer.OrdinalIgnoreCase);

        private sealed class Selection
        {
            internal RuntimePedRecord Record;
            internal PedPopulationMode Mode;
            internal string TargetModel;
            internal int TargetModelHash;
        }

        private sealed class AddedPed
        {
            internal int AddedAt;
            internal int ModelHash;
        }

        private sealed class PendingSpawn
        {
            internal RuntimePedRecord Record;
            internal PedPopulationMode Mode;
            internal string TargetModel;
            internal int TargetModelHash;
            internal int SourceHandle;
            internal int SourceModelHash;
            internal Vector3 Position;
            internal float Heading;
            internal Stopwatch Wait;
            internal int MetadataFailures;
            internal int MetadataRetryNotBefore;
        }

        private readonly List<Selection> _selections = new List<Selection>();
        private readonly List<Selection> _addSelections = new List<Selection>();
        private readonly Dictionary<int, List<Selection>> _replacementSelections =
            new Dictionary<int, List<Selection>>();
        private readonly HashSet<int> _customModelHashes = new HashSet<int>();
        private readonly HashSet<string> _quarantinedModels =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<int> _seenHandles = new HashSet<int>();
        private readonly Queue<KeyValuePair<int, int>> _seenOrder =
            new Queue<KeyValuePair<int, int>>();
        private readonly Dictionary<int, AddedPed> _addedHandles =
            new Dictionary<int, AddedPed>();
        private readonly Random _random = new Random();
        private static volatile PopulationRuntimeDiagnostics _diagnostics =
            new PopulationRuntimeDiagnostics();
        private bool _enabled;
        private float _replacementChance;
        private int _maximumAdded;
        private int _lastConfigurationRefresh = int.MinValue;
        private string _configurationIdentity = "";
        private string _catalogAuthorizationIdentity = "";
        private bool _configurationIdentityKnown;
        private int _lastWork;
        private int _lastPrune;
        private int _lastTelemetry;
        private PendingSpawn _pending;
        private string _warmModel = "";
        private int _warmUntil;
        private long _workMilliseconds;
        private long _scanMilliseconds;
        private long _nearbyQueryMilliseconds;
        private long _createMilliseconds;
        private long _configurationMilliseconds;
        private long _maximumWorkMilliseconds;
        private long _maximumNearbyQueryMilliseconds;
        private long _maximumCreateMilliseconds;
        private long _maximumConfigurationMilliseconds;
        private float _smoothedFps = 60f;
        private long _scannedCount;
        private long _addedCount;
        private long _replacedCount;
        private long _rejectedCount;
        private long _attemptedCount;
        private string _lastError = "";
        private int _configuredChoices;
        private string _configurationState = "starting";
        private string _configurationDetail =
            "Waiting for ped population configuration";

        internal static PopulationRuntimeDiagnostics Diagnostics => _diagnostics;

        public PedPopulationSpawner()
        {
            Interval = 100;
            Tick += OnTick;
            Aborted += (sender, args) => { CancelPending(true); ReleaseOwnedPeds(); };
        }

        private void OnTick(object sender, EventArgs e)
        {
            int now = Game.GameTime;
            UpdatePerformance();
            ReleaseExpiredWarmModel(now);
            if (unchecked((uint)(now - _lastConfigurationRefresh)) >=
                (uint)ConfigurationRefreshMs)
            {
                _lastConfigurationRefresh = now;
                RefreshConfiguration();
            }
            Ped player = Game.Player.Character;
            if (!_enabled)
            {
                CancelPending(true);
                ReleaseOwnedPeds();
                PublishDiagnostics(_configurationState, _configurationDetail);
                EmitTelemetry(now);
                return;
            }
            string pauseReason = WorldPauseReason(player);
            if (!string.IsNullOrEmpty(pauseReason))
            {
                CancelPending(true);
                ReleaseOwnedPeds();
                PublishDiagnostics("paused", pauseReason);
                EmitTelemetry(now);
                return;
            }
            if (unchecked((uint)(now - _lastPrune)) >= 500U)
            {
                _lastPrune = now;
                PruneHandles(now);
            }
            if (_pending != null)
            {
                AdvancePending(player, now);
                EmitTelemetry(now);
                return;
            }
            bool throttled = _smoothedFps < 40f;
            if (!PedPopulationPolicy.IsWorkDue(now, _lastWork, throttled))
            {
                // Keep the last scan outcome readable but refresh live counts,
                // and do not leave a stale pause after the safety gate clears.
                PopulationRuntimeDiagnostics previous = _diagnostics;
                PublishDiagnostics(previous.State == "paused" ? "waiting" : previous.State,
                    previous.State == "paused" ? "Resumed; waiting for the next scan" : previous.Detail);
                EmitTelemetry(now);
                return;
            }
            _lastWork = now;
            Stopwatch work = Stopwatch.StartNew();
            TryPopulate(player, throttled, now, work);
            _workMilliseconds += work.ElapsedMilliseconds;
            _maximumWorkMilliseconds = Math.Max(_maximumWorkMilliseconds,
                work.ElapsedMilliseconds);
            EmitTelemetry(now);
        }

        private void RefreshConfiguration()
        {
            Stopwatch configuration = Stopwatch.StartNew();
            string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory,
                ".allin1", "ped-population.json");
            try
            {
                string identity;
                byte[] documentBytes = ReadBoundedFile(path,
                    MaximumDocumentBytes, "ped population document", out identity);
                string catalogIdentity;
                ReadBoundedFile(Path.Combine(
                    AppDomain.CurrentDomain.BaseDirectory, ".allin1",
                    "extensions", "registry.json"), MaximumRegistryBytes,
                    "extension registry", out catalogIdentity);
                if (_configurationIdentityKnown && string.Equals(identity,
                        _configurationIdentity, StringComparison.Ordinal) &&
                    string.Equals(catalogIdentity, _catalogAuthorizationIdentity,
                        StringComparison.Ordinal)) return;
                _configurationIdentityKnown = true;
                _configurationIdentity = identity;
                _catalogAuthorizationIdentity = catalogIdentity;
                CancelPending(true);
                ReleaseOwnedPeds();
                _selections.Clear();
                _addSelections.Clear();
                _replacementSelections.Clear();
                _customModelHashes.Clear();
                _enabled = false;
                _configuredChoices = 0;
                _lastError = "";
                if (documentBytes == null)
                {
                    _configurationState = "unconfigured";
                    _configurationDetail = "ped-population.json was not found";
                    return;
                }
                string text = new UTF8Encoding(false, true).GetString(documentBytes);
                Dictionary<string, object> root = Object(PortableJsonParser.Parse(text),
                    "ped population document");
                ExactFields(root, "ped population document", new[] {
                    "schema_version", "enabled", "replacement_chance", "max_added", "entries"
                });
                if (Integer(root, "schema_version") != 1)
                    throw new InvalidDataException("Unsupported ped population schema version");
                _enabled = Boolean(root, "enabled");
                _replacementChance = (float)Number(root, "replacement_chance", 0d, 1d);
                _maximumAdded = Integer(root, "max_added");
                if (_maximumAdded < 0 || _maximumAdded > 20)
                    throw new InvalidDataException("max_added must be between 0 and 20");
                object[] entries = JsonArray(Value(root, "entries"), "ped population entries");
                _configuredChoices = entries.Length;
                if (entries.Length > 512)
                    throw new InvalidDataException("ped population has too many entries");
                // The default-off/missing policy never touches package catalogs.
                // A catalog refresh is only warranted after a changed, enabled
                // policy has passed its bounded structural checks.
                if (!_enabled)
                {
                    _configurationState = "disabled";
                    _configurationDetail = "Ped population is disabled in its configuration";
                    return;
                }
                RuntimePedCatalog.Refresh();
                var selected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (object value in entries)
                {
                    Dictionary<string, object> row = Object(value, "ped population entry");
                    ExactFields(row, "ped population entry", new[] {
                        "package_id", "model", "mode"
                    }, new[] { "target_model" });
                    string packageId = Identifier(Text(row, "package_id"));
                    string model = ModelName(Text(row, "model"));
                    PedPopulationMode mode;
                    if (!PedPopulationPolicy.TryParseMode(Text(row, "mode"), out mode))
                        throw new InvalidDataException("ped population mode is invalid");
                    string key = packageId + "/" + model;
                    if (!selected.Add(key))
                        throw new InvalidDataException("ped population repeats a package/model selection");
                    RuntimePedRecord record;
                    if (!RuntimePedCatalog.TryGet(packageId, model, out record))
                        throw new InvalidDataException(
                            "ped selection is not receipt-authorized: " + key);
                    string target = "";
                    object targetValue;
                    if (mode == PedPopulationMode.Replace)
                    {
                        if (!row.TryGetValue("target_model", out targetValue))
                            throw new InvalidDataException("replace mode requires target_model");
                        target = ModelName(targetValue as string);
                        if (!VanillaTargets.Contains(target))
                            throw new InvalidDataException("replace target is not an approved ambient model");
                    }
                    else if (row.TryGetValue("target_model", out targetValue) &&
                        targetValue != null)
                        throw new InvalidDataException("target_model is only valid in replace mode");
                    if (mode != PedPopulationMode.Disabled)
                    {
                        _selections.Add(new Selection {
                            Record = record, Mode = mode, TargetModel = target,
                            TargetModelHash = mode == PedPopulationMode.Replace
                                ? new Model(target).Hash : 0,
                        });
                        Selection selection = _selections[_selections.Count - 1];
                        if (mode == PedPopulationMode.Add) _addSelections.Add(selection);
                        else if (mode == PedPopulationMode.Replace)
                        {
                            List<Selection> replacements;
                            if (!_replacementSelections.TryGetValue(
                                    selection.TargetModelHash, out replacements))
                            {
                                replacements = new List<Selection>();
                                _replacementSelections.Add(selection.TargetModelHash,
                                    replacements);
                            }
                            replacements.Add(selection);
                        }
                        _customModelHashes.Add(new Model(record.Model).Hash);
                    }
                }
                ClientLog.Info("PedPopulation", "configuration_loaded",
                    new Dictionary<string, object> {
                        { "enabled", _enabled }, { "selections", _selections.Count },
                        { "max_added", _maximumAdded },
                    });
                _configurationState = _selections.Count == 0 ? "waiting" : "ready";
                _configurationDetail = _selections.Count == 0
                    ? "No enabled authorized ped selections" : "Configuration loaded";
                PublishDiagnostics(_configurationState, _configurationDetail);
            }
            catch (Exception ex) when (ex is IOException ||
                ex is UnauthorizedAccessException || ex is InvalidDataException ||
                ex is FormatException || ex is ArgumentException)
            {
                _enabled = false;
                _selections.Clear();
                _addSelections.Clear();
                _replacementSelections.Clear();
                _customModelHashes.Clear();
                _configuredChoices = 0;
                _lastError = ex.Message;
                _configurationState = "configuration_rejected";
                _configurationDetail = ex.Message;
                ClientLog.Warn("PedPopulation", "configuration_rejected",
                    new Dictionary<string, object> { { "reason", ex.Message } });
                PublishDiagnostics(_configurationState, _configurationDetail);
            }
            finally
            {
                _configurationMilliseconds += configuration.ElapsedMilliseconds;
                _maximumConfigurationMilliseconds = Math.Max(
                    _maximumConfigurationMilliseconds, configuration.ElapsedMilliseconds);
            }
        }

        private void TryPopulate(Ped player, bool throttled, int now,
            Stopwatch work)
        {
            Stopwatch scan = Stopwatch.StartNew();
            try { TryPopulateCore(player, throttled, now, work); }
            finally { _scanMilliseconds += scan.ElapsedMilliseconds; }
        }

        private void TryPopulateCore(Ped player, bool throttled, int now,
            Stopwatch work)
        {
            if (_selections.Count == 0)
            {
                PublishDiagnostics("waiting", "No enabled ped selections");
                return;
            }
            // At the hard added-ped cap, a pure-add policy cannot make progress;
            // avoid both the nearest-ped query and any model work in that window.
            if (!PedPopulationPolicy.CanAdd(_addedHandles.Count, _maximumAdded) &&
                _replacementSelections.Count == 0)
            {
                PublishDiagnostics("cap", "Configured added-ped limit is reached");
                return;
            }
            Ped[] nearby;
            Stopwatch nearbyQuery = Stopwatch.StartNew();
            try { nearby = World.GetNearbyPeds(player, ScanRadius); }
            catch { PublishDiagnostics("waiting", "Nearby pedestrian scan unavailable"); return; }
            finally
            {
                _nearbyQueryMilliseconds += nearbyQuery.ElapsedMilliseconds;
                _maximumNearbyQueryMilliseconds = Math.Max(
                    _maximumNearbyQueryMilliseconds, nearbyQuery.ElapsedMilliseconds);
            }
            if (nearby == null)
            {
                PublishDiagnostics("waiting", "No nearby pedestrians");
                return;
            }
            int inspected = 0;
            foreach (Ped source in nearby)
            {
                if (source == null || !source.Exists() || _seenHandles.Contains(source.Handle))
                    continue;
                if (!PedPopulationPolicy.CanInspectCandidate(inspected,
                        PedPopulationPolicy.CandidateBudget(throttled),
                        PedPopulationPolicy.WithinWorkBudget(work.ElapsedMilliseconds))) break;
                RememberSeen(source.Handle, now);
                inspected++;
                _scannedCount++;
                if (!IsAmbientCandidate(source, player)) { _rejectedCount++; continue; }
                Selection replacement = SelectReplacement(source);
                if (replacement != null)
                {
                    bool chosen = _random.NextDouble() <= _replacementChance;
                    if (chosen && BeginPending(source, replacement, source.Position,
                            source.Heading, now))
                    {
                        PublishDiagnostics("streaming", "Streaming an eligible replacement");
                    }
                    else
                        PublishDiagnostics(_lastError.Length > 0 ? "quarantined" :
                            "waiting", _lastError.Length > 0 ? _lastError : chosen
                                ? "Replacement did not pass its safety gates"
                                : "Replacement chance skipped the eligible candidate");
                    return;
                }
                Selection addition = SelectAddition();
                bool canAdd = PedPopulationPolicy.CanAdd(_addedHandles.Count,
                    _maximumAdded);
                Vector3 additionPosition;
                if (addition != null && canAdd && TrySafeAdditionPosition(source,
                        out additionPosition) && BeginPending(source, addition,
                        additionPosition, source.Heading, now))
                {
                    PublishDiagnostics("streaming", "Streaming an eligible addition");
                }
                else if (addition != null && !canAdd)
                    PublishDiagnostics("cap", "Configured added-ped limit is reached");
                else if (addition != null)
                    PublishDiagnostics(_lastError.Length > 0 ? "quarantined" :
                        "waiting", _lastError.Length > 0 ? _lastError :
                            "Addition did not pass its safety gates");
                return; // one native create attempt per bounded work window
            }
            PublishDiagnostics("waiting", "No eligible off-screen ambient ped found");
        }

        private Selection SelectReplacement(Ped source)
        {
            int sourceHash = source.Model.Hash;
            List<Selection> choices;
            return _replacementSelections.TryGetValue(sourceHash, out choices) &&
                choices.Count > 0 ? choices[_random.Next(choices.Count)] : null;
        }

        private Selection SelectAddition()
        {
            return _addSelections.Count == 0 ? null :
                _addSelections[_random.Next(_addSelections.Count)];
        }

        private bool IsAmbientCandidate(Ped ped, Ped player)
        {
            try
            {
                // These rejects are both common and inexpensive.  Keep every
                // later mission/ownership/interior/scenario check below.
                if (ped == null || player == null || !ped.Exists() ||
                    !player.Exists() || ped == player || ped.IsOnScreen ||
                    ped.IsPersistent || Function.Call<bool>(Hash.IS_PED_A_PLAYER,
                        ped.Handle) || ped.Position.DistanceTo(player.Position) <
                        MinimumDistance) return false;
                bool inVehicle = ped.CurrentVehicle != null;
                int population = Function.Call<int>(Hash.GET_ENTITY_POPULATION_TYPE,
                    ped.Handle);
                return PedPopulationPolicy.IsAmbientCandidate(
                    false, false,
                    Function.Call<bool>(Hash.IS_ENTITY_A_MISSION_ENTITY, ped.Handle),
                    inVehicle, ped.IsInCombat, ped.IsDead, ped.IsInjured,
                    ped.IsRagdoll, ped.IsFleeing, ped.IsShooting, false, false,
                    population) && Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY,
                        ped.Handle) == 0 && !_customModelHashes.Contains(ped.Model.Hash) &&
                    !Function.Call<bool>(Hash.IS_PED_USING_ANY_SCENARIO, ped.Handle);
            }
            catch { return false; }
        }

        private bool BeginPending(Ped source, Selection selection, Vector3 position,
            float heading, int now)
        {
            if (source == null || selection == null || selection.Record == null ||
                _pending != null || _quarantinedModels.Contains(selection.Record.Model))
                return false;
            try
            {
                var model = new Model(selection.Record.Model);
                if (!model.IsInCdImage) { Quarantine(selection.Record.Model, "not_in_cd_image"); return false; }
                bool alreadyWarm = string.Equals(_warmModel, selection.Record.Model,
                    StringComparison.OrdinalIgnoreCase);
                ReleaseWarmModelIfDifferent(selection.Record.Model);
                if (!alreadyWarm)
                    model.Request(); // One request is advanced on later 100ms ticks; never spin-wait.
                _warmModel = selection.Record.Model;
                _warmUntil = unchecked(now + 30000);
                _attemptedCount++;
                _pending = new PendingSpawn { Record = selection.Record, Mode = selection.Mode,
                    TargetModel = selection.TargetModel, TargetModelHash = selection.TargetModelHash,
                    SourceHandle = source.Handle,
                    SourceModelHash = source.Model.Hash, Position = position, Heading = heading,
                    Wait = Stopwatch.StartNew() };
                return true;
            }
            catch { Quarantine(selection.Record.Model, "stream_request_failed"); return false; }
        }

        private void AdvancePending(Ped player, int now)
        {
            PendingSpawn pending = _pending;
            if (pending == null) return;
            Stopwatch create = null;
            Ped staged = null;
            bool committed = false;
            try
            {
                var model = new Model(pending.Record.Model);
                bool loaded = model.IsLoaded;
                Ped source = null;
                bool exactSource = false;
                bool revalidated = false;
                Vector3 position = pending.Position;
                bool usable = false;
                if (PedPopulationPolicy.IsModelLoadTimedOut(
                        pending.Wait.ElapsedMilliseconds, ModelLoadTimeoutMs))
                {
                    LogMetadataDecision(pending, model, loaded, false, false, false,
                        "stream_timeout");
                    Quarantine(pending.Record.Model, "stream_timeout");
                    CancelPending(true);
                    return;
                }
                // Do no source/world native work while streaming.  Once loaded,
                // reacquire by handle rather than retaining a native source object.
                if (loaded)
                {
                    if (!PedPopulationPolicy.IsMetadataRetryDue(now,
                            pending.MetadataRetryNotBefore)) return;
                    bool isPed = model.IsPed;
                    bool isHumanPed = model.IsHumanPed;
                    PedPopulationMetadataAction metadata =
                        PedPopulationPolicy.DecideModelMetadata(false, true, isPed,
                            isHumanPed, pending.MetadataFailures,
                            MaximumModelMetadataRetries, true);
                    if (metadata == PedPopulationMetadataAction.Retry)
                    {
                        pending.MetadataFailures++;
                        int delay = PedPopulationPolicy.MetadataRetryDelayMilliseconds(
                            pending.MetadataFailures);
                        pending.MetadataRetryNotBefore = unchecked(now + delay);
                        LogMetadataDecision(pending, model, true, true, isPed,
                            isHumanPed, "metadata_retry_" + pending.MetadataFailures +
                            "_after_" + delay + "ms");
                        model.Request();
                        return;
                    }
                    if (metadata == PedPopulationMetadataAction.Quarantine)
                    {
                        LogMetadataDecision(pending, model, true, true, isPed,
                            isHumanPed, "not_a_human_ped_after_retries");
                        Quarantine(pending.Record.Model,
                            "not_a_human_ped_after_retries");
                        CancelPending(true);
                        return;
                    }
                    usable = metadata == PedPopulationMetadataAction.Accept;
                    if (usable && pending.MetadataFailures > 0)
                        LogMetadataDecision(pending, model, true, true, isPed,
                            isHumanPed, "metadata_recovered");
                    source = Entity.FromHandle(pending.SourceHandle) as Ped;
                    exactSource = source != null && source.Exists() &&
                        source.Model.Hash == pending.SourceModelHash;
                    bool eligible = exactSource && IsAmbientCandidate(source, player);
                    if (pending.Mode == PedPopulationMode.Replace && exactSource)
                        eligible = eligible && pending.TargetModelHash == source.Model.Hash;
                    if (pending.Mode == PedPopulationMode.Replace && exactSource)
                        position = source.Position;
                    revalidated = PedPopulationPolicy.CanRevalidatePendingSource(
                        source != null && source.Exists(), exactSource, eligible,
                        IsWorldSafe(player), IsSafeDestinationPosition(position, player),
                        IsExteriorPosition(position));
                }
                PedPopulationPendingAction action = PedPopulationPolicy.AdvancePending(
                    false, pending.Wait.ElapsedMilliseconds, ModelLoadTimeoutMs,
                    loaded, usable, revalidated);
                if (action == PedPopulationPendingAction.KeepWaiting) return;
                if (action == PedPopulationPendingAction.Timeout) { Quarantine(pending.Record.Model, "stream_timeout"); CancelPending(true); return; }
                if (action != PedPopulationPendingAction.Create) { CancelPending(false); return; }
                create = Stopwatch.StartNew();
                staged = World.CreatePed(model, position, pending.Mode == PedPopulationMode.Replace && exactSource ? source.Heading : pending.Heading);
                if (staged == null || !staged.Exists()) { CancelPending(false); return; }
                staged.IsPersistent = true; staged.IsPositionFrozen = true;
                staged.IsCollisionEnabled = false; staged.IsVisible = false;
                if (!IsStagedDestinationSafe(staged, player)) { DeleteStaged(staged); CancelPending(false); return; }
                if (pending.Mode == PedPopulationMode.Replace)
                {
                    bool commit = exactSource && IsAmbientCandidate(source, player) &&
                        pending.TargetModelHash == source.Model.Hash &&
                        PedPopulationPolicy.CanCommitReplacement(staged.Exists(),
                            IsWorldSafe(player) && IsStagedDestinationSafe(staged, player),
                            !source.IsOnScreen);
                    if (!commit) { DeleteStaged(staged); CancelPending(false); return; }
                    bool sourceGone = false;
                    try
                    {
                        source.IsPersistent = true;
                        source.Delete();
                        sourceGone = !source.Exists();
                    }
                    catch
                    {
                        // A delete call can throw after native state changed; the
                        // follow-up existence check decides the safe branch.
                        try { sourceGone = !source.Exists(); } catch { }
                    }
                    if (!sourceGone)
                    {
                        try { source.MarkAsNoLongerNeeded(); } catch { }
                        DeleteStaged(staged); CancelPending(false); return;
                    }
                    // The source is gone.  Never delete its replacement from a
                    // later activation exception; finish the release defensively.
                    committed = true;
                    ReleaseAmbient(staged, true); _replacedCount++;
                }
                else
                {
                    if (!IsWorldSafe(player) || !IsAmbientCandidate(source, player) ||
                        !IsStagedDestinationSafe(staged, player) ||
                        !PedPopulationPolicy.CanAdd(_addedHandles.Count, _maximumAdded))
                    { DeleteStaged(staged); CancelPending(false); return; }
                    ReleaseAmbient(staged, false);
                    if (!BelongsToThisScript(staged)) { ReleaseAmbient(staged, true); CancelPending(false); return; }
                    _addedHandles[staged.Handle] = new AddedPed { AddedAt = now, ModelHash = staged.Model.Hash }; _addedCount++; committed = true;
                }
                _pending = null; PublishDiagnostics("active", "Created a revalidated ambient ped");
            }
            catch { CancelPending(false); }
            finally
            {
                // Any exception after World.CreatePed but before the lifecycle
                // commit must not leave a hidden, frozen, persistent ped behind.
                if (!committed) DeleteStaged(staged);
                if (create != null)
                {
                    _createMilliseconds += create.ElapsedMilliseconds;
                    _maximumCreateMilliseconds = Math.Max(_maximumCreateMilliseconds,
                        create.ElapsedMilliseconds);
                }
            }
        }

        private void CancelPending(bool releaseWarm)
        {
            bool rejected = _pending != null && !releaseWarm;
            _pending = null;
            if (releaseWarm) ReleaseWarmModel();
            if (rejected)
            {
                _rejectedCount++;
                PublishDiagnostics("waiting", "Pending spawn cancelled; safety checks no longer passed");
            }
        }

        private void ReleaseWarmModelIfDifferent(string model)
        {
            if (!string.Equals(_warmModel, model, StringComparison.OrdinalIgnoreCase)) ReleaseWarmModel();
        }

        private void ReleaseExpiredWarmModel(int now)
        {
            if (_pending == null && _warmModel.Length > 0 && unchecked((uint)(now - _warmUntil)) < 0x80000000U) ReleaseWarmModel();
        }

        private void ReleaseWarmModel()
        {
            if (_warmModel.Length == 0) return;
            try { new Model(_warmModel).MarkAsNoLongerNeeded(); } catch { }
            _warmModel = ""; _warmUntil = 0;
        }

        private static bool IsWorldSafe(Ped player)
        {
            try
            {
                return string.IsNullOrEmpty(WorldPauseReason(player));
            }
            catch { return false; }
        }

        private static string WorldPauseReason(Ped player)
        {
            try
            {
                bool available = player != null && player.Exists() && !player.IsDead;
                return PedPopulationPolicy.SuppressionReason(Game.IsLoading, available,
                    Game.Player.WantedLevel > 0,
                    Function.Call<bool>(Hash.GET_MISSION_FLAG),
                    Function.Call<bool>(Hash.IS_CUTSCENE_ACTIVE),
                    Function.Call<bool>(Hash.IS_PLAYER_SWITCH_IN_PROGRESS),
                    available && Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY,
                        player.Handle) != 0, GarageManager.TransitionInProgress);
            }
            catch { return "world safety check unavailable"; }
        }

        private static bool IsSafeDestinationPosition(Vector3 position, Ped player)
        {
            return player != null && player.Exists() &&
                position.DistanceTo(player.Position) >= MinimumDistance &&
                IsExteriorPosition(position);
        }

        private static bool IsExteriorPosition(Vector3 position)
        {
            try
            {
                return Function.Call<int>(Hash.GET_INTERIOR_AT_COORDS,
                    position.X, position.Y, position.Z) == 0;
            }
            catch { return false; }
        }

        private static bool IsStagedDestinationSafe(Ped ped, Ped player)
        {
            try
            {
                bool exists = ped != null && ped.Exists();
                if (!exists) return false;
                Vector3 position = ped.Position;
                return PedPopulationPolicy.IsStagedDestinationSafe(exists,
                    !ped.IsOnScreen, !Function.Call<bool>(Hash.IS_SPHERE_VISIBLE,
                        position.X, position.Y, position.Z, 1.5f),
                    IsSafeDestinationPosition(position, player),
                    Function.Call<int>(Hash.GET_INTERIOR_FROM_ENTITY,
                        ped.Handle) == 0);
            }
            catch { return false; }
        }

        private static bool TrySafeAdditionPosition(Ped anchor, out Vector3 position)
        {
            position = Vector3.Zero;
            try
            {
                Vector3 desired = anchor.Position + new Vector3(2f, 0f, 0f);
                Vector3 safe = World.GetSafeCoordForPed(desired, true, 0);
                if (safe == Vector3.Zero || safe.DistanceTo(desired) > 7f)
                    return false;
                position = safe;
                return true;
            }
            catch { return false; }
        }

        private static byte[] ReadBoundedFile(string path, int maximumBytes,
            string label, out string digest)
        {
            if (!File.Exists(path))
            {
                digest = "missing";
                return null;
            }
            byte[] bytes;
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                FileShare.Read))
            {
                if (stream.Length < 0 || stream.Length > maximumBytes)
                    throw new InvalidDataException(label + " exceeds its byte limit");
                bytes = new byte[(int)stream.Length];
                int offset = 0;
                while (offset < bytes.Length)
                {
                    int read = stream.Read(bytes, offset, bytes.Length - offset);
                    if (read == 0) throw new EndOfStreamException(label + " ended early");
                    offset += read;
                }
            }
            using (SHA256 hash = SHA256.Create())
                digest = BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "");
            return bytes;
        }

        private static void ReleaseAmbient(Ped ped, bool relinquishOwnership)
        {
            try
            {
                if (ped == null || !ped.Exists()) return;
            }
            catch { return; }
            // Complete each recovery action independently.  This is especially
            // important after a replacement source has already been deleted.
            try { ped.IsVisible = true; } catch { }
            try { ped.IsCollisionEnabled = true; } catch { }
            try { ped.IsPositionFrozen = false; } catch { }
            try { Function.Call(Hash.SET_ENTITY_DYNAMIC, ped.Handle, true); } catch { }
            try { Function.Call(Hash.TASK_WANDER_STANDARD, ped.Handle, 10f, 10); } catch { }
            if (relinquishOwnership)
                try { ped.MarkAsNoLongerNeeded(); } catch { }
        }

        private static void DeleteStaged(Ped ped)
        {
            try
            {
                if (ped == null || !ped.Exists()) return;
                ped.IsPersistent = true;
                ped.Delete();
            }
            catch { }
        }

        private static bool BelongsToThisScript(Ped ped)
        {
            try
            {
                return ped != null && ped.Exists() && Function.Call<bool>(
                    Hash.DOES_ENTITY_BELONG_TO_THIS_SCRIPT, ped.Handle, true);
            }
            catch { return false; }
        }

        private void ReleaseOwnedPeds()
        {
            // Population aborts (disabled configuration or an unsafe world
            // state) must relinquish every safe, still-owned tracked ped.
            // A handle claimed by another script is deliberately fail-closed.
            foreach (KeyValuePair<int, AddedPed> entry in _addedHandles)
            {
                try
                {
                    Ped ped = Entity.FromHandle(entry.Key) as Ped;
                    if (ped == null || !PedPopulationPolicy.CanRelinquishOwnedPed(
                            ped.Exists(), ped.Model.Hash == entry.Value.ModelHash,
                            BelongsToThisScript(ped))) continue;
                    // Do not force a visible/destructive cleanup: only relinquish
                    // ownership of the exact custom ped this runtime created.
                    // Another script that claimed it as a mission entity keeps
                    // its current persistence and lifecycle intact.
                    ped.IsPersistent = false;
                    ped.MarkAsNoLongerNeeded();
                }
                catch { }
            }
            _addedHandles.Clear();
        }

        private void Quarantine(string model, string reason)
        {
            if (!_quarantinedModels.Add(model)) return;
            _lastError = model + ": " + reason;
            ClientLog.Warn("PedPopulation", "model_quarantined",
                new Dictionary<string, object> {
                    { "model", model }, { "reason", reason },
                });
            PublishDiagnostics("quarantined", model + ": " + reason);
        }

        private static void LogMetadataDecision(PendingSpawn pending, Model model,
            bool loaded, bool metadataChecked, bool isPed, bool isHumanPed,
            string reason)
        {
            try
            {
                ClientLog.Info("PedPopulation", "model_metadata_decision",
                    new Dictionary<string, object> {
                        { "model", pending.Record.Model }, { "model_hash", model.Hash },
                        { "loaded", loaded }, { "is_ped", isPed },
                        { "is_human_ped", isHumanPed },
                        { "metadata_checked", metadataChecked },
                        { "metadata_failures", pending.MetadataFailures },
                        { "retry_not_before", pending.MetadataRetryNotBefore },
                        { "reason", reason },
                    });
            }
            catch { }
        }

        // Keep population observability bounded: a single aggregate event per minute,
        // rather than an event for each ambient pedestrian examined.
        private void EmitTelemetry(int now)
        {
            if (unchecked((uint)(now - _lastTelemetry)) < (uint)TelemetryIntervalMs)
                return;
            _lastTelemetry = now;
            ClientLog.Info("PedPopulation", "population_activity",
                new Dictionary<string, object> {
                    { "added", _addedCount }, { "replaced", _replacedCount },
                    { "rejected", _rejectedCount },
                    { "active_added", _addedHandles.Count },
                    { "selections", _selections.Count },
                    { "state", _diagnostics.State }, { "detail", _diagnostics.Detail },
                    { "session_scanned", _scannedCount }, { "session_attempted", _attemptedCount },
                    { "work_ms", _workMilliseconds }, { "scan_ms", _scanMilliseconds },
                    { "nearby_query_ms", _nearbyQueryMilliseconds },
                    { "create_ms", _createMilliseconds },
                    { "configuration_ms", _configurationMilliseconds },
                    { "max_work_ms_last_minute", _maximumWorkMilliseconds },
                    { "max_nearby_query_ms_last_minute", _maximumNearbyQueryMilliseconds },
                    { "max_create_ms_last_minute", _maximumCreateMilliseconds },
                    { "max_configuration_ms_last_minute", _maximumConfigurationMilliseconds },
                    { "counter_scope", "session" },
                });
            // The cumulative fields establish total cost; the peak is deliberately
            // per-minute so a future hitch can be localized without per-tick logs.
            _maximumWorkMilliseconds = 0;
            _maximumNearbyQueryMilliseconds = 0;
            _maximumCreateMilliseconds = 0;
            _maximumConfigurationMilliseconds = 0;
        }

        private void PublishDiagnostics(string state, string detail)
        {
            PopulationRuntimeDiagnostics previous = _diagnostics;
            double publishedFps = Math.Round(_smoothedFps);
            if (previous.Enabled == _enabled && previous.State == state &&
                previous.Detail == detail && previous.Selections == _selections.Count &&
                previous.Active == _addedHandles.Count && previous.Limit == _maximumAdded &&
                previous.Scanned == _scannedCount && previous.Added == _addedCount &&
                previous.Replaced == _replacedCount && previous.Rejected == _rejectedCount &&
                previous.Attempted == _attemptedCount && previous.LastError == _lastError &&
                previous.Quarantined == _quarantinedModels.Count &&
                previous.ReplacementChance == _replacementChance &&
                previous.Throttled == (_smoothedFps < 40f) &&
                previous.SmoothedFps == publishedFps) return;
            _diagnostics = new PopulationRuntimeDiagnostics(enabled: _enabled,
                state: state, detail: detail, selections: _selections.Count,
                active: _addedHandles.Count, limit: _maximumAdded,
                scanned: _scannedCount, attempted: _attemptedCount, added: _addedCount,
                replaced: _replacedCount, rejected: _rejectedCount,
                quarantined: _quarantinedModels.Count,
                replacementChance: _replacementChance, lastError: _lastError,
                throttled: _smoothedFps < 40f, configured: _configuredChoices,
                smoothedFps: publishedFps);
        }

        private void RememberSeen(int handle, int now)
        {
            if (handle == 0 || !_seenHandles.Add(handle)) return;
            _seenOrder.Enqueue(new KeyValuePair<int, int>(handle, now));
        }

        private void PruneHandles(int now)
        {
            while (_seenOrder.Count > 0)
            {
                KeyValuePair<int, int> oldest = _seenOrder.Peek();
                if (unchecked((uint)(now - oldest.Value)) <= (uint)SeenHandleTtlMs &&
                    _seenOrder.Count <= MaximumSeenHandles) break;
                _seenOrder.Dequeue();
                _seenHandles.Remove(oldest.Key);
            }
            var expired = new List<int>();
            foreach (KeyValuePair<int, AddedPed> entry in _addedHandles)
            {
                Ped ped = null;
                try { ped = Entity.FromHandle(entry.Key) as Ped; }
                catch { }
                if (!PedPopulationPolicy.ShouldRetainTrackedPed(now,
                        entry.Value.AddedAt, SeenHandleTtlMs) || ped == null ||
                    !ped.Exists() || ped.Model.Hash != entry.Value.ModelHash)
                {
                    try
                    {
                        if (ped != null && PedPopulationPolicy.CanRelinquishOwnedPed(
                                ped.Exists(), ped.Model.Hash == entry.Value.ModelHash,
                                BelongsToThisScript(ped)))
                        {
                            ped.IsPersistent = false;
                            ped.MarkAsNoLongerNeeded();
                        }
                    }
                    catch { }
                    expired.Add(entry.Key);
                }
            }
            foreach (int handle in expired) _addedHandles.Remove(handle);
        }

        private void UpdatePerformance()
        {
            float frameTime = Function.Call<float>(Hash.GET_FRAME_TIME);
            if (frameTime > 0.0001f)
                _smoothedFps = _smoothedFps * 0.92f + (1f / frameTime) * 0.08f;
        }

        private static Dictionary<string, object> Object(object value, string label)
        {
            if (!(value is Dictionary<string, object> result))
                throw new InvalidDataException(label + " must be an object");
            return result;
        }

        private static object[] JsonArray(object value, string label)
        {
            if (!(value is object[] result))
                throw new InvalidDataException(label + " must be an array");
            return result;
        }

        private static object Value(Dictionary<string, object> value, string key)
        {
            if (!value.TryGetValue(key, out object result))
                throw new InvalidDataException("Missing required field: " + key);
            return result;
        }

        private static string Text(Dictionary<string, object> value, string key)
        {
            if (!(Value(value, key) is string result) || string.IsNullOrWhiteSpace(result))
                throw new InvalidDataException(key + " must be non-empty text");
            return result;
        }

        private static string Identifier(string value)
        {
            string result = (value ?? "").Trim().ToLowerInvariant();
            if (!System.Text.RegularExpressions.Regex.IsMatch(result,
                    "^[a-z][a-z0-9._-]{1,95}$"))
                throw new InvalidDataException("Invalid ped package id");
            return result;
        }

        private static string ModelName(string value)
        {
            string result = (value ?? "").Trim().ToLowerInvariant();
            if (!System.Text.RegularExpressions.Regex.IsMatch(result,
                    "^[a-z0-9_]{1,64}$"))
                throw new InvalidDataException("Invalid ped model name");
            return result;
        }

        private static int Integer(Dictionary<string, object> value, string key)
        {
            object raw = Value(value, key);
            if (raw is bool || !(raw is int result))
                throw new InvalidDataException(key + " must be an integer");
            return result;
        }

        private static bool Boolean(Dictionary<string, object> value, string key)
        {
            if (!(Value(value, key) is bool result))
                throw new InvalidDataException(key + " must be a boolean");
            return result;
        }

        private static double Number(Dictionary<string, object> value, string key,
            double minimum, double maximum)
        {
            object raw = Value(value, key);
            double result;
            if (raw is int integer) result = integer;
            else if (raw is long longInteger) result = longInteger;
            else if (raw is decimal decimalNumber) result = (double)decimalNumber;
            else if (raw is double doubleNumber) result = doubleNumber;
            else throw new InvalidDataException(key + " must be a number");
            if (double.IsNaN(result) || double.IsInfinity(result) ||
                result < minimum || result > maximum)
                throw new InvalidDataException(key + " is outside supported range");
            return result;
        }

        private static void ExactFields(Dictionary<string, object> value,
            string label, IEnumerable<string> required, IEnumerable<string> optional = null)
        {
            var allowed = new HashSet<string>(required, StringComparer.Ordinal);
            if (optional != null) allowed.UnionWith(optional);
            foreach (string key in value.Keys)
                if (!allowed.Contains(key))
                    throw new InvalidDataException(label + " contains unknown field: " + key);
            foreach (string key in required)
                if (!value.ContainsKey(key))
                    throw new InvalidDataException(label + " is missing field: " + key);
        }
    }
}
