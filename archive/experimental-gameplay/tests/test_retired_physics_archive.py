"""Preserved contract evidence for the retired physics experiment.

This archive is intentionally outside pytest's active ``testpaths``.  It
documents the implementation that was retired, without representing it as a
currently supported runtime feature.
"""

from pathlib import Path


ARCHIVE_ROOT = Path(__file__).resolve().parents[1]


def test_archived_physics_sources_preserve_the_last_experiment_contract() -> None:
    physics = (ARCHIVE_ROOT / "native/src/NpcPhysicsExperiment.cs").read_text(
        encoding="utf-8"
    )
    diagnostics = (ARCHIVE_ROOT / "native/src/PhysicsExperimentLog.cs").read_text(
        encoding="utf-8"
    )

    assert "uprightValue <= 0.55f" in physics
    assert "relax.Relaxation = relaxation" in physics
    assert "private const int ScanIntervalMs = 50" in physics
    assert "private const float LiveBodyRelaxation = 25f" in physics
    assert "LiveBalanceReinforcementDelayMs = 90" in physics
    assert '"delayed_live_balance"' in physics
    assert "balance.LegStiffness = 12f" in physics
    assert "balance.MaxSteps = 32" in physics
    assert "balance.MaxBalanceTime = 6.2f" in physics
    assert "PhysicsExperimentLog.Step" in physics
    assert '"reaction_observation"' in physics
    assert '"heartbeat"' in physics
    assert "IS_ENTITY_TOUCHING_ENTITY" in physics
    assert "ShouldForceVehicleImpactRagdoll" in physics
    assert '"vehicle_push_vanilla_preserved"' in physics
    assert '"vehicle_native_reaction_observed"' in physics
    assert 'fields["natural_motion_dispatched"] = false' in physics
    assert "state.WasAlive = true;" in physics
    assert "Enum.GetValues(typeof(ExplosionType))" in physics
    assert "PhysicsExperimentLog.Configure(_debug)" in physics
    assert "Assembly.Location" not in diagnostics
    assert "MaxBytes" in diagnostics and "RotateIfNeeded" in diagnostics
