"""Helpers for querying materials by chemical system.

The :func:`download_materials` convenience wrapper performs one or more
searches against ``mpr.materials`` and returns the combined results as a list
of dictionaries.  This module keeps the public API small; more advanced
queries can be issued directly through :func:`mp_helper.api.get_client`.
"""

from pymatgen.core.structure import Structure
from pymatgen.io.vasp.sets import MPRelaxSet

from .api import get_client

__all__ = ["MaterialsSearcher"]


MaterialRecord = dict[str, object]  # ``mp_api`` returns pydantic models, but for
# simplicity we convert them to plain mappings in the helper layer.


class MaterialsSearcher:
    """Convenience wrapper around ``mpr.materials.search``.

    Each instance simply opens a fresh ``MPRester`` using
    :func:`mp_helper.api.get_client`.  The two key operations from the earlier
    version are provided as methods, which accept *any* keyword argument that
    the underlying ``search`` call supports.  In other words, callers may use
    ``chemsys`` (the usual case), ``elements``, ``density=(0,5)``,
    ``formula="Fe2O3"``, etc.  Positional arguments are **not** accepted;
    all filters must be provided as keywords.
    """

    def download_materials(self, **search_kwargs) -> list[MaterialRecord]:
        """Return raw records matching the given query.

        Parameters
        ----------
        search_kwargs:
            Keyword arguments directly forwarded to
            ``mpr.materials.search``.  Consult the Materials Project API
            documentation for the full list of available filters (for example
            ``chemsys``, ``elements``, ``density``, ``material_ids``, etc.).

        Returns
        -------
        list[MaterialRecord]
            A flat list containing every record returned by the API.  Objects
            that implement ``dict()`` are converted to plain dictionaries.
        """
        results: list[MaterialRecord] = []
        with get_client() as mpr:
            for item in mpr.materials.search(**search_kwargs):
                results.append(item.dict() if hasattr(item, "dict") else item)
        return results

    def download_relax_sets(self, **search_kwargs) -> list["MPRelaxSet"]:
        """Return ``MPRelaxSet`` objects for materials matching ``search_kwargs``.

        The semantics mirror :meth:`download_materials`; any argument that may be
        passed to ``mpr.materials.search`` is accepted.  Records lacking a
        ``structure`` field are silently skipped.
        """
        if (
            Structure is None or MPRelaxSet is None
        ):  # pragma: no cover - import error path
            raise ImportError("pymatgen is required to build MPRelaxSet objects")

        sets: list["MPRelaxSet"] = []
        for rec in self.download_materials(**search_kwargs):
            struct_json = rec.get("structure")
            if struct_json is None:
                continue
            structure = Structure.from_dict(struct_json)  # type: ignore[attr-defined]
            sets.append(MPRelaxSet(structure))  # type: ignore[call-arg]
        return sets
