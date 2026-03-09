# materials-project-helper

Helper code for the Materials Project

This small package provides a convenience wrapper around the ``mp-api``
client.  It makes it easy to load your ``MP_API_KEY`` from an environment
variable or from a configuration file located anywhere on disk.

## Usage

```python
from mp_helper import get_client

# option 1: point at a file or directory
with get_client("/path/to/my/config.env") as mpr:
    print(mpr.materials.search(task_id="fcc")[:1])

# option 2: use a directory containing a supported file name:
#    .env, config.json, config.toml, config.yml or config.yaml
with get_client("/some/dir") as mpr:
    ...

# option 3: rely on the environment variable or a .env in cwd
# export MP_API_KEY="..."
with get_client() as mpr:
    ...

# convenience helpers

```python
from mp_helper import download_materials

# get all entries in the Fe–Co chemical system
results = download_materials("Fe-Co")

# or query multiple systems at once
results = download_materials(["Fe-Co", "Fe-O"])

# generate a relaxation input set for each result
from mp_helper import download_relax_sets

relax_sets = download_relax_sets("Fe-Co")  # returns list of MPRelaxSet objects
```

Supported config file formats are:

* ``.env`` – processed automatically by ``pydantic-settings``.
* JSON, TOML, YAML – the loader reads the file and looks for a
  ``mp_api_key`` key at the top level.

In all cases the key is also injected into ``os.environ["MP_API_KEY"]`` so
code that expects the normal environment variable will continue to work.

> **Security note:** keep configuration files containing secret keys out of
> version control (add them to ``.gitignore``).
