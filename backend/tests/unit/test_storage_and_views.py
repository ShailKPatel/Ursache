from pathlib import Path

import pytest

from ursache.db.views import PROCESS_PARAMETERS, coil_process_summary_sql
from ursache.storage.blob_store import LocalBlobStore


async def test_local_blob_store_round_trip(tmp_path: Path) -> None:
    store = LocalBlobStore(tmp_path)
    await store.put("neu-det/scratches/1.png", b"\x89PNG", "image/png")

    assert await store.exists("neu-det/scratches/1.png")
    assert await store.get("neu-det/scratches/1.png") == b"\x89PNG"
    assert not await store.exists("missing.png")
    assert store.public_url("x") is None


async def test_local_blob_store_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        await LocalBlobStore(tmp_path / "root").put("../outside", b"x", "text/plain")


def test_coil_summary_has_mean_min_max_per_parameter() -> None:
    sql = coil_process_summary_sql()
    for parameter in PROCESS_PARAMETERS:
        for suffix in ("mean", "min", "max"):
            assert f"AS {parameter}_{suffix}" in sql


def test_coil_summary_rejects_unsafe_parameter_names() -> None:
    with pytest.raises(ValueError, match="invalid parameter"):
        coil_process_summary_sql(["roll_force'; DROP TABLE x; --"])
