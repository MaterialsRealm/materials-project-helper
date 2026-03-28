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

# querying materials

By default the records returned from ``search`` are the raw objects
produced by the MP API (usually pydantic ``MaterialsDoc`` models).

You can also write VASP inputs for every matching material by using the
new :meth:`MaterialsSearcher.download_relax_sets` helper.  Supply a
``root_dir`` and the same filters you would to ``search``; each material
gets its own subfolder named for the MP ID::

```python
searcher = MaterialsSearcher()
paths = searcher.download_relax_sets("./inputs", chemsys="Fe-Co")
# paths -> [Path("./inputs/mp-1234"), Path("./inputs/mp-5678"), ...]
```

A helper that creates its own client should be closed when no longer
needed.  The simplest way is to use it as a context manager, which ensures
its internal ``MPRester`` is shut down promptly:

```python
with MaterialsSearcher() as searcher:
    docs = searcher.search(chemsys="Fe-Co")
# client closed here
```

Alternatively, explicitly delete the helper or call ``del searcher``; the
object's destructor will close the client eventually.  If you supply your
own ``mpr`` instance the helper will **not** close it for you.

For large explicit ID lists, avoid one giant ``material_ids=[...]`` call.
Use the batched CSV helper instead so results are written incrementally and
can be resumed:

```bash
uv run python scripts/download_all_cifs.py \
  --csv mp_all_summary.csv \
  --out /Users/qz/Downloads/cifs \
  --batch-size 1000 \
  --workers 1 \
  --skip-existing
```

The package exposes a single helper class that wraps an
``mp_api.client.MPRester`` instance.  You can either let the helper create
its own client or inject one of your own.

```python
from mp_helper import MaterialsSearcher, get_client

# simple usage with automatic client creation
searcher = MaterialsSearcher()
results = searcher.search(chemsys="Fe-Co")

# pass any supported filter
results = searcher.search(elements=["Fe","Co"], density=(0,7))

# convert results to RelaxSet objects (requires pymatgen)
relax_sets = searcher.get_relax_sets(chemsys="Fe-Co")

# if you already have a client, you can provide it
with get_client() as mpr:
    custom_searcher = MaterialsSearcher(mpr=mpr)
    results = custom_searcher.search(task_ids=["fcc"])
```

Supported config file formats are:

* ``.env`` – processed automatically by ``pydantic-settings``.
* JSON, TOML, YAML – the loader reads the file and looks for a
  ``mp_api_key`` key at the top level.

In all cases the key is also injected into ``os.environ["MP_API_KEY"]`` so
code that expects the normal environment variable will continue to work.

> **Security note:** keep configuration files containing secret keys out of
> version control (add them to ``.gitignore``).
