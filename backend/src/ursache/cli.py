from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

import typer

from ursache.api.health import health_service
from ursache.config import get_settings
from ursache.db import admin
from ursache.indexing.qdrant_bootstrap import bootstrap
from ursache.ingestion import IngestionError, ingest_documents
from ursache.logging import configure_logging

app = typer.Typer(help="Ursache operations CLI.", no_args_is_help=True)


@app.callback()
def _main() -> None:
    configure_logging(get_settings().log_level)


@app.command("db-migrate")
def db_migrate(revision: str = typer.Argument("head")) -> None:
    """Apply Alembic migrations as the migration role."""
    admin.upgrade(get_settings(), revision)
    typer.echo(f"migrated to {revision}")


@app.command("db-roles")
def db_roles() -> None:
    """Create schemas and roles, apply grants, set role passwords (idempotent)."""
    admin.apply_roles(get_settings())
    typer.echo("roles applied")


@app.command("db-seed")
def db_seed() -> None:
    """Insert one user per role (idempotent)."""
    inserted = asyncio.run(admin.seed_users(get_settings()))
    typer.echo(f"seeded {inserted} new user(s)")


@app.command("qdrant-bootstrap")
def qdrant_bootstrap() -> None:
    """Create Qdrant collections, payload indexes and aliases (idempotent)."""
    created = asyncio.run(bootstrap(get_settings()))
    typer.echo(f"created: {', '.join(created)}" if created else "collections already present")


def _add_simulator_to_path() -> None:
    # The simulator ships with the source tree, not with the installed package or the image.
    backend_dir = Path(__file__).resolve().parents[2]
    if (backend_dir / "simulator").is_dir() and str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


@app.command()
def simulate(
    seed: int = typer.Option(42, help="Random seed; the same seed gives identical data."),
    days: int = typer.Option(90, min=14, help="Simulated days."),
    coils_per_day: int = typer.Option(40, min=4, max=400, help="Coils per line per day."),
    samples_per_coil: int = typer.Option(3, min=1, max=20, help="Readings per sensor per coil."),
    reset: bool = typer.Option(False, "--reset", help="Clear the simulator's tables first."),
) -> None:
    """Generate the simulated plant, documents and ground truth (writes plant, kb, eval)."""
    _add_simulator_to_path()
    try:
        from simulator import SimConfig, SimulatorError
        from simulator import simulate as run_simulation
    except ModuleNotFoundError:
        typer.echo("simulate needs a source checkout (backend/simulator)", err=True)
        raise typer.Exit(code=2) from None

    settings = get_settings()
    cfg = SimConfig(
        seed=seed, days=days, coils_per_day=coils_per_day, samples_per_coil=samples_per_coil
    )
    try:
        summary = run_simulation(
            cfg,
            admin.libpq_url(settings.migration_database_url),
            Path(settings.generated_docs_dir),
            reset=reset,
        )
    except SimulatorError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps({**summary.counts, "digest": summary.digest, "size_mb": summary.size_mb}))


@app.command("ingest-docs")
def ingest_docs(
    force: bool = typer.Option(False, "--force", help="Rebuild chunks of unchanged documents."),
) -> None:
    """Chunk the documents in kb.documents into kb.chunks (writes kb as ursache_app)."""
    settings = get_settings()
    try:
        summary = ingest_documents(
            admin.libpq_url(settings.app_database_url),
            Path(settings.generated_docs_dir),
            force=force,
        )
    except IngestionError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    typer.echo(json.dumps(asdict(summary)))


@app.command()
def health() -> None:
    """Check Postgres, Qdrant and remaining quota; exit 1 if degraded."""

    async def _check() -> str:
        async with health_service(get_settings()) as service:
            report = await service.check()
        typer.echo(json.dumps(report.model_dump(), indent=2))
        return report.status

    if asyncio.run(_check()) != "ok":
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
