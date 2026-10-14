"""Planted root causes: what each one is, where and when it acts, and what it changes."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Shape = Literal["ramp", "plateau", "step"]


@dataclass(frozen=True, slots=True)
class ReadingEffect:
    """value * (1 + relative * intensity) + absolute * intensity"""

    suffix: str
    parameter: str
    relative: float = 0.0
    absolute: float = 0.0


@dataclass(frozen=True, slots=True)
class CauseSpec:
    key: str
    category_6m: str
    mechanism: str
    target_class: str
    line: str
    equipment: str | None
    window: tuple[float, float]  # fractions of the horizon; a lot-based cause uses only [0]
    shape: Shape
    defect_boost: float
    readings: tuple[ReadingEffect, ...] = ()
    ramp_floor: float = 0.0
    crew: str | None = None
    supplier: str | None = None
    keywords: tuple[str, ...] = ()


# Changes from revision 2 to revision 3 of this instruction; see documents.py.
WORK_ROLL_WI = "WI-HSM2-RC-007"
WORK_ROLL_WI_CHANGE_AT = 0.62
LAMINAR_START_WI = "WI-HSM-014"

CAUSES: tuple[CauseSpec, ...] = (
    CauseSpec(
        key="descaler_nozzle_wear",
        category_6m="machine",
        mechanism=(
            "Worn nozzles on the HSM-1 descaler header lower the descaling pressure; scale is not "
            "fully removed after the furnace and is rolled into the strip in the finishing mill."
        ),
        target_class="rolled-in_scale",
        line="HSM-1",
        equipment="DSC",
        window=(0.15, 0.32),
        shape="ramp",
        ramp_floor=0.25,
        defect_boost=0.26,
        readings=(ReadingEffect("DSC", "descaler_pressure", relative=-0.13),),
        keywords=("descal", "nozzle", "düse", "entzunder", "pressure", "druck", "header"),
    ),
    CauseSpec(
        key="contaminated_lot",
        category_6m="material",
        mechanism=(
            "One slab lot from Ostravel Slab s.r.o. carries elevated non-metallic inclusions "
            "(total oxygen and sulphur high but inside the certificate limits); the inclusions "
            "open up at the strip surface during rolling."
        ),
        target_class="inclusion",
        line="HSM-2",
        equipment=None,
        window=(0.36, 0.36),
        shape="step",
        defect_boost=0.42,
        supplier="Ostravel Slab s.r.o.",
        keywords=(
            "supplier",
            "lieferant",
            "lot",
            "charge",
            "certificate",
            "zeugnis",
            "contamina",
            "oxygen",
            "sauerstoff",
            "slab",
            "bramme",
            "ostravel",
            "brennhagen",
            "kestrelmoor",
            "valdoria",
        ),
    ),
    CauseSpec(
        key="work_roll_overrun",
        category_6m="method",
        mechanism=(
            f"Revision 3 of {WORK_ROLL_WI} extended the finishing-stand work-roll change interval "
            "on HSM-2 from 4 to 7 days; the F3 work rolls run past their wear limit, roll force "
            "rises and the worn roll surface scratches the strip."
        ),
        target_class="scratches",
        line="HSM-2",
        equipment="F3",
        window=(0.70, 0.88),
        shape="ramp",
        ramp_floor=0.15,
        defect_boost=0.24,
        readings=(ReadingEffect("F3", "roll_force", relative=0.10),),
        keywords=(
            "work roll",
            "arbeitswalze",
            "roll change",
            "walzenwechsel",
            "interval",
            "intervall",
            "wear",
            "verschleiß",
            "revision",
            "instruction",
            "anweisung",
        ),
    ),
    CauseSpec(
        key="crew_skipped_step",
        category_6m="man",
        mechanism=(
            f"After a crew change, crew C on HSM-1 skips step 4 of {LAMINAR_START_WI} (top-spray "
            "purge and edge-mask check at laminar-cooling start-up); residual water on the strip "
            "leaves patches and lowers the coiling temperature."
        ),
        target_class="patches",
        line="HSM-1",
        equipment="LCT",
        window=(0.50, 0.70),
        shape="step",
        crew="C",
        defect_boost=0.40,
        readings=(ReadingEffect("LCT", "strip_temperature", absolute=-14.0),),
        keywords=(
            "skip",
            "purge",
            "spray",
            "edge mask",
            "training",
            "schulung",
            "procedure",
            "verfahren",
            "new crew",
            "neue",
            "start-up",
            "anfahr",
            "water",
            "wasser",
        ),
    ),
    CauseSpec(
        key="thermocouple_drift",
        category_6m="measurement",
        mechanism=(
            "The control thermocouple in the HSM-2 reheat furnace drifts low; the furnace control "
            "compensates, so the displayed discharge temperature stays on target while slabs leave "
            "hotter, downstream strip temperatures rise and the overheated surface crazes."
        ),
        target_class="crazing",
        line="HSM-2",
        equipment="FUR",
        window=(0.06, 0.22),
        shape="ramp",
        ramp_floor=0.10,
        defect_boost=0.22,
        readings=(
            ReadingEffect("RM", "strip_temperature", absolute=31.5),
            ReadingEffect("F1", "strip_temperature", absolute=28.0),
            ReadingEffect("F6", "strip_temperature", absolute=19.0),
            ReadingEffect("LCT", "strip_temperature", absolute=10.0),
        ),
        keywords=(
            "thermocouple",
            "thermoelement",
            "calibrat",
            "kalibrier",
            "drift",
            "sensor",
            "furnace",
            "ofen",
            "overheat",
            "überhitz",
            "temperature",
            "temperatur",
        ),
    ),
    CauseSpec(
        key="cooling_water_heat",
        category_6m="environment",
        mechanism=(
            "During a heat wave the cooling-water supply temperature of the HSM-1 laminar "
            "cooling rises; the controller raises the flow, the coiling temperature still "
            "overshoots, scale grows thicker in the coil and pickling exposes pits."
        ),
        target_class="pitted_surface",
        line="HSM-1",
        equipment="LCT",
        window=(0.80, 0.94),
        shape="plateau",
        defect_boost=0.20,
        readings=(
            ReadingEffect("LCT", "coolant_flow", relative=0.10),
            ReadingEffect("LCT", "strip_temperature", absolute=16.0),
        ),
        keywords=(
            "heat",
            "hitze",
            "humid",
            "feucht",
            "weather",
            "wetter",
            "cooling water",
            "kühlwasser",
            "ambient",
            "umgebung",
            "temperature",
            "temperatur",
            "summer",
            "sommer",
        ),
    ),
)

# Words that would reveal any ground truth if they appeared in plant text.
GLOBAL_KEYWORDS: tuple[str, ...] = (
    "root cause",
    "cause",
    "ursache",
    "injection",
    "planted",
    "simulat",
)


def leaked_keywords(text: str) -> list[str]:
    """Keywords from any cause (or the global list) that occur as word prefixes in text."""
    lowered = text.lower()
    words = {kw for spec in CAUSES for kw in spec.keywords} | set(GLOBAL_KEYWORDS)
    return sorted(kw for kw in words if re.search(r"(?<!\w)" + re.escape(kw), lowered))


@dataclass(frozen=True, slots=True)
class Injection:
    """A cause placed on a concrete line, equipment and time window."""

    spec: CauseSpec
    id: uuid.UUID
    cause_id: uuid.UUID
    line_id: uuid.UUID
    equipment_id: uuid.UUID | None
    start: datetime
    end: datetime
    lot_ids: frozenset[uuid.UUID] = frozenset()

    def progress(self, ts: datetime) -> float | None:
        if not self.start <= ts <= self.end:
            return None
        return (ts - self.start) / (self.end - self.start)

    def intensity(self, *, line_id: uuid.UUID, ts: datetime, crew: str, lot_id: uuid.UUID) -> float:
        """0 when the coil is unaffected, up to 1 at full effect."""
        if line_id != self.line_id:
            return 0.0
        p = self.progress(ts)
        if p is None:
            return 0.0
        if self.spec.crew is not None and crew != self.spec.crew:
            return 0.0
        if self.lot_ids and lot_id not in self.lot_ids:
            return 0.0
        match self.spec.shape:
            case "ramp":
                return self.spec.ramp_floor + (1 - self.spec.ramp_floor) * p
            case "plateau":
                return max(0.0, min(1.0, p / 0.2, (1 - p) / 0.2))
            case "step":
                return 1.0

    def params(self) -> dict[str, object]:
        spec = self.spec
        params: dict[str, object] = {
            "key": spec.key,
            "defect_class": spec.target_class,
            "shape": spec.shape,
            "defect_rate_boost": spec.defect_boost,
            "reading_effects": [
                {
                    "equipment": e.suffix,
                    "parameter": e.parameter,
                    "relative": e.relative,
                    "absolute": e.absolute,
                }
                for e in spec.readings
            ],
        }
        if spec.crew is not None:
            params["crew"] = spec.crew
        if spec.supplier is not None:
            params["supplier"] = spec.supplier
        if self.lot_ids:
            params["lot_ids"] = sorted(str(i) for i in self.lot_ids)
        return params
