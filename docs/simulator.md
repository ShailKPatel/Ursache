# Plant simulator

`backend/simulator` builds a hot-strip mill with known root causes. It fills the `plant`
schema with process data, writes controlled documents to `data/generated/docs/` and
`kb.documents`, and records the ground truth in `eval`. The same seed and settings always
produce the same rows and files, byte for byte. The simulator makes no network or LLM calls.

```bash
make simulate                       # seed 42, 90 days
make simulate SEED=7 DAYS=60 RESET=1
cd backend && uv run ursache simulate --help
```

| Option               | Default | Effect                                                    |
| -------------------- | ------- | --------------------------------------------------------- |
| `--seed`             | 42      | Random seed; also the namespace for every generated UUID  |
| `--days`             | 90      | Length of the horizon, starting 2026-06-01 00:00 UTC      |
| `--coils-per-day`    | 40      | Coils per line per day                                    |
| `--samples-per-coil` | 3       | Readings per sensor per coil                              |
| `--reset`            | off     | Clears the simulator's rows first (see below)             |

Without `--reset` the command refuses to run when `plant.coils` already has rows. With it,
the simulator deletes only what it writes: all `plant` tables, the `kb.documents` rows of
its own document types (their chunks go with them through the foreign key), and the `eval`
causes, injections and `rca`/`sql` questions with their results. It refuses to reset while
`app.investigations` has rows, because those reference incidents. Everything runs in one
transaction and ends with `REFRESH MATERIALIZED VIEW plant.coil_process_summary`.

## Code layout

| Module         | Responsibility                                                          |
| -------------- | ----------------------------------------------------------------------- |
| `plant.py`     | Static plant: lines, equipment, grades, suppliers, sensors, nominals    |
| `causes.py`    | The planted causes, their windows and effects, the leak keyword list    |
| `generate.py`  | Builds the whole dataset in memory; pure and deterministic              |
| `incidents.py` | Shift-report templates (en, de)                                         |
| `documents.py` | Markdown templates for instructions, SOPs, manuals, certificates, 8Ds   |
| `questions.py` | Evaluation questions and gold answers computed from the dataset         |
| `writer.py`    | Writes files, then rows via `COPY` in one transaction; reset            |

Each generation stage draws from its own `random.Random` stream (seeded with
`"<seed>/<stage>"`), so changing the number of readings does not change the defects. IDs
are UUIDv5 values derived from the seed and a stable name, never from the order of
generation. `Dataset.digest()` hashes every row and document; the CLI prints it.

## Plant model

- **Lines:** HSM-1 and HSM-2. Each has a reheat furnace (`FUR`), a descaler (`DSC`), a
  roughing mill (`RM`), finishing stands `F1` to `F6`, laminar cooling (`LCT`) and a down
  coiler (`DC`). Tags are `HSM1-F2` and so on, 22 pieces of equipment in total.
- **Grades:** S235JR and S355J2 (EN 10025-2), DD11 (EN 10111), S420MC and S500MC
  (EN 10149-2). Each has a product share, a roll-force factor, a temperature offset and a
  coiling temperature target.
- **Suppliers:** four fictitious slab suppliers (DE, CZ, GB, ES). Each grade can come from
  two or three of them.
- **Coils:** 40 per line per day by default, spread over the day with jitter, 3 to 6 minutes
  each. Every coil has a grade, a finished thickness (1.8 to 6.0 mm), a shift and a crew.
- **Shifts and crews:** early 06–14, late 14–22, night 22–06. Four crews (A to D) rotate
  every two days, so one crew is always off.
- **Material lots:** each line's coils of one grade are grouped into delivery lots that
  cover about a week of consumption. A lot is received one to five days before its first
  coil and links to its EN 10204 3.1 certificate through `cert_document_id`.
- **Inspections and defects:** one automatic surface inspection (`ASIS`) per coil. Each of
  the six NEU-DET classes has a base rate per coil of 1.5 % to 3 %. Severity is 1 to 5;
  the result is `pass`, `pass_with_remarks` (worst severity 2) or `hold` (3 or more).
  `image_id` stays empty until images are ingested in Phase 3.
- **Maintenance:** planned work on a schedule (work-roll changes every 3 or 4 days, roughing
  rolls every 10, descaler check every 21, furnace inspection every 30, cooling and coiler
  service weekly), random unplanned repairs (about one per line every eight days), and the
  repair that ends some planted causes.

### Process parameters

The parameters are exactly `ursache.db.views.PROCESS_PARAMETERS`. 23 sensors per line:

| Parameter           | Unit | Measured at                 | Nominal value                                   | Noise (1σ) |
| ------------------- | ---- | --------------------------- | ----------------------------------------------- | ---------- |
| `strip_temperature` | °C   | FUR, RM, F1, F6, LCT        | 1230, 1110, 1040, 880 °C; LCT = coiling target  | 0.3–0.8 %  |
| `descaler_pressure` | bar  | DSC                         | 205 bar                                         | 1.2 %      |
| `roll_force`        | MN   | RM, F1–F6                   | RM 24 MN; F1 21 down to F6 9.5 MN × grade factor | 2.5–3 %    |
| `roll_speed`        | m/s  | F1–F6                       | F6 = 26 / thickness (4–13 m/s), earlier stands slower | 1 %   |
| `strip_tension`     | kN   | F6, DC                      | 6 + 4·h and 10 + 3·h kN (h in mm)               | 3 %        |
| `coolant_flow`      | m3/h | LCT                         | 3200 · √(h / 3) m3/h                            | 1.2 %      |
| `exit_thickness`    | mm   | F6                          | ordered thickness                               | 0.5 %      |

Every sensor also has a slow sinusoidal drift with a period of 18 to 40 days and an
amplitude of 0.2 % (temperatures) to 0.6 % (forces, flows, pressure). Readings are taken
`samples_per_coil` times, evenly spaced inside the coil's rolling window, so the
materialized view joins them to exactly one coil.

## Planted root causes

Six causes, one per 6M category. Windows are fractions of the horizon, so they scale with
`--days`. Each cause raises the rate of its target defect class and most also move a
process parameter. The effect strength (the *intensity*, 0 to 1) follows a shape:
`ramp` grows through the window (wear and drift), `plateau` rises, holds and falls
(weather), `step` is constant.

| Category    | Cause (`key`)          | Line, equipment | Window      | Defect class      | Defect rate boost | Reading effect                                              |
| ----------- | ---------------------- | --------------- | ----------- | ----------------- | ----------------- | ----------------------------------------------------------- |
| machine     | `descaler_nozzle_wear` | HSM-1, DSC      | 0.15–0.32   | rolled-in_scale   | +26 % · ramp      | descaler pressure −13 % · ramp                              |
| material    | `contaminated_lot`     | HSM-2           | one lot     | inclusion         | +42 %, lot only   | none; the lot's certificate shows high oxygen and sulphur   |
| method      | `work_roll_overrun`    | HSM-2, F3       | 0.70–0.88   | scratches         | +24 % · ramp      | F3 roll force +10 % · ramp; no F3 roll change in the window |
| man         | `crew_skipped_step`    | HSM-1, LCT      | 0.50–0.70   | patches           | +40 %, crew C only | coiling temperature −14 °C on crew C coils                 |
| measurement | `thermocouple_drift`   | HSM-2, FUR      | 0.06–0.22   | crazing           | +22 % · ramp      | furnace reading unchanged; RM +31.5, F1 +28, F6 +19, LCT +10 °C · ramp |
| environment | `cooling_water_heat`   | HSM-1, LCT      | 0.80–0.94   | pitted_surface    | +20 % · plateau   | coolant flow +10 %, coiling temperature +16 °C · plateau    |

Notes on the less obvious ones:

- **Material.** The simulator picks the Ostravel lot on HSM-2 whose first coil is closest to
  36 % of the horizon. The window runs from that lot's first coil to its last. Other lots of
  the same supplier are clean, so the supplier itself is not the answer.
- **Method.** Revision 3 of `WI-HSM2-RC-007` (effective at 62 % of the horizon) extends the
  F1–F4 work-roll change interval on HSM-2 from 4 to 7 days. Revision 2 stays in `kb` with
  `effective_to` set to the day revision 3 took effect. The planned F3 roll changes inside
  the window are missing from the maintenance log.
- **Man.** `WI-HSM-014` step 4 (top-spray purge and edge-mask check) is the skipped step.
- **Measurement.** The furnace controller holds its own (drifting) reading on target, so the
  furnace temperature looks normal. The evidence is downstream: every pyrometer after the
  furnace reads hotter. `SOP-MNT-002` describes exactly this cross-check.

`eval.injections.params` stores the key, defect class, shape, boosts, reading effects and,
where relevant, the crew, supplier and lot id.

### Incidents

Each injection produces `incidents_per_injection` (default 2) incidents. The simulator
groups the window's coils by shift and picks the shifts with the most coils carrying the
target defect, at least a day apart (eight hours if the window is short), ignoring the first
quarter of a ramp or plateau. The incident is
reported shortly after the shift ends, written as a shift report (line, shift, crew, coils
rolled, coils affected, highest severity, coils on hold, grades, defect positions). The
counts in the text match the data. Every fourth incident is in German.

The text names symptoms only. `causes.leaked_keywords` lists every cause's keywords
(equipment, mechanism, supplier names, "temperature", "water" and so on) plus generic words
such as "cause" and "Ursache"; the tests fail if any incident contains one.

### Red herrings

- **Coincidental maintenance:** one unplanned repair on a different piece of equipment of the
  same line, between a day before and half a day after each window starts.
- **Noise bursts:** six 6–12 hour clusters of a random defect class (+15 % rate) at random
  times, at least a day away from any window on that line. They produce no incident.
- **Background:** base defect rates for every class everywhere, slow drift on every sensor,
  unplanned repairs at random, and routine descaler checks every 21 days that report nothing
  unusual, even when one falls inside the wear window.

### Detection thresholds

The unit tests check, for a 60-day run, that each window holds at least 100 coils and that,
against the same line outside the window:

- the share of coils with the target defect is at least **2×** higher and at least
  **4 percentage points** higher;
- each reading effect (except the crew-only one) moves the window mean by at least **one
  third** of its configured peak, in the configured direction.

## Documents

Markdown files under `data/generated/docs/` (configurable with `GENERATED_DOCS_DIR`), one
`kb.documents` row each. `source_path` is relative to that directory and `sha256` is the
hash of the file, so rerunning upserts by hash. `effective_to` is exclusive.

| Type                   | Folder               | Content                                                                    |
| ---------------------- | -------------------- | -------------------------------------------------------------------------- |
| `work_instruction`     | `work_instructions/` | Work-roll change rev 2 (superseded) and rev 3, laminar-cooling start-up, descaler shift check (de), cooling-water summer operation |
| `sop`                  | `sops/`              | Surface inspection alarms, coil hold and release (de), temperature calibration, shift handover |
| `maintenance_manual`   | `maintenance_manual/`| Descaler, finishing rolls, furnace temperature measurement (de), laminar cooling, coiler |
| `material_certificate` | `certificates/`      | One EN 10204 3.1 certificate per lot; German for the German supplier       |
| `8d_report`            | `8d_reports/`        | Four closed 8Ds for older, unrelated problems (one in German)              |

## Evaluation ground truth

- `eval.root_causes`: one row per cause (category, mechanism, target defect class).
- `eval.injections`: line, optional equipment, window and `params` for each cause.
- `eval.questions`, kind `rca`: one per incident, with `gold_cause_id`.
- `eval.questions`, kind `sql`: ten questions (counts, top-N with tie rules, a daily mean)
  whose `gold_answer` is computed from the generated data. An integration test runs a
  reference query for each one against the database and compares.

Retrieval questions need chunk ids and come with Phase 3.

## Size

Process readings dominate: `2 lines × days × coils_per_day × 23 sensors × samples_per_coil`
rows at about 245 bytes each including the two indexes.

| Setting                         | Readings | Measured size of `plant` + `kb` + `eval` |
| ------------------------------- | -------- | ---------------------------------------- |
| Default (90 days, 40 coils, 3)  | 496,800  | 130 MB (readings 121 MB)                 |
| `--samples-per-coil 2`          | 331,200  | about 90 MB (estimate)                   |
| `--days 60 --coils-per-day 20`  | 165,600  | about 45 MB (estimate)                   |

The default stays under the 150 MB target for Neon Free (0.5 GB per project). Generating
the default dataset takes about 6 s; loading it into a local Postgres takes about 30 s.
