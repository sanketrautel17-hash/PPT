from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from app.api.dependencies import get_db
from app.models.template import TemplateUploadResponse
from app.services.template_service import TemplateService


router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.post("/upload", response_model=TemplateUploadResponse, status_code=201)
async def upload_template(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(...),
    db=Depends(get_db),
):
    service = TemplateService(db)
    template_id = await service.upload_template(file=file, name=name)
    background_tasks.add_task(service.analyze_template, template_id, name)
    return TemplateUploadResponse(template_id=template_id, name=name, status="analyzing")


@router.get("")
async def list_templates(db=Depends(get_db)) -> list[dict]:
    service = TemplateService(db)
    return await service.list_templates()


@router.get("/{template_id}")
async def get_template(template_id: str, db=Depends(get_db)) -> dict:
    service = TemplateService(db)
    item = await service.get_template(template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return item


@router.post("/{template_id}/re-profile", status_code=202)
async def re_profile_template(
    template_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),
) -> dict:
    """
    Re-run AI guidance extraction on an already-uploaded template.
    Use this to refresh brand rules after prompt logic changes without re-uploading the file.
    """
    service = TemplateService(db)
    item = await service.get_template(template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found")
    background_tasks.add_task(service.re_profile_template, template_id)
    return {"template_id": template_id, "status": "re-analyzing"}
