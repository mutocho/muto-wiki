---
title: Superpowers — 코딩 에이전트를 위한 스킬 기반 개발 방법론
category: 참고자료
tags: [ai-agent, development-workflow, skills, tdd, code-review]
summary: 설계 승인부터 계획·TDD·리뷰·완료 검증까지 코딩 에이전트의 작업 규율을 조합 가능한 스킬로 강제하는 오픈소스 개발 방법론.
sources: ["https://github.com/obra/superpowers"]
source_url: "https://github.com/obra/superpowers"
status: draft
created: 2026-08-12
updated: 2026-08-12
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **가져올 핵심: "설계 승인 없이 구현 시작 금지" 게이트.** DB 운영 도구 개발에서 가장 비싼 실수는 잘못된 것을 잘 만드는 것이다 — 이 게이트 하나가 그걸 막는다
> - **작업 크기에 따라 절차를 줄일 운영 기준이 반드시 필요하다.** 작은 수정에까지 설계·계획·TDD·이중 리뷰를 걸면 절차 비용이 변경 비용을 넘는다 ^[inferred]
> - **기본 흐름이 Git 브랜치·worktree를 전제한다** — 브랜치를 쓰지 않는 저장소(이 위키가 그렇다)나 운영 변경 작업에는 그대로 적용하지 않고 로컬 규칙을 우선한다
> - **설치했다는 사실과 실제로 발동한다는 사실은 다르다.** 대표 시나리오에서 게이트가 실제로 걸리는지 시험한다 ^[inferred]
> - **이중 리뷰·서브에이전트는 호출 수와 지연을 늘린다.** 실질 결함 발견률을 측정해 사용 범위를 정한다
> - [[aws-aidlc-workflows-v2-study]]와 보완 관계 — AI-DLC는 상위 생명주기 오케스트레이션, Superpowers는 세션 단위 실행 규율

# Superpowers — 코딩 에이전트를 위한 스킬 기반 개발 방법론

## 개요

[Superpowers](https://github.com/obra/superpowers)는 Jesse Vincent와 Prime Radiant가 만든 MIT 라이선스 오픈소스 프로젝트다. 코딩 에이전트가 상황에 맞는 `SKILL.md`를 자동으로 불러 설계, 계획, 구현, 디버깅, 리뷰, 완료 검증을 정해진 절차로 수행하게 한다.

핵심 가치는 에이전트의 즉흥적인 코드 생성을 줄이고 **사전 설계, 작은 실행 단위, 테스트 우선, 독립 검토, 증거 기반 완료 선언**을 기본 행동으로 만드는 데 있다. 개별 스킬은 조합 가능하지만, 적용 조건이 맞으면 선택 사항이 아니라 필수 워크플로로 취급된다.

## 기본 개발 흐름

1. **`brainstorming`** — 프로젝트 맥락을 확인하고 질문을 한 번에 하나씩 던져 목적·제약·성공 조건을 구체화한다. 2~3개 접근법과 장단점을 제시하고, 설계를 구간별로 승인받은 뒤 명세를 저장한다.
2. **`using-git-worktrees`** — 구현 전에 새 브랜치의 격리된 작업공간을 만들고 의존성 설치와 테스트 기준선을 확인한다.
3. **`writing-plans`** — 승인된 명세를 정확한 파일 경로, 구현 내용, 테스트와 검증 명령이 포함된 작은 작업으로 분해한다.
4. **`subagent-driven-development` 또는 `executing-plans`** — 계획의 각 작업을 실행한다. 서브에이전트를 지원하는 환경에서는 작업마다 새로운 구현 에이전트를 쓰고, 명세 준수 검토 후 코드 품질 검토를 수행한다.
5. **`test-driven-development`** — 실패하는 테스트를 먼저 확인하고 최소 구현으로 통과시킨 뒤 리팩터링하는 RED-GREEN-REFACTOR를 강제한다.
6. **`requesting-code-review`** — 계획과 구현을 대조하고 심각도별 문제를 식별한다. 치명적 문제는 다음 단계 진행을 막는다.
7. **`finishing-a-development-branch`** — 전체 테스트를 다시 검증하고 병합, PR, 브랜치 유지, 폐기 중 후속 처리를 선택하게 한다.

## 보조 스킬

- **`systematic-debugging`** — 오류 재현과 증거 수집, 작동하는 사례 비교, 단일 가설의 최소 검증, 근본 원인 수정의 4단계를 따른다. 근본 원인을 조사하기 전에 수정안을 내지 않는 것이 핵심 규칙이다.
- **`verification-before-completion`** — “완료”, “통과”, “수정됨” 같은 주장을 하기 직전에 검증 명령을 새로 실행하고 그 결과를 근거로 삼는다.
- **`dispatching-parallel-agents`** — 상태나 순서 의존성이 없는 작업만 병렬화한다.
- **`receiving-code-review`** — 리뷰 의견을 무조건 수용하지 않고 기술적으로 검증한 뒤 반영한다.
- **`writing-skills`** — 스킬 자체도 실패하는 행동 테스트를 먼저 만든 뒤 작성·수정하도록 요구한다.

## 설계 철학

- **TDD 우선**: 구현보다 실패 테스트가 먼저다.
- **체계적 절차 우선**: 디버깅과 개발을 추측이나 임시 대응에 맡기지 않는다.
- **복잡성 축소**: YAGNI와 작은 책임 단위를 통해 에이전트가 한 번에 이해해야 할 범위를 줄인다.
- **주장보다 증거**: 테스트·리뷰·검증 결과 없이 완료를 선언하지 않는다.
- **컨텍스트 격리**: 서브에이전트에는 현재 세션 전체가 아니라 해당 작업에 필요한 정보만 전달한다.

## 강점과 한계

### 강점

- 아이디어에서 구현 완료까지 이어지는 일관된 품질 게이트를 제공한다.
- 짧은 작업 단위, 테스트 우선, 명세·품질의 2단계 리뷰로 장시간 자율 실행의 이탈 위험을 낮춘다.
- 방법론을 Markdown 스킬로 제공하고 여러 코딩 에이전트 환경에 맞는 설치 표면을 지원한다.
- 작업 종료 시점까지 검증과 브랜치 정리를 포함해 “코드 작성” 외의 엔지니어링 절차도 다룬다.

### 한계와 도입 판단

- 작은 수정에도 설계·계획·TDD·리뷰 단계를 적용하면 절차 비용이 실제 변경 비용보다 커질 수 있다. 작업 크기에 따라 설계와 계획의 분량을 축소할 운영 기준이 필요하다. ^[inferred]
- 스킬 준수는 호스트 에이전트의 스킬 발견과 지침 우선순위 처리에 의존한다. 설치 후 “스킬이 존재한다”는 확인보다 대표 시나리오에서 실제 발동·게이트 준수를 시험해야 한다. ^[inferred]
- 기본 흐름은 Git 브랜치와 worktree를 전제로 한다. 브랜치를 쓰지 않는 저장소나 운영 변경 작업에는 그대로 적용하지 말고 로컬 규칙을 우선해야 한다.
- 서브에이전트 구현과 이중 리뷰는 품질을 높일 수 있지만 호출 수와 지연도 늘린다. 작업 독립성, 모델 비용, 리뷰의 실질적 결함 발견률을 측정해 사용 범위를 정해야 한다. ^[inferred]

## 지원 환경과 설치 메모

공식 README는 Claude Code, Antigravity, Codex App·CLI, Cursor, Factory Droid, Gemini CLI, GitHub Copilot CLI, Kimi Code, OpenCode, Pi를 안내한다. 여러 환경을 함께 쓰면 각 환경에 별도로 설치해야 한다. Codex App과 CLI에서는 공식 플러그인 마켓플레이스의 **Superpowers** 항목으로 설치할 수 있다.

`brainstorming`의 선택적 visual companion은 기본적으로 Prime Radiant 로고를 웹에서 불러오며 사용 중인 Superpowers 버전을 포함한다. 프로젝트 내용이나 클릭 정보는 전송하지 않는다고 명시되어 있고, `SUPERPOWERS_DISABLE_TELEMETRY` 등으로 비활성화할 수 있다.

## AI-DLC와의 관계

[[aws-aidlc-workflows-v2-study|AWS AI-DLC Workflows 2.0]]이 전체 생명주기의 상태 머신, 단계 계약, 감사 로그, 승인과 복구를 구조화한다면 Superpowers는 개별 코딩 세션에서 에이전트가 지켜야 할 설계·TDD·디버깅·리뷰 규율을 스킬 조합으로 강제하는 데 더 집중한다. 둘은 대체 관계라기보다 **AI-DLC가 상위 오케스트레이션을, Superpowers가 작업 단계별 실행 규율을 제공하는 보완 관계**로 검토할 수 있다. ^[inferred]

## Related

- [[aws-aidlc-workflows-v2-study|AWS AI-DLC Workflows 2.0 분석 및 학습 노트]]
- [[dba-agent-work-plan|DBA Agent 구조 개편 및 주간 분석 작업 계획]]
- [[dev-tooling-standards|개발 도구 운영 기준]]

## Sources

- <https://github.com/obra/superpowers>
- <https://github.com/obra/superpowers/blob/main/skills/brainstorming/SKILL.md>
- <https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md>
- <https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md>
- <https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md>
