"""Static description of the simulated mill: lines, equipment, grades, suppliers, sensors."""

from __future__ import annotations

from dataclasses import dataclass

from ursache.db.views import PROCESS_PARAMETERS

LINES: tuple[str, ...] = ("HSM-1", "HSM-2")
PROCESS_TYPE = "hot_strip_mill"

SHIFTS: tuple[tuple[str, int], ...] = (("early", 6), ("late", 14), ("night", 22))
CREWS: tuple[str, ...] = ("A", "B", "C", "D")

DEFECT_CLASSES: tuple[str, ...] = (
    "crazing",
    "inclusion",
    "patches",
    "pitted_surface",
    "rolled-in_scale",
    "scratches",
)
BASE_DEFECT_RATE: dict[str, float] = {
    "crazing": 0.015,
    "inclusion": 0.02,
    "patches": 0.025,
    "pitted_surface": 0.015,
    "rolled-in_scale": 0.03,
    "scratches": 0.02,
}

UNITS: dict[str, str] = {
    "roll_force": "MN",
    "strip_temperature": "°C",
    "roll_speed": "m/s",
    "strip_tension": "kN",
    "descaler_pressure": "bar",
    "coolant_flow": "m3/h",
    "exit_thickness": "mm",
}
assert set(UNITS) == set(PROCESS_PARAMETERS)


@dataclass(frozen=True, slots=True)
class EquipmentSpec:
    suffix: str
    type: str
    name: str


EQUIPMENT: tuple[EquipmentSpec, ...] = (
    EquipmentSpec("FUR", "reheat_furnace", "Walking-beam reheat furnace"),
    EquipmentSpec("DSC", "descaler", "High-pressure descaler"),
    EquipmentSpec("RM", "roughing_mill", "Reversing roughing mill"),
    *(EquipmentSpec(f"F{i}", "finishing_stand", f"Finishing stand F{i}") for i in range(1, 7)),
    EquipmentSpec("LCT", "laminar_cooling", "Laminar cooling section"),
    EquipmentSpec("DC", "coiler", "Down coiler"),
)


def tag(line: str, suffix: str) -> str:
    return f"{line.replace('-', '')}-{suffix}"


@dataclass(frozen=True, slots=True)
class Grade:
    code: str
    spec: str
    share: float
    force_factor: float
    temp_offset: float
    coiling_temp: float
    suppliers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Supplier:
    name: str
    country: str
    language: str


SUPPLIERS: tuple[Supplier, ...] = (
    Supplier("Brennhagen Brammenwerk GmbH", "DE", "de"),
    Supplier("Ostravel Slab s.r.o.", "CZ", "en"),
    Supplier("Kestrelmoor Steel Ltd", "GB", "en"),
    Supplier("Valdoria Aceros S.A.", "ES", "en"),
)

_BRENNHAGEN, _OSTRAVEL, _KESTRELMOOR, _VALDORIA = (s.name for s in SUPPLIERS)

GRADES: tuple[Grade, ...] = (
    Grade("S235JR", "EN 10025-2", 0.30, 1.00, 0.0, 640.0, (_OSTRAVEL, _VALDORIA, _BRENNHAGEN)),
    Grade("S355J2", "EN 10025-2", 0.25, 1.10, 10.0, 600.0, (_OSTRAVEL, _BRENNHAGEN, _KESTRELMOOR)),
    Grade("DD11", "EN 10111", 0.20, 0.92, -10.0, 680.0, (_VALDORIA, _KESTRELMOOR)),
    Grade("S420MC", "EN 10149-2", 0.15, 1.20, 15.0, 580.0, (_BRENNHAGEN, _KESTRELMOOR)),
    Grade("S500MC", "EN 10149-2", 0.10, 1.28, 20.0, 560.0, (_BRENNHAGEN,)),
)

# Finished strip thickness in mm and how often each is ordered.
THICKNESS_MIX: tuple[tuple[float, float], ...] = (
    (1.8, 0.08),
    (2.0, 0.15),
    (2.5, 0.20),
    (3.0, 0.20),
    (4.0, 0.17),
    (5.0, 0.12),
    (6.0, 0.08),
)

FINISHING_FORCE_MN: tuple[float, ...] = (21.0, 19.0, 16.5, 14.0, 11.5, 9.5)
FINISHING_SPEED_RATIO: tuple[float, ...] = (0.18, 0.28, 0.42, 0.60, 0.80, 1.00)


@dataclass(frozen=True, slots=True)
class SeriesSpec:
    """One sensor: a parameter measured on one piece of equipment, on every line."""

    suffix: str
    parameter: str
    noise_rel: float
    drift_rel: float


SERIES: tuple[SeriesSpec, ...] = (
    SeriesSpec("FUR", "strip_temperature", 0.003, 0.002),
    SeriesSpec("DSC", "descaler_pressure", 0.012, 0.006),
    SeriesSpec("RM", "roll_force", 0.03, 0.006),
    SeriesSpec("RM", "strip_temperature", 0.005, 0.002),
    *(SeriesSpec(f"F{i}", "roll_force", 0.025, 0.006) for i in range(1, 7)),
    *(SeriesSpec(f"F{i}", "roll_speed", 0.01, 0.004) for i in range(1, 7)),
    SeriesSpec("F1", "strip_temperature", 0.005, 0.002),
    SeriesSpec("F6", "strip_temperature", 0.006, 0.002),
    SeriesSpec("F6", "exit_thickness", 0.005, 0.0),
    SeriesSpec("F6", "strip_tension", 0.03, 0.006),
    SeriesSpec("LCT", "coolant_flow", 0.012, 0.006),
    SeriesSpec("LCT", "strip_temperature", 0.008, 0.002),
    SeriesSpec("DC", "strip_tension", 0.03, 0.006),
)


def nominal(series: SeriesSpec, grade: Grade, thickness_mm: float) -> float:
    """Expected value for a coil of this grade and thickness, before drift, noise and causes."""
    p, s, h = series.parameter, series.suffix, thickness_mm
    if p == "strip_temperature":
        base = {"FUR": 1230.0, "RM": 1110.0, "F1": 1040.0, "F6": 880.0}
        if s == "LCT":
            return grade.coiling_temp
        thin_loss = 12.0 if s == "F6" and h < 2.5 else 0.0
        return base[s] + grade.temp_offset - thin_loss
    if p == "descaler_pressure":
        return 205.0
    if p == "roll_force":
        if s == "RM":
            return 24.0 * grade.force_factor
        stand = int(s[1:]) - 1
        return FINISHING_FORCE_MN[stand] * grade.force_factor * (1 + 0.04 * (3.0 - h))
    if p == "roll_speed":
        exit_speed = min(13.0, max(4.0, 26.0 / h))
        return exit_speed * FINISHING_SPEED_RATIO[int(s[1:]) - 1]
    if p == "strip_tension":
        return 6.0 + 4.0 * h if s == "F6" else 10.0 + 3.0 * h
    if p == "coolant_flow":
        return 3200.0 * (h / 3.0) ** 0.5
    if p == "exit_thickness":
        return h
    raise ValueError(f"no nominal value for {s}/{p}")


def coil_length_m(thickness_mm: float) -> float:
    # A 20 t coil, 1.3 m wide: length = mass / (density * width * thickness).
    return 20_000 / (7850 * 1.3 * thickness_mm / 1000)


TECHNICIANS: tuple[str, ...] = (
    "J. Becker",
    "M. Novak",
    "S. Hoffmann",
    "A. Kowalski",
    "T. Weber",
    "L. Fischer",
    "R. Dvořák",
    "K. Schulz",
)
