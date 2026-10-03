from pydantic import BaseModel, Field


class FieldIssue(BaseModel):
    field: str
    message: str


class ErrorInfo(BaseModel):
    code: str
    message: str
    retryable: bool
    trace_id: str
    field_issues: list[FieldIssue] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorInfo


class GenerationError(Exception):
    def __init__(self, code: str, message: str, status: int = 502, retryable: bool = True):
        super().__init__(message)
        self.code, self.message, self.status, self.retryable = code, message, status, retryable
