from pydantic import BaseModel


class GenerateRequest(BaseModel):
    template_id: str
    prompt: str


class GenerateResponse(BaseModel):
    generation_id: str
    status: str


class StatusResponse(BaseModel):
    generation_id: str
    status: str
    stage: str | None = None
    current_step: str | None = None
    completed_steps: list[str] | None = None
    progress: int | None = None
    message: str | None = None
    error: str | None = None
