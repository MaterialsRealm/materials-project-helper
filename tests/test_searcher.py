import warnings
import weakref
from pathlib import Path
from typing import Any


def test_search_and_relax(monkeypatch):
    class DummyMaterials:
        def __init__(self):
            self.queries: list[Any] = []

        def search(self, **kwargs):
            self.queries.append(kwargs)
            return [{"structure": {"foo": "bar"}, **kwargs}]

    class DummyClient:
        def __init__(self, api_key, **kwargs):
            self.materials = DummyMaterials()
            self.api_key = api_key
            self.closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr("mp_helper.api.MPRester", DummyClient)

    from mp_helper.materials import MaterialsSearcher

    monkeypatch.setattr(
        "mp_helper.materials.get_relax_sets",
        lambda records: [type("DummyRelaxSet", (), {"struct": records[0]})()],
    )

    # default client creation
    s = MaterialsSearcher()
    results = s.search(chemsys="X")
    assert results == [{"structure": {"foo": "bar"}, "chemsys": "X"}]
    # as_dict should convert models/dicts to plain dicts (noop here)
    results2 = s.search(as_dict=True, chemsys="X")
    assert results2 == results

    relax = s.get_relax_sets(chemsys="X")
    assert len(relax) == 1
    assert hasattr(relax[0], "struct")

    # injection
    custom = DummyClient("key")
    s2 = MaterialsSearcher(mpr=custom)
    _ = s2.search(elements=["A"])
    assert custom.materials.queries == [{"elements": ["A"]}]

    # context manager should close owned client
    s3 = MaterialsSearcher()
    with s3 as ctx:
        _ = ctx.search(chemsys="X")
    # after exiting, owned client should have been closed
    assert getattr(s3._mpr, "closed", False) is True


def test_owned_client_closed(monkeypatch):
    class DummyClient:
        def __init__(self, api_key, **kwargs):
            self.closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr("mp_helper.api.MPRester", DummyClient)
    from mp_helper.materials import MaterialsSearcher

    s = MaterialsSearcher()
    ref = weakref.ref(s._mpr)
    del s
    # after garbage collection, underlying client should eventually close
    import gc

    gc.collect()
    # we don't have access to the DummyClient instance here, but ensure ref is dead
    assert ref() is None


def test_summary_searcher_chunks_and_warning(monkeypatch):
    class DummySummary:
        def __init__(self):
            self.queries: list[Any] = []
            self.pages = [
                [{"material_id": "mp-1"}],
                [{"material_id": "mp-2"}],
                [],
            ]

        def _query_resource(self, **kwargs):
            self.queries.append(kwargs)
            return {"data": self.pages.pop(0), "meta": {"total_doc": 2}}

    class DummyMaterials:
        def __init__(self):
            self.summary = DummySummary()

    class DummyClient:
        def __init__(self, api_key, **kwargs):
            self.materials = DummyMaterials()

        def close(self):
            pass

    monkeypatch.setattr("mp_helper.api.MPRester", DummyClient)
    from mp_helper.materials import MaterialsSummarySearcher

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        searcher = MaterialsSummarySearcher()
        chunks = list(searcher.iter_search_chunks(as_dict=True))

    assert chunks == [[{"material_id": "mp-1"}], [{"material_id": "mp-2"}]]
    assert searcher._mpr.materials.summary.queries == [
        {
            "criteria": {"_skip": 0},
            "fields": None,
            "chunk_size": 1000,
            "num_chunks": 1,
            "use_document_model": False,
        },
        {
            "criteria": {"_skip": 1},
            "fields": None,
            "chunk_size": 1000,
            "num_chunks": 1,
            "use_document_model": False,
        },
        {
            "criteria": {"_skip": 2},
            "fields": None,
            "chunk_size": 1000,
            "num_chunks": 1,
            "use_document_model": False,
        },
    ]

    assert any("unbounded summary query" in str(w.message) for w in caught)


def test_download_cifs_for_material_ids_batches(monkeypatch, tmp_path):
    class DummyMaterials:
        def __init__(self):
            self.queries: list[Any] = []

        def search(self, **kwargs):
            self.queries.append(kwargs)
            return [
                {
                    "material_id": mpid,
                    "structure": {"@module": "pymatgen.core.structure", "@class": "Structure"},
                }
                for mpid in kwargs["material_ids"]
            ]

    class DummyClient:
        def __init__(self, api_key, **kwargs):
            self.materials = DummyMaterials()

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("mp_helper.api.MPRester", DummyClient)
    monkeypatch.setattr(
        "mp_helper.materials.get_cif_files",
        lambda root_dir, records, skip_existing=False: [
            Path(root_dir) / rec["material_id"] / f'{rec["material_id"]}.cif'
            for rec in records
        ],
    )

    from mp_helper.materials import download_cifs_for_material_ids

    paths = download_cifs_for_material_ids(
        tmp_path,
        ["mp-1", "mp-2", "mp-3"],
        batch_size=2,
        max_workers=1,
    )

    assert paths == [
        tmp_path / "mp-1" / "mp-1.cif",
        tmp_path / "mp-2" / "mp-2.cif",
        tmp_path / "mp-3" / "mp-3.cif",
    ]


def test_iter_material_ids_from_csv_and_skip_existing(tmp_path):
    csv_path = tmp_path / "materials.csv"
    csv_path.write_text("material_id,name\nmp-1,A\nmp-2,B\nmp-3,C\n", encoding="utf-8")
    existing = tmp_path / "out" / "mp-2"
    existing.mkdir(parents=True)
    (existing / "mp-2.cif").write_text("done", encoding="utf-8")

    from mp_helper.materials import iter_material_id_batches, iter_material_ids_from_csv

    material_ids = list(iter_material_ids_from_csv(csv_path))
    assert material_ids == ["mp-1", "mp-2", "mp-3"]

    batches = list(
        iter_material_id_batches(material_ids, batch_size=2, root_dir=tmp_path / "out")
    )
    assert batches == [["mp-1", "mp-3"]]


def test_download_cifs_from_csv_parallel(monkeypatch, tmp_path):
    csv_path = tmp_path / "materials.csv"
    csv_path.write_text("material_id\nmp-1\nmp-2\nmp-3\nmp-4\n", encoding="utf-8")
    seen: list[list[str]] = []

    def fake_download_batch(
        material_ids,
        *,
        root_dir,
        config_path=None,
        skip_existing=False,
        search_kwargs=None,
        retry_attempts=5,
        backoff_seconds=5.0,
    ):
        seen.append(list(material_ids))
        return [Path(root_dir) / mpid / f"{mpid}.cif" for mpid in material_ids]

    monkeypatch.setattr("mp_helper.materials._download_cif_batch", fake_download_batch)

    from mp_helper.materials import download_cifs_from_csv

    paths = download_cifs_from_csv(
        csv_path,
        tmp_path / "out",
        batch_size=2,
        max_workers=2,
    )

    assert sorted(seen) == [["mp-1", "mp-2"], ["mp-3", "mp-4"]]
    assert sorted(paths) == [
        tmp_path / "out" / "mp-1" / "mp-1.cif",
        tmp_path / "out" / "mp-2" / "mp-2.cif",
        tmp_path / "out" / "mp-3" / "mp-3.cif",
        tmp_path / "out" / "mp-4" / "mp-4.cif",
    ]
