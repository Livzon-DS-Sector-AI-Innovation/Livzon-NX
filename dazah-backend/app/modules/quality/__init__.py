"""Quality management module."""

from app.modules.quality import repository
from app.modules.quality.api import router

__all__ = ["router", "repository"]
