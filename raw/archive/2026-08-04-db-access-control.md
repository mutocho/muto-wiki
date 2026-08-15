---
title: 3-엔진 계정·권한 관리 표준 (Notion 심층 수집)
tags: [dba, security, access-control]
topics: [dba]
summary: >-
  MySQL/PostgreSQL/SQL Server 공통 계정 설계 원칙 — Role/로그인 분리, 배포자 Role,
  모니터링 전용 계정, break-glass, 엔진별 금지 권한.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: DB 운영 쿼리 인덱스 하위 권한 문서들 (2026-07-30)"
---

# 3-엔진 계정·권한 관리 표준

## 공통 원칙

- Role과 로그인 분리. 운영 앱 계정 DDL 금지. 배포자(deployer) Role은 migration 창구에서만 사용.
- 모니터링 계정은 조회 전용: PG `pg_monitor` / MySQL PROCESS + performance_schema SELECT / SQL Server VIEW SERVER STATE (2022+는 VIEW SERVER PERFORMANCE STATE).
- break-glass(비상) 계정 분리 관리.
- 권한 변경 후 실측 검증: MySQL `SHOW GRANTS` / SQL Server `sys.database_permissions`.

## 엔진별

- **PG**: `ALTER DEFAULT PRIVILEGES`(소유자 다르면 FOR ROLE 명시), public 스키마 봉인, extensions 전용 스키마, SECURITY DEFINER는 search_path 고정. 삭제 절차: REASSIGN OWNED → DROP OWNED → DROP USER.
- **MySQL**: SUPER/FILE/SHUTDOWN/WITH GRANT OPTION 금지. DROP은 작업 단위 임시 부여. 인증 해시 추출·재사용 금지(신규 발급 원칙).
- **SQL Server**: 고정 롤(db_owner/db_ddladmin) 대신 사용자 정의 Role + 명시적 GRANT.

## 발견된 위험 (원본 교정 필요)

- 템플릿의 `PASSWORD ''`(빈 문자열)·`change-me` 자리표시자가 그대로 실행될 위험 → 시크릿 저장소 주입 표기로 교체.
- MySQL 스크립트 페이지에 과거 자격증명 노출 이력 존재(정화 완료, 재발급 고지됨) — 노출 시 문서 수정만으로 끝내지 말고 자격증명 폐기·재발급이 원칙.
