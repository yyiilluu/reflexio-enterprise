---
paths:
  - "**/*.py"
---

# Pythonic Code Conventions

## 1. Iterables & Collections

- Use `enumerate()` instead of manual index tracking
- Prefer list/dict/set comprehensions over `map()`/`filter()` with lambdas
- Use `zip()` to iterate multiple sequences in parallel
- Use tuple unpacking: `x, y = point` instead of `point[0]`, `point[1]`
- Use `*` unpacking: `first, *rest = items`

## 2. Modern Control Flow

- Use `match`/`case` for complex branching on structure or value
- Use walrus operator `:=` to combine assignment and condition: `if (n := len(items)) > 10:`
- Use truthiness checks: `if items:` not `if len(items) > 0:`
- Use chained comparisons: `0 < x < 10` not `x > 0 and x < 10`
- Use `any()` / `all()` for collection predicates
- Prefer dispatch tables (dicts mapping keys to callables) over long `if/elif` chains

## 3. String Formatting

- Always use f-strings for general string interpolation
- Use `%`-style or comma separation in `logging` calls to defer formatting: `logging.info("User %s logged in", username)`
- Use parameterized queries with driver placeholders (`%s`, `?`) for SQL — never f-strings — to prevent injection

## 4. Resource Management & Safety

- Always use `with` statements (context managers) for files, locks, DB connections
- Prefer EAFP (try/except) over LBYL (if/then check) for high-level logic (file access, network calls, duck-typing)
- In hot loops where failure rate exceeds ~5-10%, prefer LBYL — exception overhead is significant at scale
- Catch specific exceptions, never bare `except:`

## 5. Standard Library

- Use `collections.defaultdict`, `collections.Counter` where appropriate
- Use `NamedTuple` or `dataclasses.dataclass` instead of plain dicts for structured data
- Use `pathlib.Path` instead of `os.path` for filesystem operations
- Use `itertools` for advanced iteration patterns (chain, groupby, product, etc.)
- Use `functools.lru_cache` / `functools.cache` for memoization

## 6. Generators

- Use generator expressions `(x for x in ...)` instead of list comprehensions when only iterating once
- Use `yield` in functions that produce large sequences to avoid loading everything into memory
- Use `yield from` to delegate to sub-generators — cleaner than a manual `for` loop and correctly propagates `.send()`, `.throw()`, and return values

## 7. Decorators

- Use decorators for cross-cutting concerns: logging, auth, timing, retries, validation
- Keep decorator logic thin; delegate heavy work to the wrapped function

## 8. Function Design

- Keep functions short: 10-30 lines ideal, 50 lines max
- Each function should have a single responsibility
- Keep cyclomatic complexity under 10; refactor complex branches into helper functions or dispatch tables
- Max 3 levels of indentation per function; refactor deeper nesting with early returns, guard clauses, or helper functions
- Use guard clauses (early `return`/`raise`/`continue`) to handle edge cases upfront and keep the happy path at the left margin
