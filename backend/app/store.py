"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。
幂等回执也寄存在这里：带相同幂等键的重复提交直接回放首次结果，状态只落一次。
"""
from __future__ import annotations

import copy
from typing import Any

from app.seed import SEED_ROWS


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
        }
        self._idempotency: dict[str, dict[str, Any]] = {}

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def idempotent_result(self, key: str) -> dict[str, Any] | None:
        """按幂等键取回首次提交的回执；没提交过返回 None。

        返回深拷贝，避免调用方改动缓存里的回执，污染后续重复提交的回放结果。
        """
        cached = self._idempotency.get(key)
        return copy.deepcopy(cached) if cached is not None else None

    def remember_result(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """登记一次提交的回执；同键重复登记时保留首次结果，后一次不覆盖。"""
        if key not in self._idempotency:
            self._idempotency[key] = copy.deepcopy(payload)
        return copy.deepcopy(self._idempotency[key])

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
