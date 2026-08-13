"""
Thin lens calculations.

This module implements the fundamental thin lens equations and the
ray transfer matrix (ABCD matrix) method for paraxial ray tracing.

Sign convention (optics, used in optical design software):
    - Light travels from left to right.
    - Object distance (s): NEGATIVE if object is to the LEFT of the lens.
    - Object distance (s): POSITIVE if object is to the RIGHT of the lens.
    - Image distance (s'): NEGATIVE if image is to the LEFT of the lens.
    - Image distance (s'): POSITIVE if image is to the RIGHT of the lens.
    - Focal length (f): positive for converging, negative for diverging.
    - Ray height (y): positive above the optical axis.
    - Ray angle (theta): positive if ray goes upward (counterclockwise).

All values are in SI base units (meters, radians).
"""

import math
import numpy as np
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Thin Lens Equation: 1/f = 1/s' - 1/s
# ---------------------------------------------------------------------------

def image_distance(f: float, s: float) -> float:
    """
    Calculate the image distance for a thin lens.

    Uses the thin lens equation: 1/f = 1/s' - 1/s

    Sign convention (optics):
        - s < 0: object is to the LEFT of the lens (typical case)
        - s > 0: object is to the RIGHT of the lens
        - s' < 0: image is to the LEFT of the lens (virtual image)
        - s' > 0: image is to the RIGHT of the lens (real image)

    Args:
        f: Focal length of the lens (meters). Positive = converging.
        s: Object distance (meters). Negative if object is to the left.

    Returns:
        Image distance s' (meters). Positive if image is to the right
        (real image), negative if to the left (virtual image).

    Raises:
        ValueError: If s equals -f (image at infinity).

    Examples:
        >>> # Object at 2f to the left produces image at 2f to the right
        >>> image_distance(0.05, -0.10)
        0.1
        >>> # Object at infinity produces image at focal plane
        >>> image_distance(0.05, float('-inf'))
        0.05
    """
    if s == float('inf') or s == float('-inf'):
        # Object at infinity: image forms at the focal plane
        return f

    if abs(s + f) < 1e-15:
        raise ValueError(
            f"Object distance ({s}) equals -focal length ({-f}): "
            f"image is at infinity."
        )

    # From 1/f = 1/s' - 1/s:
    #   1/s' = 1/f + 1/s = (s + f) / (f * s)
    #   s' = f * s / (s + f)
    return f * s / (s + f)


def object_distance(f: float, s_prime: float) -> float:
    """
    Calculate the object distance for a thin lens.

    Uses the thin lens equation: 1/f = 1/s' - 1/s

    Sign convention (optics):
        - s < 0: object is to the LEFT of the lens (typical case)
        - s > 0: object is to the RIGHT of the lens
        - s' < 0: image is to the LEFT of the lens (virtual image)
        - s' > 0: image is to the RIGHT of the lens (real image)

    Args:
        f: Focal length of the lens (meters).
        s_prime: Image distance (meters). Positive if image is to the right.

    Returns:
        Object distance s (meters). Negative if object is to the left.

    Examples:
        >>> # Image at 2f to the right with f=50mm means object at 2f to the left
        >>> object_distance(0.05, 0.10)
        -0.1
    """
    if s_prime == float('inf') or s_prime == float('-inf'):
        return f

    if abs(s_prime - f) < 1e-15:
        raise ValueError(
            f"Image distance ({s_prime}) equals focal length ({f}): "
            f"object is at infinity."
        )

    # From 1/f = 1/s' - 1/s:
    #   1/s = 1/s' - 1/f = (f - s') / (s' * f)
    #   s = s' * f / (f - s')
    return s_prime * f / (f - s_prime)


def focal_length(s: float, s_prime: float) -> float:
    """
    Calculate the focal length given object and image distances.

    Uses the thin lens equation: 1/f = 1/s' - 1/s

    Sign convention (optics):
        - s < 0: object is to the LEFT of the lens (typical case)
        - s > 0: object is to the RIGHT of the lens
        - s' < 0: image is to the LEFT of the lens (virtual image)
        - s' > 0: image is to the RIGHT of the lens (real image)

    Args:
        s: Object distance (meters). Negative if object is to the left.
        s_prime: Image distance (meters). Positive if image is to the right.

    Returns:
        Focal length f (meters).

    Examples:
        >>> # Object at 2f to the left, image at 2f to the right => f = 50mm
        >>> focal_length(-0.10, 0.10)
        0.05
    """
    if abs(s - s_prime) < 1e-15:
        raise ValueError(
            f"Object distance ({s}) equals image distance ({s_prime}): "
            f"focal length is infinite (afocal system)."
        )

    # From 1/f = 1/s' - 1/s:
    #   1/f = (s - s') / (s' * s)
    #   f = s' * s / (s - s')
    return s_prime * s / (s - s_prime)


# ---------------------------------------------------------------------------
# Magnification
# ---------------------------------------------------------------------------

def magnification(s: float, s_prime: float) -> float:
    """
    Calculate the transverse magnification of a thin lens.

    m = s' / s

    A negative magnification means the image is inverted.
    A magnification with |m| > 1 means the image is larger than the object.

    Sign convention (optics):
        - s < 0: object is to the LEFT of the lens (typical case)
        - s > 0: object is to the RIGHT of the lens
        - s' < 0: image is to the LEFT of the lens (virtual image)
        - s' > 0: image is to the RIGHT of the lens (real image)

    Args:
        s: Object distance (meters). Negative if object is to the left.
        s_prime: Image distance (meters). Positive if image is to the right.

    Returns:
        Magnification (dimensionless).

    Examples:
        >>> # Object at 2f to the left, image at 2f to the right => m = -1
        >>> magnification(-0.10, 0.10)
        -1.0
        >>> # Object at f to the left, image at infinity => m = -inf
        >>> magnification(-0.05, float('inf'))
        -inf
    """
    if s == 0:
        raise ValueError("Object distance is zero: magnification is undefined.")
    return s_prime / s


def magnification_from_f(f: float, s: float) -> float:
    """
    Calculate magnification directly from focal length and object distance.

    m = s' / s = f / (s + f)

    Sign convention (optics):
        - s < 0: object is to the LEFT of the lens (typical case)

    Args:
        f: Focal length (meters).
        s: Object distance (meters). Negative if object is to the left.

    Returns:
        Magnification (dimensionless).
    """
    s_prime = image_distance(f, s)
    return magnification(s, s_prime)


# ---------------------------------------------------------------------------
# Two-Lens System
# ---------------------------------------------------------------------------

def two_lens_effective_focal_length(f1: float, f2: float, d: float) -> float:
    """
    Calculate the effective focal length of a two-lens system.

    1/f_eff = 1/f1 + 1/f2 - d/(f1*f2)

    Args:
        f1: Focal length of the first lens (meters).
        f2: Focal length of the second lens (meters).
        d: Distance between the two lenses (meters).

    Returns:
        Effective focal length of the system (meters).

    Examples:
        >>> # Two 50mm lenses, 0mm apart => f_eff = 25mm
        >>> two_lens_effective_focal_length(0.05, 0.05, 0.0)
        0.025
    """
    if abs(f1 * f2) < 1e-15:
        raise ValueError("One or both focal lengths are zero.")

    inv_f_eff = 1.0 / f1 + 1.0 / f2 - d / (f1 * f2)
    if abs(inv_f_eff) < 1e-10:
        raise ValueError("System is afocal (infinite effective focal length).")

    return 1.0 / inv_f_eff


def two_lens_back_focal_length(f1: float, f2: float, d: float) -> float:
    """
    Calculate the back focal length of a two-lens system.

    The back focal length is the distance from the second lens to the
    image plane when the object is at infinity.

    BFL = f2 * (f1 - d) / (f1 + f2 - d)

    Args:
        f1: Focal length of the first lens (meters).
        f2: Focal length of the second lens (meters).
        d: Distance between the two lenses (meters).

    Returns:
        Back focal length (meters).
    """
    denominator = f1 + f2 - d
    if abs(denominator) < 1e-15:
        raise ValueError("System is afocal: back focal length is undefined.")
    return f2 * (f1 - d) / denominator


def two_lens_front_focal_length(f1: float, f2: float, d: float) -> float:
    """
    Calculate the front focal length of a two-lens system.

    The front focal length is the distance from the first lens to the
    object when the image is at infinity.

    FFL = f1 * (f2 - d) / (f1 + f2 - d)

    Args:
        f1: Focal length of the first lens (meters).
        f2: Focal length of the second lens (meters).
        d: Distance between the two lenses (meters).

    Returns:
        Front focal length (meters).
    """
    denominator = f1 + f2 - d
    if abs(denominator) < 1e-15:
        raise ValueError("System is afocal: front focal length is undefined.")
    return f1 * (f2 - d) / denominator


def two_lens_system_image(
    f1: float, f2: float, d: float, s: float
) -> tuple[float, float]:
    """
    Calculate the final image position and magnification for a two-lens system.

    The image formed by the first lens becomes the object for the second lens.

    Sign convention (optics):
        - s < 0: object is to the LEFT of the first lens (typical case)
        - s > 0: object is to the RIGHT of the first lens
        - s' > 0: image is to the RIGHT of the last lens (real image)

    Args:
        f1: Focal length of the first lens (meters).
        f2: Focal length of the second lens (meters).
        d: Distance between the two lenses (meters).
        s: Object distance from the first lens (meters, negative if left).

    Returns:
        Tuple of (image_distance_from_lens2, total_magnification).
        image_distance is positive if the image is to the right of lens 2.
        total_magnification is the product of individual magnifications.
    """
    # Image from lens 1
    s1_prime = image_distance(f1, s)
    m1 = magnification(s, s1_prime)

    # Object distance for lens 2
    # The image from lens 1 is at position (lens1_pos + s1_prime)
    # The object for lens 2 is at distance s1_prime - d from lens 2
    # (negative if the intermediate image is to the left of lens 2)
    s2 = s1_prime - d

    # If s2 is very close to zero, the image is at the lens
    if abs(s2) < 1e-15:
        raise ValueError(
            "Intermediate image is at the second lens: cannot trace further."
        )

    s2_prime = image_distance(f2, s2)
    m2 = magnification(s2, s2_prime)

    total_m = m1 * m2
    return s2_prime, total_m


# ---------------------------------------------------------------------------
# Ray Transfer Matrix (ABCD Matrix) Method
# ---------------------------------------------------------------------------

@dataclass
class RayVector:
    """
    A paraxial ray represented as a vector [y, theta].

    y: height above the optical axis (meters)
    theta: angle from the optical axis (radians)
    """

    y: float
    theta: float

    def as_array(self) -> np.ndarray:
        """Convert to a NumPy array for matrix operations."""
        return np.array([self.y, self.theta])

    @classmethod
    def from_array(cls, arr: np.ndarray) -> "RayVector":
        """Create a RayVector from a NumPy array."""
        return cls(y=float(arr[0]), theta=float(arr[1]))

    def __repr__(self) -> str:
        return f"RayVector(y={self.y:.6f}, theta={self.theta:.6f})"


def propagation_matrix(d: float) -> np.ndarray:
    """
    Ray transfer matrix for free-space propagation over distance d.

    [y']   [1  d] [y]
    [θ'] = [0  1] [θ]

    Args:
        d: Propagation distance (meters). Positive = propagate to the right.

    Returns:
        2x2 ABCD matrix as a NumPy array.
    """
    return np.array([[1.0, d],
                     [0.0, 1.0]])


def thin_lens_matrix(f: float) -> np.ndarray:
    """
    Ray transfer matrix for a thin lens with focal length f.

    [y']   [1   0] [y]
    [θ'] = [-1/f 1] [θ]

    Args:
        f: Focal length (meters). Positive = converging.

    Returns:
        2x2 ABCD matrix as a NumPy array.
    """
    return np.array([[1.0, 0.0],
                     [-1.0 / f, 1.0]])


def apply_matrix(matrix: np.ndarray, ray: RayVector) -> RayVector:
    """
    Apply a ray transfer matrix to a ray.

    Args:
        matrix: 2x2 ABCD matrix.
        ray: Input ray vector.

    Returns:
        Output ray vector after applying the matrix.
    """
    result = matrix @ ray.as_array()
    return RayVector.from_array(result)


def system_matrix(matrices: list[np.ndarray]) -> np.ndarray:
    """
    Compute the overall system matrix from a list of individual matrices.

    The matrices are multiplied in order: M_total = M_n * ... * M_2 * M_1
    (the first matrix in the list is applied first to the ray).

    Args:
        matrices: List of 2x2 ABCD matrices, in the order they are
                  encountered by the ray (left to right).

    Returns:
        The overall 2x2 system matrix.
    """
    if not matrices:
        return np.eye(2)

    result = np.eye(2)
    for m in matrices:
        result = m @ result
    return result


# ---------------------------------------------------------------------------
# F-number and Numerical Aperture
# ---------------------------------------------------------------------------

def f_number(f: float, d: float) -> float:
    """
    Calculate the F-number (focal ratio) of a lens.

    F/# = f / D

    where f is the focal length and D is the aperture diameter.

    Args:
        f: Focal length (meters).
        d: Aperture diameter (meters).

    Returns:
        F-number (dimensionless).

    Examples:
        >>> f_number(0.050, 0.025)  # 50mm lens, 25mm aperture
        2.0
    """
    if d == 0:
        raise ValueError("Aperture diameter is zero: F-number is infinite.")
    return f / d


def numerical_aperture(n: float, theta: float) -> float:
    """
    Calculate the numerical aperture.

    NA = n * sin(theta)

    where n is the refractive index of the medium and theta is the
    half-angle of the cone of light.

    Args:
        n: Refractive index of the medium (dimensionless, 1.0 for air).
        theta: Half-angle of the light cone (radians).

    Returns:
        Numerical aperture (dimensionless).

    Examples:
        >>> # Air (n=1), 30 degree half-angle
        >>> numerical_aperture(1.0, math.radians(30))
        0.5
    """
    return n * math.sin(theta)


def half_angle_from_na(na: float, n: float = 1.0) -> float:
    """
    Calculate the half-angle from numerical aperture.

    theta = arcsin(NA / n)

    Args:
        na: Numerical aperture (dimensionless).
        n: Refractive index of the medium (default 1.0 for air).

    Returns:
        Half-angle in radians.
    """
    return math.asin(na / n)