import json
import os
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings


class MPSettings(BaseSettings):
    """Configuration for accessing the Materials Project API.

    Can be populated from environment variables (``MP_API_KEY``) or from a
    configuration file.  Supported file formats are ``.env``, JSON, TOML,
    and YAML.
    """

    mp_api_key: str

    class Config:
        env_prefix = ""
        env_file_encoding = "utf-8"

    @classmethod
    def load(cls, path: str | Path | None = None) -> "MPSettings":
        """Load settings, optionally from a file.

        Parameters
        ----------
        path
            Path to a configuration file or directory.  If a directory is given
            the loader will look for one of the following names (in order):

            * ``.env``
            * ``config.json``
            * ``config.toml``
            * ``config.yml``
            * ``config.yaml``

            If ``None`` (the default) the settings are read from the environment
            and a ``.env`` file in the current working directory (handled by
            :class:`pydantic_settings.BaseSettings`).

        Raises
        ------
        FileNotFoundError
            The provided path (or a candidate inside the given directory) does
            not exist.
        ValueError
            The path has an unsupported extension or the contents of the file
            are not compatible with the expected mapping structure.
        RuntimeError
            A required parsing library (for example, PyYAML) could not be
            imported when attempting to read a YAML file.
        """

        # determine which file (if any) to load from.  We support several
        # entry points:
        #
        # * an explicit path passed by the caller
        # * a configuration file found in the current working directory or
        #   any ancestor.  This is important in interactive sessions where the
        #   notebook may not be launched from the project root.
        # * no file at all, in which case BaseSettings handles env/.env
        file_path: Path | None

        if path is not None:
            file_path = Path(path)
        else:
            file_path = _find_config_in_parents(Path.cwd())

        if file_path is None:
            # no file located; fall back on environment/.env behavior
            settings = cls()
        else:
            # if the path is a directory, look for a candidate inside it
            if file_path.is_dir():
                file_path = _find_config_in_dir(file_path)

            if not file_path.exists():
                raise FileNotFoundError(f"configuration file not found: {file_path}")

            suffix = file_path.suffix.lower()
            # handle files with no suffix (common when the path ends with a
            # trailing slash) by treating them as env files
            if suffix == "" or suffix == ".env":
                settings = cls(_env_file=str(file_path))
            elif suffix in (".json", ".toml", ".yml", ".yaml"):
                data = cls._parse_config_file(file_path)
                settings = cls(**data)
            else:
                raise ValueError(f"unsupported configuration file type: {suffix}")

        # ensure the environment variable is set for downstream code that
        # might read it directly
        os.environ.setdefault("MP_API_KEY", settings.mp_api_key)
        return settings

    @staticmethod
    def _parse_config_file(path: Path) -> dict[str, Any]:
        text = path.read_text(encoding="utf-8")
        suffix = path.suffix.lower()

        if suffix == ".json":
            obj = json.loads(text)
        elif suffix == ".toml":
            # tomllib is available in Python 3.11+; use it for safety
            try:
                import tomllib

                obj = tomllib.loads(text)
            except ImportError as exc:  # pragma: no cover - python<3.11
                raise RuntimeError("TOML support requires Python 3.11+") from exc
        elif suffix in (".yml", ".yaml"):
            try:
                import yaml

                obj = yaml.safe_load(text)
            except ImportError as exc:
                raise RuntimeError("reading YAML requires PyYAML") from exc
        else:  # pragma: no cover - guarded by caller
            raise ValueError(f"unsupported extension: {suffix}")

        if not isinstance(obj, dict):
            raise ValueError("configuration file must contain a mapping/dictionary")

        return obj


# helpers


def _find_config_in_dir(directory: Path) -> Path:
    candidates = [".env", "config.json", "config.toml", "config.yml", "config.yaml"]
    for name in candidates:
        candidate = directory / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no configuration file found in {directory}")


def _find_config_in_parents(start: Path) -> Path | None:
    """Search *start* and its ancestors for a configuration file.

    The same candidate filenames used by :func:`_find_config_in_dir` are
    checked.  Returns the first match found or ``None`` if no file exists.
    """
    candidates = [".env", "config.json", "config.toml", "config.yml", "config.yaml"]
    for directory in [start] + list(start.parents):
        for name in candidates:
            candidate = directory / name
            if candidate.exists():
                # resolve to remove any trailing slashes/relative elements;
                # this also ensures ``suffix`` returns the expected extension.
                return candidate.resolve()
    return None
