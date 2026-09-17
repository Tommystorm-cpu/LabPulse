"""Shared pytest fixtures for repository-level tests."""

from collections.abc import Iterator
from pathlib import Path
import shutil
from uuid import uuid4

import pytest


@pytest.fixture
def repository_root() -> Path:
    """Return the repository root without relying on the process directory."""

    return Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace_tmp_path(repository_root: Path) -> Iterator[Path]:
    """Create a disposable path below the repository for Windows compatibility."""

    temporary_root = repository_root / "testing" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    path = temporary_root / f"pytest-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)
