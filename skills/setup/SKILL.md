---
name: setup
description: jev-gate 플러그인의 모델 계층 설치. ollaya(로컬 Jev 호환 판단 모델 서버)를 ~/.local에 설치하고 winnow:e4b(8 GB)를 내려받아 LaunchAgent로 상주시킨 뒤 판단 한 건으로 동작을 확인한다. "jev-gate 설정", "jev-gate setup", "ollaya 설치", 세션 시작 시 "decision server is not answering" 안내가 보일 때 트리거.
---

# jev-gate 설치

이 플러그인의 훅 두 개(Bash 게이트, 정지 게이트)와 `decide` MCP 도구는 로컬 판단 모델 서버가 있어야 모델 계층이 동작한다.
서버가 없어도 훅은 결정론 규칙만으로 fail-open 동작하므로 세션이 막히지는 않는다.

## 절차

1. 사용자에게 알린다: 약 8 GB 다운로드(winnow:e4b), 모델이 메모리에 올라가면 wired 메모리 약 8 GB, 1시간 유휴 후 자동 언로드. 16 GB 이하 맥이면 `JEV_GATE_MODEL=kev:0.8b`(1 GB급, 정확도 미측정)를 권한다.
2. 실행:
   ```sh
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-ollaya.sh"
   ```
   멱등이다. 이미 설치·다운로드·서빙 중인 단계는 건너뛴다. `:11435`를 다른 프로세스가 이미 서빙하면 LaunchAgent를 쓰지 않는다.
3. 출력의 마지막 `probe ok:` 줄을 사용자에게 그대로 보여준다. 이것이 모델 계층이 살아 있다는 증거다.
4. MCP 도구 `decide`는 **다음 세션부터** 보인다고 알린다(플러그인 MCP는 세션 시작 시 연결).

## 제거

```sh
launchctl bootout gui/$(id -u)/com.jev-gate.ollaya; rm ~/Library/LaunchAgents/com.jev-gate.ollaya.plist
rm -r ~/.ollaya/models        # 모델 파일 (8~10 GB)
rm ~/.local/bin/ollaya
```

## 문제가 생기면

- 첫 호출이 10초 넘게 걸리면 콜드 로드다(디스크에서 8 GB). 훅은 4~6초 타임아웃으로 그 호출을 건너뛰고 다음 호출부터 정상.
- `~/.ollaya/logs/launchd.log`에 "already running"이 반복되면 수동으로 띄운 서버가 포트를 잡고 있다: `pgrep -fl 'ollaya serve'`로 찾아 종료.
- 메모리 압력이 높은 기계(오케스트레이션 세션 다수, 대형 VM)에서는 `OLLAYA_KEEP_ALIVE=10m`로 짧게 잡는다.
