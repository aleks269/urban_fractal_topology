import numpy as np
import pandas as pd

from report_tools.postprocess_200_25m import benjamini_hochberg, silhouette_for_labels, standardize_frame


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
