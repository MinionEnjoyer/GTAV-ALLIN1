namespace ALLIN1
{
    internal static class PreviewRuntimeStatus
    {
        internal static string Describe(
            bool streamingVerified,
            bool pluginInstalled,
            bool pluginDisabled,
            bool asiLoaderInstalled)
        {
            if (streamingVerified)
                return "preview streaming verified";
            if (pluginInstalled)
                return "plug-in file installed; preview stream not yet verified";
            if (pluginDisabled)
                return "OpenRPF plug-in disabled (fallback active)";
            return asiLoaderInstalled
                ? "ASI loader detected; OpenRPF plug-in missing"
                : "ASI loader and OpenRPF plug-in missing";
        }
    }
}
