from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import ndimage as ndi
from skimage.measure import perimeter_crofton


@dataclass
class TopologySummary:
    giant_component_radius_m: float | None
    giant_threshold: float
    # Legacy/full-domain bounding-box spanning fields.
    spanning_radius_lr_m: float | None
    spanning_radius_tb_m: float | None
    spanning_radius_any_m: float | None
    # Main connected component of the analysis domain.
    spanning_radius_lr_main_component_m: float | None
    spanning_radius_tb_main_component_m: float | None
    spanning_radius_any_main_component_m: float | None
    # Recommended interpretation: bbox for a connected domain, main component
    # for a disconnected domain.
    spanning_radius_lr_recommended_m: float | None
    spanning_radius_tb_recommended_m: float | None
    spanning_radius_any_recommended_m: float | None
    spanning_reference_recommended: str
    full_domain_spanning_interpretable: bool
    domain_component_count: int
    largest_domain_component_fraction: float
    beta0_at_zero: int
    beta1_at_zero: int
    beta0_lr_at_zero: int
    beta0_tb_at_zero: int
    beta0_lr_main_component_at_zero: int
    beta0_tb_main_component_at_zero: int
    beta0_min: int
    beta0_max: int
    beta1_min: int
    beta1_max: int
    beta1_peak_radius_m: float | None
    chi_min: int
    chi_max: int
    chi_zero_crossing_radius_m: float | None
    # Raw integrals are retained for backward compatibility.
    archipelago_index: float
    void_index: float
    boundary_complexity_index: float
    # Dimensionless/size-reduced descriptors. They are comparable only when
    # cities use the same radius interval or a separately harmonized interval.
    n_components: int
    characteristic_length_m: float
    log_radius_span: float
    topology_radius_min_positive_m: float
    topology_radius_max_m: float
    archipelago_index_mean: float
    void_index_mean: float
    boundary_complexity_index_mean: float
    archipelago_index_per_component: float
    void_index_per_component: float
    boundary_index_per_characteristic_length: float
    normalized_indices_radius_interval_comparable: bool
    foreground_connectivity: int
    background_connectivity: int

    @property
    def rc_m(self) -> float | None:
        """Deprecated alias for the giant-component radius, not percolation."""
        return self.giant_component_radius_m

    def to_dict(self) -> dict:
        return asdict(self)


def disk_structure(radius_px: int) -> np.ndarray:
    r = int(radius_px)
    if r <= 0:
        return np.ones((1, 1), dtype=bool)
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    return (x * x + y * y) <= r * r


def default_radii_px(
    mask_shape: tuple[int, int],
    *,
    max_radius_fraction: float = 0.25,
    n_radii: int = 18,
) -> list[int]:
    side = int(min(mask_shape))
    max_r = max(1, int(side * max_radius_fraction))
    if max_r <= 1:
        return [0, 1]
    vals = np.unique(np.round(np.geomspace(1, max_r, num=max(2, n_radii))).astype(int))
    return [0] + [int(v) for v in vals if v > 0]


def dual_connectivity(foreground_connectivity: int) -> int:
    if foreground_connectivity == 1:
        return 2
    if foreground_connectivity == 2:
        return 1
    raise ValueError("connectivity must be 1 (4-neighbour) or 2 (8-neighbour)")


def crofton_perimeter(mask: np.ndarray, pixel_size_m: float = 1.0) -> float:
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError("crofton_perimeter expects a 2D mask")
    return float(perimeter_crofton(m, directions=4) * pixel_size_m)


def _largest_component(mask: np.ndarray, connectivity: int = 1) -> tuple[np.ndarray, int, float]:
    m = np.asarray(mask, dtype=bool)
    labels, n = ndi.label(m, structure=ndi.generate_binary_structure(2, connectivity))
    if n <= 1:
        return m.copy(), int(n), 1.0
    counts = np.bincount(labels.ravel())
    counts[0] = 0
    label = int(counts.argmax())
    largest = labels == label
    fraction = float(largest.sum() / m.sum()) if m.any() else float("nan")
    return largest, int(n), fraction


def domain_side_masks(
    domain_mask: np.ndarray,
    band_width_px: int = 1,
    *,
    reference: str = "bbox",
) -> dict[str, np.ndarray]:
    """Return opposite boundary bands of an irregular raster domain.

    ``reference="bbox"`` uses the extrema of the complete domain. This is the
    legacy/full-domain definition and is interpretable as whole-domain spanning
    only when the domain is connected.

    ``reference="largest_component"`` uses the extrema of the largest connected
    domain component. This gives a core-city spanning descriptor that is robust
    to detached administrative exclaves. It does not describe connectivity of
    the complete disconnected municipality.
    """
    domain = np.asarray(domain_mask, dtype=bool)
    if domain.ndim != 2 or not domain.any():
        raise ValueError("domain_mask must be a non-empty 2D mask")
    if reference not in {"bbox", "largest_component"}:
        raise ValueError("reference must be 'bbox' or 'largest_component'")
    extent = domain if reference == "bbox" else _largest_component(domain, connectivity=1)[0]
    rows, cols = np.nonzero(extent)
    min_row, max_row = int(rows.min()), int(rows.max())
    min_col, max_col = int(cols.min()), int(cols.max())
    band = max(1, int(band_width_px))
    yy, xx = np.indices(domain.shape)
    return {
        "left": extent & (xx <= min_col + band - 1),
        "right": extent & (xx >= max_col - band + 1),
        "top": extent & (yy <= min_row + band - 1),
        "bottom": extent & (yy >= max_row - band + 1),
    }


def _domain_boundary(domain_mask: np.ndarray) -> np.ndarray:
    domain = np.asarray(domain_mask, dtype=bool)
    eroded = ndi.binary_erosion(domain, structure=ndi.generate_binary_structure(2, 1), border_value=0)
    return domain & ~eroded


def betti_numbers_2d(
    mask: np.ndarray,
    *,
    connectivity: int = 1,
    domain_mask: np.ndarray | None = None,
) -> tuple[int, int, int, int]:
    """Return beta0, beta1, Euler characteristic and largest component size.

    Foreground and background use a dual 4/8-connectivity pair. If an irregular
    domain is supplied, only background components not touching its boundary
    count as holes.
    """
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError("betti_numbers_2d expects a 2D mask")
    domain = np.ones_like(m, dtype=bool) if domain_mask is None else np.asarray(domain_mask, dtype=bool)
    if domain.shape != m.shape:
        raise ValueError("domain_mask shape must match mask")
    m = m & domain
    if m.size == 0 or not np.any(m):
        return 0, 0, 0, 0

    fg_structure = ndi.generate_binary_structure(2, int(connectivity))
    bg_structure = ndi.generate_binary_structure(2, dual_connectivity(int(connectivity)))
    labels, beta0 = ndi.label(m, structure=fg_structure)
    counts = np.bincount(labels.ravel())
    largest = int(counts[1:].max()) if counts.size > 1 else 0

    background = domain & ~m
    bg_labels, n_bg = ndi.label(background, structure=bg_structure)
    if n_bg == 0:
        beta1 = 0
    else:
        touching = set(int(x) for x in np.unique(bg_labels[_domain_boundary(domain)]) if int(x) != 0)
        beta1 = sum(1 for lab in range(1, n_bg + 1) if lab not in touching)
    chi = int(beta0 - beta1)
    return int(beta0), int(beta1), chi, largest


def spanning_component_counts(
    mask: np.ndarray,
    *,
    connectivity: int = 1,
    domain_mask: np.ndarray | None = None,
    reference: str = "bbox",
) -> tuple[int, int]:
    m = np.asarray(mask, dtype=bool)
    domain = np.ones_like(m, dtype=bool) if domain_mask is None else np.asarray(domain_mask, dtype=bool)
    m &= domain
    labels, _ = ndi.label(m, structure=ndi.generate_binary_structure(2, connectivity))
    sides = domain_side_masks(domain, reference=reference)

    def count(a: str, b: str) -> int:
        labels_a = set(int(x) for x in np.unique(labels[sides[a] & m]) if int(x) != 0)
        labels_b = set(int(x) for x in np.unique(labels[sides[b] & m]) if int(x) != 0)
        return len(labels_a.intersection(labels_b))

    return count("left", "right"), count("top", "bottom")


def minkowski_betti_profile_2d(
    mask: np.ndarray,
    radii_px: Iterable[int],
    *,
    pixel_size_m: float,
    connectivity: int = 1,
    giant_threshold: float = 0.5,
    domain_mask: np.ndarray | None = None,
) -> tuple[pd.DataFrame, TopologySummary]:
    """Compute domain-clipped Minkowski, Betti and dual spanning profiles."""
    m0 = np.asarray(mask, dtype=bool)
    domain = np.ones_like(m0, dtype=bool) if domain_mask is None else np.asarray(domain_mask, dtype=bool)
    if m0.ndim != 2 or domain.shape != m0.shape:
        raise ValueError("mask and domain_mask must be matching 2D arrays")
    m0 &= domain
    if not np.any(m0):
        raise ValueError("Mask has no foreground pixels inside the analysis domain")
    radii = sorted(set(int(r) for r in radii_px if int(r) >= 0))
    if not radii:
        raise ValueError("At least one non-negative radius is required")

    domain_main, domain_components, largest_domain_fraction = _largest_component(domain, connectivity=1)
    domain_area_m2 = float(np.count_nonzero(domain) * pixel_size_m**2)
    distance_to_foreground = ndi.distance_transform_edt(~m0)
    rows = []
    for r in radii:
        mr = m0.copy() if r == 0 else (distance_to_foreground <= float(r)) & domain
        area_px = int(np.count_nonzero(mr))
        beta0, beta1, chi, largest = betti_numbers_2d(mr, connectivity=connectivity, domain_mask=domain)
        lr_bbox, tb_bbox = spanning_component_counts(
            mr, connectivity=connectivity, domain_mask=domain, reference="bbox"
        )
        lr_main, tb_main = spanning_component_counts(
            mr, connectivity=connectivity, domain_mask=domain, reference="largest_component"
        )
        rows.append({
            "radius_px": int(r),
            "radius_m": float(r * pixel_size_m),
            "radius_relative_to_characteristic_length": float(r * pixel_size_m / np.sqrt(domain_area_m2)),
            "area_px": area_px,
            "area_m2": float(area_px * pixel_size_m**2),
            "perimeter_m": crofton_perimeter(mr, pixel_size_m),
            "beta0": int(beta0),
            "beta1": int(beta1),
            "chi": int(chi),
            "largest_component_px": int(largest),
            "giant_fraction": float(largest / area_px) if area_px > 0 else np.nan,
            # Legacy columns retain bbox semantics.
            "beta0_lr": int(lr_bbox),
            "beta0_tb": int(tb_bbox),
            "spans_lr": bool(lr_bbox > 0),
            "spans_tb": bool(tb_bbox > 0),
            # Explicit core-city columns.
            "beta0_lr_main_component": int(lr_main),
            "beta0_tb_main_component": int(tb_main),
            "spans_lr_main_component": bool(lr_main > 0),
            "spans_tb_main_component": bool(tb_main > 0),
        })
    df = pd.DataFrame(rows)
    n0 = max(1, int(df.iloc[0]["beta0"]))
    lc = float(np.sqrt(domain_area_m2))
    df["beta0_per_initial_component"] = df["beta0"] / n0
    df["beta1_per_initial_component"] = df["beta1"] / n0
    df["perimeter_per_characteristic_length"] = df["perimeter_m"] / lc
    return df, summarize_topology_profile(
        df,
        giant_threshold=giant_threshold,
        connectivity=connectivity,
        domain_area_m2=domain_area_m2,
        domain_component_count=domain_components,
        largest_domain_component_fraction=largest_domain_fraction,
    )


def _first_radius_where(df: pd.DataFrame, col: str, predicate) -> float | None:
    sub = df[predicate(df[col])]
    return None if sub.empty else float(sub.iloc[0]["radius_m"])


def _first_zero_crossing(df: pd.DataFrame) -> float | None:
    radii = df["radius_m"].to_numpy(dtype=float)
    chi = df["chi"].to_numpy(dtype=float)
    if np.any(chi == 0):
        return float(radii[np.where(chi == 0)[0][0]])
    for i in range(1, len(chi)):
        if np.sign(chi[i - 1]) != np.sign(chi[i]):
            t = -chi[i - 1] / (chi[i] - chi[i - 1])
            return float(radii[i - 1] + t * (radii[i] - radii[i - 1]))
    return None


def _integral_over_log_radius(df: pd.DataFrame, col: str) -> float:
    radii = df["radius_m"].to_numpy(dtype=float)
    vals = df[col].to_numpy(dtype=float)
    valid = np.isfinite(radii) & np.isfinite(vals) & (radii > 0)
    if np.count_nonzero(valid) < 2:
        return float("nan")
    try:
        trapezoid = np.trapezoid
    except AttributeError:
        trapezoid = np.trapz
    return float(trapezoid(vals[valid], np.log(radii[valid])))


def summarize_topology_profile(
    df: pd.DataFrame,
    *,
    giant_threshold: float = 0.5,
    connectivity: int = 1,
    domain_area_m2: float | None = None,
    domain_component_count: int = 1,
    largest_domain_component_fraction: float = 1.0,
) -> TopologySummary:
    if df.empty:
        raise ValueError("Cannot summarize empty topology profile")
    giant = _first_radius_where(df, "giant_fraction", lambda s: s >= giant_threshold)
    lr_bbox = _first_radius_where(df, "spans_lr", lambda s: s.astype(bool))
    tb_bbox = _first_radius_where(df, "spans_tb", lambda s: s.astype(bool))
    lr_main = _first_radius_where(df, "spans_lr_main_component", lambda s: s.astype(bool))
    tb_main = _first_radius_where(df, "spans_tb_main_component", lambda s: s.astype(bool))

    def first_any(a: float | None, b: float | None) -> float | None:
        vals = [x for x in (a, b) if x is not None]
        return min(vals) if vals else None

    use_main = int(domain_component_count) > 1
    lr_rec, tb_rec = (lr_main, tb_main) if use_main else (lr_bbox, tb_bbox)
    peak = float(df.loc[df["beta1"].idxmax(), "radius_m"]) if not df["beta1"].isna().all() else None

    arch_raw = _integral_over_log_radius(df, "beta0")
    void_raw = _integral_over_log_radius(df, "beta1")
    bdry_raw = _integral_over_log_radius(df, "perimeter_m")
    radii = df["radius_m"].to_numpy(dtype=float)
    positive = radii[np.isfinite(radii) & (radii > 0)]
    rmin = float(positive.min()) if positive.size else float("nan")
    rmax = float(positive.max()) if positive.size else float("nan")
    log_span = float(np.log(rmax / rmin)) if positive.size >= 2 and rmax > rmin > 0 else float("nan")
    n_components = int(df.iloc[0]["beta0"])
    char_length = float(np.sqrt(domain_area_m2)) if domain_area_m2 and domain_area_m2 > 0 else float("nan")

    def safe_div(a: float, b: float) -> float:
        return float(a / b) if np.isfinite(a) and np.isfinite(b) and b != 0 else float("nan")

    arch_mean = safe_div(arch_raw, log_span)
    void_mean = safe_div(void_raw, log_span)
    bdry_mean = safe_div(bdry_raw, log_span)

    return TopologySummary(
        giant_component_radius_m=giant,
        giant_threshold=float(giant_threshold),
        spanning_radius_lr_m=lr_bbox,
        spanning_radius_tb_m=tb_bbox,
        spanning_radius_any_m=first_any(lr_bbox, tb_bbox),
        spanning_radius_lr_main_component_m=lr_main,
        spanning_radius_tb_main_component_m=tb_main,
        spanning_radius_any_main_component_m=first_any(lr_main, tb_main),
        spanning_radius_lr_recommended_m=lr_rec,
        spanning_radius_tb_recommended_m=tb_rec,
        spanning_radius_any_recommended_m=first_any(lr_rec, tb_rec),
        spanning_reference_recommended="largest_component" if use_main else "bbox",
        full_domain_spanning_interpretable=bool(not use_main),
        domain_component_count=int(domain_component_count),
        largest_domain_component_fraction=float(largest_domain_component_fraction),
        beta0_at_zero=int(df.iloc[0]["beta0"]),
        beta1_at_zero=int(df.iloc[0]["beta1"]),
        beta0_lr_at_zero=int(df.iloc[0]["beta0_lr"]),
        beta0_tb_at_zero=int(df.iloc[0]["beta0_tb"]),
        beta0_lr_main_component_at_zero=int(df.iloc[0]["beta0_lr_main_component"]),
        beta0_tb_main_component_at_zero=int(df.iloc[0]["beta0_tb_main_component"]),
        beta0_min=int(df["beta0"].min()),
        beta0_max=int(df["beta0"].max()),
        beta1_min=int(df["beta1"].min()),
        beta1_max=int(df["beta1"].max()),
        beta1_peak_radius_m=peak,
        chi_min=int(df["chi"].min()),
        chi_max=int(df["chi"].max()),
        chi_zero_crossing_radius_m=_first_zero_crossing(df),
        archipelago_index=arch_raw,
        void_index=void_raw,
        boundary_complexity_index=bdry_raw,
        n_components=n_components,
        characteristic_length_m=char_length,
        log_radius_span=log_span,
        topology_radius_min_positive_m=rmin,
        topology_radius_max_m=rmax,
        archipelago_index_mean=arch_mean,
        void_index_mean=void_mean,
        boundary_complexity_index_mean=bdry_mean,
        archipelago_index_per_component=safe_div(arch_mean, n_components),
        void_index_per_component=safe_div(void_mean, n_components),
        boundary_index_per_characteristic_length=safe_div(bdry_mean, char_length),
        normalized_indices_radius_interval_comparable=False,
        foreground_connectivity=int(connectivity),
        background_connectivity=dual_connectivity(int(connectivity)),
    )
