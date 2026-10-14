from __future__ import annotations

from collections.abc import Sequence

# Changing this list requires a new migration that recreates plant.coil_process_summary.
PROCESS_PARAMETERS: tuple[str, ...] = (
    "roll_force",
    "strip_temperature",
    "roll_speed",
    "strip_tension",
    "descaler_pressure",
    "coolant_flow",
    "exit_thickness",
)


def coil_process_summary_sql(parameters: Sequence[str] = PROCESS_PARAMETERS) -> str:
    for p in parameters:
        if not p.isidentifier():
            raise ValueError(f"invalid parameter name: {p!r}")
    aggregates = ",\n    ".join(
        f"{fn}(r.value) FILTER (WHERE r.parameter = '{p}') AS {p}_{suffix}"
        for p in parameters
        for fn, suffix in (("avg", "mean"), ("min", "min"), ("max", "max"))
    )
    return f"""
CREATE MATERIALIZED VIEW plant.coil_process_summary AS
SELECT
    c.id AS coil_id,
    c.line_id,
    c.started_at,
    c.finished_at,
    {aggregates}
FROM plant.coils c
LEFT JOIN plant.process_readings r
    ON r.line_id = c.line_id
   AND r.ts >= c.started_at
   AND r.ts <= c.finished_at
GROUP BY c.id, c.line_id, c.started_at, c.finished_at
"""  # noqa: S608
