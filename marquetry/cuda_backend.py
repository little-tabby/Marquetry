import numpy as np

from marquetry import Variable

try:
    import cupy as cp
    import cupyx as cpx
    GPU_ENABLE = True

except ImportError:
    GPU_ENABLE = False


def get_array_module(x):
    """Get the array module corresponding to the input variable.

        This function determines whether the input variable is  a :mod:`NumPy` or :mod:`CuPy` array and returns the
        appropriate array module.
        If CuPy is enabled and the input variable is a CuPy array, it returns the CuPy module; otherwise,
        it returns the NumPy module.

        Args:
            x (:class:`marquetry.Variable`, :class:`numpy.ndarray`, or :class:`cupy.ndarray`):
                The input variable or array.

        Returns:
            module: The array module (either NumPy or CuPy) corresponding to the input variable or array.
    """

    if isinstance(x, Variable):
        x = x.data

    if not GPU_ENABLE:
        return np

    xp = cp.get_array_module(x)

    return xp


def as_numpy(x):
    """Convert an input variable or array to a NumPy array.

        This function takes an input variable or array, checks its type, and converts it to a NumPy array
        if it is not already a NumPy array.
        If the input is a scalar, it is converted to a NumPy array as well.

        Args:
            x (:class:`marquetry.Variable`, :class:`numpy.ndarray`, or :class:`cupy.ndarray`): The input variable or array.

        Returns:
            :class:`numpy.ndarray`: The input variable or array as a NumPy array.
    """

    if isinstance(x, Variable):
        x = x.data

    if np.isscalar(x):
        return np.array(x)
    elif isinstance(x, np.ndarray):
        return x

    return cp.asnumpy(x)


def as_cupy(x):
    """Convert an input variable or array to a CuPy array.

        This function takes an input variable or array, checks its type, and converts it to a CuPy array
        if it is not already a CuPy array.
        It raises an exception if CuPy is not enabled.

        Args:
            x (:class:`marquetry.Variable`, :class:`numpy.ndarray`, or :class:`cupy.ndarray`):
                The input variable or array.

        Returns:
            :class:`cupy.ndarray`: The input variable or array as a CuPy array.

    """

    if isinstance(x, Variable):
        x = x.data

    print(type(x))
    if not GPU_ENABLE:
        raise Exception("CuPy cannot be loaded. Install CuPy at first if your machine installed Cuda GPU.")
    return cp.asarray(x)
