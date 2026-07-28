"""LabPulse monitoring, generation, and alert-delivery packages."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("labpulse")
except PackageNotFoundError:
    __version__ = "0+unknown"
