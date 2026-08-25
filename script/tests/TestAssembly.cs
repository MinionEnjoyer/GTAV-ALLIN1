using Xunit;

// Runtime catalog and garage policy fixtures intentionally exercise shared
// static state that represents one GTA process. Running those fixtures in
// parallel creates impossible multi-process interleavings and flaky results.
[assembly: CollectionBehavior(DisableTestParallelization = true)]
