"""Helpers for querying materials by chemical system.

This module exposes a single helper class, :class:`MaterialsSearcher`, which
wraps an ``mpr.materials`` client.  It provides a thin interface to issue
searches and to obtain ``MPRelaxSet`` objects without burdening callers with
client instantiation or configuration details.  Advanced usage may bypass
the helper by calling :func:`mp_helper.api.get_client` directly.
"""

import time
import warnings
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from csv import DictReader, reader
from pathlib import Path
from typing import Any

from emmet.core.mpid import MPID
from emmet.core.vasp.material import MaterialsDoc
from mp_api.client.core.exceptions import MPRestError
from pymatgen.core.structure import Structure
from pymatgen.io.vasp.sets import MPRelaxSet

from .api import get_client

__all__ = [
    "MaterialsSearcher",
    "MaterialsSummarySearcher",
    "download_cifs_for_material_ids",
    "download_cifs_from_csv",
    "get_cif_files",
    "get_relax_sets",
    "iter_material_id_batches",
    "material_ids",
]


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

    def search(self, **search_kwargs) -> list[MaterialsDoc]:
        """Return raw records matching the given query.

        The results are typically ``MaterialsDoc`` pydantic models.

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

    def download_relax_sets(self, root_dir: str | Path, **search_kwargs) -> list[Path]:
        """Search and write each result's relax set to disk.

        This helper combines :meth:`search` and :func:`get_relax_sets` to
        generate ``MPRelaxSet`` objects, then writes the VASP input files for
        each set into a subdirectory of ``root_dir`` named after the
        corresponding ``material_id``.

        The directory structure looks like::

            root_dir/
                mp-12345/
                    POSCAR  # etc.
                mp-67890/
                    POTCAR

        ``potcar_spec`` is hard-coded to ``True`` for now; callers who need
        different behaviour can construct their own sets manually.

        Args:
            root_dir: Path to the directory under which material-specific
                folders will be created.  The path is created if it does not
                already exist.
            **search_kwargs: Same filters accepted by :meth:`search` (for
                example ``chemsys`` or ``elements``).

        Returns:
            A list of ``pathlib.Path`` instances corresponding to the
            directories that were created and populated with inputs.
        """
        # Prepare destination
        root = Path(root_dir)
        root.mkdir(parents=True, exist_ok=True)
        # Perform the query and convert to relax sets
        records = self.search(**search_kwargs)
        relax_sets = get_relax_sets(records)
        ids = material_ids(records)
        paths: list[Path] = []
        for mpid, rset in zip(ids, relax_sets):
            dest = root / mpid
            dest.mkdir(parents=True, exist_ok=True)
            rset.write_input(dest, potcar_spec=True)
            paths.append(dest)

        return paths

    def download_cifs(
        self,
        root_dir: str | Path,
        *,
        batch_size: int | None = None,
        skip_existing: bool = False,
        **search_kwargs,
    ) -> list[Path]:
        """Search for materials and write their CIF files to disk.

        This helper runs :meth:`search` and writes one CIF for each record that
        contains a structure. Each material is written to
        ``<root_dir>/<material_id>/<material_id>.cif``. When ``material_ids``
        is present in ``search_kwargs`` and ``batch_size`` is provided, the
        request is executed in batches so large explicit ID lists do not need to
        materialize in one API call.

        Args:
            root_dir: Directory under which per-material subdirectories are
                created.
            batch_size: Optional size for batched requests when
                ``material_ids`` is supplied.
            skip_existing: If ``True``, skip materials whose CIF file already
                exists under ``root_dir``.
            **search_kwargs: Keyword filters accepted by :meth:`search`.

        Returns:
            Paths to the CIF files written during this call.
        """
        material_ids_arg = search_kwargs.get("material_ids")
        if batch_size is not None and material_ids_arg is not None:
            return self.download_cifs_for_material_ids(
                root_dir,
                material_ids=material_ids_arg,
                batch_size=batch_size,
                skip_existing=skip_existing,
                **{
                    key: value
                    for key, value in search_kwargs.items()
                    if key != "material_ids"
                },
            )

        records = self.search(**search_kwargs)
        return get_cif_files(root_dir, records, skip_existing=skip_existing)

    def download_cifs_for_material_ids(
        self,
        root_dir: str | Path,
        material_ids: Iterable[MPID],
        *,
        batch_size: int = 1000,
        skip_existing: bool = False,
        **search_kwargs,
    ) -> list[Path]:
        """Download CIFs for an explicit material-ID sequence in batches.

        Args:
            root_dir: Directory under which per-material subdirectories are
                created.
            material_ids: Material IDs to request from the Materials Project
                API.
            batch_size: Number of material IDs to include in each API request.
            skip_existing: If ``True``, skip IDs whose CIF file already exists
                under ``root_dir``.
            **search_kwargs: Additional keyword filters forwarded to
                :meth:`search`. Any user-provided ``fields`` are merged with the
                required ``material_id`` and ``structure`` fields.

        Returns:
            Paths to the CIF files written during this call.

        Raises:
            ValueError: If ``batch_size`` is not a positive integer.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")

        root = Path(root_dir)
        root.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        fields = _merge_fields(search_kwargs.pop("fields", None))
        for batch in iter_material_id_batches(
            material_ids,
            batch_size=batch_size,
            root_dir=root if skip_existing else None,
        ):
            records = self.search(material_ids=batch, fields=fields, **search_kwargs)
            paths.extend(get_cif_files(root, records, skip_existing=skip_existing))
        return paths


class MaterialsSummarySearcher:
    """Paged helper for the Materials Project summary route.

    This wrapper is intended for summary-table style workloads where callers
    want to keep memory bounded and process one page of results at a time.
    Unlike :class:`MaterialsSearcher`, this helper targets
    ``mpr.materials.summary`` rather than full materials documents.
    """

    def __init__(self, mpr=None):
        if mpr is None:
            self._mpr = get_client()
            self._owns_client = True
        else:
            self._mpr = mpr
            self._owns_client = False

    def __del__(self):
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

    def iter_search_chunks(
        self,
        *,
        criteria: dict | None = None,
        fields: list[str] | None = None,
        chunk_size: int = 1000,
        num_chunks: int | None = None,
        limit: int | None = None,
        all_fields: bool = False,
    ) -> Iterator[list[object]]:
        """Yield summary results one page at a time.

        Args:
            criteria: Low-level summary-route query parameters.
            fields: Explicit summary fields to fetch.
            chunk_size: Maximum number of documents per page.
            num_chunks: Optional limit on the number of pages to fetch.
            limit: Optional limit on total documents to fetch.
            all_fields: Whether to request full summary documents.
        """
        if chunk_size <= 0:
            raise ValueError("`chunk_size` must be a positive integer")
        if num_chunks is not None and num_chunks <= 0:
            raise ValueError("`num_chunks` must be positive or None")
        if limit is not None and limit <= 0:
            raise ValueError("`limit` must be positive or None")

        base_criteria = dict(criteria or {})
        if num_chunks is None and limit is None and not base_criteria:
            warnings.warn(
                "MaterialsSummarySearcher is executing an unbounded summary query. "
                "Use chunked iteration and write each page out promptly for large exports.",
                stacklevel=2,
            )

        skip = 0
        yielded = 0
        for request_chunk_size in iter_request_chunk_sizes(
            chunk_size=chunk_size,
            num_chunks=num_chunks,
            limit=limit,
        ):
            page_criteria = {**base_criteria, "_skip": skip}
            if all_fields and not fields:
                page_criteria["_all_fields"] = True

            page = self._mpr.materials.summary._query_resource(
                criteria=page_criteria,
                fields=fields,
                chunk_size=request_chunk_size,
                num_chunks=1,
                use_document_model=yielded == 0,
            )
            docs = page.get("data", [])
            if not docs:
                break

            if limit is not None:
                remaining = limit - skip
                if len(docs) > remaining:
                    docs = docs[:remaining]

            yield docs
            yielded += 1
            skip += len(docs)

            if limit is not None and skip >= limit:
                break

    def search(
        self,
        *,
        criteria: dict | None = None,
        fields: list[str] | None = None,
        chunk_size: int = 1000,
        num_chunks: int | None = None,
        limit: int | None = None,
        all_fields: bool = False,
    ) -> list[object]:
        """Materialize summary-route results into a list."""
        results: list[object] = []
        for chunk in self.iter_search_chunks(
            criteria=criteria,
            fields=fields,
            chunk_size=chunk_size,
            num_chunks=num_chunks,
            limit=limit,
            all_fields=all_fields,
        ):
            results.extend(chunk)
        return results


def get_relax_sets(records: list[MaterialsDoc]) -> list[MPRelaxSet]:
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

            structure = Structure.from_dict(struct_json)

        sets.append(MPRelaxSet(structure))  # type: ignore[call-arg]
    return sets


def get_cif_files(
    root_dir: str | Path,
    records: list[MaterialsDoc],
    *,
    skip_existing: bool = False,
) -> list[Path]:
    """Write CIF files for each record that contains a structure.

    Args:
        root_dir: Path to the directory under which per-material subfolders are
            created.
        records: Sequence of raw material documents returned by the
            Materials Project API.
    Returns:
        A list of ``pathlib.Path`` instances corresponding to the written CIF
        files.
    """
    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for rec in records:
        if isinstance(rec, dict):
            mpid = rec.get("material_id")
            struct_json = rec.get("structure")
        else:
            mpid = getattr(rec, "material_id", None)
            struct_json = getattr(rec, "structure", None)

        if mpid is None or struct_json is None:
            continue

        # If it's already a Structure object we can use it directly
        if isinstance(struct_json, Structure):
            structure = struct_json
        else:
            # Unpack any convenient converter methods
            if hasattr(struct_json, "dict"):
                struct_json = struct_json.dict()

            structure = Structure.from_dict(struct_json)

        dest = root / mpid
        dest.mkdir(parents=True, exist_ok=True)
        out_path = dest / f"{mpid}.cif"
        if skip_existing and out_path.exists():
            continue
        structure.to(filename=str(out_path))
        paths.append(out_path)
    return paths


def iter_material_id_batches(
    material_ids: Iterable[MPID],
    *,
    batch_size: int = 1000,
    root_dir: str | Path | None = None,
) -> Iterator[list[str]]:
    """Yield normalized material IDs in fixed-size batches.

    Args:
        material_ids: Sequence of raw material IDs to normalize and batch.
        batch_size: Maximum number of IDs to include in each yielded batch.
        root_dir: Optional download directory used to skip IDs whose
            ``<material_id>/<material_id>.cif`` file already exists.

    Yields:
        Lists of normalized material IDs.

    Raises:
        ValueError: If ``batch_size`` is not a positive integer.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")

    root = Path(root_dir) if root_dir is not None else None
    batch: list[str] = []
    for raw_mpid in material_ids:
        mpid = str(raw_mpid).strip()
        if not mpid:
            continue
        if root is not None and (root / mpid / f"{mpid}.cif").exists():
            continue
        batch.append(mpid)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def iter_material_ids_from_csv(
    csv_path: str | Path,
    *,
    material_id_column: str | int = 0,
) -> Iterator[str]:
    """Yield material IDs from a CSV using either a header name or index."""
    path = Path(csv_path)
    with path.open(newline="") as handle:
        if isinstance(material_id_column, str):
            csv_reader = DictReader(handle)
            for row in csv_reader:
                value = row.get(material_id_column)
                if value:
                    yield value.strip()
            return

        csv_reader = reader(handle)
        # Skip header row
        next(csv_reader, None)
        for row in csv_reader:
            if material_id_column < len(row):
                value = row[material_id_column].strip()
                if value:
                    yield value


def _merge_fields(fields: list[str] | None) -> list[str]:
    """Ensure CIF downloads request the minimum required fields."""
    merged = list(fields or [])
    for field in ("material_id", "structure"):
        if field not in merged:
            merged.append(field)
    return merged


def _download_cif_batch(
    material_ids: list[str],
    *,
    root_dir: str | Path,
    config_path: str | Path | None = None,
    skip_existing: bool = False,
    search_kwargs: dict[str, Any] | None = None,
    retry_attempts: int = 5,
    backoff_seconds: float = 5.0,
) -> list[Path]:
    """Download one material-ID batch with an isolated client."""
    for attempt in range(1, retry_attempts + 1):
        try:
            with get_client(config_path) as mpr:
                searcher = MaterialsSearcher(mpr=mpr)
                return searcher.download_cifs_for_material_ids(
                    root_dir,
                    material_ids,
                    batch_size=len(material_ids),
                    skip_existing=skip_existing,
                    **(search_kwargs or {}),
                )
        except MPRestError as exc:
            if "429" not in str(exc) or attempt >= retry_attempts:
                raise
            time.sleep(backoff_seconds * attempt)
    return []


def download_cifs_for_material_ids(
    root_dir: str | Path,
    material_ids: Iterable[MPID],
    *,
    batch_size: int = 1000,
    max_workers: int = 1,
    config_path: str | Path | None = None,
    skip_existing: bool = False,
    retry_attempts: int = 5,
    backoff_seconds: float = 5.0,
    **search_kwargs,
) -> list[Path]:
    """Download CIFs for a large explicit material-ID list.

    This helper creates one isolated MP client per worker so the underlying
    client is never shared across threads. The workload is API- and
    network-bound, so ``max_workers`` should stay conservative.

    Args:
        root_dir: Directory under which per-material subdirectories are
            created.
        material_ids: Material IDs to request from the Materials Project API.
        batch_size: Number of material IDs to include in each API request.
        max_workers: Number of worker threads used to process batches.
        config_path: Optional configuration file or directory forwarded to
            :func:`get_client`.
        skip_existing: If ``True``, skip IDs whose CIF file already exists
            under ``root_dir``.
        retry_attempts: Number of times to retry a batch after a 429 response.
        backoff_seconds: Base delay used for linear backoff between retries.
        **search_kwargs: Additional keyword filters forwarded to
            :meth:`MaterialsSearcher.search`.

    Returns:
        Paths to the CIF files written during this call.

    Raises:
        ValueError: If ``batch_size`` or ``max_workers`` is not a positive
            integer.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be a positive integer")
    if max_workers <= 0:
        raise ValueError("max_workers must be a positive integer")

    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    fields = _merge_fields(search_kwargs.pop("fields", None))
    batches = list(
        iter_material_id_batches(
            material_ids,
            batch_size=batch_size,
            root_dir=root if skip_existing else None,
        )
    )
    if not batches:
        return []

    kwargs = {**search_kwargs, "fields": fields}
    if max_workers == 1:
        with get_client(config_path) as mpr:
            searcher = MaterialsSearcher(mpr=mpr)
            paths: list[Path] = []
            for batch in batches:
                paths.extend(
                    searcher.download_cifs_for_material_ids(
                        root,
                        batch,
                        batch_size=len(batch),
                        skip_existing=skip_existing,
                        **kwargs,
                    )
                )
            return paths

    paths: list[Path] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _download_cif_batch,
                batch,
                root_dir=root,
                config_path=config_path,
                skip_existing=skip_existing,
                search_kwargs=kwargs,
                retry_attempts=retry_attempts,
                backoff_seconds=backoff_seconds,
            )
            for batch in batches
        ]
        for future in as_completed(futures):
            paths.extend(future.result())
    return paths


def download_cifs_from_csv(
    csv_path: str | Path,
    root_dir: str | Path,
    *,
    batch_size: int = 1000,
    max_workers: int = 1,
    material_id_column: str | int = "material_id",
    config_path: str | Path | None = None,
    skip_existing: bool = False,
    retry_attempts: int = 5,
    backoff_seconds: float = 5.0,
    **search_kwargs,
) -> list[Path]:
    """Read material IDs from a CSV and download CIFs in batches.

    Args:
        csv_path: CSV file containing material IDs.
        root_dir: Directory under which per-material subdirectories are
            created.
        batch_size: Number of material IDs to include in each API request.
        max_workers: Number of worker threads used to process batches.
        material_id_column: Header name or zero-based column index containing
            the material ID values.
        config_path: Optional configuration file or directory forwarded to
            :func:`get_client`.
        skip_existing: If ``True``, skip IDs whose CIF file already exists
            under ``root_dir``.
        retry_attempts: Number of times to retry a batch after a 429 response.
        backoff_seconds: Base delay used for linear backoff between retries.
        **search_kwargs: Additional keyword filters forwarded to
            :meth:`MaterialsSearcher.search`.

    Returns:
        Paths to the CIF files written during this call.
    """
    return download_cifs_for_material_ids(
        root_dir,
        iter_material_ids_from_csv(csv_path, material_id_column=material_id_column),
        batch_size=batch_size,
        max_workers=max_workers,
        config_path=config_path,
        skip_existing=skip_existing,
        retry_attempts=retry_attempts,
        backoff_seconds=backoff_seconds,
        **search_kwargs,
    )


def material_ids(records: list[MaterialsDoc]) -> list[MPID]:
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


def iter_request_chunk_sizes(
    chunk_size: int,
    num_chunks: int | None,
    limit: int | None,
) -> Iterator[int]:
    """Produce a series of per-request chunk sizes given constraints.

    Rules:
    - num_chunks and limit can both be None (unbounded mode): produce
      chunk_size forever until upstream page is empty.
    - limit=None, num_chunks set: produce `num_chunks` chunks of `chunk_size`.
    - num_chunks=None, limit set: produce chunks sized at most `chunk_size`
      until total hits `limit`.
    - both set: produce chunks exactly as above, and stop when either `requested >= num_chunks`
      or `remaining <= 0`. That is, when both limits are present, the effective total
      retrieved is limited by the first of `num_chunks * chunk_size` or `limit`.

    Returns:
        Iterator over each request's chunk_size.
    """
    if chunk_size <= 0:
        raise ValueError("`chunk_size` must be a positive integer")
    if num_chunks is not None and num_chunks <= 0:
        raise ValueError("`num_chunks` must be positive or None")
    if limit is not None and limit <= 0:
        raise ValueError("`limit` must be positive or None")

    remaining = limit
    requested = 0
    while True:
        if num_chunks is not None and requested >= num_chunks:
            break
        if remaining is not None and remaining <= 0:
            break

        next_chunk = chunk_size if remaining is None else min(chunk_size, remaining)
        yield next_chunk

        requested += 1
        if remaining is not None:
            remaining -= next_chunk

        if remaining is not None and remaining <= 0:
            break
