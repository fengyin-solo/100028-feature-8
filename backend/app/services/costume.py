"""服装造型业务规则：状态流转、字段校验、清洗记录与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "costume"
REQUIRED_FIELDS = ["服装编号", "服装名称", "角色归属"]
STATUS_ORDER = ["待定妆", "已定妆", "使用中", "已归还"]
# 每个动作要求戏服当前所处的状态：跨阶段/逆向点击一律拦下，不能把已有状态改回去。
ACTION_RULES = {
    "安排定妆": {"from": "待定妆", "to": "已定妆"},
    "确认使用": {"from": "已定妆", "to": "使用中"},
    "归还服装": {"from": "使用中", "to": "已归还"},
}
CLEANING_REQUIRED_FIELDS = ["清洗日期", "清洗方式"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cleaning_records(entry: dict[str, Any]) -> list[dict[str, Any]]:
    records = entry.get("清洗历史")
    if not isinstance(records, list):
        records = []
        entry["清洗历史"] = records
    return records


def _present(entry: dict[str, Any]) -> dict[str, Any]:
    """把内部行整理成对外结构：当前状态取真实 status，清洗记录汇总历史条数。"""
    data = dict(entry)
    history = [dict(record) for record in _cleaning_records(entry)]
    data["当前状态"] = entry.get("status")
    data["清洗记录"] = f"已清洗 {len(history)} 次" if history else "暂无清洗记录"
    data["清洗次数"] = len(history)
    data["清洗历史"] = history
    return data


class CostumeService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("服装编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_present(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

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
        entry["归还时间"] = None
        entry["清洗历史"] = []
        rows.append(entry)
        return _present(entry), []

    def run_action(
        self, entry_id: int, action: str, request_id: str | None = None
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行定妆/使用/归还。

        返回 (明细, 说明, 是否幂等回放)。任何校验失败都在改状态之前返回，
        保证保存失败不会覆盖戏服已有状态。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"戏服 {entry_id} 不存在或已归档", False

        if request_id:
            idem_key = f"costume:action:{entry_id}:{request_id}"
            cached = store.idempotent_result(idem_key)
            if cached is not None:
                return cached.get("entry"), cached.get("message", "重复提交已忽略"), True

        rule = ACTION_RULES.get(action)
        if rule is None:
            return None, f"动作「{action}」不属于服装造型可执行范围", False
        current = entry.get("status")
        if current != rule["from"]:
            return None, f"戏服当前为「{current}」，不能执行「{action}」，请刷新后确认最新状态", False

        target = rule["to"]
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = False
        if action == "归还服装":
            entry["归还时间"] = _now()
        message = f"戏服已{action}"
        payload = {"entry": _present(entry), "message": message}
        if request_id:
            payload = store.remember_result(
                f"costume:action:{entry_id}:{request_id}", payload
            )
        return payload.get("entry"), message, False

    def list_cleaning(self, entry_id: int) -> tuple[list[dict[str, Any]] | None, str]:
        """读取某件戏服的清洗历史，最新登记的排在前面。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"戏服 {entry_id} 不存在或已归档"
        history = _cleaning_records(entry)
        return [dict(record) for record in reversed(history)], ""

    def add_cleaning(
        self, entry_id: int, values: dict[str, Any], request_id: str | None = None
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """为已归还的戏服登记一条清洗记录；未归还的戏服不收，避免脏数据。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"戏服 {entry_id} 不存在或已归档", False

        if request_id:
            idem_key = f"costume:cleaning:{entry_id}:{request_id}"
            cached = store.idempotent_result(idem_key)
            if cached is not None:
                return cached.get("entry"), cached.get("message", "重复提交已忽略"), True

        if entry.get("status") != "已归还":
            return None, "戏服尚未归还，归还后才能登记清洗记录", False

        clean_values = {
            key: value for key, value in values.items()
            if key in ("清洗日期", "清洗方式", "清洗说明", "经办人")
        }
        missing = [
            field for field in CLEANING_REQUIRED_FIELDS
            if not str(clean_values.get(field) or "").strip()
        ]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}", False

        record = {"id": len(_cleaning_records(entry)) + 1, "登记时间": _now()}
        record.update(clean_values)
        _cleaning_records(entry).append(record)
        message = "清洗记录已登记"
        payload = {"entry": record, "message": message}
        if request_id:
            payload = store.remember_result(
                f"costume:cleaning:{entry_id}:{request_id}", payload
            )
        return payload.get("entry"), message, False
