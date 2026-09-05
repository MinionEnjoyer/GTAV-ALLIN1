using System.Collections.Generic;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    /// <summary>
    /// Streams the fixed Galaxy Super Yacht shell while the player is nearby.
    /// Ownership is a separate entitlement: its interactions and specialized
    /// storage are gated by <see cref="FeaturesUnlocked"/>.
    /// </summary>
    internal static class YachtManager
    {
        private const float AcquireDistance = 900f;
        private const float ReleaseDistance = 1200f;
        private const int ActivationRetryMs = 5000;

        internal static readonly Vector3 WorldPosition =
            new Vector3(-2027.946f, -1036.695f, 6.707587f);

        private static readonly string[] RequiredIpls =
        {
            "hei_yacht_heist",
        };

        private static readonly string[] Ipls =
        {
            "hei_yacht_heist",
            "hei_yacht_heist_Bar",
            "hei_yacht_heist_Bedrm",
            "hei_yacht_heist_Bridge",
            "hei_yacht_heist_DistantLights",
            "hei_yacht_heist_enginrm",
            "hei_yacht_heist_LODLights",
            "hei_yacht_heist_Lounge",
        };

        private static int _nextStreamCheck;
        private static bool _worldRequested;
        private static bool _worldStreamed;
        private static bool _streamingReadyLogged;
        private static bool _storyReadinessDeferredLogged;
        private static bool _activationBlockedUntilExit;

        // The base shell supplies the helipad collision. Supplemental room and
        // lighting IPLs can settle later and must not block aircraft delivery.
        // Updated by the bounded streaming poll. Consumers may query this from
        // frame callbacks without issuing another native every frame.
        internal static bool IsWorldStreamed =>
            _worldRequested && _worldStreamed;

        internal static bool FeaturesUnlocked =>
            CharacterInventory.IsPropertyOwned(WorldAssetList.SuperYacht);

        internal static void Initialize()
        {
            // Establish the ordinary retry before probing. UpdateStreaming may
            // extend it when Story Mode or the map pack is not ready yet.
            _nextStreamCheck = Game.GameTime + 1000;
            UpdateStreaming();
        }

        internal static void OnTick()
        {
            if (Game.GameTime < _nextStreamCheck)
                return;
            _nextStreamCheck = Game.GameTime + 1000;

            UpdateStreaming();
        }

        internal static void Shutdown()
        {
            if (_worldRequested)
            {
                RemoveWorld();
                DeferredMapContentRuntime.Release(
                    DeferredMapProperty.Yacht, RequiredIpls,
                    force: true, timeoutMs: 1500);
            }
            _worldRequested = false;
            _worldStreamed = false;
            _streamingReadyLogged = false;
            _storyReadinessDeferredLogged = false;
            _activationBlockedUntilExit = false;
            GarageManager.OnYachtWorldUnloaded();
        }

        private static void UpdateStreaming()
        {
            bool gameLoading = Game.IsLoading;
            if (gameLoading)
            {
                _nextStreamCheck = Game.GameTime + 1000;
                return;
            }

            Ped player = Game.Player.Character;
            if (player == null || !player.Exists()) return;

            float distance = player.Position.DistanceTo(WorldPosition);
            bool acquired = _worldRequested;

            // A failed activation remains blocked until the player leaves the
            // release radius. This prevents a damaged or deliberately
            // quarantined closure from retrying every few seconds in visible
            // gameplay.
            if (_activationBlockedUntilExit)
            {
                if (distance <= ReleaseDistance)
                {
                    _nextStreamCheck = Game.GameTime + ActivationRetryMs;
                    return;
                }
                _activationBlockedUntilExit = false;
            }

            bool shouldAcquire = YachtStreamingPolicy.ShouldAcquire(
                acquired, distance, AcquireDistance, ReleaseDistance);
            if (!shouldAcquire)
            {
                if (!acquired)
                {
                    _nextStreamCheck = Game.GameTime + 1000;
                    return;
                }

                RemoveWorld();
                DeferredMapContentResult release =
                    DeferredMapContentRuntime.Release(
                        DeferredMapProperty.Yacht, RequiredIpls,
                        timeoutMs: 1500);
                _worldRequested = false;
                _worldStreamed = false;
                _streamingReadyLogged = false;
                GarageManager.OnYachtWorldUnloaded();
                ClientLog.Info("Yacht", "streaming_exited",
                    new Dictionary<string, object>
                    {
                        { "distance", distance },
                        { "release_outcome", release.Outcome.ToString() },
                    });
                _nextStreamCheck = Game.GameTime + 1000;
                return;
            }

            string readinessReason = string.Empty;
            bool storyRuntimeReady = acquired ||
                DeferredMapContentRuntime.IsStoryRuntimeReady(
                    out readinessReason);
            if (!storyRuntimeReady)
            {
                _nextStreamCheck = Game.GameTime + 1000;
                if (!_storyReadinessDeferredLogged)
                {
                    _storyReadinessDeferredLogged = true;
                    ClientLog.Info("Yacht", "session_streaming_deferred",
                        new Dictionary<string, object>
                        {
                            { "reason", readinessReason },
                            { "distance", distance },
                            { "acquire_distance", AcquireDistance },
                        });
                }
                return;
            }
            _storyReadinessDeferredLogged = false;

            // The yacht's Rockstar archives are exposed through the same
            // property-scoped metadata bridge as the garages. Acquire only
            // while the player is inside the near radius and Story is stable;
            // a failed bridge or IPL probe stays quarantined until they leave.
            if (!_worldRequested)
            {
                DeferredMapContentResult activation =
                    DeferredMapContentRuntime.TryAcquire(
                        DeferredMapProperty.Yacht, RequiredIpls,
                        timeoutMs: 3000);
                if (!activation.Success)
                {
                    _nextStreamCheck = Game.GameTime + ActivationRetryMs;
                    _activationBlockedUntilExit = true;
                    ClientLog.Warn("Yacht", "session_streaming_activation_failed",
                        new Dictionary<string, object>
                        {
                            { "outcome", activation.Outcome.ToString() },
                            { "detail", activation.Detail },
                            { "retry_ms", ActivationRetryMs },
                        });
                    return;
                }
                _worldRequested = true;
                ClientLog.Info("Yacht", "streaming_entered",
                    new Dictionary<string, object>
                    {
                        { "distance", distance },
                        { "x", WorldPosition.X },
                        { "y", WorldPosition.Y },
                        { "z", WorldPosition.Z },
                    });
            }

            _worldStreamed = RequestWorld();
            if (IsWorldStreamed && !_streamingReadyLogged)
            {
                _streamingReadyLogged = true;
                ClientLog.Info("Yacht", "session_streaming_ready",
                    new Dictionary<string, object>
                    {
                        { "activation", "verified_metadata_bridge" },
                        { "x", WorldPosition.X },
                        { "y", WorldPosition.Y },
                        { "z", WorldPosition.Z },
                    });
            }
            _nextStreamCheck = Game.GameTime +
                GetStreamingPollInterval(_worldStreamed);
        }

        internal static int GetStreamingPollInterval(bool worldStreamed)
        {
            // Once active, a five-second health poll keeps the yacht resident
            // without repeatedly walking every IPL during normal gameplay.
            return worldStreamed ? ActivationRetryMs : 1000;
        }

        private static bool RequestWorld()
        {
            Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                WorldPosition.X, WorldPosition.Y, WorldPosition.Z);

            bool baseShellActive = false;
            foreach (string ipl in Ipls)
            {
                bool active = Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl);
                if (string.Equals(ipl, RequiredIpls[0],
                        System.StringComparison.Ordinal))
                    baseShellActive = active;
                if (!active)
                    Function.Call(Hash.REQUEST_IPL, ipl);
            }
            return baseShellActive;
        }

        private static void RemoveWorld()
        {
            foreach (string ipl in Ipls)
            {
                try { Function.Call(Hash.REMOVE_IPL, ipl); }
                catch (System.Exception ex)
                {
                    ClientLog.Error("Yacht", "ipl_remove_failed",
                        ex, new Dictionary<string, object> { { "ipl", ipl } });
                }
            }
        }

    }

    internal static class YachtStreamingPolicy
    {
        internal static bool ShouldAcquire(
            bool currentlyAcquired,
            float distance,
            float acquireDistance,
            float releaseDistance)
        {
            if (distance < 0f || acquireDistance <= 0f ||
                releaseDistance < acquireDistance) return false;
            return currentlyAcquired
                ? distance <= releaseDistance
                : distance <= acquireDistance;
        }
    }

}
