"""cortex-vec — Vector store CLI for the cortex vault."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("cortex-vec")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0"
