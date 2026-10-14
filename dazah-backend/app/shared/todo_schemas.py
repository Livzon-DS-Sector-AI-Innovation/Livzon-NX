from datetime import date

from pydantic import BaseModel, Field


class BusinessTodoItem(BaseModel):
    id: str
    title: str
    detail: str
    due_date: date | None = None


class BusinessTodoPage(BaseModel):
    items: list[BusinessTodoItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
