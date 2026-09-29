---
name: setup
description: jev-gate 첫 온보딩. 이 기계의 메모리·GPU에 맞는 판단 모델을 골라 ollaya(로컬 Jev 호환 서버)를 ~/.local에 설치하고 모델을 내려받아 상주시킨 뒤 판단 한 건으로 검증한다. 세션 시작 시 "jev-gate onboarding" 안내가 보일 때, "jev-gate 설정", "jev-gate setup", "판단 모델 설치", "ollaya 설치" 요청에 트리거.
---

# jev-gate 온보딩

훅 두 개(Bash 게이트, 정지 게이트)와 `decide` MCP 도구는 로컬 판단 모델 서버가 있어야 모델 계층이 동작한다.
서버가 없어도 훅은 결정론 규칙만으로 fail-open 동작하므로 세션이 막히지는 않는다. 이 스킬은 **그 모델 계층을 사용자 기계에 맞게** 켠다.

## 절차

### 1. 기계에 맞는 모델 추천을 받는다

```sh
bash "${CLAUDE_PLUGIN_ROOT}/scripts/recommend-model.sh" --json
```

메모리(Apple silicon 통합 메모리 / 시스템 RAM)와 NVIDIA VRAM을 읽어 아래 표의 한 단계를 고른다.

| 기계 | 추천 | 다운로드 | 근거 |
|---|---|---|---|
| NVIDIA VRAM ≥ 12 GB, 또는 메모리 ≥ 24 GB | `winnow:e4b` | ~8 GB | jev-gate가 직접 측정한 유일한 모델: 셸 위험도 84%(위험 명령 놓침 0건), 에이전트 보고 분류 100%. 로드 중 약 8 GB를 고정 점유, 유휴 1시간 후 해제 |
| 메모리 16–23 GB | `decider` | ~4 GB | Qwen3.5 2.2B, typed-decisions 0.680(작성자 보고). IDE·브라우저와 함께 써도 스왑을 밀지 않는 선택 |
| 메모리 8–15 GB | `decider:0.8b` | ~1.5 GB | 가장 가벼운 디코더 |
| 메모리 < 8 GB | `laya` | ~1.5 GB | 100 ms 인코더. 셸 위험 판단은 약함(36~68%)이라 게이트는 결정론 규칙에 더 의존하게 된다 |

### 2. 사용자에게 선택을 받는다 (AskUserQuestion)

추천 모델을 첫 번째 옵션 "(Recommended)"으로, 나머지를 대안으로 제시한다. 반드시 함께 알릴 것:
- 다운로드 용량과 로드 시 메모리 점유(모델 크기와 거의 같다).
- `winnow:e4b` 외에는 jev-gate가 정확도를 측정하지 않았다. 작은 모델을 고르면 훅의 임계값을 더 보수적으로 두라고 권한다(`JEV_GATE_THRESHOLD=0.85`).
- 나중에 `JEV_GATE_MODEL=<이름> bash …/setup-ollaya.sh`로 언제든 바꿀 수 있다.

### 3. 설치를 실행한다

```sh
JEV_GATE_MODEL=<선택한 모델> bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-ollaya.sh"
```

멱등이다. 이미 설치·다운로드·서빙 중인 단계는 건너뛴다. `:11435`를 다른 프로세스가 이미 서빙하면 LaunchAgent를 쓰지 않는다.
선택한 모델은 `~/.config/jev-gate/model`에 기록되어 훅 두 개와 `decide` 스킬이 같은 모델을 쓴다.

### 4. 증거를 보여준다

출력의 `probe ok:` 줄(모델이 실제로 답한 JSON)을 사용자에게 그대로 보여준다. 이것이 모델 계층이 살아 있다는 증거다.
MCP 도구 `decide`는 **다음 세션부터** 보인다고 알린다(플러그인 MCP는 세션 시작 시 연결).

### 5. (선택) 작은 모델을 골랐으면 측정을 권한다

```sh
cd "${CLAUDE_PLUGIN_ROOT}/eval" && TYPESAFE_API_KEY=local TYPESAFE_BASE_URL=http://localhost:11435 \
  uv run --with typesafe-sdk python eval.py --model <선택한 모델>
```

한국어 50건에 대한 일치율과 확신 분포가 나온다. 결과의 `agreement when confident` 열이 90% 아래면 임계값을 올린다.

## 제거

```sh
launchctl bootout gui/$(id -u)/com.jev-gate.ollaya; rm ~/Library/LaunchAgents/com.jev-gate.ollaya.plist
rm -r ~/.ollaya/models ~/.config/jev-gate    # 모델 파일과 선택 기록
rm ~/.local/bin/ollaya
```

## 문제가 생기면

- 첫 호출이 10초 넘게 걸리면 콜드 로드다(디스크에서 8 GB). 훅은 4~6초 타임아웃으로 그 호출을 건너뛰고 다음 호출부터 정상.
- `~/.ollaya/logs/launchd.log`에 "already running"이 반복되면 수동으로 띄운 서버가 포트를 잡고 있다: `pgrep -fl 'ollaya serve'`로 찾아 종료.
- 메모리 압력이 높은 기계(오케스트레이션 세션 다수, 대형 VM)에서는 `OLLAYA_KEEP_ALIVE=10m`로 짧게 잡거나 한 단계 작은 모델로 바꾼다.
