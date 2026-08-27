"""Compatibility import for the migrated product-quality model."""

from app.modules.quality.models.external_quality import ProductQualityRecord

__all__ = ["ProductQualityRecord"]
