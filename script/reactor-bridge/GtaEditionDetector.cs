using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;

namespace ALLIN1.ReactorBridge
{
    /// <summary>
    /// Resolves the installed GTA edition without assuming that a script
    /// assembly has a physical location. Script runtimes may load assemblies
    /// from bytes, which makes Assembly.Location empty or unsupported.
    /// </summary>
    internal static class GtaEditionDetector
    {
        private const int MaximumParentDepth = 3;

        internal static string Detect(
            string? processExecutablePath,
            string? contentAssemblyLocation,
            string? bridgeAssemblyLocation,
            string? runtimeBaseDirectory,
            string? currentDirectory)
        {
            string processEdition = EditionFromExecutableName(
                processExecutablePath);
            if (processEdition.Length != 0)
                return processEdition;

            var candidates = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            AddFileParents(candidates, seen, processExecutablePath);
            AddFileParents(candidates, seen, contentAssemblyLocation);
            AddFileParents(candidates, seen, bridgeAssemblyLocation);
            AddDirectoryParents(candidates, seen, runtimeBaseDirectory);
            AddDirectoryParents(candidates, seen, currentDirectory);

            foreach (string candidate in candidates)
            {
                try
                {
                    bool enhanced = File.Exists(Path.Combine(
                        candidate, "GTA5_Enhanced.exe"));
                    bool legacy = File.Exists(Path.Combine(
                        candidate, "GTA5.exe"));
                    if (enhanced) return "Enhanced";
                    if (legacy) return "Legacy";
                }
                catch (ArgumentException) { }
                catch (NotSupportedException) { }
                catch (PathTooLongException) { }
            }

            return "Unknown";
        }

        internal static string SafeAssemblyLocation(Assembly? assembly)
        {
            if (assembly == null || assembly.IsDynamic)
                return string.Empty;
            try
            {
                return assembly.Location ?? string.Empty;
            }
            catch (NotSupportedException) { return string.Empty; }
            catch (InvalidOperationException) { return string.Empty; }
        }

        internal static string SafeCurrentProcessExecutable()
        {
            try
            {
                using (Process process = Process.GetCurrentProcess())
                    return process.MainModule?.FileName ?? string.Empty;
            }
            catch (InvalidOperationException) { return string.Empty; }
            catch (NotSupportedException) { return string.Empty; }
            catch (System.ComponentModel.Win32Exception)
            {
                return string.Empty;
            }
        }

        private static string EditionFromExecutableName(string? path)
        {
            try
            {
                string name = Path.GetFileName(path ?? string.Empty);
                if (string.Equals(name, "GTA5_Enhanced.exe",
                    StringComparison.OrdinalIgnoreCase))
                    return "Enhanced";
                if (string.Equals(name, "GTA5.exe",
                    StringComparison.OrdinalIgnoreCase))
                    return "Legacy";
            }
            catch (ArgumentException) { }
            return string.Empty;
        }

        private static void AddFileParents(
            List<string> candidates,
            HashSet<string> seen,
            string? path)
        {
            if (string.IsNullOrWhiteSpace(path)) return;
            try
            {
                AddDirectoryParents(
                    candidates, seen, Path.GetDirectoryName(path));
            }
            catch (ArgumentException) { }
            catch (NotSupportedException) { }
            catch (PathTooLongException) { }
        }

        private static void AddDirectoryParents(
            List<string> candidates,
            HashSet<string> seen,
            string? path)
        {
            if (string.IsNullOrWhiteSpace(path)) return;
            string? candidate;
            try
            {
                candidate = Path.GetFullPath(path).TrimEnd(
                    Path.DirectorySeparatorChar,
                    Path.AltDirectorySeparatorChar);
            }
            catch (ArgumentException) { return; }
            catch (NotSupportedException) { return; }
            catch (PathTooLongException) { return; }

            for (int depth = 0;
                depth <= MaximumParentDepth &&
                !string.IsNullOrWhiteSpace(candidate);
                depth++)
            {
                string current = candidate!;
                if (seen.Add(current)) candidates.Add(current);
                try
                {
                    string? parent = Directory.GetParent(current)?.FullName;
                    if (string.Equals(parent, current,
                        StringComparison.OrdinalIgnoreCase))
                        break;
                    candidate = parent;
                }
                catch (ArgumentException) { break; }
                catch (NotSupportedException) { break; }
                catch (PathTooLongException) { break; }
            }
        }
    }
}
