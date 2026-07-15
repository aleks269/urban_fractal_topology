from __future__ import annotations

import numpy as np
from scipy import sparse

from urban_fractal.transport import _solve


def test_transport_solver_accepts_integer_sparse_matrix() -> None:
    """The Jacobi preconditioner must always return floating-point data."""

    matrix = sparse.csr_matrix(
        np.array(
            [
                [2, -1, 0],
                [-1, 2, -1],
                [0, -1, 2],
            ],
            dtype=np.int8,
        )
    )

    rhs = np.array(
        [1.0, 0.0, 1.0],
        dtype=np.float64,
    )

    solution, solver, converged, iterations = _solve(
        matrix,
        rhs,
    )

    assert solution.dtype.kind == "f"
    assert np.isfinite(solution).all()
    assert converged
    assert isinstance(solver, str)
    assert iterations is None or iterations >= 0

    np.testing.assert_allclose(
        matrix @ solution,
        rhs,
        rtol=1e-9,
        atol=1e-9,
    )
