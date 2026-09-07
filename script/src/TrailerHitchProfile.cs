using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using GTA.Math;

namespace ALLIN1
{
    internal sealed class TrailerHitchPoint
    {
        internal string Id, Mode, Bone, CouplerBone;
        internal Vector3 Position, Rotation, CouplerOffset;
        internal string[] CompatibleModels;
        internal float ConnectDistance, BreakForce;
        internal bool Experimental => Mode == "physical";
    }

    internal sealed class TrailerHitchProfile
    {
        internal TrailerHitchPoint[] Points;
        private static readonly Regex Identifier = new Regex("^[a-z0-9][a-z0-9_-]{0,63}$", RegexOptions.CultureInvariant);

        internal static TrailerHitchProfile Parse(object raw, string model)
        {
            var root = Obj(raw, "schema_version", "vehicle_model", "points");
            if (!(root["schema_version"] is int || root["schema_version"] is long) || Num(root["schema_version"], 1, 1) != 1 || Text(root["vehicle_model"]) != model)
                throw new InvalidDataException("Hitch profile identity mismatch");
            var points = Array(root["points"], 0, 2).Select(value =>
            {
                var p = Obj(value, "id", "mode", "bone", "position", "rotation", "coupler_bone", "coupler_offset", "compatible_models", "connect_distance", "break_force");
                var result = new TrailerHitchPoint {
                    Id = Text(p["id"]), Mode = Text(p["mode"]), Bone = Text(p["bone"]), CouplerBone = Text(p["coupler_bone"]),
                    Position = Vec(p["position"], 20), Rotation = Vec(p["rotation"], 180), CouplerOffset = Vec(p["coupler_offset"], 5),
                    CompatibleModels = Array(p["compatible_models"], 1, 64).Select(Text).ToArray(),
                    ConnectDistance = Num(p["connect_distance"], .25f, 2), BreakForce = Num(p["break_force"], 1000, 100000),
                };
                if ((result.Id != "front" && result.Id != "rear") || (result.Mode != "native" && result.Mode != "physical"))
                    throw new InvalidDataException("Invalid hitch slot or mode");
                if (result.CompatibleModels.Distinct().Count() != result.CompatibleModels.Length || result.CompatibleModels.Contains(model))
                    throw new InvalidDataException("Duplicate/self trailer models");
                if (!result.Experimental && (result.Bone != "attach_female" || result.CouplerBone != "attach_male" || result.Position != Vector3.Zero || result.Rotation != Vector3.Zero || result.CouplerOffset != Vector3.Zero))
                    throw new InvalidDataException("Native hitch must use authored attachment bones without offsets");
                return result;
            }).ToArray();
            if (points.Select(p => p.Id).Distinct().Count() != points.Length || points.Count(p => !p.Experimental) > 1)
                throw new InvalidDataException("Duplicate hitch slots/native hitches");
            return new TrailerHitchProfile { Points = points };
        }

        private static Dictionary<string, object> Obj(object value, params string[] fields)
        {
            if (!(value is Dictionary<string, object> d) || d.Count != fields.Length || fields.Any(f => !d.ContainsKey(f)))
                throw new InvalidDataException("Invalid hitch object fields");
            return d;
        }
        private static object[] Array(object value, int min, int max)
        {
            if (!(value is IList list) || list.Count < min || list.Count > max) throw new InvalidDataException("Invalid hitch array length");
            return list.Cast<object>().ToArray();
        }
        private static string Text(object value)
        {
            if (!(value is string s) || !Identifier.IsMatch(s)) throw new InvalidDataException("Invalid hitch identifier");
            return s;
        }
        private static float Num(object value, float min, float max)
        {
            if (!(value is int || value is long || value is double || value is float || value is decimal)) throw new InvalidDataException("Hitch number required");
            double number = Convert.ToDouble(value, CultureInfo.InvariantCulture);
            if (double.IsNaN(number) || double.IsInfinity(number) || number < min || number > max) throw new InvalidDataException("Hitch number out of range");
            return (float)number;
        }
        private static Vector3 Vec(object value, float limit)
        {
            var a = Array(value, 3, 3);
            return new Vector3(Num(a[0], -limit, limit), Num(a[1], -limit, limit), Num(a[2], -limit, limit));
        }
    }

    internal static class TrailerHitchPolicy
    {
        internal static string Denial(bool safeStory, bool driver, bool occupied, bool compatible, bool bones,
            bool alreadyAttached, float towSpeed, float trailerSpeed, float distance, float limit, bool experimental, bool confirmed)
        {
            if (!safeStory) return "Hitches are available only in Story Mode free roam.";
            if (!driver) return "Sit in the towing vehicle's driver seat.";
            if (occupied) return "The trailer must be empty.";
            if (!compatible) return "Trailer model is not approved for this hitch.";
            if (!bones) return "Required hitch/coupler bone is missing.";
            if (alreadyAttached) return "A vehicle already has a connection; disconnect it first.";
            if (!Finite(towSpeed) || !Finite(trailerSpeed) || towSpeed < 0 || trailerSpeed < 0 || towSpeed > .15f || trailerSpeed > .15f) return "Stop both vehicles before coupling.";
            if (!Finite(distance) || !Finite(limit) || distance < 0 || limit < .25f || limit > 2 || distance > limit) return "Move the coupler closer to the hitch.";
            if (experimental && !confirmed) return "Confirm the experimental physical connection.";
            return null;
        }
        private static bool Finite(float v) => !float.IsNaN(v) && !float.IsInfinity(v);
    }
}
