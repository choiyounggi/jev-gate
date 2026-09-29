# jev-gate

**A local Jev-compatible decision model as an assistant for Claude Code, never the decider.**
로컬 판단 모델(ollaya가 서빙하는 winnow:e4b)이 Claude Code의 세 지점을 보조한다. 텍스트를 생성하지 않고
"선택지 중 어느 것인가, 확률은 얼마인가"만 답하므로 토큰 0, 호출당 약 0.75초, 비용 0이다.
모델은 **판단만** 하고, **결정은 결정론 규칙·Claude Code 권한 흐름·사람**이 내린다.

| 지점 | 무엇을 하나 | 어떻게 결정하나 |
|---|---|---|
| **Bash 게이트** (PreToolUse) | 위험 명령을 실행 전에 거른다 | 1) 하드 거부 목록 → exit 2 차단 · 2) 읽기 전용 빠른 경로 → allow, 모델 호출 없음 · 3) 모델: caution 확신 ≥ 0.8 ∧ 비가역 ≥ 0.7 → exit 2 차단, caution 확신 ≥ 0.8 → ask, clear 확신 ≥ 0.8 → allow, 그 외 결정 없음. override 마커는 사용자 허용 목록에 있는 한 줄 명령일 때만 모델을 건너뛴다 |
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

### 현장 하루치로 바꾼 것 (2026-09-29, 0.3.0)

첫날 로그 1,023건(Bash) + 344건(정지)을 세션 기록과 대조해 보니 평가 숫자와 다른 사실 네 가지가 나왔다. 각각이 0.3.0의 변경 하나에 대응한다.

| 관찰 (실측) | 변경 |
|---|---|
| bypassPermissions에서 모델의 `ask`는 대화형이면 그냥 실행되고(41/41), headless면 거부된다(17/17, 전부 사용자가 원한 발행) | 모델 계층에도 exit 2 경로와 override 경로를 둔다: caution ≥ 0.8 ∧ 비가역 ≥ 0.7이면 strict 차단(하루 로그에서 2건: `git reset -q --hard`, `git branch -D` 루프), `# jev-gate: override`가 있으면 모델을 건너뛴다 |
| `git reset -q --hard origin/main`이 `-q` 때문에 하드 목록을 통과했다 | reset·clean·checkout 정규식이 동사와 옵션 사이의 짧은 플래그를 허용한다 |
| 차단 10건 중 3건이 heredoc으로 파일에 쓰는 산문(`DROP TABLE`, `kubectl delete`, SVG 속 `rm -rf`) | heredoc 본문을 스캔에서 빼는 기능을 만들었다가 **철회**했다: 독립 리뷰의 적대적 검토 3라운드에서 정규식 기반 셸 읽기의 우회가 18개 나왔다(`hooks/NOTES.md`). 대신 차단 메시지가 "산문이면 Write 도구로 쓰라"고 안내하고, 그 우회 입력들은 회귀 테스트로 남겼다 |
| 13,000자 명령은 모델이 5 s, 동시 4요청 × 3.7k자는 요청당 3.5~4.3 s → 타임아웃 4 s에 44건(4.3%)이 판단 없이 통과 | 모델 입력을 3,000자로 자르고(앞 2,000 + 뒤 800, 로그는 원문) 타임아웃 기본을 6 s로. 재측정: 하루 최장 10건이 0.9~2.4 s |

정확도 쪽은 예측대로였다: clear 확신 최대 0.77이라 모델 allow 0건, 정지 게이트 차단 3/344건은 전부 기준 충족이고 그중 2건은 에이전트가 실제 출력을 인용하게 만들었다.

## 설정 (환경 변수)

| 변수 | 기본 | 뜻 |
|---|---|---|
| `JEV_GATE_STRICT` | `1` | 하드 거부 목록을 exit 2로 차단(bypassPermissions에서도 문서상 보증되는 유일한 차단). `0`이면 ask |
| `JEV_GATE_MODEL` | `winnow:e4b` | 두 훅과 setup이 쓰는 모델 |
| `JEV_GATE_URL` | `http://localhost:11435/v1/systemone` | TypeSafe 호환 엔드포인트. 호스팅 Jev로 바꿀 수 있다 |
| `JEV_GATE_THRESHOLD` | `0.8` | Bash 게이트 모델 확신 임계값 |
| `JEV_GATE_BLOCK_DESTRUCTIVE` | `0.7` | caution 확신 ≥ 임계값이면서 비가역 확률이 이 값 이상이면 strict 모드에서 exit 2 차단 |
| `JEV_GATE_MODEL_MAXCHARS` | `3000` | 모델에 보내는 명령 길이 상한(앞 2,000자 + 뒤 800자). 로그에는 원문이 남는다 |
| `JEV_GATE_TIMEOUT` | `6` | Bash 게이트 모델 호출 타임아웃(초) |
| `JEV_GATE_DISABLE` / `JEV_STOP_DISABLE` | | `1`이면 해당 훅 끄기 |
| `JEV_GATE_OVERRIDE_ALLOW` | `~/.config/jev-gate/override-allow` | 모델 계층이 override 마커를 따를 명령 패턴 파일 |
| `JEV_GATE_CURL_ALLOW` | `~/.config/jev-gate/curl-allow` | curl 변경 호출 규칙에서 뺄 명령 전체 패턴 파일 |
| `JEV_STOP_THRESHOLD` / `JEV_STOP_EVIDENCE_MAX` | `0.8` / `0.2` | 정지 게이트 임계값 |

Claude Code `settings.json`의 `env`에 넣으면 훅이 읽는다.

**override 마커**: 사용자가 대화에서 명시적으로 승인한 명령은 명령 **끝**에 `# jev-gate: override`를 붙여 재실행한다.
하드 거부 목록에 걸리면 strict 차단이 ask로 내려간다(allow는 되지 않는다). 로그에 override가 남는다.

**모델 계층 override는 사용자가 쓴 허용 목록으로만 열린다** (0.3.1). 마커는 에이전트가 타이핑하는 것이라,
마커만으로 모델을 끄면 트랜스크립트에 심긴 `node -e "…rmSync…"  # jev-gate: override`가 인라인 코드를 읽는 유일한 계층을 건너뛴다.
그래서 모델 계층은 다음을 모두 만족할 때만 마커를 따른다: 명령이 한 줄, 마커를 뗀 명령이 일반 문자 집합만 담음(아래), 그 명령 **전체**가
`~/.config/jev-gate/override-allow`(또는 `JEV_GATE_OVERRIDE_ALLOW`)의 한 줄(ERE, `^(…)$`로 고정, 빈 줄·`#` 주석 무시)과 일치.
아니면 마커를 무시하고 평소처럼 판단하며 로그에 이유를 남긴다. 파일이 없으면 모델 계층 override는 없다.

headless 워커가 발행·배포처럼 모델이 caution으로 볼 명령을 돌려야 하면, 그 명령의 **정확한 모양**을 허용 목록에 넣고 워커는 그 모양 그대로 마커를 붙인다.
패턴은 좁게 쓴다: 경로는 설치 위치와 데이터 폴더를 문자 그대로 고정하고, 인자 자리에 `[^ ]*`·`.*`를 쓰지 않는다
(느슨한 경로 자리에는 `node --eval=…//scripts/…`나 `--import=` 같은 옵션이 끼어든다 — 0.3.1 리뷰에서 실제로 나온 우회).
마커를 뗀 명령은 영문자·숫자·공백과 `. / _ - @ + , : = ~ "`만 담아야 하고(탭·따옴표 `'`·괄호·`$`·`*` 등은 거부), `#` 앞에는 공백이 있어야 마커로 인정된다.
예: auto-velog 발행 (`/Users/you`를 자기 홈으로, `0\.2\.1`을 설치된 버전으로 — 캐시에 남은 옛 버전까지 맞지 않게 버전은 와일드카드로 두지 않는다)

```
# auto-velog: 헤드리스 발행 (publish.mjs --auto가 mode·점수·초안 폴더·상한·시크릿을 코드로 확인한다)
node "?/Users/you/\.claude/plugins/cache/auto-velog/auto-velog/0\.2\.1/scripts/adapters/velog/publish\.mjs"? "?/Users/you/\.auto-velog/drafts/[A-Za-z0-9_][A-Za-z0-9_.-]*\.md"?( "?/Users/you/\.auto-velog/drafts/[A-Za-z0-9_][A-Za-z0-9_.-]*\.png"?)? --auto
```

마커 없이 문구만 바꿔 재시도하는 것은 게이트를 속이는 일이다.

**curl 허용 목록** (0.3.1): 하드 거부 목록의 curl 규칙은 원격으로 가는 변경 호출(`-X POST|PUT|DELETE|PATCH`, `-d`, `--data`)을 막는다.
Jira 상태 전이처럼 늘 쓰는 호출은 그 **명령 전체 모양**을 `~/.config/jev-gate/curl-allow`(또는 `JEV_GATE_CURL_ALLOW`)에 한 줄씩(ERE, `^(…)$`로 고정) 적어 이 규칙에서 뺄 수 있다.
빠진 명령도 **허용되는 것이 아니라** 평소처럼 판단 모델과 Claude Code 권한 흐름으로 간다. 명령이 다음 중 하나면 목록과 상관없이 막힌다:

- 여러 줄이거나, 출력 가능한 ASCII 밖의 문자(탭·CR·한글 등)가 있다
- `; & | < > \`·백틱·`$(`가 있다 — 두 번째 명령이나 명령 결과를 끼워 넣을 수 없다

주소만 적는 방식은 쓰지 않는다: 리뷰에서 목록에 있는 주소 옆에 `evil.example`(스킴 없는 두 번째 주소)·`--url`·`--next`·`-x` 프록시·
`--resolve`·`-sd@파일`·`-H @파일`·`--variable`을 붙여 토큰이나 파일을 다른 곳으로 보내는 우회가 18가지 나왔다. 명령 전체를 고정하면 옵션을 더할 자리가 없다.

예: Jira Cloud 상태 전이. 막힌 명령은 `~/.local/state/jev-gate/decisions.jsonl`에 그대로 남아 있으니 그 줄을 복사해
이슈 키·전이 ID처럼 바뀌는 자리만 패턴으로 바꾼다(`$`·`{`·`}`·`.`는 `\`로 이스케이프). `acme`는 자기 사이트로, Server/DC면 호스트와 `/rest/api/2/`로.

```
# Jira 상태 전이: 사이트·인증·헤더·본문 고정, 이슈 키와 전이 ID만 바뀐다 (-q: ~/.curlrc 무시)
curl -q -s -X POST -u "\$JIRA_EMAIL:\$JIRA_API_TOKEN" -H "Content-Type: application/json" "https://acme\.atlassian\.net/rest/api/3/issue/[A-Z][A-Z0-9_]+-[0-9]+/transitions" -d '\{"transition":\{"id":"[0-9]+"\}\}'
```

줄에는 모든 옵션을 문자 그대로 고정하고 맨 앞에 `-q`를 둔다(curl이 `~/.curlrc`를 읽지 않게). 에이전트가 쓰는 명령에도 `-q`를 붙여야 일치한다.
`curl .*` 같은 느슨한 줄은 `--url evil.example` 같은 옵션을 통과시키므로 규칙을 끄는 것과 같다.
남는 위험: `https_proxy`·`CURL_CA_BUNDLE` 같은 환경 변수는 `-q`로도 막히지 않는다(세션이 뜨는 환경의 문제). 기존 localhost 예외는 `https?://` 주소만 보므로,
`http://localhost:…/` 옆에 스킴 없는 두 번째 주소를 붙인 curl도 이 규칙에서는 빠진다(모델 판단은 거친다).

**알려진 마찰**: 하드 거부 목록은 명령 *텍스트* 전체를 보므로 heredoc으로 파일에 쓰는 산문에 `git push --force` 같은 문구가 있어도 차단된다(하루 1,023건 중 3건).
차단 메시지가 그 경우를 안내하며, 그런 글은 Write/Edit 도구로 쓴다. 본문을 스캔에서 빼는 기능은 우회가 계속 나와 철회했다(`hooks/NOTES.md`).
`npm publish`는 사용자 allowlist에 흔해 하드 목록에 없고 모델 계층으로 간다.

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
