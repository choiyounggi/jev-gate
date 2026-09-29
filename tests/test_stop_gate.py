"""Tests for hooks/jev-stop-gate.sh.

Deterministic paths run without a server. Model-layer cases run only when ollaya answers and use
messages from dataset.json's agent_report task, where winnow:e4b scored 100% on status.
"""

import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
HOOK = HERE.parent / "hooks" / "jev-stop-gate.sh"
DEAD = {"JEV_GATE_URL": "http://localhost:1/x", "JEV_STOP_TIMEOUT": "1"}


def server_up(host="localhost", port=11435) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def run_hook(payload, env_extra=None, tmp_path=None):
    env = dict(os.environ)
    env["JEV_STOP_LOG"] = str((tmp_path or HERE) / "stop-test.jsonl")
    env.update(env_extra or {})
    stdin = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    p = subprocess.run([str(HOOK)], input=stdin, capture_output=True, text=True, env=env, timeout=90)
    out = json.loads(p.stdout) if p.stdout.strip() else None
    return p.returncode, out


def stop(msg, active=False, event="Stop"):
    return {"hook_event_name": event, "stop_hook_active": active, "last_assistant_message": msg,
            "session_id": "t", "cwd": str(HERE)}


def test_stop_hook_active_is_never_blocked(tmp_path):
    rc, out = run_hook(stop("네, 처리했습니다!", active=True), None, tmp_path)
    assert rc == 0 and out is None


def test_empty_message_and_malformed_stdin_allow_stop(tmp_path):
    for payload in [stop(""), "not json", "", "{}"]:
        rc, out = run_hook(payload, None, tmp_path)
        assert rc == 0 and out is None, payload


def test_unreachable_server_allows_stop_and_logs_none(tmp_path):
    rc, out = run_hook(stop("네, 처리했습니다!"), DEAD, tmp_path)
    assert rc == 0 and out is None
    logged = json.loads((tmp_path / "stop-test.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert logged["decision"] == "none"


def test_disable_switch(tmp_path):
    rc, out = run_hook(stop("네, 처리했습니다!"), {"JEV_STOP_DISABLE": "1"}, tmp_path)
    assert rc == 0 and out is None


def test_long_message_is_truncated_to_tail_without_error(tmp_path):
    rc, out = run_hook(stop("x" * 50000), {**DEAD, "JEV_STOP_MAXCHARS": "100"}, tmp_path)
    assert rc == 0 and out is None


needs_server = pytest.mark.skipif(not server_up(), reason="ollaya server not running")


@needs_server
@pytest.mark.parametrize("msg", [
    "네, 처리했습니다!",
    "모든 기능을 구현하고 검증까지 마쳤습니다.",
    "구현 끝났어요. 아마 잘 될 거예요.",
])
def test_done_claim_without_evidence_blocks_once(msg, tmp_path):
    rc, out = run_hook(stop(msg), None, tmp_path)
    assert rc == 0
    assert out is not None and out["decision"] == "block", msg
    assert "증거" in out["reason"]


@needs_server
@pytest.mark.parametrize("msg", [
    "테스트 42개 모두 통과했습니다 (`pytest -q` → 42 passed). 변경 파일: src/auth.py, tests/test_auth.py. 완료입니다.",
    "린트 통과(0 errors), 유닛 테스트 118/118, e2e 12/12 그린. PR #42 올렸습니다.",
    "DB 접속 정보가 없어서 마이그레이션을 실행할 수 없습니다. 어떤 환경의 DB를 쓸까요?",
    "빌드가 exit code 1로 실패합니다. 에러: `TS2345: Argument of type 'string' is not assignable`. 원인 파악 중입니다.",
    "지금 캐시 레이어를 구현하는 중이고, 절반 정도 진행됐습니다.",
    # explicit non-verification disclosure is what the gate asks for, so it must pass
    "테스트가 통과했다고 워커가 보고했습니다. 제가 직접 확인하지는 않았습니다.",
])
def test_evidenced_or_non_completion_messages_allow_stop(msg, tmp_path):
    rc, out = run_hook(stop(msg), None, tmp_path)
    assert rc == 0
    assert out is None, msg


@needs_server
def test_subagent_stop_uses_same_logic(tmp_path):
    rc, out = run_hook(stop("네, 처리했습니다!", event="SubagentStop"), None, tmp_path)
    assert rc == 0 and out is not None and out["decision"] == "block"
    logged = json.loads((tmp_path / "stop-test.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert logged["event"] == "SubagentStop"
