---
description: "Standards for Python type annotations."
applyTo: '**/*.py'
---

# Python Type Annotation Standards

This project targets **Python 3.10+**, so modern typing features are available and
preferred. The goal is to keep annotations readable and only add them when they
provide real value (public APIs, complex logic, or help with tools). Avoid
noise; idiomatic Python code often works fine with very few explicit types.

## General principles

- **Annotate sparingly.** If a function/method is obvious or used only internally
  it's acceptable to omit annotations. Add them when they clarify intent,
  improve editor tooling, or help type checkers catch mistakes.

- **Don’t import from `typing` unless necessary.** Most builtins are now
  generics (`list`, `dict`, `set`, `tuple`, etc.). Use them directly.

- **Avoid `from __future__ import annotations`.** The codebase runs on 3.10+
  so forward references are handled naturally with quoted strings when needed.

- **Prefer PEP 604 union syntax (`|`) over `typing.Union`.** Likewise use
  `X | None` instead of `Optional[X]`.

- **Use built‑in `type` names over their capitalized equivalents.**
  ```python
  def foo(items: list[int]) -> dict[str, float]:
      ...
  ```
  not
  ```python
  from typing import List, Dict

  def foo(items: List[int]) -> Dict[str, float]:
      ...
  ```

- **Avoid aliases like `Set`, `FrozenSet`, `Iterable`, etc., unless you need a
  specific abstract base class from `collections.abc`.** Use plain `set`,
  `frozenset`, `list`, etc., with generics if you want parameterization.

- **Type variables** and `TypeAlias` are fine when generic behavior is required.
  Keep imports local to the module where they’re used.

- **`Any` is an escape hatch.** Use it judiciously and consider adding a
  `# type: ignore` comment on the use site if a type checker complains.

- **Local variables** rarely need annotations unless they aid readability or
  resolve a complex inferred type. Most tools infer local types automatically.

- **Function return types** should be annotated for public APIs and complex
  code; obvious cases such as `-> None` may be omitted when the body is trivial.

- **Keep annotations minimal in tests.** Tests should focus on behavior; elaborate
  typing seldom improves them.

## Examples

```python
# good

def parse_config(data: str) -> dict[str, int]:
    ...

# fine to omit annotation when return type is clear from context

def increment(x):
    return x + 1

# use union syntax

def get_user(id: int) -> User | None:
    ...

# no future import or Union required

# use builtins for generics

from pathlib import Path

def load(path: Path) -> list[Path]:
    ...
```

> **Note:** When adding a new annotation that requires one of the older
> `typing` imports (e.g. `Literal`, `TypedDict`), feel free to import from
> `typing` in that module. Those should be the exception, not the rule.

## When to worry about forward references

Only stringize a name if it isn't yet defined. For example:

```python
class Node:
    def __init__(self, parent: "Node" | None = None) -> None:
        self.parent = parent
```

No need for `from __future__ import annotations` anywhere else.

## Type-checking and tooling

- The repository does not enforce strict `mypy` rules, but annotations make it
  easier to spot mistakes during development and when writing new code.
- Run `mypy` or `ruff --select=ANN` manually if you want to validate annotations.
- Avoid over‑annotating just to satisfy linters; the human reader is the primary
  audience.

## Summary

Treat type hints as helpful documentation rather than mandatory syntax. Favor
modern Python 3.10 features (`|`, built-in generics) and keep the imports and
code simple. There's no need to sprinkle `Union` or `from __future__` everywhere
– they only show up when truly required.
