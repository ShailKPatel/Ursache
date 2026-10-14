"""ORM models, one module per Postgres schema. Importing this package registers all tables."""

from ursache.db.base import Base
from ursache.db.models import app, eval, kb, plant

metadata = Base.metadata

__all__ = ["app", "eval", "kb", "metadata", "plant"]
