from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


@dataclass
class ScalingFit:
    dimension: float
    intercept: float
    r2: float
    stderr: float
    scale_min: float
    scale_max: float
    n_points: int
    method: str
    scale_span_decades: float
    grid_offset_std: float
    grid_offset_cv: float
    leave_one_out_std: float
    leave_one_out_cv: float
    count_cv_mean: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WindowFitCandidate:
    start: int
    stop: int
    slope: float
    intercept: float
    r2: float
    stderr: float
    score: float


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float]:
    if x.size < 2:
        raise ValueError("Need at least two points for linear fit")
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    A = np.vstack([x, np.ones_like(x)]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    y_hat = slope * x + intercept
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    if x.size > 2:
        s2 = ss_res / (x.size - 2)
        sxx = float(np.sum((x - np.mean(x)) ** 2))
        stderr = float(np.sqrt(s2 / sxx)) if sxx > 0 else float("nan")
    else:
        stderr = float("nan")
    return float(slope), float(intercept), float(r2), stderr


def find_best_scaling_window(
    scales: Sequence[float],
    counts: Sequence[float],
    *,
    min_points: int = 6,
    min_r2: float = 0.95,
) -> tuple[ScalingFit, pd.DataFrame]:
    """Diagnostic automatic windows; the main estimator uses a fixed range."""
    scales = np.asarray(scales, dtype=float)
    counts = np.asarray(counts, dtype=float)
    valid = np.isfinite(scales) & np.isfinite(counts) & (scales > 0) & (counts > 0)
    scales, counts = scales[valid], counts[valid]
    if scales.size < min_points:
        raise ValueError("Not enough valid scale/count pairs for scaling fit")
    x = np.log(1.0 / scales)
    y = np.log(counts)
    order = np.argsort(x)
    x, y, s_sorted = x[order], y[order], scales[order]
    candidates: list[WindowFitCandidate] = []
    n = x.size
    for i in range(0, n - min_points + 1):
        for j in range(i + min_points, n + 1):
            slope, intercept, r2, stderr = _linear_fit(x[i:j], y[i:j])
            span = float(np.ptp(x[i:j]))
            score = r2 + 0.01 * (j - i) + 0.01 * span
            if r2 < min_r2:
                score -= 0.5 * (min_r2 - r2)
            candidates.append(WindowFitCandidate(i, j, slope, intercept, r2, stderr, score))
    best = max(candidates, key=lambda c: c.score)
    scale_min = float(np.min(s_sorted[best.start:best.stop]))
    scale_max = float(np.max(s_sorted[best.start:best.stop]))
    fit = ScalingFit(
        dimension=best.slope,
        intercept=best.intercept,
        r2=best.r2,
        stderr=best.stderr,
        scale_min=scale_min,
        scale_max=scale_max,
        n_points=best.stop - best.start,
        method="diagnostic_auto_window",
        scale_span_decades=float(np.log10(scale_max / scale_min)),
        grid_offset_std=float("nan"),
        grid_offset_cv=float("nan"),
        leave_one_out_std=float("nan"),
        leave_one_out_cv=float("nan"),
        count_cv_mean=float("nan"),
    )
    return fit, pd.DataFrame([asdict(c) for c in candidates]).sort_values("score", ascending=False)


def _count_boxes_with_shift(mask: np.ndarray, box_size: int, shift_y: int, shift_x: int) -> int:
    m = np.asarray(mask, dtype=bool)
    h, w = m.shape
    top, left = int(shift_y), int(shift_x)
    h_total, w_total = h + top, w + left
    bottom = (-h_total) % box_size
    right = (-w_total) % box_size
    padded = np.pad(m, ((top, bottom), (left, right)), mode="constant", constant_values=False)
    blocks = padded.reshape(padded.shape[0] // box_size, box_size, padded.shape[1] // box_size, box_size)
    return int(blocks.any(axis=(1, 3)).sum())


def box_count_2d(mask: np.ndarray, box_sizes_px: Iterable[int]) -> pd.DataFrame:
    """Multi-origin box counts.

    Four grid origins (0/half-box shifts in x and y) are used at every scale.
    The mean count is the primary value; dispersion quantifies origin
    sensitivity.
    """
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2:
        raise ValueError("box_count_2d expects a 2D mask")
    rows = []
    for bs in sorted(set(int(x) for x in box_sizes_px if int(x) >= 1)):
        if bs > max(m.shape):
            continue
        shifts = sorted(set([0, bs // 2]))
        counts = [_count_boxes_with_shift(m, bs, sy, sx) for sy in shifts for sx in shifts]
        mean = float(np.mean(counts))
        std = float(np.std(counts, ddof=1)) if len(counts) > 1 else 0.0
        minimum = float(np.min(counts))
        row = {
            "box_size_px": bs,
            "count": minimum,
            "count_fit": minimum,
            "count_mean": mean,
            "count_min": minimum,
            "count_max": float(np.max(counts)),
            "count_std": std,
            "count_cv": std / mean if mean > 0 else np.nan,
            "n_grid_offsets": len(counts),
        }
        for i, value in enumerate(counts):
            row[f"count_offset_{i}"] = int(value)
        rows.append(row)
    if not rows:
        raise ValueError("No valid box sizes for 2D mask")
    return pd.DataFrame(rows)


def _fixed_range_fit(counts: pd.DataFrame, min_points: int) -> ScalingFit:
    x = np.log(1.0 / counts["scale_m"].to_numpy(dtype=float))
    y = np.log(counts["count_fit"].to_numpy(dtype=float))
    if len(x) < min_points:
        raise ValueError(f"Fixed scaling range has {len(x)} points; at least {min_points} required")
    slope, intercept, r2, stderr = _linear_fit(x, y)

    offset_slopes = []
    for col in [c for c in counts.columns if c.startswith("count_offset_")]:
        vals = counts[col].to_numpy(dtype=float)
        if np.all(vals > 0):
            offset_slopes.append(_linear_fit(x, np.log(vals))[0])
    offset_std = float(np.std(offset_slopes, ddof=1)) if len(offset_slopes) > 1 else 0.0

    loo = []
    if len(x) >= 4:
        for i in range(len(x)):
            keep = np.arange(len(x)) != i
            loo.append(_linear_fit(x[keep], y[keep])[0])
    loo_std = float(np.std(loo, ddof=1)) if len(loo) > 1 else 0.0
    smin = float(counts["scale_m"].min())
    smax = float(counts["scale_m"].max())
    return ScalingFit(
        dimension=slope,
        intercept=intercept,
        r2=r2,
        stderr=stderr,
        scale_min=smin,
        scale_max=smax,
        n_points=len(counts),
        method="box_counting_fixed_physical_range_multi_origin",
        scale_span_decades=float(np.log10(smax / smin)) if smax > smin else 0.0,
        grid_offset_std=offset_std,
        grid_offset_cv=offset_std / abs(slope) if abs(slope) > 1e-15 else float("nan"),
        leave_one_out_std=loo_std,
        leave_one_out_cv=loo_std / abs(slope) if abs(slope) > 1e-15 else float("nan"),
        count_cv_mean=float(counts["count_cv"].mean()),
    )


def box_count_dimension_2d(
    mask: np.ndarray,
    pixel_size_m: float,
    box_sizes_px: Iterable[int],
    *,
    min_points: int = 6,
    scale_min_m: float | None = None,
    scale_max_m: float | None = None,
) -> tuple[ScalingFit, pd.DataFrame, pd.DataFrame]:
    all_counts = box_count_2d(mask, box_sizes_px)
    all_counts["scale_m"] = all_counts["box_size_px"] * float(pixel_size_m)
    counts = all_counts.copy()
    if scale_min_m is not None:
        counts = counts[counts["scale_m"] >= float(scale_min_m)]
    if scale_max_m is not None:
        counts = counts[counts["scale_m"] <= float(scale_max_m)]
    counts = counts.sort_values("scale_m").reset_index(drop=True)
    used_fallback = False
    if len(counts) < min_points:
        counts = all_counts.sort_values("scale_m").reset_index(drop=True)
        used_fallback = True
    fit = _fixed_range_fit(counts, min_points=min_points)
    if used_fallback:
        fit.method = "box_counting_available_range_multi_origin_fallback"
    try:
        _, candidates = find_best_scaling_window(
            counts["scale_m"].to_numpy(), counts["count_fit"].to_numpy(), min_points=min_points
        )
    except ValueError:
        candidates = pd.DataFrame()
    return fit, counts, candidates


def integral_image(mask: np.ndarray) -> np.ndarray:
    m = np.asarray(mask, dtype=np.float64)
    return np.pad(m.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)), mode="constant")


def window_sums(mask: np.ndarray, window_size: int, stride: int = 1) -> np.ndarray:
    if window_size < 1:
        raise ValueError("window_size must be positive")
    m = np.asarray(mask, dtype=np.float64)
    h, w = m.shape
    if window_size > h or window_size > w:
        return np.array([], dtype=float)
    ii = integral_image(m)
    ys = np.arange(0, h - window_size + 1, stride)
    xs = np.arange(0, w - window_size + 1, stride)
    out = np.empty((len(ys), len(xs)), dtype=float)
    for iy, y in enumerate(ys):
        y2 = y + window_size
        out[iy, :] = ii[y2, xs + window_size] - ii[y, xs + window_size] - ii[y2, xs] + ii[y, xs]
    return out.ravel()


def lacunarity_2d(
    mask: np.ndarray,
    window_sizes_px: Iterable[int],
    *,
    domain_mask: np.ndarray | None = None,
    stride: int | None = None,
    include_empty: bool = True,
    min_domain_fraction: float = 0.95,
) -> pd.DataFrame:
    """Domain-aware gliding-box lacunarity.

    Windows mostly outside an irregular city boundary are excluded rather than
    being interpreted as urban voids.
    """
    m = np.asarray(mask, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError("lacunarity_2d expects a 2D mask")
    domain = np.ones_like(m, dtype=float) if domain_mask is None else np.asarray(domain_mask, dtype=float)
    if domain.shape != m.shape:
        raise ValueError("domain_mask shape must match mask")
    rows = []
    for ws in sorted(set(int(x) for x in window_sizes_px if int(x) >= 1)):
        if ws > min(m.shape):
            continue
        st = stride if stride is not None else max(1, ws // 4)
        sums = window_sums(m, ws, st)
        domain_sums = window_sums(domain, ws, st)
        valid = domain_sums >= float(min_domain_fraction) * ws * ws
        sums = sums[valid]
        domain_sums = domain_sums[valid]
        if not include_empty:
            keep = sums > 0
            sums, domain_sums = sums[keep], domain_sums[keep]
        if sums.size == 0:
            continue
        mean = float(np.mean(sums))
        var = float(np.var(sums))
        lac = float(var / (mean * mean) + 1.0) if mean > 0 else float("nan")
        rows.append({
            "window_size_px": ws,
            "stride_px": st,
            "mean_mass": mean,
            "var_mass": var,
            "mean_occupancy": float(np.mean(sums / domain_sums)),
            "lacunarity": lac,
            "n_windows": int(sums.size),
            "min_domain_fraction": float(min_domain_fraction),
        })
    if not rows:
        raise ValueError("No valid interior windows for lacunarity")
    return pd.DataFrame(rows)


def compactness_2d(area: float, perimeter: float) -> float:
    if area <= 0 or perimeter <= 0:
        return float("nan")
    return float(4.0 * np.pi * area / (perimeter * perimeter))


def isoperimetric_compactness_3d(volume: float, closed_surface_area: float) -> float:
    if volume <= 0 or closed_surface_area <= 0:
        return float("nan")
    return float(36.0 * np.pi * volume * volume / (closed_surface_area ** 3))


def _pad_to_multiple(array: np.ndarray, box_size: int, shift_y: int = 0, shift_x: int = 0) -> np.ndarray:
    a = np.asarray(array)
    h, w = a.shape
    top, left = int(shift_y), int(shift_x)
    bottom = (-(h + top)) % box_size
    right = (-(w + left)) % box_size
    return np.pad(a, ((top, bottom), (left, right)), mode="constant", constant_values=0)


def multifractal_spectrum_2d(
    mass: np.ndarray,
    box_sizes_px: Iterable[int],
    q_values: Sequence[float],
    pixel_size_m: float,
    *,
    min_points: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate generalized dimensions using zero padding, never cropping.

    The probability masses are normalized separately at every scale and their
    sum is recorded as a diagnostic. Thus no mass disappears when a raster side
    is not divisible by a box size.
    """
    m = np.asarray(mass, dtype=np.float64).copy()
    m[m < 0] = 0
    if float(m.sum()) <= 0:
        raise ValueError("Mass field must have positive sum")
    box_sizes = sorted(set(int(x) for x in box_sizes_px if int(x) >= 1 and int(x) <= max(m.shape)))
    rows = []
    for bs in box_sizes:
        padded = _pad_to_multiple(m, bs)
        blocks = padded.reshape(padded.shape[0] // bs, bs, padded.shape[1] // bs, bs)
        masses = blocks.sum(axis=(1, 3)).ravel()
        scale_total = float(masses.sum())
        if scale_total <= 0:
            continue
        p = masses[masses > 0] / scale_total
        for q0 in q_values:
            q = float(q0)
            if abs(q - 1.0) < 1e-12:
                value = float(np.sum(p * np.log(p)))
                kind = "info_sum"
            else:
                value = float(np.sum(p ** q))
                kind = "partition"
            rows.append({
                "q": q,
                "box_size_px": bs,
                "scale_m": bs * float(pixel_size_m),
                "value": value,
                "kind": kind,
                "mass_sum": scale_total,
                "probability_sum": float(p.sum()),
                "padding_rows": int(padded.shape[0] - m.shape[0]),
                "padding_cols": int(padded.shape[1] - m.shape[1]),
            })
    raw = pd.DataFrame(rows)
    spectrum_rows = []
    for q, sub in raw.groupby("q"):
        sub = sub.sort_values("scale_m")
        if len(sub) < min_points:
            continue
        x = np.log(sub["scale_m"].to_numpy(dtype=float))
        if abs(float(q) - 1.0) < 1e-12:
            y = sub["value"].to_numpy(dtype=float)
            slope, _, r2, stderr = _linear_fit(x, y)
            d_q, tau = slope, np.nan
        else:
            y = np.log(sub["value"].to_numpy(dtype=float))
            slope, _, r2, stderr = _linear_fit(x, y)
            tau = slope
            d_q = tau / (float(q) - 1.0)
        spectrum_rows.append({
            "q": float(q), "Dq": float(d_q), "tau": float(tau) if np.isfinite(tau) else np.nan,
            "r2": float(r2), "stderr": float(stderr) if np.isfinite(stderr) else np.nan,
            "n_points": int(len(sub)),
            "max_probability_normalization_error": float(np.max(np.abs(sub["probability_sum"] - 1.0))),
        })
    return pd.DataFrame(spectrum_rows), raw

# Backward-compatible name. In 0.4 this function is valid only when the caller
# passes a genuinely closed surface area.
def compactness_3d(volume: float, surface_area: float) -> float:
    return isoperimetric_compactness_3d(volume, surface_area)
