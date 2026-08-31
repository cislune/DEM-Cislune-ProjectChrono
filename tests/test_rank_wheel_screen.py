import json

from rank_wheel_screen import canonical_wheel_name, load_rows


def write_case(root, case_id, settlement_mm, strain_percent, torque):
    case = root / case_id
    case.mkdir()
    (case / "frozen_case.json").write_text(
        json.dumps({"wheel": {"feature_height_in_particle_radii": 1.0}})
    )
    (case / "wheel_performance.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "status": "PASS_COMPARATIVE_METRICS",
                "model_status": "test",
                "lane": {
                    "p95_surface_settlement_m": settlement_mm / 1000.0,
                    "column_strain_proxy": strain_percent / 100.0,
                },
                "mobility": {
                    "torque_y_nm": {"median": torque},
                    "median_abs_drawbar_over_normal_load": 0.1,
                },
                "reference_spin_gate": {"status": "PASS_REFERENCE_SPIN"},
            }
        )
    )


def test_canonical_name_handles_calibration_suffix():
    assert canonical_wheel_name("screen-smooth_control-coarse-cpt-informed") == "smooth_control"


def test_canonical_name_handles_shared_bed_suffix():
    assert (
        canonical_wheel_name("screen-smooth_control-coarse-cpt-informed-shared-bed")
        == "smooth_control"
    )


def test_positive_compaction_beats_dilation(tmp_path):
    write_case(tmp_path, "screen-smooth_control-coarse-cpt-informed", 1.0, 1.0, 1.0)
    write_case(tmp_path, "screen-compactor-coarse-cpt-informed", 3.0, 3.0, 1.1)
    write_case(tmp_path, "screen-dilator-coarse-cpt-informed", -2.0, -2.0, 0.8)
    rows = load_rows(tmp_path)
    assert rows[0]["wheel"] == "compactor"
    assert rows[-1]["wheel"] == "dilator"
