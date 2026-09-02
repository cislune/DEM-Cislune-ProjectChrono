from pathlib import Path


def test_version_probe_preserves_baseline_tag_and_isolates_output():
    script = Path("run_deme_version_probe.sh").read_text()

    assert "dem-simulation:deme-${DEME_VERSION}" in script
    assert "GRASP_DEM_IMAGE=\"$TARGET_IMAGE\"" in script
    assert 'PROFILE_ROOT="$OUTPUT_ROOT/deme-${DEME_VERSION}-cub"' in script
    assert "docker tag" not in script
