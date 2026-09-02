from types import SimpleNamespace

from solver_execution import configure_solver_execution


class FakeSolver:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, args))

        return record


def test_configure_solver_execution_applies_deterministic_profile():
    solver = FakeSolver()
    config = SimpleNamespace(
        SOLVER_USE_CUB_FORCE_COLLECTION_st=True,
        SOLVER_SORT_CONTACT_PAIRS_st=True,
        SOLVER_DISABLE_ADAPTIVE_BIN_SIZE_st=True,
        SOLVER_CD_UPDATE_FREQUENCY_st=20,
        SOLVER_DISABLE_ADAPTIVE_UPDATE_FREQUENCY_st=True,
    )

    applied = configure_solver_execution(solver, config)

    assert solver.calls == [
        ("UseCubForceCollection", (True,)),
        ("SetSortContactPairs", (True,)),
        ("DisableAdaptiveBinSize", ()),
        ("SetCDUpdateFreq", (20,)),
        ("DisableAdaptiveUpdateFreq", ()),
    ]
    assert applied == {
        "use_cub_force_collection": True,
        "sort_contact_pairs": True,
        "disable_adaptive_bin_size": True,
        "cd_update_frequency": 20,
        "disable_adaptive_update_frequency": True,
    }


def test_configure_solver_execution_keeps_backward_compatible_defaults():
    solver = FakeSolver()

    applied = configure_solver_execution(solver, SimpleNamespace())

    assert solver.calls == []
    assert applied["use_cub_force_collection"] is None
    assert applied["sort_contact_pairs"] is None
