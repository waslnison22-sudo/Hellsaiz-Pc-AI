from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    SAFE = "safe"
    CONFIRM = "confirm"


@dataclass
class ToolResult:
    ok: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)

    def as_openai_message(self, tool_call_id: str) -> dict[str, str]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(
                {"ok": self.ok, "output": self.output, "data": self.data}, ensure_ascii=False
            ),
        }
