# jev-gate

**A local Jev-compatible decision model as an assistant for Claude Code, never the decider.**
로컬 판단 모델(ollaya가 서빙하는 winnow:e4b)이 Claude Code의 세 지점을 보조한다. 텍스트를 생성하지 않고
"선택지 중 어느 것인가, 확률은 얼마인가"만 답하므로 토큰 0, 호출당 약 0.75초, 비용 0이다.
모델은 **판단만** 하고, **결정은 결정론 규칙·Claude Code 권한 흐름·사람**이 내린다.

| 지점 | 무엇을 하나 | 어떻게 결정하나 |
|---|---|---|
| **Bash 게이트** (PreToolUse) | 위험 명령을 실행 전에 거른다 | 1) 하드 거부 목록 → exit 2 차단 · 2) 읽기 전용 빠른 경로 → allow, 모델 호출 없음 · 3) 모델: caution 확신 ≥ 0.8 → ask, clear 확신 ≥ 0.8 → allow, 그 외 결정 없음 |
| **정지 게이트** (Stop · SubagentStop) | 증거 없는 "완료" 주장을 되돌린다 | done_claimed p ≥ 0.8 ∧ evidence p ≤ 0.2 → 정지 1회 차단, 이유 반환. 미검증을 명시한 보고는 통과 |
| **`decide` MCP 도구 + `jev-decide` 스킬** | 에이전트가 분류·순위·예/아니오 판단을 병렬로 넘긴다 | 확신 ≥ 0.8만 신뢰, 선택지 열거·설계·인가는 에이전트가 |

서버가 없거나 타임아웃이면 모든 훅은 **결정 없이 통과**(fail-open)하고, 오류로 자동 allow 하는 일은 없다.
모든 판단은 `~/.local/state/jev-gate/*.jsonl`에 남아 임계값을 다시 잡는 근거가 된다.

## 설치

```sh
claude plugin marketplace add choiyounggi/groundwork
claude plugin install jev-gate@groundwork
```

### 첫 온보딩: 기계에 맞는 모델 고르기

설치 직후 첫 세션이 시작되면 SessionStart 훅이 모델 계층이 비어 있음을 알리고 **이 기계에 맞는 모델**을 추천한다.
그 상태에서도 훅 두 개는 결정론 규칙만으로 동작하며 아무것도 막지 않는다. `/jev-gate:setup`을 실행하면 추천을 첫 옵션으로
선택지를 묻고, ollaya를 `~/.local`에 설치하고 모델을 받아 상주시킨 뒤 판단 한 건으로 검증한다. 선택은 `~/.config/jev-gate/model`에
기록되어 훅 두 개와 `decide` 도구가 같은 모델을 쓴다.

| 기계 (`scripts/recommend-model.sh`가 감지) | 추천 모델 | 다운로드 | 정확도 근거 |
|---|---|---|---|
| NVIDIA VRAM ≥ 12 GB 또는 메모리 ≥ 24 GB | `winnow:e4b` (Gemma-4 7.5B Q8) | ~8 GB | jev-gate 측정: 셸 위험도 84%(위험 명령 놓침 0건), 보고 분류 100% |
| 메모리 16–23 GB | `decider` (Qwen3.5 2.2B) | ~4 GB | 작성자 보고 typed-decisions 0.680, jev-gate 미측정 |
| 메모리 8–15 GB | `decider:0.8b` | ~1.5 GB | 미측정 |
| 메모리 < 8 GB | `laya` (인코더, ~100 ms) | ~1.5 GB | 셸 위험 판단 약함(36~68%) → 규칙 계층에 의존 |

로드 중 메모리 점유는 다운로드 크기와 거의 같고, 1시간 유휴 후 자동 해제된다. 언제든 `JEV_GATE_MODEL=<이름> bash scripts/setup-ollaya.sh`로 바꿀 수 있고,
작은 모델을 골랐다면 `eval/eval.py --model <이름>`으로 먼저 재 보고 `JEV_GATE_THRESHOLD`를 0.85로 올리는 것을 권한다.

요구 사항: macOS Apple silicon 또는 Linux(glibc ≥ 2.38), `jq`, `curl`.

## 왜 이 설계인가 (측정 근거)

한국어 50건 데이터셋(`eval/dataset.json`: 셸 명령 25건 + 에이전트 보고 25건)으로 재 본 결과, Apple M4 Pro 24 GB:

| 모델 | 셸 위험도 | 셸 비가역 | 보고 분류 | 증거 유무 | p50 지연 |
|---|---|---|---|---|---|
| **winnow:e4b** | 84% (위험 명령 놓침 0건) | 96% | 100% | 92% | 763 ms |
| laya | 68% | 36% | 52% | 56% | 127 ms |

- 모델은 **위험한 쪽에만 확신**한다. caution 라벨 12건 중 11건이 p ≥ 0.85, clear 라벨 13건은 최대 p 0.77.
  그래서 임계값 0.8에서 모델의 allow는 나오지 않고(잘못된 allow 0건), 절약은 읽기 전용 빠른 경로가, 모델은 안전 방향 ask만 더한다.
- 위험도 오답 4건은 전부 과잉 에스컬레이션(`git status`, `rm -rf node_modules && npm ci`, `prettier --write`, `docker compose up -d`).
- laya는 100 ms지만 셸 판단이 편향되어 이 용도에 부적합하다. 기본 모델은 항상 winnow:e4b.
- 첫 버전의 빠른 경로는 `cat ~/.ssh/id_ed25519 | pbcopy`까지 통과시키는 버그가 있었다(`while read`가 개행 없는 마지막 줄을 버림).
  **게이트는 알려진-나쁜 입력으로 깨뜨려 보기 전까지 가설이다.** `tests/`에 그 입력들이 남아 있다.

자세한 기록: `hooks/NOTES.md`, 결과 파일: `eval/results/`.

## 설정 (환경 변수)

| 변수 | 기본 | 뜻 |
|---|---|---|
| `JEV_GATE_STRICT` | `1` | 하드 거부 목록을 exit 2로 차단(bypassPermissions에서도 문서상 보증되는 유일한 차단). `0`이면 ask |
| `JEV_GATE_MODEL` | `winnow:e4b` | 두 훅과 setup이 쓰는 모델 |
| `JEV_GATE_URL` | `http://localhost:11435/v1/systemone` | TypeSafe 호환 엔드포인트. 호스팅 Jev로 바꿀 수 있다 |
| `JEV_GATE_THRESHOLD` | `0.8` | Bash 게이트 모델 확신 임계값 |
| `JEV_GATE_TIMEOUT` | `4` | Bash 게이트 모델 호출 타임아웃(초) |
| `JEV_GATE_DISABLE` / `JEV_STOP_DISABLE` | | `1`이면 해당 훅 끄기 |
| `JEV_STOP_THRESHOLD` / `JEV_STOP_EVIDENCE_MAX` | `0.8` / `0.2` | 정지 게이트 임계값 |

Claude Code `settings.json`의 `env`에 넣으면 훅이 읽는다.

**override 마커**: 사용자가 대화에서 명시적으로 승인한 명령이 하드 거부 목록에 걸리면, 명령 **끝**에 `# jev-gate: override`를 붙여 재실행한다.
strict 차단이 ask로 내려가고 로그에 override가 남는다.

**알려진 마찰**: 하드 거부 목록은 명령 *텍스트*를 보므로 heredoc으로 파일에 쓰는 산문에 `git push --force` 같은 문구가 있어도 차단된다.
그런 글은 Write/Edit 도구로 쓴다. `npm publish`는 사용자 allowlist에 흔해 하드 목록에 없고 모델 계층으로 간다.

## 레포 구조

```
.claude-plugin/plugin.json   플러그인 매니페스트
hooks/hooks.json             SessionStart(preflight) · PreToolUse Bash · Stop · SubagentStop
hooks/jev-bash-gate.sh       Bash 게이트
hooks/jev-stop-gate.sh       정지 게이트
hooks/preflight.sh           서버가 없으면 한 줄 안내
.mcp.json                    ollaya MCP 서버(decide · list_models · show_model · pull_model)
scripts/ollaya-mcp-launch.sh ollaya 위치를 찾아 `ollaya mcp` 실행
scripts/setup-ollaya.sh      멱등 설치 스크립트
skills/jev-decide/           에이전트가 판단을 넘길 때의 규칙
skills/setup/                설치 절차
eval/                        데이터셋 50건, 측정 하네스(공식 typesafe-sdk로 드롭인 검증), 결과
tests/                       훅 테스트(알려진-좋은/나쁜 입력, 서버 없이 결정론 계층 검증)
```

테스트: `uv run --with pytest --with typesafe-sdk python -m pytest -q tests eval`

## 한계

- 라벨 50건은 한 사람이 만든 것이다. "정확도"가 아니라 "라벨 작성자와의 일치율"로 읽을 것.
- 한국어 state에 영어 지시문 조합으로만 측정했다. 다른 언어·도메인은 `eval/eval.py --model <이름>`으로 먼저 재 볼 것.
- bypassPermissions 모드에서 훅의 `ask`가 프롬프트를 띄우는지는 공식 문서에 없다. 그래서 strict 모드가 기본이다.
- Jev 자체의 접근·가격·한계는 [TypeSafe 문서](https://docs.typesafe.ai)와 `hooks/NOTES.md`를 볼 것. 이 플러그인은 TypeSafe·ollaya와 무관한 독립 프로젝트다.

## 라이선스

MIT. 모델과 ollaya는 각자의 라이선스를 따른다(winnow: Apache-2.0, Gemma 4 기반).
