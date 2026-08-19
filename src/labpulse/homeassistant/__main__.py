"""Generate LabPulse Home Assistant configuration."""

import sys

from .cli import main


# Keep this file small. cli.py contains the real command so it can be tested
# without starting another Python process.
if __name__ == "__main__":
    sys.exit(main())
