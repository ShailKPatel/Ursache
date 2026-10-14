"""Incident titles and shift-report descriptions. They describe symptoms only, never causes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

CLASS_NAMES: dict[str, tuple[str, str]] = {
    "crazing": ("Crazing", "Netzrisse"),
    "inclusion": ("Inclusions", "Einschlüsse"),
    "patches": ("Patches", "Flecken"),
    "pitted_surface": ("Pitted surface", "Narbige Oberfläche"),
    "rolled-in_scale": ("Rolled-in scale", "Eingewalzter Zunder"),
    "scratches": ("Scratches", "Kratzer"),
}
SHIFT_NAMES: dict[str, tuple[str, str]] = {
    "early": ("early", "Frühschicht"),
    "late": ("late", "Spätschicht"),
    "night": ("night", "Nachtschicht"),
}


@dataclass(frozen=True, slots=True)
class ShiftSummary:
    line: str
    shift: str
    shift_start: datetime
    crew: str
    coils: int
    affected: int
    max_severity: int
    on_hold: int
    grades: tuple[str, ...]
    position_range_m: tuple[float, float]


def severity(summary: ShiftSummary) -> int:
    score = 2 + (summary.affected >= 4) + (summary.affected >= 8) + (summary.max_severity == 5)
    return min(5, score)


def render(defect_class: str, s: ShiftSummary, language: str) -> tuple[str, str]:
    hours = f"{s.shift_start:%H}:00-{(s.shift_start.hour + 8) % 24:02d}:00"
    lo, hi = (round(x) for x in s.position_range_m)
    grades = ", ".join(s.grades)
    if language == "de":
        name, shift = CLASS_NAMES[defect_class][1], SHIFT_NAMES[s.shift][1]
        day = f"{s.shift_start:%d.%m.%Y}"
        title = f"{name} an Coils {s.line}, {shift} {day}"
        description = (
            f"Schichtbericht {s.line}, {shift} {day} ({hours}), Schichtgruppe {s.crew}.\n"
            f"{s.coils} Coils gewalzt. Die automatische Oberflächeninspektion meldet "
            f"{name} an {s.affected} Coils (höchster Schweregrad {s.max_severity}); "
            f"{s.on_hold} Coils gesperrt.\n"
            f"Betroffene Güten: {grades}. Fehler über die Bandlänge zwischen {lo} m und {hi} m.\n"
            "Anlage lief mit normaler Leistung, keine Stillstände oder Alarme in der Schicht.\n"
            "Die Qualitätssicherung bittet um Untersuchung. Betroffene Coils liegen im "
            "Sperrlager zur Nachprüfung."
        )
        return title, description
    name, shift = CLASS_NAMES[defect_class][0], SHIFT_NAMES[s.shift][0]
    day = f"{s.shift_start:%Y-%m-%d}"
    title = f"{name} on {s.line} coils, {shift} shift {day}"
    description = (
        f"Shift report {s.line}, {shift} shift {day} ({hours}), crew {s.crew}.\n"
        f"{s.coils} coils rolled. Automatic surface inspection flagged {name.lower()} on "
        f"{s.affected} coils (highest severity {s.max_severity}); {s.on_hold} coils on hold.\n"
        f"Affected grades: {grades}. Defects found along the strip between {lo} m and {hi} m.\n"
        "Line ran at normal rate; no stops or alarms during the shift.\n"
        "Quality requests an investigation. Affected coils are in the hold bay for re-inspection."
    )
    return title, description
