"""Helpers for querying materials by chemical system.

The :func:`download_materials` convenience wrapper performs one or more
searches against ``mpr.materials`` and returns the combined results as a list
of dictionaries.  This module keeps the public API small; more advanced
queries can be issued directly through :func:`mp_helper.api.get_client`.
"""

from typing import Iterable

from .api import get_client


__all__ = ["download_materials", "download_relax_sets"]


MaterialRecord = dict[str, object]  # ``mp_api`` returns pydantic models, but for
# simplicity we convert them to plain mappings in the helper layer.

# ``download_relax_sets`` is an optional helper that needs pymatgen.  We
# import lazily at module load so callers can still use other helpers even if
# pymatgen isn't installed.  The local names are initialized to ``None`` and
# validated inside the helper.
try:
    from pymatgen.core.structure import Structure  # type: ignore[import]
    from pymatgen.io.vasp.sets import MPRelaxSet  # type: ignore[import]
except ImportError:  # pragma: no cover - difficult to simulate in tests
    Structure = None  # type: ignore[assignment]
    MPRelaxSet = None  # type: ignore[assignment]


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


def download_relax_sets(compositions: str | Iterable[str]) -> list["MPRelaxSet"]:
    """Return :class:`~pymatgen.io.vasp.sets.MPRelaxSet` objects for each
    material in the given chemical system(s).

    This is a thin convenience wrapper around :func:`download_materials`.  For
    each record the helper attempts to construct a :class:`pymatgen`
    ``Structure`` from the serialized ``structure`` field and then instantiates
    ``MPRelaxSet`` with that structure.

    Parameters
    ----------
    compositions
        Single system string or iterable of strings, same semantics as
        :func:`download_materials`.

    Returns
    -------
    list[MPRelaxSet]
        One relaxation input set per material whose JSON emitted by the API
        contained a ``structure`` key.  Materials lacking structural data are
        skipped.

    Raises
    ------
    ImportError
        If ``pymatgen`` is not installed; the function imports the required
        classes lazily so that users who never need this helper are not forced
        to install the dependency.
    """

    if Structure is None or MPRelaxSet is None:  # pragma: no cover - import error path
        raise ImportError("pymatgen is required to build MPRelaxSet objects")

    sets: list["MPRelaxSet"] = []
    for rec in download_materials(compositions):
        struct_json = rec.get("structure")
        if struct_json is None:
            continue
        # `Structure.from_dict` handles both raw dicts and the JSON format
        structure = Structure.from_dict(struct_json)  # type: ignore[attr-defined]
        sets.append(MPRelaxSet(structure))  # type: ignore[call-arg]

    return sets
