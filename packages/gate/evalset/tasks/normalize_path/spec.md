# Task: normalize_path

Write `solution.py` defining:

```python
def normalize_path(p: str) -> str
```

Normalize a POSIX-style path purely as text (never look at the filesystem).

- A path is absolute if it starts with `/`. Any number of leading slashes means a single root `/`.
- Split on `/`; empty components (from repeated slashes) and `.` components are dropped.
- `..` removes the previous kept component if there is one that is not itself `..`. In an absolute path, `..` at the root is dropped (`/..` is `/`). In a relative path, a `..` that has nothing to remove is kept (`../a` stays `../a`, `a/../..` becomes `..`).
- Join the kept components with single slashes, prefixed with `/` if absolute. No trailing slash, except the root itself is `/`.
- If a relative path normalizes to nothing (including the empty string input), return `.`.
- Components like `...` or `.hidden` are ordinary names.

Examples: `"/a//b/./c/.."` -> `"/a/b"`, `"a/b/../../.."` -> `".."`, `"///"` -> `"/"`, `""` -> `"."`, `"./"` -> `"."`.
