from pathlib import Path


def test_version_probe_preserves_baseline_tag_and_isolates_output():
    script = Path("run_deme_version_probe.sh").read_text()

    assert "dem-simulation:deme-${DEME_LABEL}" in script
    assert "GRASP_DEM_IMAGE=\"$TARGET_IMAGE\"" in script
    assert 'PROFILE_ROOT="$OUTPUT_ROOT/deme-${DEME_LABEL}-cub"' in script
    assert "docker tag" not in script


def test_fix71_image_pins_source_and_patch_hashes():
    dockerfile = Path("docker/Dockerfile.deme-version").read_text()

    assert "6102c236b1d592932d8d4eb189895397211917f4961fffbaa62ba9e82c247e42" in dockerfile
    assert "a371f78063e30f4b5398beaf773edbac880aa14bd7d3d044f37bf16df083cdd3" in dockerfile
    assert "7fd2636c557832dfb299e7e31d6f0e072a3c0426" in dockerfile
    assert "--force-reinstall" in dockerfile
    assert "LD_LIBRARY_PATH=/root/miniconda3/envs/myenv/targets/x86_64-linux/lib" in dockerfile
    assert "import DEME, importlib.metadata" not in dockerfile
