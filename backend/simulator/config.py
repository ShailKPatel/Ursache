from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class SimConfig:
    """Scale knobs for one simulation run. The same config and seed give identical output."""

    seed: int = 42
    days: int = 90
    start: datetime = datetime(2026, 6, 1, tzinfo=UTC)
    coils_per_day: int = 40
    samples_per_coil: int = 3
    incidents_per_injection: int = 2
    noise_bursts: int = 6

    def __post_init__(self) -> None:
        if self.days < 14:
            raise ValueError("days must be at least 14 so every planted cause gets a window")
        if not 4 <= self.coils_per_day <= 400:
            raise ValueError("coils_per_day must be between 4 and 400")
        if not 1 <= self.samples_per_coil <= 20:
            raise ValueError("samples_per_coil must be between 1 and 20")
        if self.incidents_per_injection < 1:
            raise ValueError("incidents_per_injection must be at least 1")
        if self.start.tzinfo is None:
            raise ValueError("start must be timezone-aware")
