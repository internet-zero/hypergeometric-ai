"""Top-level test config.

The hypergeometric package lives at the repo root (one level up from
tests/); insert it on sys.path before any test module imports so
`import hypergeometric` resolves from every test package without requiring
an editable install — mirroring a production service repo's conftest pattern of preparing
imports and fixtures ahead of pytest collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import hypergeometric as v  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return _ROOT


@pytest.fixture(scope="session")
def example_prompt(repo_root: Path) -> str:
    return (repo_root / "examples" / "example.prompt.txt").read_text()


@pytest.fixture(scope="session")
def example_rules(repo_root: Path) -> tuple[list, list]:
    return v.load_rules(repo_root / "examples" / "rules.example.yaml")


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"
