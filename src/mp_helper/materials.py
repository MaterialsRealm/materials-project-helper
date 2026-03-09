"""Helpers for querying materials by chemical system.

The :func:`download_materials` convenience wrapper performs one or more
searches against ``mpr.materials`` and returns the combined results as a list
of dictionaries.  This module keeps the public API small; more advanced
queries can be issued directly through :func:`mp_helper.api.get_client`.
"""

from typing import Iterable

from .api import get_client


__all__ = ["download_materials"]


MaterialRecord = dict[str, object]  # ``mp_api`` returns pydantic models, but for
# simplicity we convert them to plain mappings in the helper layer.


def download_materials(compositions: str | Iterable[str]) -> list[MaterialRecord]:
    """Download materials for one or more chemical systems.

    Parameters
    ----------
    compositions:
        A single chemical system string such as ``"Fe-Co"`` or an iterable of
        such strings.  Each string is passed to the Materials Project API as
        ``chemsys``.

    Returns
    -------
    list[MaterialRecord]
        A flat list containing every record returned by ``mpr.materials.search``
        for each chemical system.  The raw objects returned by ``mp-api`` are
        converted to dictionaries for convenience (this also makes the helper
        easier to test).

    Notes
    -----
    The helper simply wraps :func:`mp_helper.api.get_client` and issues one
    query per chemical system.  It does **not** perform any caching or rate
    limiting; callers who need those features should implement them
    themselves.
    """

    if isinstance(compositions, str):
        comps = [compositions]
    else:
        comps = list(compositions)

    results: list[MaterialRecord] = []

    with get_client() as mpr:
        for comp in comps:
            # ``mp-api`` returns a generator-like ``SearchResults`` object; we
            # convert each item to a dict because the user of this helper may be
            # expecting plain data structures and it makes testing simpler.
            for item in mpr.materials.search(chemsys=comp):
                # ``item`` may already have a ``dict`` method, so use it when
                # available.
                results.append(item.dict() if hasattr(item, "dict") else item)

    return results
