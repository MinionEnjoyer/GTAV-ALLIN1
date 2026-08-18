using System;
using System.Collections.Generic;

namespace ALLIN1
{
    internal static class StructuredLogKeyPolicy
    {
        private static readonly HashSet<string> ReservedKeys =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            {
                "ts", "level", "session", "component", "message",
                "exception_type", "exception", "stack",
            };

        internal static string Normalize(string key)
        {
            string normalized = string.IsNullOrWhiteSpace(key)
                ? "field" : key;
            return ReservedKeys.Contains(normalized)
                ? "field_" + normalized.ToLowerInvariant()
                : normalized;
        }
    }
}
