"""Top-level test config.

validate.py lives at the prototype root (one level up from tests/); insert
it on sys.path before any test module imports so `import validate` resolves
from every test package — mirroring asato-svc's conftest pattern of
preparing imports and fixtures ahead of pytest collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import validate as v  # noqa: E402


@pytest.fixture(scope="session")
def prototype_root() -> Path:
    return _ROOT


@pytest.fixture(scope="session")
def example_prompt(prototype_root: Path) -> str:
    return (prototype_root / "example.prompt.txt").read_text()


@pytest.fixture(scope="session")
def example_rules(prototype_root: Path) -> tuple[list, list]:
    return v.load_rules(prototype_root / "rules.example.yaml")


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
