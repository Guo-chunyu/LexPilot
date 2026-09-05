"""Run the exact first-stage acceptance conversation without API keys."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.workflow import LexPilotEngine


MESSAGES = [
    "我在公司工作8个月，昨天领导微信告诉我明天不用来了，说我试用期表现不合格，我没有拿到赔偿。",
    "签了劳动合同，合同期限3年，试用期6个月。",
    "公司没有告知录用条件，也没有考核记录，只有微信，没有书面通知。",
    "我的月工资是10000元。",
    "我有劳动合同和工资流水。",
]


def main() -> None:
    engine = LexPilotEngine()
    state = None
    for message in MESSAGES:
        result = engine.process(message, state)
        state = result["case_state"]
        print(f"\nUSER: {message}")
        print(f"LEXPILOT: {result['reply']}")
    print("\n=== DECISION TIMELINE ===")
    for record in state.action_history:
        print(f"Step {record.step}: {record.action.name} -> {record.result}")
    print("\n=== FINAL REPORT ===")
    print(json.dumps(state.final_report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
