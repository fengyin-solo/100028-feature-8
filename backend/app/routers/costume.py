"""服装造型接口：维护戏服，覆盖安排定妆、确认使用、归还服装等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.costume import CostumeService

router = APIRouter(prefix="/api/costume", tags=["服装造型"])

service = CostumeService()

LIST_FIELDS = ["服装编号", "服装名称", "角色归属", "尺码规格", "造型师", "使用场次", "当前状态", "清洗记录"]
STATUSES = ["待定妆", "已定妆", "使用中", "已归还"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按服装编号检索"),
    status: str | None = Query(default=None, description="待定妆、已定妆、使用中、已归还"),
    服装编号: str | None = Query(default=None, description="筛选栏字段：按服装编号包含匹配"),
    服装名称: str | None = Query(default=None, description="筛选栏字段：按服装名称包含匹配"),
    角色归属: str | None = Query(default=None, description="筛选栏字段：按角色归属包含匹配"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按筛选栏条件过滤服装造型列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    field_filters = {"服装编号": 服装编号, "服装名称": 服装名称, "角色归属": 角色归属}
    field_filters = {field: value for field, value in field_filters.items() if value}
    items, total = service.list_entries(keyword=keyword, status=status, field_filters=field_filters, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 静态路径要排在 /{entry_id} 之前，否则 "draft"、"export" 会被当成戏服编号拦下。
@router.get("/draft", response_model=dict)
def get_draft() -> dict[str, Any]:
    """读取当前筛选、正在处理的戏服与未提交清洗记录；没保存过时返回空草稿。"""
    return service.get_draft()


@router.put("/draft", response_model=ActionResult)
def save_draft(payload: EntryPayload) -> ActionResult:
    """整体保存草稿；校验不通过时已有草稿原样保留，不被失败请求覆盖。"""
    draft, message = service.save_draft(payload.values)
    if draft is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=draft)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出服装造型清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "costume", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条戏服明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"戏服 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条戏服，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="戏服已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条戏服执行安排定妆、确认使用、归还服装；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/cleaning", response_model=ActionResult)
def submit_cleaning(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交一条清洗记录；同一提交标识或相同内容只登记一次，失败时不改动已有记录。"""
    content = str(payload.values.get("content") or "")
    submission_id = str(payload.values.get("submission_id") or "").strip()
    entry, message = service.submit_cleaning(entry_id, content, submission_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/{entry_id}/cleaning", response_model=dict)
def list_cleaning(entry_id: int) -> dict[str, Any]:
    """读出某件戏服的历史清洗记录，刷新页面后依然可查。"""
    records, message = service.list_cleaning(entry_id)
    if records is None:
        raise HTTPException(status_code=404, detail=message)
    return {"items": records, "total": len(records)}
