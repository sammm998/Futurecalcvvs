"""Return unused native allocations between bounded analysis stages on Linux."""
import ctypes
import gc
import sys


def release_unused_memory():
    # ONNX/PDF buffers can be freed by Python but still retained by glibc. Do not
    # change image resolution, OCR coverage, or any live analysis objects.
    gc.collect()
    if not sys.platform.startswith('linux'):
        return
    try:
        trim = ctypes.CDLL(None).malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        trim(0)
    except (AttributeError, OSError):
        pass  # musl and other allocators do not expose glibc's optional hook
