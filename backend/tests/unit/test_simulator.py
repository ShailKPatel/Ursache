from collections import defaultdict
from pathlib import Path
from statistics import fmean

import pytest

from simulator import SimConfig, generate
from simulator.causes import CAUSES, leaked_keywords
from simulator.model import Dataset
from simulator.writer import write_documents
from ursache.db.views import PROCESS_PARAMETERS

# Large enough that every planted window holds a few hundred coils, small enough to run fast.
CONFIG = SimConfig(seed=42, days=60, coils_per_day=20, samples_per_coil=2)

# A window must at least double the target defect rate and add 4 percentage points.
MIN_RATE_RATIO = 2.0
MIN_RATE_DELTA = 0.04
# A reading effect must show at least a third of its configured peak in the window mean.
MIN_EFFECT_SHARE = 1 / 3


@pytest.fixture(scope="module")
def dataset() -> Dataset:
    return generate(CONFIG)


def test_same_seed_gives_identical_output(dataset: Dataset, tmp_path: Path) -> None:
    again = generate(CONFIG)
    assert again.digest() == dataset.digest()

    write_documents(dataset, tmp_path / "a")
    write_documents(again, tmp_path / "b")
    files_a = sorted(p.relative_to(tmp_path / "a") for p in (tmp_path / "a").rglob("*.md"))
    files_b = sorted(p.relative_to(tmp_path / "b") for p in (tmp_path / "b").rglob("*.md"))
    assert files_a == files_b
    assert len(files_a) == len(dataset.documents)
    for rel in files_a:
        assert (tmp_path / "a" / rel).read_bytes() == (tmp_path / "b" / rel).read_bytes()


def test_different_seed_gives_different_output(dataset: Dataset) -> None:
    other = generate(SimConfig(seed=43, days=60, coils_per_day=20, samples_per_coil=2))
    assert other.digest() != dataset.digest()
    assert [c.started_at for c in other.coils] != [c.started_at for c in dataset.coils]


@pytest.mark.parametrize("key", [c.key for c in CAUSES])
def test_window_raises_target_defect_rate(dataset: Dataset, key: str) -> None:
    injection = next(i for i in dataset.injections if i.params["key"] == key)
    target = next(c.target_defect_class for c in dataset.root_causes if c.id == injection.cause_id)
    with_target = {d.coil_id for d in dataset.defects if d.defect_class == target}
    on_line = [c for c in dataset.coils if c.line_id == injection.line_id]
    inside = [c for c in on_line if injection.start_ts <= c.started_at <= injection.end_ts]
    outside = [c for c in on_line if not injection.start_ts <= c.started_at <= injection.end_ts]

    rate_in = fmean(c.id in with_target for c in inside)
    rate_out = fmean(c.id in with_target for c in outside)
    assert len(inside) >= 100
    assert rate_in >= MIN_RATE_RATIO * rate_out, (rate_in, rate_out)
    assert rate_in - rate_out >= MIN_RATE_DELTA, (rate_in, rate_out)


@pytest.mark.parametrize(
    ("key", "suffix", "parameter", "relative", "absolute"),
    [
        (c.key, e.suffix, e.parameter, e.relative, e.absolute)
        for c in CAUSES
        if c.crew is None  # crew effects touch a quarter of the coils; covered by defect rate
        for e in c.readings
    ],
)
def test_window_shifts_target_reading(
    dataset: Dataset, key: str, suffix: str, parameter: str, relative: float, absolute: float
) -> None:
    injection = next(i for i in dataset.injections if i.params["key"] == key)
    line = next(line.name for line in dataset.lines if line.id == injection.line_id)
    tag = f"{line.replace('-', '')}-{suffix}"
    equipment_id = next(e.id for e in dataset.equipment if e.tag == tag)
    values: dict[bool, list[float]] = defaultdict(list)
    for r in dataset.readings:
        if r.equipment_id == equipment_id and r.parameter == parameter:
            values[injection.start_ts <= r.ts <= injection.end_ts].append(r.value)
    mean_in, mean_out = fmean(values[True]), fmean(values[False])

    if relative:
        shift = (mean_in - mean_out) / mean_out
        assert shift * relative > 0
        assert abs(shift) >= MIN_EFFECT_SHARE * abs(relative), shift
    else:
        shift = mean_in - mean_out
        assert shift * absolute > 0
        assert abs(shift) >= MIN_EFFECT_SHARE * abs(absolute), shift


def test_readings_use_only_known_parameters(dataset: Dataset) -> None:
    assert {r.parameter for r in dataset.readings} == set(PROCESS_PARAMETERS)


def test_incident_text_names_no_cause(dataset: Dataset) -> None:
    assert len(dataset.incidents) == len(CAUSES) * CONFIG.incidents_per_injection
    for incident in dataset.incidents:
        assert leaked_keywords(f"{incident.title}\n{incident.description}") == []
    assert {i.language for i in dataset.incidents} == {"en", "de"}


def test_plant_and_kb_hold_no_ground_truth_ids(dataset: Dataset) -> None:
    secret = {str(i.id) for i in dataset.injections} | {str(c.id) for c in dataset.root_causes}
    texts = [
        *(f"{i.title} {i.description}" for i in dataset.incidents),
        *(m.description for m in dataset.maintenance),
        *(d.content for d in dataset.documents),
    ]
    assert not [s for s in secret for text in texts if s in text]


def test_every_incident_has_an_rca_question(dataset: Dataset) -> None:
    rca = {q.incident_id: q.gold_cause_id for q in dataset.questions if q.kind == "rca"}
    assert set(rca) == {i.id for i in dataset.incidents}
    assert set(rca.values()) == {c.id for c in dataset.root_causes}


def test_sql_questions_have_answers_and_checks(dataset: Dataset) -> None:
    sql = [q for q in dataset.questions if q.kind == "sql"]
    assert len(sql) >= 8
    assert all(q.gold_answer and q.check_sql for q in sql)


def test_superseded_instruction_hands_over_to_its_successor(dataset: Dataset) -> None:
    revisions = sorted(
        (d for d in dataset.documents if d.source_path.startswith("work_instructions/WI-HSM2-RC")),
        key=lambda d: d.version,
    )
    assert [d.version for d in revisions] == ["2", "3"]
    assert revisions[0].effective_to == revisions[1].effective_from
    assert revisions[1].effective_to is None
    assert "**4 days**" in revisions[0].content and "**7 days**" in revisions[1].content


def test_every_lot_links_a_certificate(dataset: Dataset) -> None:
    certificates = {d.id for d in dataset.documents if d.doc_type == "material_certificate"}
    assert {lot.cert_document_id for lot in dataset.lots} == certificates
    assert len({d.sha256 for d in dataset.documents}) == len(dataset.documents)


def test_config_rejects_too_short_horizon() -> None:
    with pytest.raises(ValueError, match="days"):
        SimConfig(days=7)
