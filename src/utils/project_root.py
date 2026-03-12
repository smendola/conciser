from __future__ import annotations

from pathlib import Path


_MARKER_FILE = ".project-root"


def get_project_root(start: Path | None = None) -> Path:
    """Return the project root by searching upward for the `.project-root` marker.

    This is designed to be reliable from any subdirectory and to not depend on git.

    Raises:
        FileNotFoundError: if no marker is found when walking upward.
    """

    if start is None:
        start = Path.cwd()

    start = start.resolve()

    for candidate in [start, *start.parents]:
        marker = candidate / _MARKER_FILE
        if marker.exists():
            return candidate

    raise FileNotFoundError(
        f"Could not locate project root: missing `{_MARKER_FILE}` when searching upward from {start}"
    )


def resolve_from_root(path: str | Path, *, start: Path | None = None) -> Path:
    """Resolve `path` against project root unless it is already absolute."""

    p = Path(path)
    if p.is_absolute():
        return p
    return get_project_root(start=start) / p


def resolve_env_file(*, start: Path | None = None) -> Path:
    """Return the absolute path to the repo `.env` file."""

    return get_project_root(start=start) / ".env"
