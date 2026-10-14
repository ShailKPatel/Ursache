# ADR 0003: A simulated plant with planted root causes

- Status: accepted
- Date: 2026-10-14

## Context

Evaluating a root-cause assistant needs cases where the true cause is known, together with
the evidence a real investigation would have: process time series, maintenance history,
material lots and certificates, inspection results, defect images and procedures. No
public dataset links all of these for the same parts. Real plant data is confidential, and
it would rule out free hosted APIs.

## Decision

- **Simulate a hot-rolling mill**: lines, stands and equipment, coils, shifts and crews,
  supplier lots, sensor readings, maintenance, inspections and defects.
- **Plant root causes** as explicit injections. Each one has a cause from the 6M taxonomy,
  a mechanism, a target defect class, and an affected line or equipment over a time window,
  for example "descaler nozzle wear on F2 raises rolled-in scale". The simulator applies
  their effects to readings and defect rates. Every incident is generated from a known
  injection.
- Use **real defect images** from the public NEU-DET dataset (six hot-rolled strip defect
  classes) and sample them per defect class. The images are not redistributed; see
  `scripts/download_neu_det.sh`.
- **Isolate the ground truth** in the `eval` schema (`root_causes`, `injections`, gold
  `questions`). Only `ursache_eval` can read it. The agent role and the app role cannot.

## Alternatives considered

- **Public datasets only** (for example SECOM, NEU-DET, generic manuals). They cannot be
  joined, so there are no end-to-end cases and no RCA ground truth.
- **Hand-written case studies.** Realistic, but too few for meaningful metrics and too
  laborious to vary.
- **LLM-generated scenarios without a simulator.** Cheap, but the "truth" would not be
  enforced consistently across the time series, so evaluation would score fluency rather
  than diagnosis.

## Consequences

- Retrieval and RCA can be measured exactly: did the top hypotheses include the planted
  cause, and did the evidence cite the injected window?
- The plant is only as realistic as the simulator. Results measure reasoning over
  plausible data, not field performance, and the README says so.
- Images come from a different source than the simulated coils, so image–coil links are
  synthetic. Only visual similarity within a defect class is meaningful.
- Leaks of ground truth would make results invalid. Schema-level isolation and tests guard
  against this.
