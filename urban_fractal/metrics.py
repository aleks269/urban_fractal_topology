from __future__ import annotations

from dataclasses import dataclass, asdict
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
    """Return slope, intercept, R^2, slope stderr for y = slope*x + intercept."""
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
        sxx = np.sum((x - np.mean(x)) ** 2)
        stderr = float(np.sqrt(s2 / sxx)) if sxx > 0 else float("nan")
    else:
        stderr = float("nan")
    return float(slope), float(intercept), float(r2), stderr


def find_best_scaling_window(
    scales: Sequence[float],
    counts: Sequence[float],
    *,
    min_points: int = 4,
    min_r2: float = 0.95,
    prefer_long_windows: bool = True,
) -> tuple[ScalingFit, pd.DataFrame]:
    """Find the most stable approximately linear log-log interval.

    Parameters
    ----------
    scales:
        Physical grid sizes. Larger scale means coarser covering boxes.
    counts:
        Number of non-empty boxes at each scale.
    min_points:
        Minimal number of log-log samples in a candidate interval.
    min_r2:
        Candidate windows below this R^2 are penalized.
    prefer_long_windows:
        If true, longer intervals receive a weak score bonus.
    """
    scales = np.asarray(scales, dtype=float)
    counts = np.asarray(counts, dtype=float)
    valid = np.isfinite(scales) & np.isfinite(counts) & (scales > 0) & (counts > 0)
    scales = scales[valid]
    counts = counts[valid]
    if scales.size < min_points:
        raise ValueError("Not enough valid scale/count pairs for scaling fit")

    # Sort by increasing x = log(1/scale)
    x = np.log(1.0 / scales)
    y = np.log(counts)
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    s_sorted = scales[order]

    candidates: list[WindowFitCandidate] = []
    n = x.size
    for i in range(0, n - min_points + 1):
        for j in range(i + min_points, n + 1):
            slope, intercept, r2, stderr = _linear_fit(x[i:j], y[i:j])
            length = j - i
            span = float(np.max(x[i:j]) - np.min(x[i:j]))
            if span <= 0:
                continue
            # Penalize poor linearity and unstable slopes; reward long log spans.
            score = r2
            if prefer_long_windows:
                score += 0.015 * length + 0.02 * span
            if r2 < min_r2:
                score -= 0.25 * (min_r2 - r2)
            if np.isfinite(stderr):
                score -= 0.02 * stderr
            candidates.append(WindowFitCandidate(i, j, slope, intercept, r2, stderr, score))

    if not candidates:
        raise ValueError("No scaling window candidates were found")
    best = max(candidates, key=lambda c: c.score)
    fit = ScalingFit(
        dimension=best.slope,
        intercept=best.intercept,
        r2=best.r2,
        stderr=best.stderr,
        scale_min=float(np.min(s_sorted[best.start:best.stop])),
        scale_max=float(np.max(s_sorted[best.start:best.stop])),
        n_points=int(best.stop - best.start),
        method="box_counting_auto_window",
    )
    df = pd.DataFrame([c.__dict__ for c in candidates]).sort_values("score", ascending=False)
    return fit, df


def _crop_to_multiple(mask: np.ndarray, box_size: int) -> np.ndarray:
    h, w = mask.shape
    h2 = (h // box_size) * box_size
    w2 = (w // box_size) * box_size
    if h2 == 0 or w2 == 0:
        raise ValueError("Box size is larger than mask")
    return mask[:h2, :w2]


def box_count_2d(mask: np.ndarray, box_sizes_px: Iterable[int]) -> pd.DataFrame:
    """Count non-empty boxes in a 2D binary mask for each pixel box size."""
    m = np.asarray(mask).astype(bool)
    if m.ndim != 2:
        raise ValueError("box_count_2d expects a 2D mask")
    rows = []
    for bs in sorted(set(int(x) for x in box_sizes_px if int(x) >= 1)):
        if bs > min(m.shape):
            continue
        cropped = _crop_to_multiple(m, bs)
        blocks = cropped.reshape(cropped.shape[0] // bs, bs, cropped.shape[1] // bs, bs)
        occupied = blocks.any(axis=(1, 3))
        rows.append({"box_size_px": bs, "count": int(occupied.sum())})
    if not rows:
        raise ValueError("No valid box sizes for 2D mask")
    return pd.DataFrame(rows)


def box_count_dimension_2d(
    mask: np.ndarray,
    pixel_size_m: float,
    box_sizes_px: Iterable[int],
    *,
    min_points: int = 4,
) -> tuple[ScalingFit, pd.DataFrame, pd.DataFrame]:
    counts = box_count_2d(mask, box_sizes_px)
    counts["scale_m"] = counts["box_size_px"] * float(pixel_size_m)
    fit, candidates = find_best_scaling_window(
        counts["scale_m"].to_numpy(),
        counts["count"].to_numpy(),
        min_points=min_points,
    )
    return fit, counts, candidates


def integral_image(mask: np.ndarray) -> np.ndarray:
    m = np.asarray(mask, dtype=np.float64)
    return np.pad(m.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)), mode="constant")


def window_sums(mask: np.ndarray, window_size: int, stride: int = 1) -> np.ndarray:
    """Fast sums over square sliding windows using an integral image."""
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
        vals = ii[y2, xs + window_size] - ii[y, xs + window_size] - ii[y2, xs] + ii[y, xs]
        out[iy, :] = vals
    return out.ravel()


def lacunarity_2d(
    mask: np.ndarray,
    window_sizes_px: Iterable[int],
    *,
    stride: int | None = None,
    include_empty: bool = True,
) -> pd.DataFrame:
    """Compute gliding-box lacunarity curve for a binary or weighted 2D mask.

    Lambda(r) = Var(M_r) / E(M_r)^2 + 1.
    """
    m = np.asarray(mask, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError("lacunarity_2d expects a 2D mask")
    rows = []
    for ws in sorted(set(int(x) for x in window_sizes_px if int(x) >= 1)):
        if ws > min(m.shape):
            continue
        st = stride if stride is not None else max(1, ws // 4)
        sums = window_sums(m, ws, st)
        if not include_empty:
            sums = sums[sums > 0]
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
            "lacunarity": lac,
            "n_windows": int(sums.size),
        })
    if not rows:
        raise ValueError("No valid window sizes for lacunarity")
    return pd.DataFrame(rows)


def compactness_2d(area: float, perimeter: float) -> float:
    if area <= 0 or perimeter <= 0:
        return float("nan")
    return float(4.0 * np.pi * area / (perimeter * perimeter))


def compactness_3d(volume: float, surface_area: float) -> float:
    if volume <= 0 or surface_area <= 0:
        return float("nan")
    return float(36.0 * np.pi * volume * volume / (surface_area ** 3))


def multifractal_spectrum_2d(
    mass: np.ndarray,
    box_sizes_px: Iterable[int],
    q_values: Sequence[float],
    pixel_size_m: float,
    *,
    min_points: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Estimate generalized dimensions D_q for a non-negative 2D mass field.

    For q != 1: Z_q(eps)=sum p_i^q ~ eps^tau(q), D_q=tau(q)/(q-1).
    For q = 1: information dimension from sum p_i log p_i ~ D_1 log eps.
    """
    m = np.asarray(mass, dtype=np.float64)
    m[m < 0] = 0
    total = float(m.sum())
    if total <= 0:
        raise ValueError("Mass field must have positive sum")
    box_sizes = sorted(set(int(x) for x in box_sizes_px if int(x) >= 1 and int(x) <= min(m.shape)))
    rows = []
    for bs in box_sizes:
        cropped = _crop_to_multiple(m, bs)
        blocks = cropped.reshape(cropped.shape[0] // bs, bs, cropped.shape[1] // bs, bs)
        masses = blocks.sum(axis=(1, 3)).ravel()
        p = masses[masses > 0] / total
        scale_m = bs * pixel_size_m
        for q in q_values:
            q = float(q)
            if abs(q - 1.0) < 1e-12:
                val = float(np.sum(p * np.log(p)))
                kind = "info_sum"
            else:
                val = float(np.sum(p ** q))
                kind = "partition"
            rows.append({"q": q, "box_size_px": bs, "scale_m": scale_m, "value": val, "kind": kind})
    raw = pd.DataFrame(rows)
    spectrum_rows = []
    for q, sub in raw.groupby("q"):
        sub = sub.sort_values("scale_m")
        if len(sub) < min_points:
            continue
        if abs(float(q) - 1.0) < 1e-12:
            x = np.log(sub["scale_m"].to_numpy())
            y = sub["value"].to_numpy()
            slope, intercept, r2, stderr = _linear_fit(x, y)
            d_q = slope
            tau = np.nan
        else:
            x = np.log(sub["scale_m"].to_numpy())
            y = np.log(sub["value"].to_numpy())
            slope, intercept, r2, stderr = _linear_fit(x, y)
            tau = slope
            d_q = tau / (float(q) - 1.0)
        spectrum_rows.append({
            "q": float(q), "Dq": float(d_q), "tau": float(tau) if np.isfinite(tau) else np.nan,
            "r2": float(r2), "stderr": float(stderr) if np.isfinite(stderr) else np.nan,
            "n_points": int(len(sub)),
        })
    return pd.DataFrame(spectrum_rows), raw
