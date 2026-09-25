"""服装造型业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "costume"
REQUIRED_FIELDS = ["服装编号", "服装名称", "角色归属"]
STATUS_ORDER = ["待定妆", "已定妆", "使用中", "已归还"]
ACTION_RULES = {"安排定妆": "已定妆", "确认使用": "使用中", "归还服装": "已归还"}
NEGATIVE_ACTIONS = []

# 草稿结构：当前筛选、正在处理的戏服、未提交的清洗记录。
# 正式清洗记录落在戏服行的「清洗记录列表」里，草稿只放还没提交的部分。
EMPTY_DRAFT: dict[str, Any] = {"filters": {}, "active_entry_id": None, "pending_cleaning": []}


class CostumeService:
    def __init__(self) -> None:
        # 草稿按当前值班操作员留一份；提交键集合用来挡住重复提交。
        self._draft: dict[str, Any] = dict(EMPTY_DRAFT)
        self._cleaning_keys: set[str] = set()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        field_filters: dict[str, str] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("服装编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        # 筛选栏按字段名直传（服装编号、服装名称、角色归属），与 keyword 一样做包含匹配
        for field, value in (field_filters or {}).items():
            value = str(value).strip()
            if value:
                rows = [row for row in rows if value in str(row.get(field, ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"戏服 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于服装造型可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"戏服已{action}"

    # ---- 草稿：筛选条件、正在处理的戏服、未提交清洗记录 ----

    def get_draft(self) -> dict[str, Any]:
        """读出当前草稿；没有保存过时返回空草稿，前端按初始状态渲染。"""
        return {
            "filters": dict(self._draft.get("filters") or {}),
            "active_entry_id": self._draft.get("active_entry_id"),
            "pending_cleaning": [dict(item) for item in self._draft.get("pending_cleaning") or []],
            "updated_at": self._draft.get("updated_at"),
        }

    def save_draft(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """整体替换草稿。先校验再落笔：任何一项不合法都不动已有草稿。"""
        filters = values.get("filters") or {}
        if not isinstance(filters, dict):
            return None, "草稿里的筛选条件格式不对，已有草稿未改动"
        pending = values.get("pending_cleaning") or []
        if not isinstance(pending, list):
            return None, "草稿里的清洗记录格式不对，已有草稿未改动"
        cleaned_pending: list[dict[str, Any]] = []
        for item in pending:
            if not isinstance(item, dict):
                return None, "草稿里的清洗记录格式不对，已有草稿未改动"
            entry_id = item.get("entry_id")
            content = str(item.get("content") or "").strip()
            submission_id = str(item.get("submission_id") or "").strip()
            if entry_id is None or not content or not submission_id:
                return None, "草稿里的清洗记录缺少戏服、内容或提交标识，已有草稿未改动"
            try:
                entry_id = int(entry_id)
            except (TypeError, ValueError):
                return None, "草稿里的戏服编号不对，已有草稿未改动"
            cleaned_pending.append({
                "entry_id": entry_id,
                "content": content,
                "submission_id": submission_id,
            })
        active_entry_id = values.get("active_entry_id")
        if active_entry_id is not None:
            try:
                active_entry_id = int(active_entry_id)
            except (TypeError, ValueError):
                return None, "草稿里正在处理的戏服编号不对，已有草稿未改动"
        self._draft = {
            "filters": {str(key): str(value) for key, value in filters.items()},
            "active_entry_id": active_entry_id,
            "pending_cleaning": cleaned_pending,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        return self.get_draft(), "草稿已保存"

    # ---- 清洗记录：正式数据，重复提交只更新一次 ----

    def submit_cleaning(
        self,
        entry_id: int,
        content: str,
        submission_id: str,
    ) -> tuple[dict[str, Any] | None, str]:
        """登记一条清洗记录。先校验后写入，失败时已有记录原样保留。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"戏服 {entry_id} 不存在或已归档"
        content = content.strip()
        if not content:
            return None, "清洗记录内容为空，未保存"
        records = entry.setdefault("清洗记录列表", [])
        if submission_id and submission_id in self._cleaning_keys:
            return entry, "该清洗记录已提交过，未重复登记"
        if records and records[-1].get("content") == content:
            return entry, "清洗记录与最新一条一致，未重复登记"
        records.append({
            "seq": len(records) + 1,
            "content": content,
            "submission_id": submission_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        # 列表页的「清洗记录」列始终展示最新一条，历史明细留在「清洗记录列表」。
        entry["清洗记录"] = content
        if submission_id:
            self._cleaning_keys.add(submission_id)
        return entry, "清洗记录已登记"

    def list_cleaning(self, entry_id: int) -> tuple[list[dict[str, Any]] | None, str]:
        """按时间顺序读出某件戏服的全部清洗记录，刷新页面后依然可查。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"戏服 {entry_id} 不存在或已归档"
        return list(entry.get("清洗记录列表") or []), "ok"
