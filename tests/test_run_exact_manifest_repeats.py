import json

import pytest

from run_exact_manifest_repeats import (
    load_prior_rows,
    sha256_file,
    summarize,
    variation,
    wheel_run_complete,
)


def test_variation_reports_cv_and_range():
    result = variation([1.0, 1.1, 0.9])
    assert abs(result["mean"] - 1.0) < 1e-12
    assert abs(result["range"] - 0.2) < 1e-12
    assert abs(result["coefficient_of_variation"] - 0.1) < 1e-12


def test_summary_rejects_unstable_complete_probe(tmp_path):
    manifest = tmp_path / "case.json"
    manifest.write_text("{}\n")
    rows = [
        {
            "completed": True,
            "torque_nm": torque,
            "column_strain_proxy": strain,
        }
        for torque, strain in ((1.0, 0.01), (1.8, 0.08), (0.9, 0.02))
    ]

    result = summarize(manifest, tmp_path, rows, 3, 0.15, 0.03)

    assert result["status"] == "REJECT_QUALITY_GATE"
    assert not result["quality_gate"]["torque_cv"]["pass"]
    assert not result["quality_gate"]["column_strain_range"]["pass"]


def test_summary_allows_bounded_replacement_attempts(tmp_path):
    manifest = tmp_path / "case.json"
    manifest.write_text("{}\n")
    rows = [
        {"completed": False},
        {"completed": True, "torque_nm": 1.0, "column_strain_proxy": 0.10},
        {"completed": True, "torque_nm": 1.02, "column_strain_proxy": 0.11},
        {"completed": True, "torque_nm": 0.98, "column_strain_proxy": 0.09},
    ]

    result = summarize(manifest, tmp_path, rows, 3, 0.15, 0.03, max_attempts=6)

    assert result["status"] == "PASS_PROVISIONAL"
    assert result["completed_repeats"] == 3
    assert result["attempts_allowed"] == 6
    assert result["attempts_recorded"] == 4


def test_prior_failed_attempt_is_preserved_for_next_launch(tmp_path):
    manifest = tmp_path / "case.json"
    manifest.write_text("{}\n")
    summary = tmp_path / "exact-repeat-summary.json"
    summary.write_text(
        json.dumps(
            {
                "manifest_sha256": sha256_file(manifest),
                "repeats": [
                    {"attempt": 1, "repeat": 1, "completed": False},
                    {"attempt": 2, "repeat": 2, "completed": True},
                ],
            }
        )
    )

    rows = load_prior_rows(summary, manifest)

    assert [row["attempt"] for row in rows] == [1, 2]
    assert max(row["attempt"] for row in rows) + 1 == 3


def test_prior_summary_must_match_manifest_hash(tmp_path):
    manifest = tmp_path / "case.json"
    manifest.write_text("{}\n")
    summary = tmp_path / "exact-repeat-summary.json"
    summary.write_text(json.dumps({"manifest_sha256": "wrong", "repeats": []}))

    with pytest.raises(RuntimeError, match="manifest hash mismatch"):
        load_prior_rows(summary, manifest)


def test_wheel_run_complete_counts_expected_final_states(tmp_path):
    case = tmp_path / "case"
    final = case / "wheel" / "slip" / "pass" / "settled data"
    final.mkdir(parents=True)
    (final / "state.csv").write_text("done")

    assert wheel_run_complete(
        case, {"test": {"slip_ratios": [0.1], "passes": 1}}
    )
