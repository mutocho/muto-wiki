---
title: AWS AI-DLC Workflows 2.0 분석 및 학습 노트
category: 업무기록
tags: [worklog, ai, agent, workflow, aidlc]
summary: AWS AI-DLC Workflows 2.0의 멀티 에이전트 생명주기와 승인·학습 구조를 정리하고, 사내 DBA Agent 적용 및 Superpowers 비교 과제를 추적하는 학습 노트.
sources: ["https://github.com/awslabs/aidlc-workflows", "https://github.com/awslabs/aidlc-workflows/tree/v2", 사내 공유 (2026-08-12)]
source_url: "https://github.com/awslabs/aidlc-workflows"
status: draft
created: 2026-08-12
updated: 2026-08-12
notion_page_id: "3befb969-b8be-81e0-8f87-fc0a5e184d39"
notion_synced: "2026-08-16T20:19:56+09:00"
---

> [!tip] 핵심 Takeaway
> - **DBA Agent에 가져올 핵심 한 가지: 상태 전이·재시도·승인·감사 기록을 LLM 프롬프트 밖의 결정론적 계층으로 분리한다.** 판단은 에이전트가, 통제는 코드가 — 이게 32 stage 구조의 본질이고 [[dba-agent-work-plan]]에 바로 적용할 지점
> - **분석 에이전트와 검증 에이전트를 분리하고, 검증 통과 전에는 운영 변경을 막는다.** DB 운영 자동화에서는 이 게이트가 선택이 아니라 필수
> - **모든 stage 승인은 통제력을 주지만 작은 작업에는 승인 피로를 만든다.** adaptive scope가 실제로 단계를 줄이는지 측정한 뒤 도입한다 — 무비판 이식 금지 ^[inferred]
> - **사내 규칙은 core를 포크하지 말고 별도 지식·규칙 계층으로 둔다.** 업그레이드 경로를 살려두는 조건 ^[inferred]
> - **모델을 바꾸면 승인 누락·리뷰 생략·단계 축약을 회귀 테스트한다.** 강한 모델 전제로 설계된 흐름이다
> - 실행 규율 쪽은 [[superpowers-agentic-development-methodology]]가 보완재 — AI-DLC가 상위 오케스트레이션, Superpowers가 단계별 실행 규율

# AWS AI-DLC Workflows 2.0 분석 및 학습 노트

## 분석 목적

AWS Labs의 AI-DLC(AI-Driven Development Life Cycle) Workflows 2.0을 향후 에이전트 개발 방식 학습과 사내 자동화 구조 검토에 재사용할 수 있도록 분석했다. 단순 프롬프트 모음이 아니라, 결정론적 상태 관리와 전문 에이전트의 판단을 결합한 **검증 가능하고 자기 교정하는 개발 워크플로**라는 점이 핵심이다.

## V2 핵심 구조

- **5개 phase, 32개 stage**: Initialization → Ideation → Inception → Construction → Operation으로 전체 개발 생명주기를 구성한다.
- **14개 agent roster**: 11개 도메인 전문가, 2개 리뷰 전용 에이전트, 작업에 맞는 단계를 조합하는 adaptive-workflows composer로 역할을 분리한다.
- **9개 adaptive scope**: enterprise부터 workshop까지 요청의 자유 형식 의도를 바탕으로 범위를 자동 감지한다.
- **독립적인 깊이와 테스트 전략**: 산출물 상세도와 테스트 범위를 각각 Minimal·Standard·Comprehensive로 조절할 수 있다.
- **단계별 승인 게이트**: 에이전트가 제안하고 사람이 승인한 뒤 다음 단계로 넘어간다.
- **학습 루프**: 사람의 교정을 지속적인 행동 규칙으로 남겨 같은 실수를 줄인다.
- **82개 이벤트 감사 추적**: 상태 변화와 의사결정 이력을 구조화해 추적 가능성을 높인다.

## 구현 아키텍처

V2는 방법론을 harness-neutral `core/`에 한 번만 정의하고, Claude Code·Kiro·Codex CLI·Cursor·opencode·GitHub Copilot별 얇은 어댑터와 배포본을 생성한다. 상태 머신, 감사 로그, 병렬 에이전트를 조정하는 referee는 각 하네스에서 동일하게 유지되고, 하네스별 차이는 명령·훅·설치 표면에 국한한다.

이 구조가 주는 설계 원칙은 다음과 같다. ^[inferred]

1. 방법론과 실행 환경의 결합을 끊고 단일 원본에서 플랫폼별 배포물을 생성한다.
2. 진행 상태·승인·감사 기록은 결정론적 엔진이 맡고, 분석·설계·리뷰는 전문 에이전트가 맡는다.
3. 자유로운 에이전트 대화보다 stage 계약, 산출물, 승인 조건을 중심으로 흐름을 통제한다.
4. 병렬 실행은 속도 최적화가 아니라 명시적 작업 분해와 referee 조정 아래 둔다.

## 기존 방식과 비교해 배울 점

저장소의 기본 소개는 초기 AI-DLC를 Inception·Construction·Operations의 3단계 적응형 워크플로로 설명한다. V2 구현은 Initialization과 Ideation을 앞에 추가하고, 32개 stage·14개 agent·상태 머신·감사 로그·복구 기능으로 운영 가능성을 구체화했다.

| 관점 | 초기 워크플로 | V2 학습 포인트 |
|---|---|---|
| 흐름 | 3개 상위 phase 중심 | 5개 phase와 32개 stage의 명시적 상태 전이 |
| 역할 | 하나의 코딩 에이전트가 규칙을 수행 | 도메인 전문가·리뷰어·composer 역할 분리 |
| 통제 | 계획과 산출물의 사용자 승인 | 모든 stage의 승인 게이트와 감사 이벤트 |
| 적응 | 복잡도에 따라 단계 선택 | scope·depth·test strategy를 독립 조정 |
| 재현성 | Markdown steering rule 중심 | 결정론적 엔진과 동일한 multi-harness core |
| 개선 | 사용자 피드백 | 교정을 영속 규칙으로 바꾸는 learning loop |

## Codex에서 후속 실습

공식 V2 기준 Codex 실습 전제는 Git 저장소, Bun, Codex CLI 0.145.0 이상이다. `dist/codex/`의 `.codex/`, `.agents/`, `aidlc/`, `AGENTS.md`를 대상 프로젝트에 복사하고 `bun .codex/tools/aidlc-utility.ts doctor`로 설치 상태를 검증한 뒤 `$aidlc`로 호출한다.

- [ ] 릴리스 또는 검증된 커밋을 고정해 실습용 저장소에서 설치한다.
- [ ] `$aidlc --doctor` 결과와 생성되는 프로젝트 파일을 확인한다.
- [ ] 작은 기존 프로젝트에서 scope·depth·test strategy 변화에 따른 stage 계획을 비교한다.
- [ ] 승인 거부, stage 재실행, 세션 재개가 상태와 감사 로그에 어떻게 남는지 확인한다.
- [ ] 동일 과제를 기존 Codex 작업 방식과 AI-DLC 방식으로 수행해 토큰·시간·결함·리뷰 부담을 비교한다.
- [ ] 사람의 교정이 persistent rule로 승격되는 조건과 잘못된 규칙을 되돌리는 절차를 확인한다.

## Superpowers brainstorming 비교 후속 조사

AI-DLC 분석에 [[superpowers-agentic-development-methodology|Superpowers]]의 `brainstorming` 접근법과의 비교를 추가한다. Superpowers 저장소의 전체 방법론과 기본 개발 흐름은 정리했으며, 항목별 상세 비교와 완료 기한은 확정되지 않았다.

- [ ] 문제·요구사항을 구체화하는 질문 방식을 비교한다.
- [ ] 설계 대안을 탐색하고 선택하는 절차를 비교한다.
- [ ] 사용자 승인·검토가 개입하는 지점을 비교한다.
- [ ] 산출물이 다음 구현 단계로 이어지는 방식을 비교한다.
- [ ] [[dba-agent-work-plan|DBA Agent]] 등 실제 업무 흐름에 적용할 때의 장단점을 정리한다.

## 사내 에이전트 적용 검토

[[dba-agent-work-plan|DBA Agent 구조 개편]]에 적용한다면 다음 순서가 현실적이다. ^[inferred]

1. 반복 가능한 DB 점검 작업을 stage와 산출물 계약으로 먼저 모델링한다.
2. 상태 전이·재시도·승인·감사 기록을 LLM 프롬프트 밖의 결정론적 계층으로 분리한다.
3. 분석 에이전트와 결과 검증 전용 에이전트를 분리하고, 검증 통과 전 운영 변경을 막는다.
4. 팀 교정 사항을 바로 영구 규칙으로 만들지 말고 검토·버전·롤백 절차를 둔다.
5. golden case, 정적 검사, 의미 평가, NFR(토큰·실행 시간·모델 간 일관성)을 포함한 회귀 평가를 만든다.

## 도입 시 주의점

- 저장소는 의존하는 환경에서 알려진 정상 버전을 고정하고 생성 결과와 비용을 검토하라고 권고한다.
- 모든 stage 승인 방식은 통제력을 높이지만 작은 작업에는 승인 피로와 산출물 과잉을 만들 수 있으므로 adaptive scope가 실제로 단계를 잘 줄이는지 측정해야 한다. ^[inferred]
- 강한 모델에서 더 안정적으로 동작한다는 저장소 설명이 있으므로, 모델 변경 시 승인 누락·리뷰 생략·단계 축약을 회귀 테스트해야 한다.
- 팀 지식과 방법론 지식이 분리되어 있으므로, 사내 규칙은 core를 직접 포크하기보다 별도 지식·규칙 계층으로 관리하는 편이 업그레이드에 유리하다. ^[inferred]
- 보안·복원력 확장은 방향성 예시이며, 조직 환경에 맞게 수정하고 충분히 시험한 뒤 사용해야 한다.

## Related

- [[worklog-kakaogames-2026|2026년 작업 이력]]
- [[dba-agent-work-plan|DBA Agent 구조 개편 및 주간 분석 작업 계획]]
- [[dev-tooling-standards|개발 도구 운영 기준]]
- [[todo]] — 이 노트의 후속 비교 과제가 등록된 곳

## Sources

- <https://github.com/awslabs/aidlc-workflows>
- <https://github.com/awslabs/aidlc-workflows/tree/v2>
- <https://github.com/awslabs/aidlc-workflows/blob/v2/assets/AI-DLC-Workflows-2.0-Specification.pdf>
