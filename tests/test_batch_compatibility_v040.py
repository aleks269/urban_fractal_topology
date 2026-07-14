from urban_fractal import __version__
from types import SimpleNamespace

from batch_tools.run_city_batch import result_is_compatible


def args(**overrides):
    base = dict(
        mode="final",
        pixel=25.0,
        resolution_sweep=[10.0, 20.0, 50.0],
        all_touched=False,
        min_scaling_points=6,
        scaling_min_m=50.0,
        scaling_max_m=3200.0,
        topology_max_radius_fraction=0.25,
        topology_n_radii=18,
        topology_connectivity=1,
        giant_threshold=0.5,
        transport_phases="open_space,buildings",
        transport_contrasts="1000",
        transport_max_active_cells=250000,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def summary():
    return {
        "software": {"version": __version__},
        "input": {
            "pixel_size_m": 25.0,
            "all_touched": False,
            "min_scaling_points": 6,
            "scaling_scale_min_m": 50.0,
            "scaling_scale_max_m": 3200.0,
            "topology_max_radius_fraction": 0.25,
            "topology_n_radii": 18,
            "topology_connectivity": 1,
            "giant_threshold": 0.5,
            "topology": True,
            "multifractal": True,
            "transport": True,
            "transport_phases": ["open_space", "buildings"],
            "transport_contrasts": [1000.0],
            "transport_max_active_cells": 250000,
        },
    }


def test_skip_existing_requires_full_method_match():
    assert result_is_compatible(summary(), args())
    assert not result_is_compatible(summary(), args(pixel=50.0))
    assert not result_is_compatible(summary(), args(transport_phases="open_space"))
    assert not result_is_compatible(summary(), args(topology_max_radius_fraction=0.05))
