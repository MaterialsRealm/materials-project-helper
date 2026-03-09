from typing import Any


def test_download_single_and_multiple(monkeypatch):
    # stub out the MPRester so we can inspect calls
    class DummyMaterials:
        def __init__(self):
            self.queries: list[Any] = []

        def search(self, **kwargs):
            self.queries.append(kwargs)
            # return a list of simple dict-like objects
            return [{"chemsys": kwargs.get("chemsys"), "foo": "bar"}]

    class DummyClient:
        def __init__(self, api_key, **kwargs):
            self.materials = DummyMaterials()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("mp_helper.api.MPRester", DummyClient)

    from mp_helper.materials import download_materials

    # single string should produce a list with one query
    out = download_materials("Fe-Co")
    assert out == [{"chemsys": "Fe-Co", "foo": "bar"}]

    # multiple values should concatenate results
    out = download_materials(["Fe-Co", "Fe-O"])
    assert out == [
        {"chemsys": "Fe-Co", "foo": "bar"},
        {"chemsys": "Fe-O", "foo": "bar"},
    ]

    # iterable types other than list work as well
    out = download_materials(("Fe-Co", "Fe-C"))
    assert out == [
        {"chemsys": "Fe-Co", "foo": "bar"},
        {"chemsys": "Fe-C", "foo": "bar"},
    ]

    # empty input yields an empty list instead of error
    assert download_materials([]) == []


def test_download_relax_sets(monkeypatch):
    """Ensure MPRelaxSet is constructed from the structure JSON"""

    # monkeypatch the lower-level client as before
    class DummyMaterials:
        def __init__(self):
            self.queries = []

        def search(self, **kwargs):
            self.queries.append(kwargs)
            return [{"structure": {"foo": "bar"}}]

    class DummyClient:
        def __init__(self, api_key, **kwargs):
            self.materials = DummyMaterials()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("mp_helper.api.MPRester", DummyClient)

    # stub out pymatgen classes by overriding module attributes
    class DummyStructure:
        @classmethod
        def from_dict(cls, d):
            assert d == {"foo": "bar"}
            return "struct"

    class DummyRelaxSet:
        def __init__(self, struct):
            self.struct = struct

    import mp_helper.materials as materials_mod
    monkeypatch.setattr(materials_mod, "Structure", DummyStructure)
    monkeypatch.setattr(materials_mod, "MPRelaxSet", DummyRelaxSet)

    from mp_helper.materials import download_relax_sets

    out = download_relax_sets("X")
    assert len(out) == 1
    assert isinstance(out[0], DummyRelaxSet)
    assert out[0].struct == "struct"
