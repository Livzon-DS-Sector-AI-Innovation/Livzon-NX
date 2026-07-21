"""Shared Pydantic schemas."""

from pydantic import BaseModel


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20
