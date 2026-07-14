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
    spanning_radius_lr_m: float | None
    spanning_radius_tb_m: float | None
    spanning_radius_any_m: float | None
    beta0_at_zero: int
    beta1_at_zero: int
    beta0_lr_at_zero: int
    beta0_tb_at_zero: int
    beta0_min: int
    beta0_max: int
    beta1_min: int
    beta1_max: int
    beta1_peak_radius_m: float | None
    chi_min: int
    chi_max: int
    chi_zero_crossing_radius_m: float | None
    archipelago_index: float
    void_index: float
    boundary_complexity_index: float
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


def domain_side_masks(domain_mask: np.ndarray, band_width_px: int = 1) -> dict[str, np.ndarray]:
    """Return global opposite boundary bands of an irregular domain.

    The sides are tied to the global raster extrema of the analysis domain.
    Interior islands therefore do not count as independently spanning from
    their own local left edge to their own local right edge.
    """
    domain = np.asarray(domain_mask, dtype=bool)
    if domain.ndim != 2 or not domain.any():
        raise ValueError("domain_mask must be a non-empty 2D mask")
    rows, cols = np.nonzero(domain)
    min_row, max_row = int(rows.min()), int(rows.max())
    min_col, max_col = int(cols.min()), int(cols.max())
    band = max(1, int(band_width_px))
    yy, xx = np.indices(domain.shape)
    return {
        "left": domain & (xx <= min_col + band - 1),
        "right": domain & (xx >= max_col - band + 1),
        "top": domain & (yy <= min_row + band - 1),
        "bottom": domain & (yy >= max_row - band + 1),
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
) -> tuple[int, int]:
    m = np.asarray(mask, dtype=bool)
    domain = np.ones_like(m, dtype=bool) if domain_mask is None else np.asarray(domain_mask, dtype=bool)
    m &= domain
    labels, _ = ndi.label(m, structure=ndi.generate_binary_structure(2, connectivity))
    sides = domain_side_masks(domain)

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
    """Compute domain-clipped Minkowski, Betti and spanning profiles."""
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

    distance_to_foreground = ndi.distance_transform_edt(~m0)
    rows = []
    for r in radii:
        mr = m0.copy() if r == 0 else (distance_to_foreground <= float(r)) & domain
        area_px = int(np.count_nonzero(mr))
        beta0, beta1, chi, largest = betti_numbers_2d(mr, connectivity=connectivity, domain_mask=domain)
        beta0_lr, beta0_tb = spanning_component_counts(mr, connectivity=connectivity, domain_mask=domain)
        rows.append({
            "radius_px": int(r),
            "radius_m": float(r * pixel_size_m),
            "area_px": area_px,
            "area_m2": float(area_px * pixel_size_m**2),
            "perimeter_m": crofton_perimeter(mr, pixel_size_m),
            "beta0": int(beta0),
            "beta1": int(beta1),
            "chi": int(chi),
            "largest_component_px": int(largest),
            "giant_fraction": float(largest / area_px) if area_px > 0 else np.nan,
            "beta0_lr": int(beta0_lr),
            "beta0_tb": int(beta0_tb),
            "spans_lr": bool(beta0_lr > 0),
            "spans_tb": bool(beta0_tb > 0),
        })
    df = pd.DataFrame(rows)
    return df, summarize_topology_profile(df, giant_threshold=giant_threshold, connectivity=connectivity)


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
    return float(np.trapezoid(vals[valid], np.log(radii[valid])))


def summarize_topology_profile(
    df: pd.DataFrame,
    *,
    giant_threshold: float = 0.5,
    connectivity: int = 1,
) -> TopologySummary:
    if df.empty:
        raise ValueError("Cannot summarize empty topology profile")
    giant = _first_radius_where(df, "giant_fraction", lambda s: s >= giant_threshold)
    lr = _first_radius_where(df, "spans_lr", lambda s: s.astype(bool))
    tb = _first_radius_where(df, "spans_tb", lambda s: s.astype(bool))
    any_values = [x for x in (lr, tb) if x is not None]
    peak = float(df.loc[df["beta1"].idxmax(), "radius_m"]) if not df["beta1"].isna().all() else None
    return TopologySummary(
        giant_component_radius_m=giant,
        giant_threshold=float(giant_threshold),
        spanning_radius_lr_m=lr,
        spanning_radius_tb_m=tb,
        spanning_radius_any_m=min(any_values) if any_values else None,
        beta0_at_zero=int(df.iloc[0]["beta0"]),
        beta1_at_zero=int(df.iloc[0]["beta1"]),
        beta0_lr_at_zero=int(df.iloc[0]["beta0_lr"]),
        beta0_tb_at_zero=int(df.iloc[0]["beta0_tb"]),
        beta0_min=int(df["beta0"].min()),
        beta0_max=int(df["beta0"].max()),
        beta1_min=int(df["beta1"].min()),
        beta1_max=int(df["beta1"].max()),
        beta1_peak_radius_m=peak,
        chi_min=int(df["chi"].min()),
        chi_max=int(df["chi"].max()),
        chi_zero_crossing_radius_m=_first_zero_crossing(df),
        archipelago_index=_integral_over_log_radius(df, "beta0"),
        void_index=_integral_over_log_radius(df, "beta1"),
        boundary_complexity_index=_integral_over_log_radius(df, "perimeter_m"),
        foreground_connectivity=int(connectivity),
        background_connectivity=dual_connectivity(int(connectivity)),
    )
