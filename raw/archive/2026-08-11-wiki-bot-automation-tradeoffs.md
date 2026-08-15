---
title: >-
  Slack 위키 봇 자동화 — _raw 검색 누락과 ingest/lint 비용 구조
tags: [dba, automation]
summary: >-
  승격 전 _raw 초안은 query에서 누락된다. ingest 비용은 파일 수에, lint 비용은 실행 횟수에 비례한다.
project: muto
base_confidence: 0.75
lifecycle: draft
lifecycle_changed: 2026-08-11
provenance:
  extracted: 0.8
  inferred: 0.2
sources:
  - "muto session (2026-08-11)"
---

## 승격 전 `_raw` 초안은 위키 검색에서 누락된다

`slack-bot/runner.py`의 query 프롬프트는 `second-brain/index.md`로 후보 페이지를 고른 뒤 grep으로 좁히는 순서다. 그런데 `index.md`에는 `_raw` 항목이 전혀 없다. 따라서 적재 직후 `_raw/`에 떨어진 초안은 정식 페이지로 승격되기 전까지 조회 대상에서 빠진다.

해결은 ingest 주기를 줄이는 게 아니라 query 프롬프트에 `_raw/` grep을 명시하는 것이다 — 정보 자체는 승격 전에도 `_raw`에 100% 있고, ingest가 추가하는 것은 정보가 아니라 구조(frontmatter, 위키링크, index 등재)다. 구조는 여러 페이지를 엮는 질문에만 필요하다.^[inferred]

## ingest와 lint는 비용이 붙는 축이 다르다

- **ingest 비용 ∝ `_raw` 파일 수.** 실행 횟수와 무관하다. 하루 10건을 한 번에 처리하든 나눠 처리하든 총량은 같다.
- **lint 비용 ∝ 볼트 전체 크기 × 실행 횟수.** 매 실행이 링크 그래프·frontmatter 전수 스캔이라 실행 횟수가 그대로 고정비 배수가 된다.

따라서 적재가 잦아질수록 lint는 배치를 크게 묶어야 하고, 자주 돌려야 하는 것은 ingest 쪽뿐이다.

## `wiki-lint --consolidate`는 무인 실행 전제가 아니다

`--consolidate`가 자동 수행하는 액션에는 판단이 섞인 것들이 포함된다: `lifecycle: draft → reviewed` 자동 승격(생성 30일 초과 + confidence 0.7 초과), tier 강등, 180일 경과 페이지에 stale 배너 삽입, 모순 콜아웃 삽입. 게다가 대상은 신규 페이지가 아니라 볼트 전체이며, 스킬 자체가 dry-run 후 사용자 확인을 요구한다.

무인 스케줄로 돌리려면 되돌릴 필요조차 없는 액션(깨진 링크 수정, 고아 페이지 크로스링크 추가, 태그 별칭 정규화)만 화이트리스트로 허용하고 나머지는 리포트로 돌려야 한다. 그러지 않으면 시간이 지나 볼트의 lifecycle 값이 사람 판단인지 봇 판단인지 구분되지 않는다.^[inferred]
