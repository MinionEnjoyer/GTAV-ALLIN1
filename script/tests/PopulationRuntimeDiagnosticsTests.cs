using Xunit;

namespace ALLIN1.Tests
{
    public sealed class PopulationRuntimeDiagnosticsTests
    {
        [Fact]
        public void Default_and_waiting_summaries_are_compact_and_operational()
        {
            var snapshot = new PopulationRuntimeDiagnostics(state: "waiting",
                detail: "Next bounded scan pending; no nearby pedestrians");

            Assert.Equal("0/0 managed, 60 FPS", snapshot.Summary(true));
            Assert.Equal("0 swaps, 60 FPS", snapshot.Summary(false));
            Assert.Equal("neutral", snapshot.Tone);
            Assert.DoesNotContain("waiting", snapshot.Summary(true));
            Assert.DoesNotContain("pending", snapshot.Summary(false));
        }

        [Fact]
        public void Unconfigured_snapshot_is_neutral_when_no_error_occurred()
        {
            var snapshot = new PopulationRuntimeDiagnostics(state: "unconfigured",
                detail: "No weapon population configuration was found");

            Assert.Equal("neutral", snapshot.Tone);
            Assert.Equal("0 weapons • 0% replacement chance",
                snapshot.Describe(false));
        }

        [Fact]
        public void Authorization_expiry_remains_an_actionable_warning()
        {
            var snapshot = new PopulationRuntimeDiagnostics(enabled: false,
                state: "authorization_expired",
                detail: "A configured weapon is no longer receipt-authorized",
                lastError: "A configured weapon is no longer receipt-authorized");

            Assert.Equal("warning", snapshot.Tone);
            Assert.Contains("authorization expired", snapshot.Status);
            Assert.Equal("0 swaps, 60 FPS (authorization unavailable)",
                snapshot.Summary(false));
            Assert.Contains("Last error:", snapshot.Describe(false));
        }

        [Fact]
        public void Ped_summary_and_description_are_readable_without_telemetry()
        {
            var snapshot = new PopulationRuntimeDiagnostics(enabled: true,
                state: "active", detail: "Added an eligible ambient ped",
                configured: 1, selections: 1, active: 2, limit: 20, added: 10,
                scanned: 30, rejected: 20, quarantined: 1,
                lastError: "l4dzoey: stream_timeout", smoothedFps: 104.6);
            Assert.Equal("2/20 managed, 105 FPS (1 quarantined)",
                snapshot.Summary(true));
            Assert.Equal("1 model • 10 spawned this session • Last error: " +
                "l4dzoey: stream_timeout", snapshot.Describe(true));
            Assert.DoesNotContain("eligible", snapshot.Describe(true));
            Assert.DoesNotContain("scanned", snapshot.Describe(true));
            Assert.Contains("l4dzoey: stream_timeout", snapshot.Describe(true));
            Assert.Equal("warning", snapshot.Tone);
        }

        [Fact]
        public void Paused_and_disabled_summaries_only_append_actionable_state()
        {
            var paused = new PopulationRuntimeDiagnostics(state: "paused",
                detail: "wanted level active", active: 3, limit: 20,
                smoothedFps: 104.6);
            var disabled = new PopulationRuntimeDiagnostics(enabled: false,
                state: "disabled", configured: 15, selections: 15,
                replacementChance: 0.5f,
                smoothedFps: 104.6);

            Assert.Equal("3/20 managed, 105 FPS (paused: wanted level active)",
                paused.Summary(true));
            Assert.Equal("0 swaps, 105 FPS (disabled)",
                disabled.Summary(false));
            Assert.Equal("15 weapons • 50% replacement chance",
                disabled.Describe(false));
        }

        [Fact]
        public void Configuration_markers_and_throttle_remain_compact()
        {
            var unconfigured = new PopulationRuntimeDiagnostics(
                state: "unconfigured", detail: "No configuration document");
            var configurationError = new PopulationRuntimeDiagnostics(
                state: "configuration_error", lastError: "Invalid selection");
            var throttled = new PopulationRuntimeDiagnostics(state: "waiting",
                throttled: true, smoothedFps: 39.6);

            Assert.Equal("0 swaps, 60 FPS (unconfigured)",
                unconfigured.Summary(false));
            Assert.Equal("0/0 managed, 60 FPS (configuration error)",
                configurationError.Summary(true));
            Assert.Equal("0 swaps, 40 FPS (adaptive throttle)",
                throttled.Summary(false));
        }

        [Fact]
        public void Long_runtime_errors_cannot_break_Reactor_status_contract_limits()
        {
            var snapshot = new PopulationRuntimeDiagnostics(
                detail: new string('x', 2048) + "\r\n", lastError: new string('y', 2048),
                added: long.MaxValue, scanned: long.MaxValue);
            Assert.InRange(snapshot.Status.Length, 1, 256);
            Assert.InRange(snapshot.Describe(true).Length, 1, 512);
            Assert.DoesNotContain("\n", snapshot.Status);
            Assert.EndsWith("...", snapshot.Describe(true));
        }

        [Fact]
        public void Ped_rejection_uses_same_configuration_marker_as_weapons()
        {
            var snapshot = new PopulationRuntimeDiagnostics(
                state: "configuration_rejected", lastError: "Invalid selection");
            Assert.Equal("0/0 managed, 60 FPS (configuration error)", snapshot.Summary(true));
            Assert.Equal("warning", snapshot.Tone);
        }

        [Fact]
        public void Disabled_choices_do_not_inflate_eligible_counts()
        {
            var snapshot = new PopulationRuntimeDiagnostics(configured: 5,
                selections: 1, replacementChance: 0.5f);
            Assert.Equal("1 model • 0 spawned this session", snapshot.Describe(true));
            Assert.Equal("1 weapon • 50% replacement chance", snapshot.Describe(false));
        }

        [Theory]
        [InlineData("active")]
        [InlineData("streaming")]
        [InlineData("waiting")]
        [InlineData("cap")]
        public void Ordinary_population_phases_do_not_flash_the_status_tone(string state)
        {
            Assert.Equal("neutral", new PopulationRuntimeDiagnostics(
                enabled: true, state: state).Tone);
        }
    }
}
