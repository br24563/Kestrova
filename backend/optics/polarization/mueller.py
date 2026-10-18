"""
Mueller calculus for polarization analysis.

Mueller calculus uses 4x4 real matrices to represent polarization
state and optical elements. Valid for partially polarized light.
"""

from typing import Union, TYPE_CHECKING
from dataclasses import dataclass
import numpy as np

if TYPE_CHECKING:
    from .stokes import StokesVector


@dataclass
class MuellerMatrix:
    """4x4 real matrix representing optical element."""

    matrix: np.ndarray

    def __post_init__(self):
        if self.matrix.shape != (4, 4):
            raise ValueError("Mueller matrix must be 4x4")
        self.matrix = self.matrix.astype(float)

    def __matmul__(self, other: Union["MuellerMatrix", "StokesVector"]):
        """Matrix multiplication."""
        from .stokes import StokesVector

        if isinstance(other, MuellerMatrix):
            return MuellerMatrix(self.matrix @ other.matrix)
        elif isinstance(other, StokesVector):
            result = self.matrix @ other.vector
            return StokesVector(result[0], result[1], result[2], result[3])
        else:
            raise TypeError(f"Cannot multiply MuellerMatrix with {type(other)}")

    @property
    def is_physical(self) -> bool:
        """Check if matrix represents physical element."""
        # Cloude's coherency matrix test
        M = self.matrix
        # Extract blocks
        A = M[0:2, 0:2]
        B = M[0:2, 2:4]
        C = M[2:4, 0:2]
        D = M[2:4, 2:4]

        # Coherency matrix must be positive semi-definite
        H = np.block([[A, B], [C, D]])
        eigenvalues = np.linalg.eigvalsh(H)
        return bool(np.all(eigenvalues >= -1e-10))

    @classmethod
    def from_jones(cls, J: np.ndarray) -> "MuellerMatrix":
        """Convert Jones matrix to Mueller matrix."""
        # Mueller matrix from Jones matrix
        # M_ij = 0.5 * Tr(sigma_i * J * sigma_j * J^dagger)
        sigma = [
            np.array([[1, 0], [0, 1]]),  # sigma_0
            np.array([[1, 0], [0, -1]]),  # sigma_1
            np.array([[0, 1], [1, 0]]),  # sigma_2
            np.array([[0, -1j], [1j, 0]]),  # sigma_3
        ]

        M = np.zeros((4, 4))
        for i in range(4):
            for j in range(4):
                M[i, j] = 0.5 * np.trace(sigma[i] @ J @ sigma[j] @ J.conj().T).real

        return cls(M)


def mueller_identity() -> MuellerMatrix:
    """Identity matrix."""
    return MuellerMatrix(np.eye(4))


def mueller_linear_polarizer(
    angle: float = 0.0, transmission: float = 1.0
) -> MuellerMatrix:
    """
    Linear polarizer.

    Args:
        angle: Transmission axis angle in radians
        transmission: Maximum transmission (0-1)
    """
    c2 = np.cos(2 * angle)
    s2 = np.sin(2 * angle)
    T = transmission

    M = (
        0.5
        * T
        * np.array(
            [
                [1, c2, s2, 0],
                [c2, c2**2, c2 * s2, 0],
                [s2, c2 * s2, s2**2, 0],
                [0, 0, 0, 0],
            ]
        )
    )

    return MuellerMatrix(M)


def mueller_wave_plate(retardance: float, fast_axis: float = 0.0) -> MuellerMatrix:
    """
    Linear retarder. Derived from :func:`jones.jones_wave_plate` so the Jones
    and Mueller calculi share one sign convention.
    """
    from .jones import jones_wave_plate

    return MuellerMatrix.from_jones(jones_wave_plate(retardance, fast_axis).matrix)


def mueller_quarter_wave(fast_axis: float = 0.0) -> MuellerMatrix:
    """Quarter-wave plate."""
    return mueller_wave_plate(np.pi / 2, fast_axis)


def mueller_half_wave(fast_axis: float = 0.0) -> MuellerMatrix:
    """Half-wave plate."""
    return mueller_wave_plate(np.pi, fast_axis)


def mueller_depolarizer(degree: float = 1.0) -> MuellerMatrix:
    """
    Depolarizer.

    Args:
        degree: Depolarization degree (0=no depolarization, 1=complete)
    """
    d = degree
    M = np.array([[1, 0, 0, 0], [0, 1 - d, 0, 0], [0, 0, 1 - d, 0], [0, 0, 0, 1 - d]])

    return MuellerMatrix(M)


def mueller_partial_polarizer(
    tx: float, ty: float, angle: float = 0.0
) -> MuellerMatrix:
    """
    Linear diattenuator: intensity transmittances tx along its axis and ty
    across it, axis at ``angle`` (radians).
    """
    from .jones import JonesMatrix

    c, s = np.cos(angle), np.sin(angle)
    R = np.array([[c, -s], [s, c]])
    J = R @ np.diag([np.sqrt(tx), np.sqrt(ty)]) @ R.T
    return MuellerMatrix.from_jones(J)
