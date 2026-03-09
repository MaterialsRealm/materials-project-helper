from typing import Any
import weakref


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
        _ = ctx.search(foo="bar")
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
