from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_box_count(counts: pd.DataFrame, fit: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.log(1.0 / counts["scale_m"].to_numpy())
    y = np.log(counts["count"].to_numpy())
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(x, y, label="counts")
    xmin = np.log(1.0 / fit["scale_max"])
    xmax = np.log(1.0 / fit["scale_min"])
    xx = np.linspace(xmin, xmax, 100)
    yy = fit["dimension"] * xx + fit["intercept"]
    ax.plot(xx, yy, label=f"D={fit['dimension']:.3f}, R²={fit['r2']:.3f}")
    ax.set_xlabel("log(1 / scale)")
    ax.set_ylabel("log(N(scale))")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_lacunarity(lacunarity: pd.DataFrame, pixel_size_m: float, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scale = lacunarity["window_size_px"].to_numpy() * pixel_size_m
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(scale, lacunarity["lacunarity"].to_numpy(), marker="o")
    ax.set_xscale("log")
    ax.set_xlabel("window size, m")
    ax.set_ylabel("lacunarity")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_mask(mask, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(mask, origin="upper", interpolation="nearest")
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_minkowski_profile(profile: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = profile["radius_m"].to_numpy(dtype=float)
    fig, ax1 = plt.subplots(figsize=(7, 5))
    ax1.plot(x, profile["area_m2"].to_numpy(dtype=float), marker="o", label="A(r)")
    ax1.set_xlabel("dilation radius r, m")
    ax1.set_ylabel("area A(r), m²")
    ax1.grid(True, alpha=0.3)
    ax2 = ax1.twinx()
    ax2.plot(x, profile["perimeter_m"].to_numpy(dtype=float), marker="s", label="P(r)")
    ax2.set_ylabel("lattice perimeter P(r), m")
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_betti_profile(profile: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = profile["radius_m"].to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(x, profile["beta0"].to_numpy(dtype=float), marker="o", label="beta0 components")
    ax.plot(x, profile["beta1"].to_numpy(dtype=float), marker="s", label="beta1 holes")
    ax.plot(x, profile["chi"].to_numpy(dtype=float), marker="^", label="chi")
    ax.set_xlabel("dilation radius r, m")
    ax.set_ylabel("topological count")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_percolation_profile(profile: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = profile["radius_m"].to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(x, profile["giant_fraction"].to_numpy(dtype=float), marker="o")
    ax.set_xlabel("dilation radius r, m")
    ax.set_ylabel("largest component fraction G(r)")
    ax.set_ylim(-0.02, 1.02)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_resolution_sweep(summary: pd.DataFrame, path: str | Path) -> None:
    """Plot key resolution-dependence diagnostics for one-city sweeps."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if summary.empty or "pixel_size_m" not in summary:
        return

    df = summary.copy()
    for col in [
        "pixel_size_m",
        "D_build",
        "D_r2",
        "raster_area_error_rel",
        "lacunarity_mean",
        "rc_m",
    ]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.sort_values("pixel_size_m")

    metrics = [
        ("D_build", "box-counting D"),
        ("raster_area_error_rel", "raster area error"),
        ("lacunarity_mean", "mean lacunarity"),
        ("rc_m", "percolation radius, m"),
    ]
    available = [(col, label) for col, label in metrics if col in df and df[col].notna().any()]
    if not available:
        return

    fig, axes = plt.subplots(len(available), 1, figsize=(7, 3.2 * len(available)), squeeze=False)
    axes = axes.ravel()
    x = df["pixel_size_m"].to_numpy(dtype=float)
    for ax, (col, label) in zip(axes, available):
        y = df[col].to_numpy(dtype=float)
        ax.plot(x, y, marker="o")
        ax.set_xscale("log")
        ax.set_xlabel("pixel size, m")
        ax.set_ylabel(label)
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
