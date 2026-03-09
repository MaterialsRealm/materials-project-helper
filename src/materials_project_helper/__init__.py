"""Top-level package for materials-project-helper.

This project is intentionally very small; helpers for interacting with the
Materials Project API are available via the :mod:`api` submodule.
"""

from .api import get_client as get_client
from .api import open_client as open_client
from .config import MPSettings as MPSettings
