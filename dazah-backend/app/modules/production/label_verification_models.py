"""Re-export from production models to avoid duplicate definitions."""
from app.modules.production.models import LabelVerification

__all__ = ["LabelVerification"]
