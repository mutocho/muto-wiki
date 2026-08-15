---
title: "obsidian-wiki graph-query가 folded summary를 파싱하지 못해 index_only를 오탐"
category: skills
tags: [tooling, knowledge-management, gotcha]
summary: "graph-query는 frontmatter의 `summary: >-` 폴디드 스칼라를 리터럴 '>-'로 읽어, 요약이 비어 있는데도 index_only:true를 반환한다."
tier: supporting
related: []
extends: null
contradicts: null
superseded_by: null
capture_source: claude-session
project: second-brain
base_confidence: 0.75
lifecycle: draft
lifecycle_changed: 2026-08-04
provenance:
  extracted: 0.8
  inferred: 0.2
sources:
  - "second-brain session (2026-08-04)"
---

# obsidian-wiki graph-query의 folded summary 파싱 문제

## graph-query가 `summary: >-`를 리터럴로 읽는다

**Behavior:** `obsidian-wiki graph-query <vault> "<질문>" --pretty` 실행 시 모든 후보 페이지의 `summary` 필드가 문자열 `">-"` 로 반환되고, 그 상태에서 `index_only: true` 와 빈 `should_read: []` 가 함께 나온다. wiki-query 스킬의 결정 트리는 `index_only: true`면 `candidates[0].summary`만으로 답하고 페이지 읽기를 건너뛰라고 지시하므로, 그대로 따르면 **내용이 전혀 없는 답을 하게 된다.**

**Explanation:** 볼트의 페이지들은 summary를 여러 줄로 쓰기 위해 YAML 폴디드 스칼라(`summary: >-` 다음 줄에 본문)를 사용한다. graph-query의 frontmatter 파서가 `key: value` 한 줄 형태만 처리해서, 값으로 구분자 `>-` 자체를 저장한다. 요약 길이가 2자에 불과하므로 "요약만으로 충분하다"는 index_only 판정 로직이 잘못 발동한다.^[inferred]

**Workaround / Pattern:** graph-query 결과의 `summary`가 `">-"`(또는 `"|"`, `">"`)이면 `index_only`를 무시하고 Step 3(섹션 grep)으로 바로 내려간다. `candidates[].page` 경로는 정상이므로 랭킹 용도로는 그대로 쓸 수 있다.

**Confirmed by:** 4개 후보 페이지 전부 `">-"` 반환, 실제 파일의 frontmatter는 정상적인 2줄 폴디드 summary 보유 (`dba/sqlserver-operations.md` 등).

**Notes:** 근본 해결은 두 갈래 — (1) 페이지 frontmatter를 한 줄 `summary: "..."` 로 통일, (2) graph-query 파서 수정. 볼트 쪽 통일이 더 싸지만 요약 200자 제한과 충돌할 수 있다.^[ambiguous] 이 볼트의 페이지 대부분이 Notion 심층 수집분이라 동일 패턴을 공유하므로 영향 범위는 전체다.
