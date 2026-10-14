import pytest

from ursache.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not see the developer's shell environment."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
