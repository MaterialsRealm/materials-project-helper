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
