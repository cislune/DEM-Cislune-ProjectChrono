# GRASP DEM Wheel Validation Toolchain

This repository turns wheel CAD exported as Wavefront OBJ into reproducible
Project Chrono DEM Engine (DEME) cases for wheel mobility and regolith-state
screening. The workflow freezes geometry, loading, kinematics, terrain
preparation, solver settings, and provenance before a run starts.

The toolchain is intended to support controlled comparison and calibration. A
successful software run is not, by itself, a validated prediction of physical
compaction. Absolute claims require calibrated material parameters and a held-out
physical test performed under the same test-card definition.

## Workflow

1. Export a watertight, triangulated OBJ and record its source units and axes.
2. Copy `examples/wheel_case.example.json` and replace the example values.
3. Run preflight. The runner normalizes the mesh to meters in a +X travel, +Y
   axle, +Z up frame; checks geometry and dimensions; freezes the manifest; and
   records file hashes and runtime provenance.
4. Run one settled terrain bed, then one or more wheel passes against that fixed
   realization.
5. Post-process sinkage, mobility demand, and terrain-state change.
6. Compare only cases that share the same controlled-test definition.

```bash
python dem_case_runner.py examples/wheel_case.example.json --stage preflight
python dem_case_runner.py examples/wheel_case.example.json --stage terrain
python dem_case_runner.py examples/wheel_case.example.json --stage wheel
python dem_case_runner.py examples/wheel_case.example.json --stage compaction
```

The simulation stages require the repository's PyDEME/CUDA environment. The
preflight, analysis, schema, and most unit tests do not require a GPU.

## Public Repository Boundary

This public repository contains reusable source, tests, schemas, and synthetic
examples. It intentionally excludes physical partner datasets, local Drive
paths, proprietary CAD, generated collision meshes, solver outputs, and
calibration results. Store those inputs in the controlled GRASP Drive and record
their SHA-256 hashes in each frozen case.

## Acceptance Ladder

- **Checkout:** mesh and software path execute without claiming physical accuracy.
- **Control repeatability:** at least three accepted repeats establish rig and
  measurement noise before candidate comparisons.
- **Calibration:** selected material parameters fit declared calibration
  measurements while the wheel/test definition is fixed.
- **Held-out validation:** frozen parameters predict physical cases that were not
  used for fitting.
- **Candidate comparison:** candidates share bed preparation, load, speed, slip
  definition, pass count, measurement locations, and acceptance gates.

Use `schemas/wheel_test_record.schema.json` as the common record for CRATR,
RIDER, geotechnical measurements, and DEM results. The project-level controlled
test card owns provisional thresholds and approval status.

## Numerical Repeatability Diagnostic

Before interpreting small differences between wheels, run the same wheel cases
three times against one byte-identical settled bed. The standard queue preserves
DEME defaults. The `repeatability-cub` queue uses CUB force reduction and sorted
contact pairs to test whether GPU accumulation order is a material source of
run-to-run spread.

```bash
python generate_wheel_repeatability_cases.py \
  --source-queue cases/frozen_candidate_screen_mu0p9_r8mm/frozen_candidate_screen_queue.json \
  --output-dir cases/wheel_repeatability_cub_r8mm \
  --bed-case-id wheel-shared-bed-r8mm-cpt-informed-process-dt5us-margin0p18 \
  --bed-state-sha256 f43125a9acd2e84d84633b794e8c3a25498fee1cd8c74b05ddd64476e108a7ff \
  --case-prefix repeatability-cub \
  --use-cub-force-collection
```

Evaluate standard and CUB outputs separately. Treat a lower spread as a numerical
stability result; it does not replace multi-bed or held-out physical validation.

## Tests

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

The repository does not include or install DEME. Full GPU integration tests must
run in the pinned Cislune DEME environment.
