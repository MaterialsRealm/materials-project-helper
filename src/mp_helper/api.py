import time
from pathlib import Path

from mp_api.client import MPRester

from .config import MPSettings

__all__ = ["get_client", "open_client", "throttle_pause"]


def throttle_pause(
    count: int, pause_after: int = 20, pause_seconds: float = 1.1
) -> None:
    """Pause execution periodically to avoid API rate limiting."""
    if pause_after <= 0 or pause_seconds <= 0:
        return

    if count > 0 and count % pause_after == 0:
        print(f"Paused after {count} steps to avoid API rate limits")
        time.sleep(pause_seconds)


def get_client(config_path: str | Path | None = None, **mpr_kwargs: object) -> MPRester:
    """Return an :class:`mp_api.client.MPRester` instance.

    Parameters
    ----------
    config_path
        Optional path to a configuration file or directory; see
        :meth:`MPSettings.load` for supported formats.  If omitted the key is
        read from the environment (and ``.env`` in the current directory).
    **mpr_kwargs
        Any additional keyword arguments are forwarded to the ``MPRester``
        constructor (for example ``endpoint`` or ``timeout``).
    """

    settings = MPSettings.load(config_path)
    return MPRester(settings.mp_api_key, **mpr_kwargs)


# context-manager alias


def open_client(
    config_path: str | Path | None = None, **mpr_kwargs: object
) -> MPRester:
    """Context manager that yields an :class:`MPRester`.

    This is simply a thin wrapper around :func:`get_client` that ensures the
    client is closed when the ``with`` block exits.
    """

    return get_client(config_path, **mpr_kwargs)
