"""Helpers for querying materials by chemical system.

This module exposes a single helper class, :class:`MaterialsSearcher`, which
wraps an ``mpr.materials`` client.  It provides a thin interface to issue
searches and to obtain ``MPRelaxSet`` objects without burdening callers with
client instantiation or configuration details.  Advanced usage may bypass
the helper by calling :func:`mp_helper.api.get_client` directly.
"""

from emmet.core.mpid import MPID
from emmet.core.vasp.material import MaterialsDoc
from pymatgen.core.structure import Structure
from pymatgen.io.vasp.sets import MPRelaxSet

from .api import get_client

__all__ = ["MaterialsSearcher", "get_relax_sets", "material_ids"]


class MaterialsSearcher:
    """Lightweight wrapper around an ``mpr.materials`` client.

    The constructor accepts an optional ``mpr`` object (an
    :class:`mp_api.client.MPRester` instance).  If none is provided the helper
    will call :func:`mp_helper.api.get_client()` to create its own client; in
    that case the helper will also close the client when it is garbage-
    collected.  The underlying client is exposed via the read-only
    :attr:`mpr` property so callers can reuse it for other operations.

    If you create a helper without supplying a client you should either
    explicitly close it when finished (by deleting it or using it as a
    context manager) or trust the destructor to clean up; using ``with`` is
    the recommended pattern to avoid lingering connections.

    The two public methods mirror the core ``search`` functionality:
    ``search`` returns the raw documents, and ``get_relax_sets`` converts
    records obtained from :meth:`search` into ``MPRelaxSet`` objects.  Both
    methods accept whatever keyword arguments the Materials Project API
    supports (``chemsys``, ``elements``, ``density`` etc.).  Positional
    arguments are not accepted; supply filters by keyword only.
    """

    def __init__(self, mpr=None):
        """Initialize the helper.

        Args:
            mpr: Optional ``MPRester`` instance.  If omitted the helper will
                create one from :func:`get_client` and take responsibility for
                closing it.
        """
        if mpr is None:
            self._mpr = get_client()
            self._owns_client = True
        else:
            self._mpr = mpr
            self._owns_client = False

    @property
    def mpr(self):
        """The underlying :class:`MPRester` client (read-only)."""
        return self._mpr

    def __del__(self):
        # Close owned client when garbage-collected; ignore if already closed
        if getattr(self, "_owns_client", False) and self._mpr is not None:
            try:
                self._mpr.close()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if getattr(self, "_owns_client", False) and self._mpr is not None:
            try:
                self._mpr.close()
            except Exception:
                pass

    def search(self, *, as_dict: bool = False, **search_kwargs) -> list[MaterialsDoc]:
        """Return raw records matching the given query.

        The results are typically ``MaterialsDoc`` pydantic models, which
        expose many methods and internal attributes when inspected.  If
        ``as_dict`` is ``True`` each record will be converted to a plain
        dictionary via the model's :meth:`dict` method (falling back to the
        object itself when that method is unavailable).

        The keyword arguments mirror the signature of
        :meth:`mp_api.client.routes.materials.materials.MaterialsRester.search`.

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
            list[MaterialsDoc]: A flat list containing every record returned by
                the API.  The helper does not modify the objects; they are
                returned exactly as produced by ``mpr.materials.search``.
        """
        results: list[MaterialsDoc] = []
        # Use the stored client rather than opening a fresh one each call
        for item in self._mpr.materials.search(**search_kwargs):
            if as_dict and hasattr(item, "dict"):
                results.append(item.dict())
            else:
                results.append(item)
        return results

    def get_relax_sets(self, **search_kwargs) -> list[MPRelaxSet]:
        """Convenience method mirroring :meth:`search`.

        The keywords are passed through to :meth:`search`, and the returned
        sequence of records is then handed off to the module-level
        :func:`get_relax_sets` helper for conversion.  This keeps the class
        method lightweight and allows callers to process arbitrary collections
        of records without needing an instance.
        """
        return get_relax_sets(self.search(**search_kwargs))


def get_relax_sets(records: list[MaterialRecord]) -> list[MPRelaxSet]:
    """Convert a sequence of materials records to ``MPRelaxSet`` objects.

    This logic was previously embedded in :class:`MaterialsSearcher`.  The
    standalone helper accepts *any* iterable of records, where each record may
    be a mapping-like object or a pydantic model; records without a
    ``structure`` field are silently ignored.  This makes it easier to reuse
    the conversion code outside of the search helper (for example, when
    combining results from multiple queries).

    Args:
        records: Sequence of raw material documents returned by the
            Materials Project API.

    Returns:
        A list of ``MPRelaxSet`` instances constructed from the structures
        present in the input records.
    """
    sets: list[MPRelaxSet] = []
    for rec in records:
        # ``rec`` could be a dict-like object, a pydantic model.  Grab the
        # serialized structure data however we can.
        if isinstance(rec, dict):
            struct_json = rec.get("structure")
        else:
            struct_json = getattr(rec, "structure", None)

        if struct_json is None:
            continue

        # If it's already a Structure object we can use it directly
        if isinstance(struct_json, Structure):
            structure = struct_json
        else:
            # Unpack any convenient converter methods
            if hasattr(struct_json, "dict"):
                struct_json = struct_json.dict()
            elif hasattr(struct_json, "as_dict"):
                struct_json = struct_json.as_dict()

            structure = Structure.from_dict(struct_json)

        sets.append(MPRelaxSet(structure))  # type: ignore[call-arg]
    return sets


def material_ids(records: list[MaterialRecord]) -> list[MPID]:
    """Extract ``material_id`` values from a sequence of records.

    The input may contain either mapping-like objects (e.g. dictionaries) or
    Pydantic models with attributes.  We silently ignore records that lack a
    ``material_id`` field so callers can safely pass mixed lists.

    Args:
        records: List of records returned by :meth:`MaterialsSearcher.search` or
            similar APIs.

    Returns:
        A list of the material identifiers present in the input, in the same
        order as the original records.
    """
    ids: list[MPID] = []
    for rec in records:
        if isinstance(rec, dict):
            mpid = rec.get("material_id")
        else:
            mpid = getattr(rec, "material_id", None)

        if mpid is not None:
            ids.append(mpid)
    return ids
