"""Shared schemas: error envelope, pagination, base config."""

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    """Standard error detail object."""

    code: str
    message: str
    retry: bool = False


class ErrorResponse(BaseModel):
    """Standard error envelope — every non-2xx response uses this shape."""

    error: ErrorDetail


class PaginationMeta(BaseModel):
    """Pagination metadata returned with list endpoints."""

    total: int
    page: int
    per_page: int


class OrmBase(BaseModel):
    """Base for schemas that read from SQLAlchemy models."""

    model_config = ConfigDict(from_attributes=True)
