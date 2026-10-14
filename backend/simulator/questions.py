"""Evaluation questions: one RCA question per incident, and SQL questions with computed answers."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import date, timedelta
from statistics import fmean

from simulator.config import SimConfig
from simulator.model import Dataset, QuestionRow, stable_id

# Each check query returns a single value equal to the gold answer; tests run them against the DB.
_COILS_ON = "plant.coils c JOIN plant.lines l ON l.id = c.line_id"


def _utc(d: date) -> str:
    return f"'{d.isoformat()} 00:00:00+00'"


def build_questions(
    cfg: SimConfig, ds: Dataset, incident_cause: dict[uuid.UUID, uuid.UUID]
) -> list[QuestionRow]:
    lines = {line.id: line.name for line in ds.lines}
    questions = [
        QuestionRow(
            id=stable_id(cfg.seed, "question", "rca", incident.id),
            kind="rca",
            query=(
                f'Find the root cause of incident "{incident.title}" '
                f"({lines[incident.line_id]}, reported {incident.reported_at:%Y-%m-%d %H:%M} UTC)."
            ),
            incident_id=incident.id,
            gold_cause_id=incident_cause[incident.id],
            gold_answer=None,
        )
        for incident in ds.incidents
    ]
    for key, (query, answer, check_sql) in _sql_questions(cfg, ds).items():
        questions.append(
            QuestionRow(
                id=stable_id(cfg.seed, "question", "sql", key),
                kind="sql",
                query=query,
                incident_id=None,
                gold_cause_id=None,
                gold_answer=answer,
                check_sql=check_sql,
            )
        )
    return questions


def _top(counter: Counter[str]) -> str:
    """Most common key; ties go to the alphabetically first."""
    return min(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _sql_questions(cfg: SimConfig, ds: Dataset) -> dict[str, tuple[str, str, str]]:
    line_name = {line.id: line.name for line in ds.lines}
    eq_tag = {eq.id: eq.tag for eq in ds.equipment}
    eq_line = {eq.id: line_name[eq.line_id] for eq in ds.equipment}
    supplier_name = {s.id: s.name for s in ds.suppliers}
    grade_code = {g.id: g.code for g in ds.grades}
    coil_line = {c.id: line_name[c.line_id] for c in ds.coils}
    coil_day = {c.id: c.started_at.date() for c in ds.coils}
    start = cfg.start.date()

    def day(fraction: float) -> date:
        return start + timedelta(days=int(fraction * cfg.days))

    def on(line: str) -> Callable[[uuid.UUID], bool]:
        return lambda coil_id: coil_line[coil_id] == line

    out: dict[str, tuple[str, str, str]] = {}

    d1 = day(0.30)
    d2 = d1 + timedelta(days=6)
    n = sum(1 for c in ds.coils if on("HSM-2")(c.id) and d1 <= coil_day[c.id] <= d2)
    out["coils_week_hsm2"] = (
        f"How many coils were rolled on HSM-2 from {d1} to {d2} inclusive (UTC dates)?",
        str(n),
        f"SELECT count(*) FROM {_COILS_ON} WHERE l.name = 'HSM-2'"
        f" AND c.started_at >= {_utc(d1)} AND c.started_at < {_utc(d2 + timedelta(days=1))}",
    )

    lots_by_supplier = Counter(supplier_name[lot.supplier_id] for lot in ds.lots)
    out["top_supplier_lots"] = (
        "Which supplier delivered the most material lots? If tied, give the alphabetically first.",
        _top(lots_by_supplier),
        "SELECT s.name FROM plant.material_lots m JOIN plant.suppliers s ON s.id = m.supplier_id"
        " GROUP BY s.name ORDER BY count(*) DESC, s.name LIMIT 1",
    )

    ostravel = lots_by_supplier["Ostravel Slab s.r.o."]
    out["ostravel_lots"] = (
        "How many material lots did Ostravel Slab s.r.o. deliver?",
        str(ostravel),
        "SELECT count(*) FROM plant.material_lots m JOIN plant.suppliers s ON s.id = m.supplier_id"
        " WHERE s.name = 'Ostravel Slab s.r.o.'",
    )

    severe_scale = sum(
        1
        for d in ds.defects
        if d.defect_class == "rolled-in_scale" and d.severity >= 4 and on("HSM-1")(d.coil_id)
    )
    out["severe_scale_hsm1"] = (
        "How many rolled-in scale defects with severity 4 or higher were recorded on HSM-1 coils?",
        str(severe_scale),
        f"SELECT count(*) FROM plant.defects d JOIN {_COILS_ON} ON c.id = d.coil_id"
        " WHERE l.name = 'HSM-1' AND d.defect_class = 'rolled-in_scale' AND d.severity >= 4",
    )

    unplanned_hsm2 = sum(
        1 for m in ds.maintenance if m.kind == "unplanned" and eq_line[m.equipment_id] == "HSM-2"
    )
    out["unplanned_hsm2"] = (
        "How many unplanned maintenance events were logged for equipment on HSM-2?",
        str(unplanned_hsm2),
        "SELECT count(*) FROM plant.maintenance_events m"
        " JOIN plant.equipment e ON e.id = m.equipment_id JOIN plant.lines l ON l.id = e.line_id"
        " WHERE l.name = 'HSM-2' AND m.kind = 'unplanned'",
    )

    unplanned_by_tag = Counter(
        eq_tag[m.equipment_id]
        for m in ds.maintenance
        if m.kind == "unplanned" and eq_line[m.equipment_id] == "HSM-1"
    )
    out["top_unplanned_equipment_hsm1"] = (
        "Which HSM-1 equipment tag had the most unplanned maintenance events? If tied, give the "
        "alphabetically first.",
        _top(unplanned_by_tag),
        "SELECT e.tag FROM plant.maintenance_events m"
        " JOIN plant.equipment e ON e.id = m.equipment_id JOIN plant.lines l ON l.id = e.line_id"
        " WHERE l.name = 'HSM-1' AND m.kind = 'unplanned'"
        " GROUP BY e.tag ORDER BY count(*) DESC, e.tag LIMIT 1",
    )

    held = {i.coil_id for i in ds.inspections if i.result == "hold"}
    holds_by_crew = Counter(c.crew for c in ds.coils if c.id in held and on("HSM-1")(c.id))
    out["top_hold_crew_hsm1"] = (
        "Which crew rolled the most HSM-1 coils that were put on hold at inspection? If tied, "
        "give the alphabetically first.",
        _top(holds_by_crew),
        f"SELECT c.crew FROM {_COILS_ON} JOIN plant.inspections i ON i.coil_id = c.id"
        " WHERE l.name = 'HSM-1' AND i.result = 'hold'"
        " GROUP BY c.crew ORDER BY count(*) DESC, c.crew LIMIT 1",
    )

    s355 = sum(1 for c in ds.coils if on("HSM-2")(c.id) and grade_code[c.grade_id] == "S355J2")
    out["s355_hsm2"] = (
        "How many coils of grade S355J2 were rolled on HSM-2?",
        str(s355),
        f"SELECT count(*) FROM {_COILS_ON} JOIN plant.steel_grades g ON g.id = c.grade_id"
        " WHERE l.name = 'HSM-2' AND g.code = 'S355J2'",
    )

    inclusions_by_day = Counter(
        coil_day[d.coil_id].isoformat()
        for d in ds.defects
        if d.defect_class == "inclusion" and on("HSM-2")(d.coil_id)
    )
    out["top_inclusion_day_hsm2"] = (
        "On which UTC date were the most inclusion defects found on coils rolled on HSM-2? If "
        "tied, give the earliest date (YYYY-MM-DD).",
        _top(inclusions_by_day),
        "SELECT to_char((c.started_at AT TIME ZONE 'UTC')::date, 'YYYY-MM-DD')"
        f" FROM plant.defects d JOIN {_COILS_ON} ON c.id = d.coil_id"
        " WHERE l.name = 'HSM-2' AND d.defect_class = 'inclusion'"
        " GROUP BY 1 ORDER BY count(*) DESC, 1 LIMIT 1",
    )

    pressure_day = day(0.05)
    dsc = next(eq.id for eq in ds.equipment if eq.tag == "HSM1-DSC")
    mean = fmean(
        r.value
        for r in ds.readings
        if r.equipment_id == dsc
        and r.parameter == "descaler_pressure"
        and r.ts.date() == pressure_day
    )
    out["descaler_pressure_mean"] = (
        f"What was the mean descaler pressure in bar on HSM1-DSC on {pressure_day} (UTC), "
        "rounded to one decimal?",
        f"{mean:.1f}",
        "SELECT round(avg(r.value)::numeric, 1) FROM plant.process_readings r"
        " JOIN plant.equipment e ON e.id = r.equipment_id"
        " WHERE e.tag = 'HSM1-DSC' AND r.parameter = 'descaler_pressure'"
        f" AND r.ts >= {_utc(pressure_day)} AND r.ts < {_utc(pressure_day + timedelta(days=1))}",
    )
    return out
