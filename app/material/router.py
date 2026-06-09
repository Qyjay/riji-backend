"""
素材管理路由
prefix="/api/materials", tags=["素材管理"]
"""
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.response import success
from app.material import schemas, service
from app.material.schemas import MaterialOut

router = APIRouter(prefix="/materials", tags=["素材管理"])


def _serialize(m_dict: dict) -> dict:
    """转 camelCase 输出"""
    return MaterialOut(**m_dict).model_dump(by_alias=True)


@router.post("/voice", summary="语音上传与转写")
async def upload_voice(
    file: UploadFile = File(..., description="语音文件（mp3/wav/m4a/ogg，最大 20MB）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """语音上传并转写"""
    result = await service.upload_voice_and_transcribe(file, current_user.id)
    return success(result)


@router.post("", summary="创建素材")
async def create_material(
    body: schemas.MaterialCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建一条素材记录，情绪由前端随后异步触发提取。"""
    data = body.model_dump()
    result = service.create_material(db, current_user.id, data, index_memory=False)
    background_tasks.add_task(service.ingest_material_by_id, result["id"], current_user.id)
    return success(_serialize(result))


@router.get("", summary="素材列表（裸数组）")
def list_materials(
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按日期查询素材，返回裸数组"""
    items = service.list_materials(db, current_user.id, date)
    return success([_serialize(m) for m in items])


@router.get("/{material_id}", summary="素材详情")
def get_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单条素材"""
    result = service.get_material(db, current_user.id, material_id)
    return success(_serialize(result))


@router.put("/{material_id}", summary="编辑素材")
def update_material(
    material_id: str,
    body: schemas.MaterialUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新素材字段"""
    result = service.update_material(
        db, current_user.id, material_id, body.model_dump(exclude_unset=True), index_memory=False
    )
    background_tasks.add_task(service.ingest_material_by_id, material_id, current_user.id)
    return success(_serialize(result))


@router.delete("/{material_id}", summary="删除素材")
def delete_material(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除素材"""
    service.delete_material(db, current_user.id, material_id)
    return success(None)


@router.post("/{material_id}/emotion", summary="AI 情绪提取")
async def extract_emotion(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """调用 AI 提取素材情绪，结果写回数据库"""
    result = await service.extract_emotion(db, current_user.id, material_id)
    return success(result)


@router.post("/{material_id}/polish", summary="AI 文字润色")
async def polish_text(
    material_id: str,
    body: schemas.PolishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按指定风格润色素材文字，只返回 {polished}"""
    result = await service.polish_text(db, current_user.id, material_id, body.style)
    return success(result)
