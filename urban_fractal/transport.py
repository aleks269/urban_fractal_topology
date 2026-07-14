from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .topology import domain_side_masks


Direction = Literal["lr", "tb"]
Phase = Literal["open_space", "buildings"]


@dataclass
class TransportResult:
    phase: str
    direction: str
    contrast: float
    pixel_size_m: float
    original_pixel_size_m: float
    coarsening_factor: int
    active_cells: int
    excluded_unanchored_cells: int
    unknown_cells: int
    solver: str
    converged: bool
    iterations: int | None
    conductance: float
    resistance: float
    dissipation_fixed_delta_u: float
    dissipation_fixed_unit_flux: float
    energy_identity_relative_error: float
    homogeneous_conductance: float
    relative_conductance: float
    effective_conductivity_bbox: float

    def to_dict(self) -> dict:
        return asdict(self)


def harmonic_mean(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    den = a + b
    return np.divide(2.0 * a * b, den, out=np.zeros_like(den, dtype=float), where=den > 0)


def _block_reduce_mean(a: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return np.asarray(a, dtype=float)
    h, w = a.shape
    pad_h = (-h) % factor
    pad_w = (-w) % factor
    padded = np.pad(np.asarray(a, dtype=float), ((0, pad_h), (0, pad_w)), constant_values=0)
    return padded.reshape(padded.shape[0] // factor, factor, padded.shape[1] // factor, factor).mean(axis=(1, 3))


def prepare_transport_grid(
    building_mask: np.ndarray,
    domain_mask: np.ndarray,
    *,
    pixel_size_m: float,
    max_active_cells: int = 250_000,
) -> tuple[np.ndarray, np.ndarray, float, int]:
    building = np.asarray(building_mask, dtype=bool)
    domain = np.asarray(domain_mask, dtype=bool)
    active = int(domain.sum())
    factor = max(1, int(np.ceil(np.sqrt(active / max_active_cells)))) if max_active_cells > 0 else 1
    if factor == 1:
        return building.astype(float), domain, float(pixel_size_m), 1
    domain_fraction = _block_reduce_mean(domain.astype(float), factor)
    building_fraction_raw = _block_reduce_mean((building & domain).astype(float), factor)
    domain_coarse = domain_fraction >= 0.5
    building_fraction = np.divide(
        building_fraction_raw,
        domain_fraction,
        out=np.zeros_like(building_fraction_raw),
        where=domain_fraction > 0,
    )
    building_fraction[~domain_coarse] = 0.0
    return np.clip(building_fraction, 0.0, 1.0), domain_coarse, float(pixel_size_m * factor), factor


def conductivity_from_fraction(
    building_fraction: np.ndarray,
    domain_mask: np.ndarray,
    *,
    phase: Phase,
    contrast: float,
) -> np.ndarray:
    if contrast <= 1:
        raise ValueError("contrast must be > 1")
    f = np.asarray(building_fraction, dtype=float)
    domain = np.asarray(domain_mask, dtype=bool)
    k_high, k_low = 1.0, 1.0 / float(contrast)
    # Geometric mixing is conservative for a coarsened high-contrast field and
    # preserves the two exact phase values when f is 0 or 1.
    if phase == "open_space":
        logk = (1.0 - f) * np.log(k_high) + f * np.log(k_low)
    elif phase == "buildings":
        logk = f * np.log(k_high) + (1.0 - f) * np.log(k_low)
    else:
        raise ValueError(f"Unknown transport phase: {phase}")
    k = np.exp(logk)
    k[~domain] = np.nan
    return k


def _source_sink_masks(domain: np.ndarray, direction: Direction) -> tuple[np.ndarray, np.ndarray]:
    sides = domain_side_masks(domain)
    source, sink = (sides["left"], sides["right"]) if direction == "lr" else (sides["top"], sides["bottom"])
    overlap = source & sink
    source = source & ~overlap
    sink = sink & ~overlap
    if not source.any() or not sink.any():
        raise ValueError(f"Domain has no distinct source/sink sides for direction {direction}")
    return source, sink


def _assemble_system(k: np.ndarray, domain: np.ndarray, source: np.ndarray, sink: np.ndarray):
    ny, nx = domain.shape
    dirichlet = source | sink
    unknown = domain & ~dirichlet
    index = np.full((ny, nx), -1, dtype=np.int32)
    index[unknown] = np.arange(int(unknown.sum()), dtype=np.int32)
    n = int(unknown.sum())
    diag = np.zeros(n, dtype=float)
    b = np.zeros(n, dtype=float)
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    data: list[np.ndarray] = []

    def add_edges(a_slice, b_slice):
        a_dom = domain[a_slice]
        b_dom = domain[b_slice]
        pair = a_dom & b_dom
        if not pair.any():
            return
        ga = k[a_slice][pair]
        gb = k[b_slice][pair]
        g = harmonic_mean(ga, gb)
        ia_grid = index[a_slice][pair]
        ib_grid = index[b_slice][pair]
        a_unknown = ia_grid >= 0
        b_unknown = ib_grid >= 0

        both = a_unknown & b_unknown
        if both.any():
            ia, ib, gg = ia_grid[both], ib_grid[both], g[both]
            np.add.at(diag, ia, gg)
            np.add.at(diag, ib, gg)
            rows.extend([ia, ib])
            cols.extend([ib, ia])
            data.extend([-gg, -gg])

        a_only = a_unknown & ~b_unknown
        if a_only.any():
            ia, gg = ia_grid[a_only], g[a_only]
            np.add.at(diag, ia, gg)
            b_values = source[b_slice][pair][a_only].astype(float)
            np.add.at(b, ia, gg * b_values)

        b_only = b_unknown & ~a_unknown
        if b_only.any():
            ib, gg = ib_grid[b_only], g[b_only]
            np.add.at(diag, ib, gg)
            a_values = source[a_slice][pair][b_only].astype(float)
            np.add.at(b, ib, gg * a_values)

    add_edges((slice(None), slice(0, -1)), (slice(None), slice(1, None)))
    add_edges((slice(0, -1), slice(None)), (slice(1, None), slice(None)))

    ids = np.arange(n, dtype=np.int32)
    rows.append(ids)
    cols.append(ids)
    data.append(diag)
    A = sp.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    return A, b, unknown, index


def _solve(A: sp.csr_matrix, b: np.ndarray) -> tuple[np.ndarray, str, bool, int | None]:
    n = A.shape[0]
    if n == 0:
        return np.array([], dtype=float), "none", True, 0
    if n <= 80_000:
        return spla.spsolve(A, b), "spsolve", True, None
    diag = A.diagonal()
    M = spla.LinearOperator(A.shape, matvec=lambda x: np.divide(x, diag, out=np.zeros_like(x), where=diag != 0))
    counter = {"n": 0}

    def callback(_):
        counter["n"] += 1

    x, info = spla.cg(A, b, rtol=1e-8, atol=0.0, maxiter=3000, M=M, callback=callback)
    return x, "cg_jacobi", info == 0, counter["n"]


def _field_and_energy(
    x: np.ndarray,
    k: np.ndarray,
    domain: np.ndarray,
    source: np.ndarray,
    sink: np.ndarray,
    unknown: np.ndarray,
) -> tuple[np.ndarray, float, float]:
    u = np.full(domain.shape, np.nan, dtype=float)
    u[source] = 1.0
    u[sink] = 0.0
    u[unknown] = x
    phi = 0.0
    flux = 0.0

    def edge_energy(a_slice, b_slice):
        nonlocal phi, flux
        pair = domain[a_slice] & domain[b_slice]
        if not pair.any():
            return
        g = harmonic_mean(k[a_slice][pair], k[b_slice][pair])
        ua = u[a_slice][pair]
        ub = u[b_slice][pair]
        phi += float(np.sum(g * (ua - ub) ** 2))
        sa = source[a_slice][pair]
        sb = source[b_slice][pair]
        flux += float(np.sum(g[sa & ~sb] * (ua[sa & ~sb] - ub[sa & ~sb])))
        flux += float(np.sum(g[sb & ~sa] * (ub[sb & ~sa] - ua[sb & ~sa])))

    edge_energy((slice(None), slice(0, -1)), (slice(None), slice(1, None)))
    edge_energy((slice(0, -1), slice(None)), (slice(1, None), slice(None)))
    return u, float(flux), float(phi)


def solve_transport(
    k: np.ndarray,
    domain_mask: np.ndarray,
    *,
    pixel_size_m: float,
    direction: Direction,
) -> tuple[dict, np.ndarray]:
    domain_original = np.asarray(domain_mask, dtype=bool)
    source, sink = _source_sink_masks(domain_original, direction)
    # Components touching neither imposed-potential side are Neumann-isolated;
    # their potential is undetermined and they do not contribute to through-flow.
    from scipy import ndimage as ndi
    labels, n_components = ndi.label(domain_original, structure=ndi.generate_binary_structure(2, 1))
    anchored_labels = set(int(v) for v in np.unique(labels[source | sink]) if int(v) != 0)
    domain = np.isin(labels, list(anchored_labels)) if anchored_labels else np.zeros_like(domain_original)
    excluded_unanchored = int(domain_original.sum() - domain.sum())
    source &= domain
    sink &= domain
    k = np.asarray(k, dtype=float).copy()
    k[~domain] = np.nan
    A, b, unknown, _ = _assemble_system(k, domain, source, sink)
    x, solver, converged, iterations = _solve(A, b)
    u, conductance, phi = _field_and_energy(x, k, domain, source, sink, unknown)
    if conductance <= 0 or not np.isfinite(conductance):
        resistance = float("inf")
        fixed_flux_phi = float("inf")
    else:
        resistance = 1.0 / conductance
        fixed_flux_phi = resistance
    length = (domain.shape[1] - 1) * pixel_size_m if direction == "lr" else (domain.shape[0] - 1) * pixel_size_m
    width = domain.shape[0] * pixel_size_m if direction == "lr" else domain.shape[1] * pixel_size_m
    k_bbox = conductance * length / width if width > 0 else np.nan
    return {
        "solver": solver,
        "converged": bool(converged),
        "iterations": iterations,
        "unknown_cells": int(unknown.sum()),
        "excluded_unanchored_cells": excluded_unanchored,
        "active_cells_used": int(domain.sum()),
        "conductance": conductance,
        "resistance": resistance,
        "dissipation_fixed_delta_u": phi,
        "dissipation_fixed_unit_flux": fixed_flux_phi,
        "energy_identity_relative_error": abs(phi - conductance) / max(abs(conductance), 1e-15),
        "effective_conductivity_bbox": float(k_bbox),
    }, u


def analyze_transport_phase(
    building_fraction: np.ndarray,
    domain_mask: np.ndarray,
    *,
    phase: Phase,
    contrast: float,
    pixel_size_m: float,
    original_pixel_size_m: float,
    coarsening_factor: int,
    direction: Direction,
    homogeneous_cache: dict[str, tuple[dict, np.ndarray]] | None = None,
) -> tuple[TransportResult, np.ndarray]:
    domain = np.asarray(domain_mask, dtype=bool)
    k = conductivity_from_fraction(building_fraction, domain, phase=phase, contrast=contrast)
    result, potential = solve_transport(k, domain, pixel_size_m=pixel_size_m, direction=direction)
    cache = homogeneous_cache if homogeneous_cache is not None else {}
    if direction not in cache:
        kh = np.ones_like(k, dtype=float)
        kh[~domain] = np.nan
        cache[direction] = solve_transport(kh, domain, pixel_size_m=pixel_size_m, direction=direction)
    homogeneous = cache[direction][0]["conductance"]
    rel = result["conductance"] / homogeneous if homogeneous > 0 else np.nan
    return TransportResult(
        phase=phase,
        direction=direction,
        contrast=float(contrast),
        pixel_size_m=float(pixel_size_m),
        original_pixel_size_m=float(original_pixel_size_m),
        coarsening_factor=int(coarsening_factor),
        active_cells=int(result.get("active_cells_used", domain.sum())),
        excluded_unanchored_cells=int(result.get("excluded_unanchored_cells", 0)),
        unknown_cells=int(result["unknown_cells"]),
        solver=str(result["solver"]),
        converged=bool(result["converged"]),
        iterations=result["iterations"],
        conductance=float(result["conductance"]),
        resistance=float(result["resistance"]),
        dissipation_fixed_delta_u=float(result["dissipation_fixed_delta_u"]),
        dissipation_fixed_unit_flux=float(result["dissipation_fixed_unit_flux"]),
        energy_identity_relative_error=float(result["energy_identity_relative_error"]),
        homogeneous_conductance=float(homogeneous),
        relative_conductance=float(rel),
        effective_conductivity_bbox=float(result["effective_conductivity_bbox"]),
    ), potential
