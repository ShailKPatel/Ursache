"""Controlled documents rendered from templates: instructions, SOPs, manuals, certificates, 8Ds."""

from __future__ import annotations

import hashlib
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from simulator.causes import LAMINAR_START_WI, WORK_ROLL_WI
from simulator.model import DocumentRow, stable_id
from simulator.plant import Grade, Supplier


@dataclass(frozen=True, slots=True)
class LotInfo:
    id: uuid.UUID
    supplier: Supplier
    grade: Grade
    received_at: datetime
    slabs: int
    contaminated: bool


@dataclass(frozen=True, slots=True)
class _Doc:
    key: str
    doc_type: str
    title: str
    language: str
    version: str
    effective_from: date
    effective_to: date | None
    path: str
    body: str


def build_documents(
    seed: int, start: date, wi_change: date, lots: list[LotInfo], rng: random.Random
) -> tuple[list[DocumentRow], dict[uuid.UUID, uuid.UUID]]:
    """Return document rows (with content) and the certificate document id for each lot."""
    docs = [
        *_work_instructions(start, wi_change),
        *_sops(start),
        *_manual_sections(start),
        *_eight_d_reports(start),
    ]
    cert_for_lot: dict[uuid.UUID, uuid.UUID] = {}
    for lot in lots:
        doc = _certificate(lot, rng)
        docs.append(doc)
        cert_for_lot[lot.id] = stable_id(seed, "doc", doc.key)
    rows = [
        DocumentRow(
            id=stable_id(seed, "doc", d.key),
            doc_type=d.doc_type,
            title=d.title,
            language=d.language,
            version=d.version,
            effective_from=d.effective_from,
            effective_to=d.effective_to,
            source_path=d.path,
            sha256=hashlib.sha256(d.body.encode()).hexdigest(),
            content=d.body,
        )
        for d in docs
    ]
    return rows, cert_for_lot


def _header(doc_id: str, title: str, version: str, effective: date, owner: str) -> str:
    return (
        f"# {doc_id} {title}\n\n"
        f"| Field | Value |\n|---|---|\n"
        f"| Document | {doc_id} |\n| Revision | {version} |\n"
        f"| Effective from | {effective.isoformat()} |\n| Owner | {owner} |\n\n"
    )


def _work_instructions(start: date, wi_change: date) -> list[_Doc]:
    rev2_from = start - timedelta(days=210)
    roll_change_common = (
        "## 1 Scope\n\n"
        "Work-roll change on finishing stands F1 to F6 of HSM-2. Backup rolls are covered by "
        "MM-FS-07.\n\n"
        "## 2 Safety\n\n"
        "Lock out the main drive and the hydraulic gap control before entering the stand. "
        "Two-person rule for crane lifts.\n\n"
    )
    rev2 = (
        _header(WORK_ROLL_WI, "Work-roll change, finishing stands HSM-2", "2", rev2_from, "Rolling")
        + roll_change_common
        + "## 3 Change interval\n\n"
        "1. Change the work rolls of F1 to F4 every **4 days** or after **90 km** of strip, "
        "whichever comes first.\n"
        "2. Change the work rolls of F5 and F6 every **3 days** or after **70 km**.\n"
        "3. Change any stand immediately when surface inspection reports roll marks or "
        "periodic scratches.\n\n"
        "## 4 Procedure\n\n"
        "1. Open the stand, pull the roll set onto the change car.\n"
        "2. Inspect the chocks and bearings; record findings in the maintenance log.\n"
        "3. Insert the ground roll set; check the crown and roughness certificate from the "
        "roll shop (Ra 0.8 to 1.2 µm).\n"
        "4. Zero the roll gap and run the stand in at reduced speed for the first coil.\n"
    )
    rev3 = (
        _header(WORK_ROLL_WI, "Work-roll change, finishing stands HSM-2", "3", wi_change, "Rolling")
        + roll_change_common
        + "## 3 Change interval\n\n"
        "1. Change the work rolls of F1 to F4 every **7 days** or after **160 km** of strip, "
        "whichever comes first.\n"
        "2. Change the work rolls of F5 and F6 every **3 days** or after **70 km**.\n"
        "3. Change any stand immediately when surface inspection reports roll marks or "
        "periodic scratches.\n\n"
        "## 4 Procedure\n\n"
        "1. Open the stand, pull the roll set onto the change car.\n"
        "2. Inspect the chocks and bearings; record findings in the maintenance log.\n"
        "3. Insert the ground roll set; check the crown and roughness certificate from the "
        "roll shop (Ra 0.8 to 1.2 µm).\n"
        "4. Zero the roll gap and run the stand in at reduced speed for the first coil.\n\n"
        "## Change history\n\n"
        "| Revision | Change |\n|---|---|\n"
        "| 3 | Interval for F1 to F4 extended to 7 days / 160 km to reduce roll-shop load. |\n"
        "| 2 | Added immediate change on roll marks. |\n"
    )
    laminar = (
        _header(
            LAMINAR_START_WI,
            "Laminar cooling start-up check",
            "1",
            start - timedelta(days=400),
            "Rolling",
        )
        + "## 1 Scope\n\n"
        "Applies to HSM-1 and HSM-2 at every shift start and after any stop longer than "
        "30 minutes.\n\n"
        "## 2 Steps\n\n"
        "1. Confirm the cooling pattern for the first coil on the level-2 screen.\n"
        "2. Check header valve feedback for all banks (no valve in fault).\n"
        "3. Check strip-guide rollers in the run-out table turn freely.\n"
        "4. **Purge the top sprays for 60 s and check that the edge masks are in position.** "
        "Water left on the strip from unpurged headers or open edge masks causes stains and "
        "patches on the coil surface.\n"
        "5. Sign the start-up checklist in the shift log.\n"
    )
    descaler_de = (
        _header(
            "WI-HSM-021",
            "Entzunderung: Kontrolle in jeder Schicht",
            "2",
            start - timedelta(days=150),
            "Walzwerk",
        )
        + "## 1 Zweck\n\n"
        "Sicherstellen, dass der Hochdruck-Entzunderer den Primärzunder vollständig entfernt.\n\n"
        "## 2 Ablauf\n\n"
        "1. Zu Schichtbeginn den Düsendruck am Sammelrohr ablesen. Sollwert 205 bar, "
        "Mindestwert **185 bar**.\n"
        "2. Liegt der Druck bei gleicher Pumpendrehzahl mehr als 5 % unter dem Sollwert, "
        "Instandhaltung informieren (Verdacht auf verschlissene oder verstopfte Düsen).\n"
        "3. Sichtprüfung des Spritzbilds beim ersten Coil.\n"
        "4. Ergebnis im Schichtbuch eintragen.\n"
    )
    cooling_water = (
        _header(
            "WI-HSM1-CW-004",
            "Cooling water circuit HSM-1: summer operation",
            "1",
            start - timedelta(days=300),
            "Utilities",
        )
        + "## 1 Scope\n\n"
        "Cooling-water supply for the HSM-1 laminar cooling (cooling tower circuit 1).\n\n"
        "## 2 Limits\n\n"
        "| Quantity | Normal | Alarm |\n|---|---|---|\n"
        "| Supply temperature | 25 to 30 °C | > 32 °C |\n"
        "| Flow at full pattern | up to 3600 m3/h | > 3800 m3/h |\n\n"
        "## 3 Actions when the supply temperature exceeds 32 °C\n\n"
        "1. Start the standby cooling-tower fan.\n"
        "2. Inform the rolling shift leader; coiling temperature can overshoot because "
        "warmer water removes less heat.\n"
        "3. For grades with coiling temperature below 600 °C, ask quality whether the "
        "pickling line must be warned (thicker scale, risk of pits).\n"
    )
    return [
        _Doc(
            "wi-hsm2-rc-007-r2",
            "work_instruction",
            "Work-roll change, finishing stands HSM-2",
            "en",
            "2",
            rev2_from,
            wi_change,
            "work_instructions/WI-HSM2-RC-007_rev2.md",
            rev2,
        ),
        _Doc(
            "wi-hsm2-rc-007-r3",
            "work_instruction",
            "Work-roll change, finishing stands HSM-2",
            "en",
            "3",
            wi_change,
            None,
            "work_instructions/WI-HSM2-RC-007_rev3.md",
            rev3,
        ),
        _Doc(
            "wi-hsm-014-r1",
            "work_instruction",
            "Laminar cooling start-up check",
            "en",
            "1",
            start - timedelta(days=400),
            None,
            "work_instructions/WI-HSM-014_rev1.md",
            laminar,
        ),
        _Doc(
            "wi-hsm-021-r2",
            "work_instruction",
            "Entzunderung: Kontrolle in jeder Schicht",
            "de",
            "2",
            start - timedelta(days=150),
            None,
            "work_instructions/WI-HSM-021_rev2.md",
            descaler_de,
        ),
        _Doc(
            "wi-hsm1-cw-004-r1",
            "work_instruction",
            "Cooling water circuit HSM-1: summer operation",
            "en",
            "1",
            start - timedelta(days=300),
            None,
            "work_instructions/WI-HSM1-CW-004_rev1.md",
            cooling_water,
        ),
    ]


def _sops(start: date) -> list[_Doc]:
    defect_alarms = (
        _header(
            "SOP-QM-003",
            "Handling of surface inspection alarms",
            "4",
            start - timedelta(days=120),
            "Quality",
        )
        + "## 1 Purpose\n\nDefine how the shift reacts to defects found by the automatic "
        "surface inspection system (ASIS).\n\n"
        "## 2 Severity scale\n\n"
        "| Severity | Meaning | Action |\n|---|---|---|\n"
        "| 1 | Cosmetic | Release |\n| 2 | Minor | Release with remark |\n"
        "| 3 | Significant | Hold, re-inspect |\n| 4 | Major | Hold, inform quality engineer |\n"
        "| 5 | Critical | Hold, stop line if repeated |\n\n"
        "## 3 Escalation\n\n"
        "1. Three or more coils with the same defect class at severity 3 or higher within one "
        "shift: open an incident and write a shift report.\n"
        "2. The quality engineer starts an 8D when the defect repeats in the next shift.\n"
        "3. Record defect class, positions and affected grades; attach ASIS images.\n"
    )
    hold_de = (
        _header(
            "SOP-QM-005",
            "Sperren und Freigeben von Coils",
            "2",
            start - timedelta(days=260),
            "Qualität",
        )
        + "## 1 Geltungsbereich\n\nAlle Coils von HSM-1 und HSM-2.\n\n"
        "## 2 Sperren\n\n"
        "1. Coils mit Schweregrad 3 oder höher werden im Sperrlager abgelegt.\n"
        "2. Die Sperre wird im MES mit Fehlerklasse und Prüfer eingetragen.\n\n"
        "## 3 Freigabe\n\n"
        "1. Nachprüfung durch die Qualitätssicherung innerhalb von 48 Stunden.\n"
        "2. Freigabe, Umstufung oder Verschrottung dokumentieren.\n"
    )
    calibration = (
        _header(
            "SOP-MNT-002",
            "Calibration of temperature measurement",
            "3",
            start - timedelta(days=330),
            "Maintenance",
        )
        + "## 1 Scope\n\nFurnace control thermocouples and the strip pyrometers of HSM-1 and "
        "HSM-2.\n\n"
        "## 2 Intervals\n\n"
        "| Instrument | Interval |\n|---|---|\n"
        "| Furnace control thermocouples (type S) | 90 days |\n"
        "| Roughing and finishing pyrometers | 180 days |\n\n"
        "## 3 Cross-check\n\n"
        "Compare the furnace discharge temperature with the roughing-mill pyrometer once per "
        "week. A difference that grows by more than 15 °C against the long-term mean points to "
        "a drifting thermocouple: recalibrate or replace it before the next campaign.\n"
    )
    handover = (
        _header("SOP-PRD-001", "Shift handover", "5", start - timedelta(days=500), "Production")
        + "## 1 Shift pattern\n\n"
        "Early 06:00 to 14:00, late 14:00 to 22:00, night 22:00 to 06:00. Four crews (A to D) "
        "rotate every two days.\n\n"
        "## 2 Handover content\n\n"
        "1. Open incidents and coils on hold.\n"
        "2. Equipment out of service and planned maintenance in the coming shift.\n"
        "3. Deviations from work instructions and the reason for them.\n"
        "4. New or temporary crew members and who supervises them.\n"
    )
    return [
        _Doc(
            "sop-qm-003-r4",
            "sop",
            "Handling of surface inspection alarms",
            "en",
            "4",
            start - timedelta(days=120),
            None,
            "sops/SOP-QM-003_rev4.md",
            defect_alarms,
        ),
        _Doc(
            "sop-qm-005-r2",
            "sop",
            "Sperren und Freigeben von Coils",
            "de",
            "2",
            start - timedelta(days=260),
            None,
            "sops/SOP-QM-005_rev2.md",
            hold_de,
        ),
        _Doc(
            "sop-mnt-002-r3",
            "sop",
            "Calibration of temperature measurement",
            "en",
            "3",
            start - timedelta(days=330),
            None,
            "sops/SOP-MNT-002_rev3.md",
            calibration,
        ),
        _Doc(
            "sop-prd-001-r5",
            "sop",
            "Shift handover",
            "en",
            "5",
            start - timedelta(days=500),
            None,
            "sops/SOP-PRD-001_rev5.md",
            handover,
        ),
    ]


_MANUAL: tuple[tuple[str, str, str, str], ...] = (
    (
        "MM-DSC-03",
        "Descaler: nozzles, headers and pump",
        "en",
        "## Function\n\nTwo headers spray water at 180 to 220 bar onto the slab after the "
        "furnace and remove primary scale.\n\n"
        "## Wear\n\nNozzle bores erode with use. A worn nozzle widens its jet and lowers the "
        "header pressure at constant pump speed. A loss of more than 5 % against the setpoint "
        "means the nozzles must be checked; above 10 % descaling is incomplete and scale is "
        "rolled into the strip in the first finishing stands (defect class rolled-in scale).\n\n"
        "## Inspection\n\nVisual check of the spray pattern every 21 days; replace nozzles in "
        "sets per header.\n",
    ),
    (
        "MM-FS-07",
        "Finishing stands: work and backup rolls",
        "en",
        "## Roll wear\n\nWork rolls in the front stands (F1 to F4) wear fastest because of the "
        "high temperature and reduction. Past the wear limit the surface develops bands and "
        "fire cracks; roll force increases for the same reduction and the strip shows "
        "scratches and roll marks.\n\n"
        "## Monitoring\n\nTrend roll force per stand against grade and thickness. A rise of "
        "5 % or more over a campaign is a sign of worn rolls.\n",
    ),
    (
        "MM-FUR-02",
        "Wärmeofen: Temperaturmessung",
        "de",
        "## Thermoelemente\n\nJede Zone wird über ein Thermoelement Typ S geregelt. Altert das "
        "Thermoelement, zeigt es zu niedrige Werte. Die Regelung heizt dann nach, die "
        "angezeigte Ziehtemperatur bleibt im Sollbereich, die tatsächliche Brammentemperatur "
        "steigt.\n\n"
        "## Erkennung\n\nVergleich mit dem Pyrometer hinter dem Vorgerüst: steigt die "
        "gemessene Bandtemperatur ohne Änderung der Ofenanzeige, Thermoelement prüfen. "
        "Überhitzte Oberflächen neigen zu Netzrissen (crazing).\n",
    ),
    (
        "MM-LCT-04",
        "Laminar cooling: headers, valves and water quality",
        "en",
        "## Function\n\nTop and bottom headers cool the strip from finishing to coiling "
        "temperature. The controller adjusts the number of open headers and the flow.\n\n"
        "## Water temperature\n\nCooling capacity falls as the supply water gets warmer. The "
        "controller opens more headers; when it runs out of headers the coiling temperature "
        "overshoots. High coiling temperature grows thicker scale in the coil, and pickling "
        "can leave a pitted surface.\n\n"
        "## Edge masks and purge\n\nEdge masks stop over-cooling of the strip edges. Headers "
        "must be purged at start-up so no standing water drops onto the strip.\n",
    ),
    (
        "MM-DC-01",
        "Down coiler: mandrel, pinch rolls and wrapper rolls",
        "en",
        "## Pinch rolls\n\nMisaligned pinch rolls cause edge damage and telescoping coils. Check "
        "the gap and alignment every 7 days.\n\n"
        "## Mandrel\n\nLubricate the mandrel segments weekly. Worn segments leave marks on the "
        "inner wraps only, not along the strip.\n",
    ),
)


def _manual_sections(start: date) -> list[_Doc]:
    effective = start - timedelta(days=540)
    docs: list[_Doc] = []
    for code, title, language, body in _MANUAL:
        owner = "Instandhaltung" if language == "de" else "Maintenance"
        docs.append(
            _Doc(
                f"manual-{code.lower()}",
                "maintenance_manual",
                title,
                language,
                "2024.1",
                effective,
                None,
                f"maintenance_manual/{code}.md",
                _header(code, title, "2024.1", effective, owner) + body,
            )
        )
    return docs


_EIGHT_D: tuple[tuple[str, str, str, int, str], ...] = (
    (
        "8D-2025-031",
        "Edge cracks on S420MC coils, HSM-1",
        "en",
        230,
        "## D2 Problem\n\nEdge cracks on 11 S420MC coils over two days.\n\n"
        "## D4 Root cause\n\nSlab corners cooled too fast in the slab yard during frost; "
        "corner temperature at the roughing mill was 60 °C below the slab centre.\n\n"
        "## D5/D6 Corrective actions\n\nCovered slab storage for microalloyed grades in "
        "winter; edge heaters enabled for S420MC and S500MC.\n\n"
        "## D7 Prevention\n\nSlab yard instruction updated; winter checklist added.\n",
    ),
    (
        "8D-2025-044",
        "Telescoping coils at the HSM-2 down coiler",
        "en",
        190,
        "## D2 Problem\n\nNine coils telescoped by more than 30 mm.\n\n"
        "## D4 Root cause\n\nPinch roll gap out of parallel by 0.6 mm after a bearing change; "
        "the alignment check was not done after the repair.\n\n"
        "## D5/D6 Corrective actions\n\nPinch rolls realigned; post-repair alignment added to "
        "the work order template.\n\n"
        "## D7 Prevention\n\nMM-DC-01 revised to require alignment after every bearing change.\n",
    ),
    (
        "8D-2026-007",
        "Head-end thickness overshoot on thin gauges, HSM-1",
        "en",
        120,
        "## D2 Problem\n\nFirst 40 m of 1.8 mm and 2.0 mm coils were up to 0.12 mm too thick.\n\n"
        "## D4 Root cause\n\nThe automatic gauge control gain was reset to defaults after a "
        "software update of the level-1 system.\n\n"
        "## D5/D6 Corrective actions\n\nGain restored; parameter backup compared after each "
        "update.\n\n"
        "## D7 Prevention\n\nChange procedure for level-1 updates includes a parameter diff.\n",
    ),
    (
        "8D-2026-012",
        "Rollenabdrücke durch beschädigte Rollgangsrolle, HSM-2",
        "de",
        75,
        "## D2 Problembeschreibung\n\nPeriodische Abdrücke im Abstand von 1,1 m auf der "
        "Bandunterseite an 14 Coils.\n\n"
        "## D4 Grundursache\n\nEine Rolle im Auslaufrollgang hatte eine Schweißperle nach "
        "einer Reparatur; der Umfang der Rolle entspricht dem Abstand der Abdrücke.\n\n"
        "## D5/D6 Abstellmaßnahmen\n\nRolle getauscht, alle Rollen nach Schweißarbeiten "
        "geprüft.\n\n"
        "## D7 Vorbeugung\n\nSichtprüfung des Rollgangs nach jeder Heißarbeit.\n",
    ),
)


def _eight_d_reports(start: date) -> list[_Doc]:
    docs: list[_Doc] = []
    for number, title, language, days_before, body in _EIGHT_D:
        closed = start - timedelta(days=days_before)
        owner = "Qualität" if language == "de" else "Quality"
        docs.append(
            _Doc(
                f"8d-{number.lower()}",
                "8d_report",
                title,
                language,
                "final",
                closed,
                None,
                f"8d_reports/{number}.md",
                _header(number, title, "final", closed, owner) + body,
            )
        )
    return docs


_CHEMISTRY: dict[str, tuple[tuple[str, float, float], ...]] = {
    "S235JR": (("C", 0.12, 0.17), ("Mn", 0.50, 1.40), ("Si", 0.05, 0.30)),
    "S355J2": (("C", 0.14, 0.20), ("Mn", 1.20, 1.60), ("Si", 0.15, 0.50)),
    "DD11": (("C", 0.04, 0.10), ("Mn", 0.20, 0.50), ("Si", 0.01, 0.05)),
    "S420MC": (("C", 0.06, 0.12), ("Mn", 1.00, 1.60), ("Nb", 0.02, 0.05)),
    "S500MC": (("C", 0.06, 0.12), ("Mn", 1.30, 1.70), ("Nb", 0.03, 0.06)),
}


def _certificate(lot: LotInfo, rng: random.Random) -> _Doc:
    issued = (lot.received_at - timedelta(days=2)).date()
    german = lot.supplier.language == "de"
    heats = [f"H{rng.randint(10000, 99999)}" for _ in range(max(1, lot.slabs // 12))]
    chem = [
        (el, round(rng.uniform(lo + 0.2 * (hi - lo), hi - 0.2 * (hi - lo)), 3))
        for el, lo, hi in _CHEMISTRY[lot.grade.code]
    ]
    if lot.contaminated:
        sulphur, oxygen, k3 = rng.uniform(0.017, 0.019), rng.randint(33, 37), rng.randint(34, 38)
    else:
        sulphur, oxygen, k3 = rng.uniform(0.004, 0.009), rng.randint(11, 19), rng.randint(8, 18)
    rows = [*chem, ("S", round(sulphur, 4))]
    number = f"{lot.supplier.name.split()[0][:3].upper()}-{issued:%y%m%d}-{str(lot.id)[:6]}"
    if german:
        title = f"Abnahmeprüfzeugnis 3.1 {number}, {lot.grade.code}"
        body = (
            f"# {title}\n\n"
            f"Nach EN 10204, Typ 3.1. Hersteller: {lot.supplier.name}.\n\n"
            f"| Feld | Wert |\n|---|---|\n"
            f"| Kunden-Los | {lot.id} |\n| Güte | {lot.grade.code} ({lot.grade.spec}) |\n"
            f"| Brammen | {lot.slabs} |\n| Schmelzen | {', '.join(heats)} |\n"
            f"| Ausstellungsdatum | {issued.isoformat()} |\n\n"
            "## Chemische Analyse (Schmelze, Masse-%)\n\n| Element | Wert |\n|---|---|\n"
            + "".join(f"| {el} | {v} |\n" for el, v in rows)
            + "\n## Reinheitsgrad\n\n| Merkmal | Wert | Grenzwert |\n|---|---|---|\n"
            f"| Gesamtsauerstoff (ppm) | {oxygen} | 40 |\n"
            f"| Mikroreinheit DIN EN 10247, K3 | {k3} | 40 |\n\n"
            "Die Lieferung entspricht der Bestellung.\n"
        )
    else:
        title = f"Inspection certificate 3.1 {number}, {lot.grade.code}"
        body = (
            f"# {title}\n\n"
            f"According to EN 10204, type 3.1. Manufacturer: {lot.supplier.name}.\n\n"
            f"| Field | Value |\n|---|---|\n"
            f"| Customer lot | {lot.id} |\n| Grade | {lot.grade.code} ({lot.grade.spec}) |\n"
            f"| Slabs | {lot.slabs} |\n| Heats | {', '.join(heats)} |\n"
            f"| Date of issue | {issued.isoformat()} |\n\n"
            "## Chemical analysis (ladle, mass %)\n\n| Element | Value |\n|---|---|\n"
            + "".join(f"| {el} | {v} |\n" for el, v in rows)
            + "\n## Cleanliness\n\n| Property | Value | Limit |\n|---|---|---|\n"
            f"| Total oxygen (ppm) | {oxygen} | 40 |\n"
            f"| Microcleanliness DIN EN 10247, K3 | {k3} | 40 |\n\n"
            "The delivery conforms to the order.\n"
        )
    return _Doc(
        f"cert-{lot.id}",
        "material_certificate",
        title,
        "de" if german else "en",
        "1",
        issued,
        None,
        f"certificates/{number}.md",
        body,
    )
