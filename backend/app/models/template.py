from pydantic import BaseModel


class TemplateUploadResponse(BaseModel):
    template_id: str
    name: str
    status: str


class TemplateListItem(BaseModel):
    id: str
    name: str
    status: str
    total_slides: int = 0
    usable_layouts: int = 0
