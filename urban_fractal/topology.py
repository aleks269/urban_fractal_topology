from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable

import numpy as np
import pandas as pd
from scipy import ndimage as ndi


@dataclass
class TopologySummary:
    rc_m: float | None
    giant_threshold: float
    beta0_at_zero: int
    beta1_at_zero: int
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

    def to_dict(self) -> dict:
        return asdict(self)


def disk_structure(radius_px: int) -> np.ndarray:
    """Return a circular 2D structuring element with integer pixel radius."""
    r = int(radius_px)
    if r <= 0:
        return np.ones((1, 1), dtype=bool)
    y, x = np.ogrid[-r : r + 1, -r : r + 1]
    return (x * x + y * y) <= r * r


def default_radii_px(
    mask_shape: tuple[int, int],
    *,
    max_radius_fraction: float = 0.05,
    n_radii: int = 18,
) -> list[int]:
    """Generate approximately logarithmic radii for dilation profiles."""
    side = int(min(mask_shape))
    max_r = max(1, int(side * max_radius_fraction))
    if max_r <= 1:
        return [0, 1]
    vals = np.unique(np.round(np.geomspace(1, max_r, num=max(2, n_radii))).astype(int))
    radii = [0] + [int(v) for v in vals if v > 0]
    return sorted(set(radii))


def lattice_perimeter(mask: np.ndarray, pixel_size_m: float = 1.0) -> float:
    """Estimate perimeter by counting foreground/background grid-edge transitions.

    This is a conservative lattice perimeter, not a Crofton perimeter. It is fast,
    reproducible and adequate for comparing profiles when pixel size is fixed.
    """
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError("lattice_perimeter expects a 2D mask")
    padded = np.pad(m, 1, mode="constant", constant_values=False)
    vertical = np.count_nonzero(padded[:, 1:] != padded[:, :-1])
    horizontal = np.count_nonzero(padded[1:, :] != padded[:-1, :])
    return float((vertical + horizontal) * pixel_size_m)


def betti_numbers_2d(mask: np.ndarray, *, connectivity: int = 1) -> tuple[int, int, int, int]:
    """Return beta0, beta1, Euler characteristic and largest component size.

    beta0 is the number of foreground connected components.
    beta1 is the number of background components not touching the raster border.
    connectivity=1 means 4-neighbour connectivity; connectivity=2 means 8-neighbour.
    """
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError("betti_numbers_2d expects a 2D mask")
    if m.size == 0 or not np.any(m):
        return 0, 0, 0, 0

    structure = ndi.generate_binary_structure(2, int(connectivity))
    labels, beta0 = ndi.label(m, structure=structure)
    if beta0 > 0:
        counts = np.bincount(labels.ravel())
        largest = int(counts[1:].max()) if counts.size > 1 else 0
    else:
        largest = 0

    bg = ~m
    bg_labels, n_bg = ndi.label(bg, structure=structure)
    if n_bg == 0:
        beta1 = 0
    else:
        border_labels = np.unique(
            np.concatenate([
                bg_labels[0, :], bg_labels[-1, :], bg_labels[:, 0], bg_labels[:, -1]
            ])
        )
        border_labels = set(int(x) for x in border_labels if int(x) != 0)
        holes = [lab for lab in range(1, n_bg + 1) if lab not in border_labels]
        beta1 = len(holes)
    chi = int(beta0 - beta1)
    return int(beta0), int(beta1), chi, largest


def minkowski_betti_profile_2d(
    mask: np.ndarray,
    radii_px: Iterable[int],
    *,
    pixel_size_m: float,
    connectivity: int = 1,
    giant_threshold: float = 0.5,
) -> tuple[pd.DataFrame, TopologySummary]:
    """Compute multiscale Minkowski and Betti profiles under disk dilation.

    For each radius r, X_r = X \\oplus B_r. The function returns area A(r),
    lattice perimeter P(r), beta0(r), beta1(r), chi(r) and largest-component
    fraction G(r).
    """
    m0 = np.asarray(mask, dtype=bool)
    if m0.ndim != 2:
        raise ValueError("minkowski_betti_profile_2d expects a 2D mask")
    if not np.any(m0):
        raise ValueError("Mask has no foreground pixels")
    radii = sorted(set(int(r) for r in radii_px if int(r) >= 0))
    if not radii:
        raise ValueError("At least one non-negative radius is required")

    rows = []
    for r in radii:
        if r == 0:
            mr = m0.copy()
        else:
            mr = ndi.binary_dilation(m0, structure=disk_structure(r))
        area_px = int(np.count_nonzero(mr))
        area_m2 = float(area_px * pixel_size_m * pixel_size_m)
        perimeter_m = lattice_perimeter(mr, pixel_size_m)
        beta0, beta1, chi, largest = betti_numbers_2d(mr, connectivity=connectivity)
        giant_fraction = float(largest / area_px) if area_px > 0 else np.nan
        rows.append({
            "radius_px": int(r),
            "radius_m": float(r * pixel_size_m),
            "area_px": area_px,
            "area_m2": area_m2,
            "perimeter_m": perimeter_m,
            "beta0": int(beta0),
            "beta1": int(beta1),
            "chi": int(chi),
            "largest_component_px": int(largest),
            "giant_fraction": giant_fraction,
        })
    df = pd.DataFrame(rows)
    summary = summarize_topology_profile(df, giant_threshold=giant_threshold)
    return df, summary


def _first_radius_where(df: pd.DataFrame, col: str, predicate) -> float | None:
    sub = df[predicate(df[col])]
    if sub.empty:
        return None
    return float(sub.iloc[0]["radius_m"])


def _first_zero_crossing(df: pd.DataFrame) -> float | None:
    radii = df["radius_m"].to_numpy(dtype=float)
    chi = df["chi"].to_numpy(dtype=float)
    if np.any(chi == 0):
        return float(radii[np.where(chi == 0)[0][0]])
    for i in range(1, len(chi)):
        if chi[i - 1] == 0 or chi[i] == 0 or np.sign(chi[i - 1]) != np.sign(chi[i]):
            # Linear interpolation in radius for a rough crossing location.
            if chi[i] == chi[i - 1]:
                return float(radii[i])
            t = -chi[i - 1] / (chi[i] - chi[i - 1])
            return float(radii[i - 1] + t * (radii[i] - radii[i - 1]))
    return None


def _integral_over_log_radius(df: pd.DataFrame, col: str) -> float:
    radii = df["radius_m"].to_numpy(dtype=float)
    vals = df[col].to_numpy(dtype=float)
    valid = np.isfinite(radii) & np.isfinite(vals) & (radii > 0)
    if np.count_nonzero(valid) < 2:
        return float("nan")
    x = np.log(radii[valid])
    y = vals[valid]
    return float(np.trapezoid(y, x))


def summarize_topology_profile(df: pd.DataFrame, *, giant_threshold: float = 0.5) -> TopologySummary:
    if df.empty:
        raise ValueError("Cannot summarize empty topology profile")
    rc = _first_radius_where(df, "giant_fraction", lambda s: s >= giant_threshold)
    beta1_peak_radius = None
    if "beta1" in df and not df["beta1"].isna().all():
        beta1_peak_radius = float(df.loc[df["beta1"].idxmax(), "radius_m"])
    return TopologySummary(
        rc_m=rc,
        giant_threshold=float(giant_threshold),
        beta0_at_zero=int(df.iloc[0]["beta0"]),
        beta1_at_zero=int(df.iloc[0]["beta1"]),
        beta0_min=int(df["beta0"].min()),
        beta0_max=int(df["beta0"].max()),
        beta1_min=int(df["beta1"].min()),
        beta1_max=int(df["beta1"].max()),
        beta1_peak_radius_m=beta1_peak_radius,
        chi_min=int(df["chi"].min()),
        chi_max=int(df["chi"].max()),
        chi_zero_crossing_radius_m=_first_zero_crossing(df),
        archipelago_index=_integral_over_log_radius(df, "beta0"),
        void_index=_integral_over_log_radius(df, "beta1"),
        boundary_complexity_index=_integral_over_log_radius(df, "perimeter_m"),
    )
