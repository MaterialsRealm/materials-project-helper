import os

def test_env_loading(tmp_path, monkeypatch):
    # write a simple .env file
    env = tmp_path / ".env"
    env.write_text("MP_API_KEY=abc123\n")

    # no key in environment initially
    monkeypatch.delenv("MP_API_KEY", raising=False)

    from materials_project_helper.config import MPSettings

    settings = MPSettings.load(env)
    assert settings.mp_api_key == "abc123"
    assert os.environ.get("MP_API_KEY") == "abc123"


def test_directory_search(tmp_path):
    # create a directory with a JSON config
    cfg = tmp_path / "config.json"
    cfg.write_text("{\"mp_api_key\": \"xyz789\"}\n")

    from materials_project_helper.config import MPSettings

    settings = MPSettings.load(tmp_path)
    assert settings.mp_api_key == "xyz789"


def test_missing_file(tmp_path):
    from materials_project_helper.config import MPSettings

    try:
        MPSettings.load(tmp_path / "nonexistent")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_api_wrapper(monkeypatch):
    # ensure get_client passes correct key to MPRester
    from materials_project_helper.api import get_client

    class Dummy:
        def __init__(self, api_key, **kwargs):
            self.api_key = api_key
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    monkeypatch.setattr("materials_project_helper.api.MPRester", Dummy)
    # set env variable for loader
    monkeypatch.setenv("MP_API_KEY", "fromenv")
    with get_client() as d:
        assert d.api_key == "fromenv"
