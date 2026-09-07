// No spawning, teleporting, bone writes, or per-frame attachment retries.
using System;
using System.Collections.Generic;
using System.Linq;
using GTA;
using GTA.Math;
using GTA.Native;

namespace ALLIN1
{
    public sealed class Allin1HitchOption
    {
        public string Token { get; internal set; }
        public string Label { get; internal set; }
        public string Status { get; internal set; }
        public bool Available { get; internal set; }
        public bool Experimental { get; internal set; }
    }
    public sealed class Allin1HitchSnapshot
    {
        public string Status { get; internal set; }
        public string DisconnectToken { get; internal set; }
        public IReadOnlyList<Allin1HitchOption> Options { get; internal set; } = Array.Empty<Allin1HitchOption>();
    }
    // Optional capability preserves compatibility with older storefront bridges.
    public interface IAllin1HitchStorefront
    {
        Allin1HitchSnapshot BrowseHitches();
        Allin1GbayActionResult ConnectHitch(string token, bool experimentalConfirmed);
        Allin1GbayActionResult DisconnectHitch(string token);
    }

    internal static class TrailerHitchRuntime
    {
        private sealed class Offer
        {
            internal Vehicle Tow, Trailer;
            internal IntPtr TowAddress, TrailerAddress;
            internal int TowModel, TrailerModel;
            internal TrailerHitchPoint Point;
            internal string Token = Guid.NewGuid().ToString("N");
            internal bool Valid => Tow != null && Trailer != null && Tow.Exists() && Trailer.Exists()
                && Tow.MemoryAddress == TowAddress && Trailer.MemoryAddress == TrailerAddress
                && Tow.Model.Hash == TowModel && Trailer.Model.Hash == TrailerModel;
        }
        private static readonly Dictionary<string, Offer> Offers = new Dictionary<string, Offer>();
        private static readonly List<Offer> Joints = new List<Offer>();
        private static Offer _disconnect;
        private static Allin1HitchSnapshot _cached;
        private static IntPtr _cachedTow;
        private static int _cachedAt;
        private static readonly string[] StockTrailers = { "trailers", "trailers2", "trailers3", "trailers4", "trailers5", "trailersmall", "boattrailer", "boattrailer2", "boattrailer3", "tanker", "tanker2", "trflat", "trailerlogs", "armytrailer", "armytrailer2", "armytanker", "baletrailer", "graintrailer", "docktrailer", "raketrailer", "tr2", "tr3", "tr4", "tvtrailer" };

        private static bool SafeStory() => !Game.IsLoading && !Game.IsCutsceneActive
            && !Function.Call<bool>(Hash.GET_MISSION_FLAG)
            && !Function.Call<bool>(Hash.NETWORK_IS_SESSION_ACTIVE)
            && !Function.Call<bool>(Hash.IS_SCREEN_FADED_OUT);
        private static Vehicle CurrentTow()
        {
            var ped = Game.Player.Character;
            var vehicle = ped?.CurrentVehicle;
            return ped != null && ped.Exists() && ped.IsAlive && vehicle != null && vehicle.Exists()
                && vehicle.Driver == ped && !vehicle.IsDead ? vehicle : null;
        }
        private static Offer NewOffer(Vehicle tow, Vehicle trailer, TrailerHitchPoint point) => new Offer {
            Tow = tow, Trailer = trailer, TowAddress = tow.MemoryAddress, TrailerAddress = trailer.MemoryAddress,
            TowModel = tow.Model.Hash, TrailerModel = trailer.Model.Hash, Point = point,
        };
        private static Vehicle NativeTrailer(Vehicle tow)
        {
            var output = new OutputArgument();
            return Function.Call<bool>(Hash.GET_VEHICLE_TRAILER_VEHICLE, tow.Handle, output)
                ? Entity.FromHandle(output.GetResult<int>()) as Vehicle : null;
        }
        private static bool PhysicalAttached(Offer o) => o.Valid && Function.Call<bool>(Hash.IS_ENTITY_ATTACHED_TO_ENTITY, o.Trailer.Handle, o.Tow.Handle);
        private static void Prune() => Joints.RemoveAll(o => !PhysicalAttached(o));
        private static bool Busy(Vehicle v) => Function.Call<bool>(Hash.IS_ENTITY_ATTACHED, v.Handle)
            || Function.Call<bool>(Hash.IS_VEHICLE_ATTACHED_TO_TRAILER, v.Handle)
            || Joints.Any(o => o.Valid && (o.Tow.Handle == v.Handle || o.Trailer.Handle == v.Handle));
        private static HashSet<int> TowedNearby(Vehicle v)
        {
            var cars = World.GetNearbyVehicles(v.Position, 40);
            if (cars.Length > 128) throw new InvalidOperationException("Too many nearby vehicles; move to an open area.");
            var result = new HashSet<int>();
            foreach (var car in cars)
            {
                if (!car.Exists()) continue;
                var trailer = NativeTrailer(car);
                if (trailer != null && trailer.Exists()) result.Add(trailer.Handle);
            }
            return result;
        }
        private static TrailerHitchPoint[] Points(Vehicle tow)
        {
            if (RuntimeVehicleCatalog.TryGetByHash(tow.Model.Hash, out GbayVehicleRecord record) && record.Hitches != null)
                return record.Hitches.Points;
            var bone = tow.Bones["attach_female"];
            if (!bone.IsValid) return Array.Empty<TrailerHitchPoint>();
            return new[] { new TrailerHitchPoint { Id = bone.RelativePosition.Y >= 0 ? "front" : "rear", Mode = "native",
                Bone = "attach_female", CouplerBone = "attach_male", CompatibleModels = StockTrailers,
                ConnectDistance = 1, BreakForce = 10000 } };
        }
        private static string Denial(Offer o, bool confirmed, HashSet<int> towed)
        {
            if (!o.Valid) return "Vehicle changed; choose a current trailer.";
            var a = o.Tow.Bones[o.Point.Bone]; var b = o.Trailer.Bones[o.Point.CouplerBone];
            bool bones = a.IsValid && b.IsValid;
            float distance = bones ? a.GetOffsetPosition(o.Point.Position).DistanceTo(b.GetOffsetPosition(o.Point.CouplerOffset)) : float.PositiveInfinity;
            return TrailerHitchPolicy.Denial(SafeStory(), CurrentTow()?.Handle == o.Tow.Handle,
                o.Trailer.Occupants.Length != 0 || o.Trailer.IsDead,
                o.Point.CompatibleModels.Any(m => Game.GenerateHash(m) == o.Trailer.Model.Hash), bones,
                Busy(o.Tow) || Busy(o.Trailer) || towed.Contains(o.Trailer.Handle) || towed.Contains(o.Tow.Handle),
                o.Tow.Speed, o.Trailer.Speed, distance, o.Point.ConnectDistance, o.Point.Experimental, confirmed);
        }
        internal static Allin1HitchSnapshot Browse()
        {
            try
            {
                Prune();
                var tow = CurrentTow();
                if (!SafeStory() || tow == null) { _cached = null; Offers.Clear(); _disconnect = null; return new Allin1HitchSnapshot { Status = "Sit in the driver's seat in Story Mode free roam to use trailer hitches." }; }
                var physical = Joints.FirstOrDefault(o => o.Valid && o.Tow.Handle == tow.Handle);
                var attached = physical?.Trailer ?? NativeTrailer(tow);
                if (attached != null && attached.Exists())
                {
                    _cached = null;
                    Offers.Clear();
                    if (_disconnect == null || !_disconnect.Valid || _disconnect.Tow.Handle != tow.Handle || _disconnect.Trailer.Handle != attached.Handle)
                        _disconnect = NewOffer(tow, attached, physical?.Point);
                    return new Allin1HitchSnapshot { Status = "Trailer connected. Stop both vehicles before disconnecting.", DisconnectToken = _disconnect.Token };
                }
                _disconnect = null;
                var points = Points(tow);
                if (points.Length == 0) { _cached = null; Offers.Clear(); return new Allin1HitchSnapshot { Status = "No hitch configured or native attach_female bone found. Author a profile in the SDK." }; }
                int elapsed = unchecked(Environment.TickCount - _cachedAt);
                if (_cached != null && _cachedTow == tow.MemoryAddress && elapsed >= 0 && elapsed < 1000) return _cached;
                var nearby = World.GetNearbyVehicles(tow.Position, 30);
                var towed = TowedNearby(tow);
                var next = new Dictionary<string, Offer>(); var options = new List<Allin1HitchOption>();
                foreach (var point in points)
                {
                    var candidates = nearby.Where(t => t.Exists() && t.Handle != tow.Handle && point.CompatibleModels.Any(m => Game.GenerateHash(m) == t.Model.Hash))
                        .OrderBy(t => t.Position.DistanceTo(tow.Position)).Take(16);
                    foreach (var trailer in candidates)
                    {
                        var old = Offers.Values.FirstOrDefault(o => o.Valid && o.Tow.Handle == tow.Handle && o.Trailer.Handle == trailer.Handle && SamePoint(o.Point, point));
                        var offer = old ?? NewOffer(tow, trailer, point); next[offer.Token] = offer;
                        string denial = Denial(offer, true, towed);
                        options.Add(new Allin1HitchOption { Token = offer.Token, Label = point.Id + " hitch · " + trailer.DisplayName,
                            Experimental = point.Experimental, Available = denial == null,
                            Status = denial ?? (point.Experimental ? "Ready · experimental physical joint" : "Ready · native towing") });
                    }
                }
                Offers.Clear(); foreach (var item in next) Offers[item.Key] = item.Value;
                _cachedAt = Environment.TickCount; _cachedTow = tow.MemoryAddress;
                return _cached = new Allin1HitchSnapshot { Status = options.Count == 0 ? "No compatible trailers nearby. Position an approved trailer within 30 m, then bring its coupler to the hitch."
                    : "Choose a hitch and trailer. Connections are rechecked at confirmation; no vehicles are spawned or repositioned.", Options = options };
            }
            catch (Exception ex) { _cached = null; Offers.Clear(); _disconnect = null; return new Allin1HitchSnapshot { Status = "Hitch inspection unavailable: " + ex.Message }; }
        }
        internal static Allin1GbayActionResult Connect(string token, bool confirmed)
        {
            _cached = null;
            try
            {
                if (token == null || !Offers.TryGetValue(token, out Offer o) || !o.Valid) return Fail("Trailer selection expired.");
                // Re-resolve package configuration and live entities, not UI-provided transforms.
                if (!Points(o.Tow).Any(p => SamePoint(p, o.Point))) return Fail("Hitch configuration changed; select again.");
                Prune();
                string denial = Denial(o, confirmed, TowedNearby(o.Tow));
                if (denial != null) return Fail(denial);
                if (Joints.Count >= 16) return Fail("Disconnect an existing experimental joint before adding another.");
                Offers.Clear();
                DrivingRuntime.Event("hitch_connect_attempt", EventFields(o));
                if (!o.Point.Experimental)
                {
                    Function.Call(Hash.ATTACH_VEHICLE_TO_TRAILER, o.Tow.Handle, o.Trailer.Handle, o.Point.ConnectDistance);
                    var actual = NativeTrailer(o.Tow);
                    if (actual == null || actual.Handle != o.Trailer.Handle) return Fail("GTA did not accept the native coupling. Check the authored bones and vehicle compatibility.");
                }
                else
                {
                    var p = o.Point; var a = p.CouplerOffset; var b = p.Position; var r = p.Rotation;
                    Function.Call(Hash.ATTACH_ENTITY_TO_ENTITY_PHYSICALLY, o.Trailer.Handle, o.Tow.Handle,
                        o.Trailer.Bones[p.CouplerBone].Index, o.Tow.Bones[p.Bone].Index,
                        a.X, a.Y, a.Z, b.X, b.Y, b.Z, r.X, r.Y, r.Z, p.BreakForce,
                        false, false, true, true, 2);
                    if (!PhysicalAttached(o)) return Fail("GTA did not accept the experimental joint; no retry was issued.");
                    Joints.Add(o);
                }
                DrivingRuntime.Event("hitch_connected", EventFields(o));
                return Allin1GbayActionResult.Success("hitch_connected", "Trailer connected.");
            }
            catch (Exception ex) { ClientLog.Error("Hitches", "connect_failed", ex); return Fail("Connection failed; inspect the vehicles before retrying."); }
        }
        private static bool SamePoint(TrailerHitchPoint a, TrailerHitchPoint b) => a.Id == b.Id && a.Mode == b.Mode && a.Bone == b.Bone && a.CouplerBone == b.CouplerBone
            && a.Position == b.Position && a.Rotation == b.Rotation && a.CouplerOffset == b.CouplerOffset && a.ConnectDistance == b.ConnectDistance && a.BreakForce == b.BreakForce && a.CompatibleModels.SequenceEqual(b.CompatibleModels);
        internal static Allin1GbayActionResult Disconnect(string token)
        {
            _cached = null;
            try
            {
                var o = _disconnect;
                if (o == null || token != o.Token || !o.Valid || CurrentTow()?.Handle != o.Tow.Handle || !SafeStory()) return Fail("Connection selection expired.");
                if (!(o.Tow.Speed >= 0 && o.Tow.Speed <= .15f && o.Trailer.Speed >= 0 && o.Trailer.Speed <= .15f) || o.Trailer.Occupants.Length != 0) return Fail("Stop both vehicles and empty the trailer first.");
                var physical = Joints.FirstOrDefault(p => p.Valid && p.Tow.Handle == o.Tow.Handle && p.Trailer.Handle == o.Trailer.Handle);
                if (physical != null && PhysicalAttached(physical))
                {
                    Function.Call(Hash.DETACH_ENTITY, o.Trailer.Handle, true, true);
                    if (PhysicalAttached(physical)) return Fail("GTA did not release the physical joint.");
                    Joints.Remove(physical);
                }
                else
                {
                    var current = NativeTrailer(o.Tow);
                    if (current == null || current.Handle != o.Trailer.Handle) return Fail("Trailer connection changed.");
                    Function.Call(Hash.DETACH_VEHICLE_FROM_TRAILER, o.Tow.Handle);
                    if (NativeTrailer(o.Tow) != null) return Fail("GTA did not release the native coupling.");
                }
                _disconnect = null;
                DrivingRuntime.Event("hitch_disconnected", EventFields(o));
                return Allin1GbayActionResult.Success("hitch_disconnected", "Trailer disconnected.");
            }
            catch (Exception ex) { ClientLog.Error("Hitches", "disconnect_failed", ex); return Fail("Could not disconnect the trailer."); }
        }
        private static Dictionary<string, object> EventFields(Offer o) => new Dictionary<string, object> {
            ["tow_handle"] = o.Tow.Handle, ["trailer_handle"] = o.Trailer.Handle,
            ["tow_model_hash"] = o.TowModel, ["trailer_model_hash"] = o.TrailerModel,
            ["hitch_id"] = o.Point?.Id, ["mode"] = o.Point?.Mode ?? "native",
            ["configured_break_force"] = o.Point?.Experimental == true ? (object)o.Point.BreakForce : null,
        };
        // Main-thread sampling only. Covers both front and rear joints without any world scan.
        internal static Dictionary<string, object> Telemetry(Vehicle tow, out string pair)
        {
            Prune();
            var samples = new List<Dictionary<string, object>>(); var identities = new List<string>();
            var physical = Joints.Where(o => o.Valid && o.Tow.Handle == tow.Handle).ToList();
            foreach (var o in physical)
            { samples.Add(JointSample(tow, o.Trailer, o.Point)); identities.Add(o.Token); }
            var native = NativeTrailer(tow);
            if (native != null && native.Exists() && !physical.Any(o => o.Trailer.Handle == native.Handle))
            {
                var point = Points(tow).FirstOrDefault(p => !p.Experimental);
                samples.Add(JointSample(tow, native, point));
                identities.Add("native:" + tow.Handle + ":" + native.Handle + ":" + native.Model.Hash);
            }
            pair = identities.Count == 0 ? null : string.Join("|", identities);
            return new Dictionary<string, object> { ["joints"] = samples };
        }
        private static Dictionary<string, object> JointSample(Vehicle tow, Vehicle trailer, TrailerHitchPoint point)
        {
            object gap = null;
            if (point != null && tow.Bones.Contains(point.Bone) && trailer.Bones.Contains(point.CouplerBone))
                gap = DrivingPolicy.Number(tow.Bones[point.Bone].GetOffsetPosition(point.Position)
                    .DistanceTo(trailer.Bones[point.CouplerBone].GetOffsetPosition(point.CouplerOffset)));
            return new Dictionary<string, object> {
                ["trailer_handle"] = trailer.Handle, ["trailer_model_hash"] = trailer.Model.Hash,
                ["hitch_id"] = point?.Id, ["mode"] = point?.Mode ?? "native",
                ["configured_break_force"] = point?.Experimental == true ? (object)point.BreakForce : null, ["coupler_gap_m"] = gap,
                ["yaw_difference_deg"] = DrivingPolicy.Number(DrivingPolicy.Angle(trailer.Heading - tow.Heading)),
                ["trailer_speed_mps"] = DrivingPolicy.Number(trailer.Speed),
                ["trailer_roll_deg"] = DrivingPolicy.Number(trailer.Rotation.Y),
                ["trailer_pitch_deg"] = DrivingPolicy.Number(trailer.Rotation.X),
                ["trailer_collided"] = trailer.HasCollided,
            };
        }
        internal static void Shutdown()
        {
            foreach (var joint in Joints.ToArray())
                try { if (PhysicalAttached(joint)) Function.Call(Hash.DETACH_ENTITY, joint.Trailer.Handle, true, true); }
                catch (Exception ex) { ClientLog.Error("Hitches", "shutdown_failed", ex); }
            Joints.Clear(); Offers.Clear(); _disconnect = null; _cached = null;
        }
        private static Allin1GbayActionResult Fail(string reason)
        {
            DrivingRuntime.Event("hitch_action_failed", new Dictionary<string, object> { ["reason"] = reason });
            return Allin1GbayActionResult.Failure("hitch_unavailable", reason);
        }
    }
}
