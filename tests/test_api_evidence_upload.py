from fastapi.testclient import TestClient

import backend.api as api_module
from backend.workflow import LexPilotEngine


def test_api_accepts_evidence_and_continues_same_case(tmp_path, monkeypatch):
    engine = LexPilotEngine()
    first = engine.process("我在公司工作8个月，公司说试用期表现不合格，明天不用来了。")
    second = engine.process("签了劳动合同，合同期限三年，试用期六个月。", first["case_state"])
    third = engine.process("公司没告知录用条件，也没有考核记录，只有微信，没有书面通知。", second["case_state"])
    fourth = engine.process("月工资10000元。", third["case_state"])
    assert fourth["case_state"].pending_evidence_requests

    thread_id = "api_evidence_upload_test"
    api_module._sessions[thread_id] = fourth["case_state"]
    monkeypatch.setattr(api_module, "_upload_root", lambda: tmp_path)
    client = TestClient(api_module.api_app)

    try:
        response = client.post(
            f"/cases/{thread_id}/evidence",
            files=[
                (
                    "files",
                    (
                        "劳动合同和工资流水.txt",
                        "劳动合同原件；银行工资流水，月工资10000元。".encode("utf-8"),
                        "text/plain",
                    ),
                )
            ],
        )
    finally:
        api_module._sessions.pop(thread_id, None)

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["case_state"]["uploaded_files"]) == 1
    assert set(payload["case_state"]["uploaded_files"][0]["evidence_names"]) >= {"劳动合同", "工资流水"}
    assert "stored_path" not in payload["case_state"]["uploaded_files"][0]
    assert "已接收并登记 1 份材料" in payload["reply"]
    assert payload["decision_mode"] == "rules"

    chat_schema = client.get("/openapi.json").json()["components"]["schemas"]["ChatRequest"]
    assert "policy_type" not in chat_schema["properties"]
