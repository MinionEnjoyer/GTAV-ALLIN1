using System.Collections.Generic;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    /// <summary>
    /// Keeps the fixed Galaxy Super Yacht shell streamed into Story Mode.
    /// Ownership is a separate entitlement: the yacht remains visible in the
    /// world, while its interactions and specialized storage are gated by
    /// <see cref="FeaturesUnlocked"/>.
    /// </summary>
    internal static class YachtManager
    {
        private const float AcquireDistance = 900f;
        private const float ReleaseDistance = 1200f;

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
        private static bool _activationBlockedUntilExit;

        // The base shell supplies the helipad collision. Supplemental room and
        // lighting IPLs can settle later and must not block aircraft delivery.
        internal static bool IsWorldStreamed => _worldRequested &&
            Function.Call<bool>(Hash.IS_IPL_ACTIVE, "hei_yacht_heist");

        internal static bool FeaturesUnlocked =>
            CharacterInventory.IsPropertyOwned(WorldAssetList.SuperYacht);

        internal static void Initialize()
        {
            UpdateStreaming();
            _nextStreamCheck = Game.GameTime + 1000;
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
            RemoveWorld();
            _worldRequested = false;
            _activationBlockedUntilExit = false;
            GarageManager.OnYachtWorldUnloaded();
        }

        private static void UpdateStreaming()
        {
            Ped player = Game.Player.Character;
            if (player == null || !player.Exists()) return;

            float distance = player.Position.DistanceTo(WorldPosition);
            bool acquired = _worldRequested;

            // A missing or incomplete local map pack must fail closed. Never
            // switch the whole session to the Online map as a fallback: that
            // creates global loading zones and can strand Story Mode.
            if (_activationBlockedUntilExit)
            {
                if (distance <= ReleaseDistance) return;
                _activationBlockedUntilExit = false;
            }

            bool shouldAcquire = YachtStreamingPolicy.ShouldAcquire(
                acquired, distance, AcquireDistance, ReleaseDistance);

            if (shouldAcquire)
            {
                if (!acquired)
                {
                    if (!StandaloneMapPack.TryActivate(RequiredIpls, 1500))
                    {
                        _activationBlockedUntilExit = true;
                        ClientLog.Warn("Yacht", "standalone_map_unavailable");
                        return;
                    }
                    _worldRequested = true;
                    ClientLog.Info("Yacht", "streaming_entered", new Dictionary<string, object>
                    {
                        { "distance", distance },
                        { "x", WorldPosition.X },
                        { "y", WorldPosition.Y },
                        { "z", WorldPosition.Z },
                    });
                }

                RequestWorld();
                return;
            }

            if (!acquired) return;

            RemoveWorld();
            _worldRequested = false;
            GarageManager.OnYachtWorldUnloaded();
            ClientLog.Info("Yacht", "streaming_exited",
                new Dictionary<string, object> { { "distance", distance } });
        }

        private static void RequestWorld()
        {
            Function.Call(Hash.REQUEST_COLLISION_AT_COORD,
                WorldPosition.X, WorldPosition.Y, WorldPosition.Z);

            foreach (string ipl in Ipls)
            {
                if (!Function.Call<bool>(Hash.IS_IPL_ACTIVE, ipl))
                    Function.Call(Hash.REQUEST_IPL, ipl);
            }
        }

        private static void RemoveWorld()
        {
            foreach (string ipl in Ipls)
                Function.Call(Hash.REMOVE_IPL, ipl);
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
