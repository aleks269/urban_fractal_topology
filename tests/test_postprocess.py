import numpy as np
import pandas as pd

from report_tools.postprocess_200_25m import (
    benjamini_hochberg,
    harmonize_topology_profiles,
    silhouette_for_labels,
    standardize_frame,
)


def test_benjamini_hochberg_is_monotone_in_sorted_order():
    p = pd.Series([0.01, 0.04, 0.03, 0.20])
    q = benjamini_hochberg(p)
    order = p.sort_values().index
    values = q.loc[order].to_numpy()
    assert np.all(np.diff(values) >= -1e-12)
    assert np.all((values >= 0) & (values <= 1))


def test_standardize_frame_drops_constant_feature():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [7.0, 7.0, 7.0]})
    x, quality = standardize_frame(df, ["a", "b"])
    assert list(x.columns) == ["a"]
    assert quality.set_index("feature").loc["b", "status"] == "drop_zero_variance"


def test_silhouette_separated_clusters_is_positive():
    arr = np.array([[0.0, 0.0], [0.1, 0.0], [5.0, 5.0], [5.1, 5.0]])
    labels = np.array([1, 1, 2, 2])
    assert silhouette_for_labels(arr, labels) > 0.9

from report_tools.postprocess_200_25m import remove_redundant_features


def test_redundancy_filter_drops_near_duplicate_feature():
    x = pd.DataFrame({
        "a": np.arange(20, dtype=float),
        "b": np.arange(20, dtype=float) * 2.0,
        "c": np.array([0, 1] * 10, dtype=float),
    })
    reduced, table = remove_redundant_features(x, threshold=0.9)
    assert "a" in reduced.columns
    assert "b" not in reduced.columns
    assert table.set_index("feature").loc["b", "status"] == "drop_redundant"


def test_harmonize_topology_profiles_uses_common_relative_interval(tmp_path):
    rows = []
    for i, (area, radii) in enumerate([(10000.0, [0, 10, 20, 40]), (40000.0, [0, 20, 40, 80])]):
        result_dir = tmp_path / f"city_{i}"
        result_dir.mkdir()
        # Both cities have identical profiles as functions of rho=r/sqrt(area).
        pd.DataFrame({
            "radius_m": radii,
            "beta0": [10, 8, 6, 4],
            "beta1": [0, 1, 2, 1],
            "perimeter_m": np.sqrt(area) * np.array([2.0, 1.8, 1.5, 1.2]),
        }).to_csv(result_dir / "topology_minkowski_betti_profile.csv", index=False)
        rows.append({"plan_area_m2": area, "result_dir": str(result_dir)})
    frame = pd.DataFrame(rows)
    harmonized, meta = harmonize_topology_profiles(frame)
    assert meta["status"] == "ok"
    assert np.isclose(meta["rho_min"], 0.1)
    assert np.isclose(meta["rho_max"], 0.4)
    for col in ["archipelago_index_harmonized", "void_index_harmonized", "boundary_complexity_harmonized"]:
        assert np.isclose(harmonized.loc[0, col], harmonized.loc[1, col])
