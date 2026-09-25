"""服装造型接口：维护戏服，覆盖安排定妆、确认使用、归还服装与清洗记录。"""
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
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按服装编号与状态过滤服装造型列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：静态路径要排在 /{entry_id} 之前，否则「export」会被当成戏服 id 解析。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出服装造型清单：返回全量数据（含清洗历史）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "costume", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条戏服明细（含归还时间与清洗历史）；不存在时给出可读的错误说明。"""
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
    """对单条戏服执行安排定妆、确认使用、归还服装。

    values.request_id 为幂等键：同一件戏服带同一个键重复提交只生效一次，
    后续重复请求回放首次回执，不会再改状态。
    """
    action = str(payload.values.get("action") or "").strip()
    request_id = str(payload.values.get("request_id") or "").strip() or None
    entry, message, replayed = service.run_action(entry_id, action, request_id)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry, replayed=replayed)


@router.get("/{entry_id}/cleaning", response_model=dict)
def list_cleaning(entry_id: int) -> dict[str, Any]:
    """查询某件戏服的历史清洗记录，归还后随时可查。"""
    records, message = service.list_cleaning(entry_id)
    if records is None:
        raise HTTPException(status_code=404, detail=message)
    return {"entry_id": entry_id, "total": len(records), "items": records}


@router.post("/{entry_id}/cleaning", response_model=ActionResult)
def add_cleaning(entry_id: int, payload: EntryPayload) -> ActionResult:
    """为已归还戏服登记清洗记录。

    values.request_id 为幂等键：网络重试或重复点击只追加一条记录。
    """
    values = dict(payload.values)
    request_id = str(values.pop("request_id", "") or "").strip() or None
    record, message, replayed = service.add_cleaning(entry_id, values, request_id)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record, replayed=replayed)
