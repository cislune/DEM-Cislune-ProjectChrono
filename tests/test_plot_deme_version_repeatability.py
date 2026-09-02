import json

from plot_deme_version_repeatability import collect


def test_collect_returns_only_completed_repeat_metrics(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text(
        json.dumps(
            {
                "status": "REJECT_QUALITY_GATE",
                "completed_repeats": 2,
                "repeats": [
                    {
                        "completed": True,
                        "torque_nm": 0.4,
                        "column_strain_proxy": 0.1,
                    },
                    {
                        "completed": False,
                        "torque_nm": None,
                        "column_strain_proxy": None,
                    },
                    {
                        "completed": True,
                        "torque_nm": 0.6,
                        "column_strain_proxy": 0.11,
                    },
                ],
                "torque_nm": {"coefficient_of_variation": 0.2},
                "column_strain_proxy": {"range": 0.01},
            }
        )
    )

    result = collect(path, "patched")

    assert result["label"] == "patched"
    assert result["torques"] == [0.4, 0.6]
    assert result["strains"] == [0.1, 0.11]
    assert result["torque_cv"] == 0.2
    assert result["strain_range"] == 0.01
