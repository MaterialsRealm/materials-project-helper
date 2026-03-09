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


MaterialRecord = object  # whatever ``mpr.materials.search`` yields (typically
# pydantic models).  We do not mutate or convert the results, preserving the
# original types so callers can access attributes directly.


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

        The keyword arguments mirror the signature of
        :meth:`mp_api.client.routes.materials.materials.MaterialsRester.search`.
        Commonly-used parameters are listed below, but any argument supported
        by the client is accepted.

        Args:
            material_ids (str | list[str] | None): One or more MP material
                identifiers.
            chemsys (str | list[str] | None): Chemical system(s) (e.g.
                ``"Fe-Co"`` or ``["Si-O"]``).
            crystal_system (CrystalSystem | None): crystal system filter.
            density (tuple[float, float] | None): min/max density.
            deprecated (bool | None): filter deprecated materials.
            elements (list[str] | None): include these elements.
            exclude_elements (list[str] | None): exclude these elements.
            formula (str | list[str] | None): formula or wildcard.
            num_elements (tuple[int, int] | None): element-count range.
            num_sites (tuple[int, int] | None): site-count range.
            spacegroup_number (int | None): space group number.
            spacegroup_symbol (str | None): space group symbol.
            task_ids (list[str] | None): specific task identifiers.
            volume (tuple[float, float] | None): volume range.
            num_chunks (int | None): number of result chunks.
            chunk_size (int): size of each chunk.
            all_fields (bool): whether to return all fields.
            fields (list[str] | None): explicit list of fields to fetch.
            **search_kwargs: Other keyword arguments are passed through.

        Returns:
            list[MaterialRecord]: A flat list containing every record returned by
                the API.  The helper does not modify the objects; they are
                returned exactly as produced by ``mpr.materials.search``.
        """
        results: list[MaterialRecord] = []
        with get_client() as mpr:
            for item in mpr.materials.search(**search_kwargs):
                results.append(item)
        return results

    def download_relax_sets(self, **search_kwargs) -> list["MPRelaxSet"]:
        """Return ``MPRelaxSet`` objects for materials matching ``search_kwargs``.

        The semantics mirror :meth:`download_materials`; any argument that may be
        passed to ``mpr.materials.search`` is accepted.  Records lacking a
        ``structure`` field are silently skipped.
        """
        sets: list["MPRelaxSet"] = []
        for rec in self.download_materials(**search_kwargs):
            struct_json = rec.get("structure")
            if struct_json is None:
                continue
            structure = Structure.from_dict(struct_json)  # type: ignore[attr-defined]
            sets.append(MPRelaxSet(structure))  # type: ignore[call-arg]
        return sets
