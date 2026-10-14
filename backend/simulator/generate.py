"""Build the whole simulated plant in memory. Pure and deterministic: no I/O, no clock."""

from __future__ import annotations

import logging
import math
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from simulator.causes import CAUSES, WORK_ROLL_WI_CHANGE_AT, Injection
from simulator.config import SimConfig
from simulator.documents import LotInfo, build_documents
from simulator.incidents import ShiftSummary, render, severity
from simulator.model import (
    CoilRow,
    Dataset,
    DefectRow,
    EquipmentRow,
    GradeRow,
    IncidentRow,
    InjectionRow,
    InspectionRow,
    LineRow,
    LotRow,
    MaintenanceRow,
    ReadingRow,
    RootCauseRow,
    SupplierRow,
    stable_id,
)
from simulator.plant import (
    BASE_DEFECT_RATE,
    CREWS,
    DEFECT_CLASSES,
    EQUIPMENT,
    GRADES,
    LINES,
    PROCESS_TYPE,
    SERIES,
    SHIFTS,
    SUPPLIERS,
    TECHNICIANS,
    THICKNESS_MIX,
    UNITS,
    Grade,
    coil_length_m,
    nominal,
    tag,
)
from simulator.questions import build_questions

logger = logging.getLogger(__name__)

BURST_BOOST = 0.15
_NO_LOT = uuid.UUID(int=0)
DAY = timedelta(days=1)

_UNPLANNED: dict[str, tuple[str, ...]] = {
    "reheat_furnace": (
        "Burner 7 flame failure; igniter replaced.",
        "Walking-beam hydraulic leak repaired.",
    ),
    "descaler": (
        "Pump coupling noise; coupling inspected and greased.",
        "Leak at a header flange repaired.",
    ),
    "roughing_mill": (
        "Edger hydraulic hose replaced.",
        "Main drive trip; reset after cooling fan fault.",
    ),
    "finishing_stand": (
        "Looper hydraulic valve replaced.",
        "Bearing temperature alarm; bearing re-greased.",
        "AGC cylinder seal leak repaired.",
    ),
    "laminar_cooling": (
        "Header valve in fault; valve actuator replaced.",
        "Run-out table roller seized; roller replaced.",
    ),
    "coiler": (
        "Pinch roll realigned after edge damage report.",
        "Wrapper roll 2 hydraulic fault reset.",
    ),
}

# Repairs logged when a planted problem is found and fixed; keyed by cause.
_CORRECTIVE: dict[str, str] = {
    "descaler_nozzle_wear": (
        "Header pressure 12 % below setpoint at constant pump speed; nozzles of header 2 replaced."
    ),
    "work_roll_overrun": (
        "F3 work rolls changed ahead of schedule after quality reported surface marks; "
        "roll surface banded."
    ),
    "thermocouple_drift": (
        "Zone 5 control thermocouple replaced after a deviation was found in the cross-check "
        "with the roughing-mill pyrometer."
    ),
}


@dataclass(slots=True)
class Coil:
    id: uuid.UUID
    line: str
    start: datetime
    finish: datetime
    grade: Grade
    thickness: float
    shift: str
    shift_start: datetime
    crew: str
    lot_id: uuid.UUID = _NO_LOT
    defects: list[tuple[str, int, float]] = field(default_factory=list[tuple[str, int, float]])
    result: str = "pass"


@dataclass(frozen=True, slots=True)
class Burst:
    line: str
    defect_class: str
    start: datetime
    end: datetime


def generate(cfg: SimConfig) -> Dataset:
    return _Generator(cfg).run()


class _Generator:
    def __init__(self, cfg: SimConfig) -> None:
        self.cfg = cfg
        self.end = cfg.start + timedelta(days=cfg.days)
        self.ds = Dataset()
        self.line_ids: dict[str, uuid.UUID] = {}
        self.equipment_ids: dict[tuple[str, str], uuid.UUID] = {}
        self.coils: list[Coil] = []
        self.lots: list[LotInfo] = []
        self.lot_line: dict[uuid.UUID, str] = {}
        self.lot_coils: dict[uuid.UUID, list[Coil]] = {}
        self.injections: list[Injection] = []
        self.bursts: list[Burst] = []
        self.incident_cause: dict[uuid.UUID, uuid.UUID] = {}

    def rng(self, stream: str) -> random.Random:
        # One stream per stage, so changing one stage's draws does not shift the others.
        return random.Random(f"{self.cfg.seed}/{stream}")

    def id(self, *parts: object) -> uuid.UUID:
        return stable_id(self.cfg.seed, *parts)

    def at_fraction(self, fraction: float) -> datetime:
        return self.cfg.start + timedelta(minutes=round(fraction * self.cfg.days * 24 * 60))

    def run(self) -> Dataset:
        self._static()
        self._coils()
        self._lots()
        self._injections()
        self._bursts()
        self._process()
        self._maintenance()
        self._incidents()
        self._documents_and_lots()
        self._ground_truth()
        logger.info("simulated plant", extra={"counts": self.ds.counts()})
        return self.ds

    def _static(self) -> None:
        for name in LINES:
            line_id = self.id("line", name)
            self.line_ids[name] = line_id
            self.ds.lines.append(LineRow(line_id, name, PROCESS_TYPE))
            for eq in EQUIPMENT:
                eq_tag = tag(name, eq.suffix)
                eq_id = self.id("equipment", eq_tag)
                self.equipment_ids[(name, eq.suffix)] = eq_id
                self.ds.equipment.append(EquipmentRow(eq_id, line_id, eq_tag, eq.type, eq.name))
        self.ds.suppliers = [
            SupplierRow(self.id("supplier", s.name), s.name, s.country) for s in SUPPLIERS
        ]
        self.ds.grades = [GradeRow(self.id("grade", g.code), g.code, g.spec) for g in GRADES]

    def _shift(self, ts: datetime) -> tuple[str, datetime, str]:
        # Before the first shift start of the day, the coil belongs to the previous night shift.
        index = (sum(ts.hour >= h for _, h in SHIFTS) - 1) % len(SHIFTS)
        name, start_hour = SHIFTS[index]
        shift_start = ts.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        if ts.hour < start_hour:
            shift_start -= DAY
        day_index = (shift_start - self.cfg.start).days
        # Four crews, three shifts: each crew works two days per shift slot, one crew is off.
        crew = CREWS[(day_index // 2 + index) % len(CREWS)]
        return name, shift_start, crew

    def _coils(self) -> None:
        rng = self.rng("coils")
        gap = 86_400 / self.cfg.coils_per_day
        grade_weights = [g.share for g in GRADES]
        thicknesses = [t for t, _ in THICKNESS_MIX]
        thickness_weights = [w for _, w in THICKNESS_MIX]
        for line in LINES:
            for day in range(self.cfg.days):
                for k in range(self.cfg.coils_per_day):
                    offset = day * 86_400 + k * gap + rng.uniform(0, 0.3 * gap)
                    start = self.cfg.start + timedelta(seconds=round(offset))
                    duration = min(rng.uniform(180, 360), 0.6 * gap)
                    shift, shift_start, crew = self._shift(start)
                    self.coils.append(
                        Coil(
                            id=self.id("coil", line, len(self.coils)),
                            line=line,
                            start=start,
                            finish=start + timedelta(seconds=round(duration)),
                            grade=rng.choices(GRADES, grade_weights)[0],
                            thickness=rng.choices(thicknesses, thickness_weights)[0],
                            shift=shift,
                            shift_start=shift_start,
                            crew=crew,
                        )
                    )

    def _lots(self) -> None:
        """Group each line's coils of one grade into delivery lots of about one week."""
        rng = self.rng("lots")
        span = timedelta(days=max(1.5, min(7.0, 0.12 * self.cfg.days)))
        suppliers = {s.name: s for s in SUPPLIERS}
        for line in LINES:
            for grade in GRADES:
                chunk: list[Coil] = []
                chunks: list[list[Coil]] = []
                for coil in self.coils:
                    if coil.line != line or coil.grade is not grade:
                        continue
                    if chunk and coil.start - chunk[0].start > span:
                        chunks.append(chunk)
                        chunk = []
                    chunk.append(coil)
                if chunk:
                    chunks.append(chunk)
                for i, members in enumerate(chunks):
                    lot_id = self.id("lot", line, grade.code, i)
                    received = members[0].start - timedelta(days=rng.uniform(1, 5))
                    received = received.replace(hour=rng.randint(7, 15), minute=0, second=0)
                    supplier = suppliers[rng.choice(grade.suppliers)]
                    slabs = len(members) + rng.randint(0, 6)
                    self.lots.append(LotInfo(lot_id, supplier, grade, received, slabs, False))
                    self.lot_line[lot_id] = line
                    self.lot_coils[lot_id] = members
                    for coil in members:
                        coil.lot_id = lot_id

    def _injections(self) -> None:
        for spec in CAUSES:
            line_id = self.line_ids[spec.line]
            equipment_id = (
                self.equipment_ids[(spec.line, spec.equipment)] if spec.equipment else None
            )
            lot_ids: frozenset[uuid.UUID] = frozenset()
            if spec.supplier is not None:
                lot = self._pick_lot(spec.line, spec.supplier, self.at_fraction(spec.window[0]))
                members = self.lot_coils[lot.id]
                start, end = members[0].start, members[-1].finish
                lot_ids = frozenset({lot.id})
                self.lots[self.lots.index(lot)] = LotInfo(
                    lot.id, lot.supplier, lot.grade, lot.received_at, lot.slabs, True
                )
            else:
                start, end = self.at_fraction(spec.window[0]), self.at_fraction(spec.window[1])
            self.injections.append(
                Injection(
                    spec=spec,
                    id=self.id("injection", spec.key),
                    cause_id=self.id("cause", spec.key),
                    line_id=line_id,
                    equipment_id=equipment_id,
                    start=start,
                    end=end,
                    lot_ids=lot_ids,
                )
            )

    def _pick_lot(self, line: str, supplier: str, target: datetime) -> LotInfo:
        on_line = [lot for lot in self.lots if self.lot_line[lot.id] == line]
        candidates = [lot for lot in on_line if lot.supplier.name == supplier] or on_line
        return min(
            candidates,
            key=lambda lot: (abs(self.lot_coils[lot.id][0].start - target), str(lot.id)),
        )

    def _bursts(self) -> None:
        """Short defect clusters outside every planted window: noise with no incident."""
        rng = self.rng("bursts")
        hours = self.cfg.days * 24
        for _ in range(self.cfg.noise_bursts):
            for _attempt in range(50):
                line = rng.choice(LINES)
                length = timedelta(hours=rng.uniform(6, 12))
                start = self.cfg.start + timedelta(hours=rng.uniform(0, hours - 12))
                end = start + length
                clash = any(
                    inj.spec.line == line and start < inj.end + DAY and end > inj.start - DAY
                    for inj in self.injections
                )
                if not clash:
                    self.bursts.append(Burst(line, rng.choice(DEFECT_CLASSES), start, end))
                    break

    def _process(self) -> None:
        """Readings, inspections and defects for every coil, with planted effects applied."""
        drift_rng, noise, defect_rng = self.rng("drift"), self.rng("readings"), self.rng("defects")
        drift = {
            (line, s): (drift_rng.uniform(18, 40), drift_rng.uniform(0, 2 * math.pi))
            for line in LINES
            for s in SERIES
        }
        n = self.cfg.samples_per_coil
        for coil in self.coils:
            line_id = self.line_ids[coil.line]
            active = [
                (inj, i)
                for inj in self.injections
                if (
                    i := inj.intensity(
                        line_id=line_id, ts=coil.start, crew=coil.crew, lot_id=coil.lot_id
                    )
                )
                > 0
            ]
            duration = coil.finish - coil.start
            for s in SERIES:
                eq_id = self.equipment_ids[(coil.line, s.suffix)]
                base = nominal(s, coil.grade, coil.thickness)
                period, phase = drift[(coil.line, s)]
                effects = [
                    (e, i)
                    for inj, i in active
                    for e in inj.spec.readings
                    if e.suffix == s.suffix and e.parameter == s.parameter
                ]
                for k in range(n):
                    ts = coil.start + duration * ((k + 0.5) / n)
                    t_days = (ts - self.cfg.start).total_seconds() / 86_400
                    value = base * (
                        1 + s.drift_rel * math.sin(2 * math.pi * t_days / period + phase)
                    )
                    value += noise.gauss(0, s.noise_rel * base)
                    for e, i in effects:
                        value = value * (1 + e.relative * i) + e.absolute * i
                    self.ds.readings.append(
                        ReadingRow(
                            line_id, eq_id, ts, s.parameter, round(value, 3), UNITS[s.parameter]
                        )
                    )
            self._defects(coil, active, defect_rng)

    def _defects(
        self, coil: Coil, active: list[tuple[Injection, float]], rng: random.Random
    ) -> None:
        length = coil_length_m(coil.thickness)
        for cls in DEFECT_CLASSES:
            planted = [i for inj, i in active if inj.spec.target_class == cls]
            boost = sum(
                inj.spec.defect_boost * i for inj, i in active if inj.spec.target_class == cls
            )
            in_burst = any(
                b.line == coil.line and b.defect_class == cls and b.start <= coil.start <= b.end
                for b in self.bursts
            )
            p = BASE_DEFECT_RATE[cls] + boost + (BURST_BOOST if in_burst else 0.0)
            if rng.random() >= p:
                continue
            count = 1 + (rng.random() < 0.35) + (rng.random() < 0.1)
            from_cause = rng.random() < boost / p
            for _ in range(count):
                if from_cause:
                    sev = round(1.5 + 3.0 * max(planted) + rng.gauss(0, 0.7))
                else:
                    sev = rng.choices((1, 2, 3), (0.5, 0.35, 0.15))[0]
                coil.defects.append((cls, max(1, min(5, sev)), round(rng.uniform(0, length), 1)))
        worst = max((sev for _, sev, _ in coil.defects), default=0)
        coil.result = "pass" if worst == 0 else "pass_with_remarks" if worst <= 2 else "hold"
        inspection_id = self.id("inspection", coil.id)
        ts = coil.finish + timedelta(seconds=round(rng.uniform(300, 1800)))
        self.ds.inspections.append(InspectionRow(inspection_id, coil.id, ts, "ASIS", coil.result))
        for j, (cls, sev, pos) in enumerate(coil.defects):
            self.ds.defects.append(
                DefectRow(self.id("defect", coil.id, j), inspection_id, coil.id, cls, sev, pos)
            )

    def _maintenance(self) -> None:
        rng = self.rng("maintenance")
        events: list[tuple[str, str, datetime, str, str]] = []

        def morning(day: float) -> datetime:
            ts = self.cfg.start + timedelta(days=math.floor(day), hours=7)
            return ts + timedelta(minutes=rng.randint(0, 180))

        wi_change = WORK_ROLL_WI_CHANGE_AT * self.cfg.days
        overrun = next(inj for inj in self.injections if inj.spec.key == "work_roll_overrun")
        schedules: list[tuple[str, float, str]] = [
            *(
                (f"F{i}", 4.0, "Planned work-roll change F{i}; roll set {n} installed.")
                for i in range(1, 5)
            ),
            *(
                (f"F{i}", 3.0, "Planned work-roll change F{i}; roll set {n} installed.")
                for i in (5, 6)
            ),
            ("RM", 10.0, "Planned work-roll change roughing mill; roll set {n} installed."),
            ("DSC", 21.0, "Descaler spray-pattern check and filter cleaning."),
            ("FUR", 30.0, "Burner and refractory inspection."),
            ("LCT", 7.0, "Header filter cleaning and valve function test."),
            ("DC", 7.0, "Mandrel segment and pinch roll lubrication; pinch roll gap checked."),
        ]
        for line in LINES:
            for suffix, interval, text in schedules:
                day, n = rng.uniform(0, interval), 1
                while day < self.cfg.days:
                    ts = morning(day)
                    skip = (
                        line == overrun.spec.line
                        and suffix == overrun.spec.equipment
                        and overrun.start <= ts <= overrun.end
                    )
                    if not skip:
                        description = text.format(i=suffix[1:], n=f"{tag(line, suffix)}-{n:03d}")
                        events.append((line, suffix, ts, "planned", description))
                        n += 1
                    extended = line == "HSM-2" and suffix in {"F1", "F2", "F3", "F4"}
                    day += 7.0 if extended and day >= wi_change else interval
            # Only HSM-1 gets its routine furnace calibration inside the horizon.
            if line == "HSM-1":
                events.append(
                    (
                        line,
                        "FUR",
                        morning(0.30 * self.cfg.days),
                        "planned",
                        "Thermocouple calibration per SOP-MNT-002; all zones within tolerance.",
                    )
                )
            for day in range(self.cfg.days):
                if rng.random() < 0.12:
                    eq = rng.choice(EQUIPMENT)
                    ts = self.cfg.start + timedelta(days=day, minutes=rng.randint(0, 1439))
                    events.append(
                        (line, eq.suffix, ts, "unplanned", rng.choice(_UNPLANNED[eq.type]))
                    )

        for inj in self.injections:
            spec = inj.spec
            if spec.key in _CORRECTIVE and spec.equipment:
                ts = inj.end + timedelta(minutes=rng.randint(30, 180))
                events.append((spec.line, spec.equipment, ts, "unplanned", _CORRECTIVE[spec.key]))
            # A coincidental repair close to the window start, on other equipment of the line.
            decoy = rng.choice([eq for eq in EQUIPMENT if eq.suffix != spec.equipment])
            ts = inj.start + timedelta(hours=rng.uniform(-24, 12))
            events.append(
                (spec.line, decoy.suffix, ts, "unplanned", rng.choice(_UNPLANNED[decoy.type]))
            )

        events.sort(key=lambda e: (e[2], e[0], e[1]))
        for k, (line, suffix, ts, kind, description) in enumerate(events):
            self.ds.maintenance.append(
                MaintenanceRow(
                    self.id("maintenance", k),
                    self.equipment_ids[(line, suffix)],
                    ts,
                    kind,
                    description,
                    rng.choice(TECHNICIANS),
                )
            )

    def _incidents(self) -> None:
        rng = self.rng("incidents")
        for inj in self.injections:
            spec = inj.spec
            shifts: dict[datetime, list[Coil]] = defaultdict(list)
            for coil in self.coils:
                if coil.line == spec.line and inj.start <= coil.start <= inj.end:
                    shifts[coil.shift_start].append(coil)
            ranked: list[tuple[int, datetime, list[Coil], list[Coil]]] = []
            for shift_start, coils in shifts.items():
                p = inj.progress(coils[0].start)
                if p is None or (p < 0.25 and spec.shape != "step"):
                    continue
                hit = [c for c in coils if any(d[0] == spec.target_class for d in c.defects)]
                if hit:
                    ranked.append((-len(hit), shift_start, coils, hit))
            ranked.sort(key=lambda r: (r[0], r[1]))
            chosen: list[tuple[datetime, list[Coil], list[Coil]]] = []
            for min_gap in (DAY, timedelta(hours=8)):
                for _, shift_start, coils, hit in ranked:
                    if len(chosen) == self.cfg.incidents_per_injection:
                        break
                    if all(abs(shift_start - c[0]) >= min_gap for c in chosen):
                        chosen.append((shift_start, coils, hit))
            for k, (shift_start, coils, hit) in enumerate(sorted(chosen, key=lambda c: c[0])):
                defects = [d for c in hit for d in c.defects if d[0] == spec.target_class]
                summary = ShiftSummary(
                    line=spec.line,
                    shift=coils[0].shift,
                    shift_start=shift_start,
                    crew=coils[0].crew,
                    coils=len(coils),
                    affected=len(hit),
                    max_severity=max(d[1] for d in defects),
                    on_hold=sum(c.result == "hold" for c in hit),
                    grades=tuple(sorted({c.grade.code for c in hit})),
                    position_range_m=(min(d[2] for d in defects), max(d[2] for d in defects)),
                )
                language = "de" if len(self.ds.incidents) % 4 == 1 else "en"
                title, description = render(spec.target_class, summary, language)
                reported = shift_start + timedelta(hours=8, minutes=rng.randint(5, 40))
                self.ds.incidents.append(
                    IncidentRow(
                        self.id("incident", spec.key, k),
                        title,
                        description,
                        self.line_ids[spec.line],
                        reported,
                        severity(summary),
                        language,
                    )
                )
                self.incident_cause[self.ds.incidents[-1].id] = inj.cause_id

    def _documents_and_lots(self) -> None:
        wi_change = self.at_fraction(WORK_ROLL_WI_CHANGE_AT).date()
        documents, certs = build_documents(
            self.cfg.seed, self.cfg.start.date(), wi_change, self.lots, self.rng("documents")
        )
        self.ds.documents = documents
        supplier_ids = {s.name: s.id for s in self.ds.suppliers}
        grade_ids = {g.code: g.id for g in self.ds.grades}
        self.ds.lots = [
            LotRow(
                lot.id,
                supplier_ids[lot.supplier.name],
                grade_ids[lot.grade.code],
                lot.received_at,
                certs[lot.id],
            )
            for lot in self.lots
        ]
        self.ds.coils = [
            CoilRow(
                c.id,
                self.line_ids[c.line],
                c.lot_id,
                grade_ids[c.grade.code],
                c.shift,
                c.crew,
                c.start,
                c.finish,
            )
            for c in self.coils
        ]

    def _ground_truth(self) -> None:
        self.ds.root_causes = [
            RootCauseRow(
                inj.cause_id, inj.spec.category_6m, inj.spec.mechanism, inj.spec.target_class
            )
            for inj in self.injections
        ]
        self.ds.injections = [
            InjectionRow(
                inj.id,
                inj.cause_id,
                inj.line_id,
                inj.equipment_id,
                inj.start,
                inj.end,
                inj.params(),
            )
            for inj in self.injections
        ]
        self.ds.questions = build_questions(self.cfg, self.ds, self.incident_cause)
