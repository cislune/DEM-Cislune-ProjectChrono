"""Apply explicit DEM solver execution settings from a case manifest."""

from __future__ import annotations

from typing import Any


def configure_solver_execution(solver: Any, config: Any) -> dict[str, Any]:
    use_cub = getattr(config, "SOLVER_USE_CUB_FORCE_COLLECTION_st", None)
    sort_contacts = getattr(config, "SOLVER_SORT_CONTACT_PAIRS_st", None)
    disable_adaptive_bin = bool(
        getattr(config, "SOLVER_DISABLE_ADAPTIVE_BIN_SIZE_st", False)
    )
    cd_update_frequency = getattr(config, "SOLVER_CD_UPDATE_FREQUENCY_st", None)
    disable_adaptive_update = bool(
        getattr(config, "SOLVER_DISABLE_ADAPTIVE_UPDATE_FREQUENCY_st", False)
    )

    if use_cub is not None:
        solver.UseCubForceCollection(bool(use_cub))
    if sort_contacts is not None:
        solver.SetSortContactPairs(bool(sort_contacts))
    if disable_adaptive_bin:
        solver.DisableAdaptiveBinSize()
    if cd_update_frequency is not None:
        solver.SetCDUpdateFreq(int(cd_update_frequency))
    if disable_adaptive_update:
        solver.DisableAdaptiveUpdateFreq()
    return {
        "use_cub_force_collection": (
            bool(use_cub) if use_cub is not None else None
        ),
        "sort_contact_pairs": (
            bool(sort_contacts) if sort_contacts is not None else None
        ),
        "disable_adaptive_bin_size": disable_adaptive_bin,
        "cd_update_frequency": cd_update_frequency,
        "disable_adaptive_update_frequency": disable_adaptive_update,
    }
