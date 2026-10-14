from __future__ import annotations

import asyncio
import json

import typer

from ursache.api.health import health_service
from ursache.config import get_settings
from ursache.db import admin
from ursache.indexing.qdrant_bootstrap import bootstrap
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
