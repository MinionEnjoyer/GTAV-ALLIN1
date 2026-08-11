"""Pure-Python reliability models used by CI and the in-game smoke workflow."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class GarageState:
    location: str = "outside"
    transition: str | None = None
    frozen: bool = False
    faded_out: bool = False

    def begin(self, operation: str) -> bool:
        if self.transition is not None:
            return False
        self.transition = operation
        return True

    def step(self, event: str) -> None:
        if self.transition is None:
            raise ValueError("no transition in progress")
        if event == "fade_out":
            self.faded_out = True
        elif event == "freeze":
            self.frozen = True
        elif event == "enter_complete":
            self.location = "garage"
        elif event == "leave_complete":
            self.location = "outside"
        else:
            raise ValueError(f"unknown transition event: {event}")

    def finish(self) -> None:
        self.transition = None
        self.frozen = False
        self.faded_out = False

    def recover(self) -> None:
        self.location = "outside"
        self.finish()


@dataclass
class SeatState:
    seats: dict[int, str] = field(default_factory=dict)
    selected: int = -1
    executing: bool = False

    def available(self) -> list[int]:
        return sorted(index for index, occupant in self.seats.items()
                      if occupant in ("free", "player"))

    def select(self, seat: int) -> bool:
        if seat not in self.available():
            return False
        self.selected = seat
        return True

    def confirm(self) -> bool:
        if self.seats.get(self.selected) != "free":
            self.executing = False
            return False
        self.executing = True
        return True

    def timeout(self) -> None:
        self.executing = False


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    passed: bool
    detail: str = ""


def write_smoke_report(path: Path, edition: str, checks: list[SmokeCheck]) -> bool:
    """Write the machine-readable result consumed by release qualification."""
    passed = all(check.passed for check in checks)
    payload = {
        "schema": 1,
        "edition": edition,
        "passed": passed,
        "checks": [asdict(check) for check in checks],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return passed


def analyze_client_log(path: Path) -> list[SmokeCheck]:
    """Derive release smoke checks from structured events emitted in-game."""
    observed: set[str] = set()
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue
        component = event.get("component", "")
        message = event.get("message", "")
        if component == "VehicleHelper" and message == "vehicle_created":
            observed.add("vehicle_spawn")
        if component == "GBAY" and message.startswith("GiveWeapon:"):
            observed.add("weapon_grant")
        if component == "Garage" and message.startswith(("EnterGarage: COMPLETE", "LeaveGarage: COMPLETE")):
            observed.add("garage_transition")
        if component == "Garage" and message.startswith(("EnterFloorGarage: COMPLETE", "LeaveFloorGarage: COMPLETE")):
            observed.add("floor_garage_transition")
        if component == "SeatSelector" and message == "seat_switch_completed":
            observed.add("seat_switch")
        if component == "Preview" and message == "texture_loaded":
            observed.add("preview_stream")
    required = (
        "vehicle_spawn", "weapon_grant", "preview_stream", "garage_transition",
        "floor_garage_transition", "seat_switch",
    )
    return [SmokeCheck(name, name in observed,
                       "observed" if name in observed else "not observed")
            for name in required]
