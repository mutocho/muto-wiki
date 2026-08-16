---
title: Obsidian 위키 도구 동작 함정
category: 참고자료
tags: [tooling, knowledge-management, gotcha, obsidian]
summary: 폴디드 YAML summary를 리터럴 '>-'로 읽는 파서 함정, wikilink 경로 접두어 함정, obsidian-git askpass 실행 권한 반복 diff 함정.
sources: [작업 세션 기록 (2026-08-04), 작업 세션 기록 (2026-08-06)]
status: reviewed
created: 2026-08-04
updated: 2026-08-15
notion_page_id: "3befb969-b8be-8113-a15f-da1d47c3b77d"
notion_synced: "2026-08-16T20:20:14+09:00"
---

> [!tip] 핵심 Takeaway
> - **`summary:`는 폴디드 스칼라(`>-`)로 쓰지 않는다.** 한 줄 문자열로 쓴다. 파서가 구분자를 값으로 읽어 요약 길이가 2자가 되고, "요약만으로 답 가능" 판정이 잘못 발동해 **내용 없는 답변**이 만들어졌다. 이 위키의 frontmatter 규칙이 한 줄 `summary`인 직접적 이유
> - **도구가 "요약만으로 충분"이라고 판정해도 그대로 믿지 않는다.** 요약이 비정상적으로 짧으면 무조건 본문 grep으로 내려간다
> - **obsidian-git은 로드될 때마다 askpass 스크립트에 `chmod +x`를 건다.** 실행 비트를 한 번 커밋하면 장비 간 반복 dirty 상태가 사라진다
> - 자동 점검 도구를 만들 때 **산문 속 예시 링크는 오탐이다** — 백틱으로 감싸 실제 링크와 구분한다

# Obsidian 위키 도구 동작 함정

## Findings

- `obsidian-wiki graph-query <vault> "<질문>"`은 후보 페이지의 `summary`를 문자열 `">-"`로 반환한다. 이 볼트의 페이지들이 YAML 폴디드 스칼라(`summary: >-` + 다음 줄 본문)로 요약을 쓰는데, graph-query의 frontmatter 파서가 `key: value` 한 줄 형태만 처리해 구분자 자체를 값으로 저장하기 때문이다.^[inferred]
- 그 결과 요약 길이가 2자가 되어 "요약만으로 답할 수 있다"는 판정이 잘못 발동하고, `index_only: true` + 빈 `should_read: []`가 함께 나온다. `wiki-query` 스킬의 결정 트리는 `index_only: true`면 `candidates[0].summary`만으로 답하라고 지시하므로, 그대로 따르면 **내용 없는 답**이 만들어진다.
- 대응: `summary`가 `">-"`·`">"`·`"|"`이면 `index_only`를 무시하고 섹션 grep 단계로 바로 내려간다. `candidates[].page` 경로와 `score` 랭킹은 정상이므로 "어느 페이지를 열지" 판단에는 그대로 쓸 수 있다.
- 근본 해결은 두 갈래 — (1) 페이지 frontmatter를 한 줄 `summary: "..."`로 통일, (2) graph-query 파서 수정. 볼트 쪽 통일이 싸지만 요약 200자 제한과 줄바꿈 가독성이 걸린다.^[ambiguous] 이 볼트 페이지 대부분이 Notion 심층 수집분이라 동일 패턴을 공유하므로 영향 범위는 전체다.
- 확인 근거: 후보로 뜬 4개 페이지 전부 `">-"` 반환, 실제 파일에는 정상적인 2줄 폴디드 summary 존재.

## Wikilink 경로 접두어 함정

- 경로 접두어 없는 wikilink(예: `[[dev-tooling-standards]]`)는 Obsidian 앱에서는 최단 고유 이름으로 정상 해석되지만, 링크 대상을 볼트 루트 상대 경로 리터럴로 검사하는 도구(파일 존재 검사 등)는 깨진 링크로 판정한다.
- 과거 볼트(`second-brain/`)는 폴더 계층을 썼기 때문에 관례가 **항상 폴더 접두어 포함**(`[[dba/dev-tooling-standards]]`)이었다. 2026-08-04 린트에서 접두어 누락 2건을 발견해 수정한 이력이 있다.
- **2026-08-15 이후 이 위키에서는 이 함정 자체가 사라졌다.** `wiki/`를 하위 폴더 없이 플랫하게 유지하면 경로 접두어가 존재할 수 없어 두 해석이 항상 일치한다. 폴더 계층을 도입하지 않는 실용적 근거 중 하나. ^[inferred]
- 반대 방향 오탐도 있다: 산문 속 예시용 링크(`[[wikilink]]`, `[[링크]]` 같은 규칙 설명)는 실제 페이지가 아니므로 점검 결과에서 제외해야 한다. 백틱으로 감싸면 Obsidian도 링크로 렌더링하지 않아 양쪽이 해결된다.^[inferred]

## obsidian-git askpass 실행 권한 함정

- obsidian-git 플러그인은 로드될 때마다 `obsidian_askpass.sh`(git 인증을 Obsidian UI로 받는 GIT_ASKPASS 헬퍼)에 `chmod +x`를 적용한다. 실행 비트가 커밋돼 있지 않으면 Obsidian을 열 때마다 mode 변경(100644→100755) diff가 다시 생긴다.
- 대응: 실행 비트를 한 번 커밋하면(내용 변경 없음, mode만) 장비 간 반복 dirty 상태가 사라진다. 2026-08-06 적용.

## Related

- [[wiki-bot-automation-tradeoffs|Slack 위키 봇 자동화 운영 기준]]
- [[claude-code-permission-guardrails|Claude Code 권한 가드레일 동작]]
- [[index|Wiki Index]]
- [[vault-governance-decisions]] — 이 함정들이 반영된 구조 결정
- [[dev-tooling-standards]] — 저장소 셋업·CI 기준. 여기 함정 대부분이 그 기준을 볼트에 적용할 때 드러난 것들이다
