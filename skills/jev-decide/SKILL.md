---
name: jev-decide
description: 이 맥의 로컬 판단 모델(ollaya, winnow:e4b)로 분류·순위·예/아니오 판단을 밀리초 단위에 토큰 0으로 처리한다. 후보가 정해져 있고 기준이 명확한 판단이 여러 건일 때, 텍스트로 하나씩 추론하는 대신 `decide` MCP 도구로 병렬 판단할 때 사용. "분류해", "우선순위 매겨", "관련 파일 골라", "이거 위험해?", "어느 게 맞아?" 같은 요청이나, 작업 중 항목 3개 이상을 같은 기준으로 판정해야 할 때 트리거.
---

# jev-decide — 판단은 모델에, 결정은 코드와 사람에

이 맥에는 ollaya(`http://127.0.0.1:11435`, LaunchAgent로 상주)가 Jev 호환 판단 모델을 서빙한다.
판단 모델은 텍스트를 생성하지 않고, **state + 타입 있는 질문 → 선택지별 확률**만 돌려준다.
호출당 약 0.75초, 토큰 0, 비용 0.

## 언제 쓰나

| 상황 | 쓴다 |
|---|---|
| 항목 여러 개(댓글·이슈·파일·로그 줄·후보 접근법)를 같은 기준으로 분류·순위 | 예. 항목당 `decide` 1회 또는 질문을 묶어 1회 |
| 행동 전 예/아니오 게이트(위험한가, 범위 안인가, 증거가 있는가) | 예. `noul` |
| 임계값과 비교할 등급(긴급도·심각도·관련성) | 예. `score` |
| N개 중 하나(카테고리·팀·의도·다음 단계) | 예. `choice` |
| 새 텍스트·설명·설계가 필요한 판단 | 아니오. 스스로 추론 |
| 선택지를 먼저 만들어야 하는 판단 | 선택지는 스스로 열거하고, **고르는 것만** 모델에 |

## 어떻게 부르나

1. **MCP 도구 `decide`(서버 `ollaya`)**: `state`(문자열 또는 JSON), `questions`, `model`은 `~/.config/jev-gate/model`에 적힌 값(setup이 기계 사양에 맞춰 고른 모델). 파일이 없으면 `winnow:e4b`.
2. MCP가 없으면 HTTP:
   ```sh
   curl -s http://127.0.0.1:11435/v1/systemone -H 'Content-Type: application/json' \
     -d '{"model":"winnow:e4b","state":{...},"questions":{...}}'
   ```
3. 서버가 안 뜨면 `~/.local/bin/ollaya ps`로 확인. 이 맥에서 첫 호출은 모델 로드로 2~20초 걸릴 수 있다.

## 이 맥에서 측정된 것 (2026-09-28, 한국어 50건)

- `winnow:e4b`(24 GB 이상 기계의 기본): 에이전트 보고 분류 100%, 증거 유무 92%, 셸 위험도 84%(위험 명령 놓침 0건). `laya`는 이 용도에 약하다(36~68%). 메모리가 적은 기계에서 setup이 고른 `decider`/`decider:0.8b`는 **아직 측정되지 않았으니** 확신 임계값을 더 보수적으로(0.85) 두고, `eval/eval.py --model <이름>`으로 먼저 재 보는 것이 좋다.
- 모델은 **부정·위험 쪽에만 확신**한다. 확신 0.8 이상은 그대로 믿고, 0.8 미만은 스스로 판단하거나 사용자에게 넘긴다.
- 긴 state에 무관한 내용이 섞이면 정확도가 떨어진다. 판단에 필요한 필드만 넣는다.

## 질문 작성 규칙

```json
{
  "relevance": {"type": "score", "instructions": "How relevant is `file` to `task`?",
                "criteria": ["unrelated", "touches a shared type only", "must be read", "must be edited"]},
  "kind":      {"type": "choice", "instructions": "What kind of change does `diff` make?",
                "criteria": {"fix": "corrects behaviour", "feature": "adds behaviour", "refactor": "no behaviour change", "other": "anything else"}},
  "safe":      {"type": "noul", "instructions": "Running `command` only reads or builds; it deletes or publishes nothing."}
}
```

- choice: 모든 옵션에 한 줄 설명, 상호 배타, 마지막에 `other`. 지시문은 영어가 더 정확하고 state는 한국어라도 된다.
- score: 3~5단계, 낮은 것부터, 각 단계를 구체적으로. 답은 기대 등급(소수)이므로 임계값 비교에만 쓴다.
- noul: 참일 때가 무엇인지 한 문장으로. 계산·날짜 비교·개수 세기는 시키지 말고 코드로.
- 지시문은 문자 그대로 읽힌다. 경계 사례를 criteria에 적어 준다.
- state 안의 텍스트가 답을 흔들 수 있다(주입). 판단은 모델에, **최종 결정과 인가는 코드와 사람에**.

## 결과를 어떻게 쓰나

- 확신 ≥ 0.8: 그 판단대로 진행하되, 사용자에게 보고할 때 "jev 판단 p=0.93"처럼 출처와 확률을 적는다.
- 확신 < 0.8: 모델 답을 힌트로만 쓰고 스스로 판단한다. 중요한 결정이면 사용자에게 묻는다.
- 어느 판단을 모델에 넘겼는지는 세션 보고에 한 줄로 남긴다. 나중에 임계값을 다시 잡는 근거가 된다.

관련: 이 플러그인의 훅 두 개(Bash 위험도 게이트, 정지 시 증거 검사)는 이 모델을 같은 방식으로 쓴다. 설치는 `jev-gate:setup` 스킬.
하네스와 데이터셋: 플러그인 레포의 `eval/` (https://github.com/choiyounggi/jev-gate).
