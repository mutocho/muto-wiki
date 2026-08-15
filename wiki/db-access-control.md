---
title: 3-엔진 계정·권한 관리 표준
category: db운영
tags: [dba, security, access-control, mysql, postgresql, sqlserver]
summary: MySQL/PostgreSQL/SQL Server 공통 계정 설계 원칙 — Role/로그인 분리, 배포자 Role, 모니터링 전용 계정, break-glass, 엔진별 금지 권한.
sources: ["Notion: DB 운영 쿼리 인덱스 하위 권한 문서들 (2026-07-30)"]
status: draft
created: 2026-08-04
updated: 2026-08-04
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **금지 권한 목록이 권한 부여 자동화의 하드 필터다** — MySQL SUPER/FILE/SHUTDOWN/WITH GRANT OPTION, SQL Server 고정 롤(db_owner/db_ddladmin). 요청이 와도 통과시키지 않는다
> - **권한 변경은 부여로 끝나지 않고 실측 검증까지가 한 단위다** (`SHOW GRANTS`, `sys.database_permissions`). 검증 쿼리는 [[operational-queries]]
> - **자격증명이 노출되면 문서 수정이 아니라 폐기·재발급이 조치다.** 과거 MySQL 스크립트 페이지에서 실제로 발생한 사고 — 이 원칙을 [[db-security-review-patterns]] 점검에 포함
> - PG 계정 삭제는 순서가 있다: REASSIGN OWNED → DROP OWNED → DROP USER. 건너뛰면 실패한다

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

## Related

- [[db-security-review-patterns]] — 권한 문서를 감사할 때 찾아야 할 위험 패턴 체크리스트
- [[operational-queries]] — 권한 감사(12)·권한 부여(13)의 실제 쿼리
- [[postgresql-operations]] — PG 롤 설계와 계정 삭제 절차 상세
- [[mysql-operations]] · [[sqlserver-operations]] — 엔진별 권한 운영 맥락
- [[dev-tooling-standards]] — 자격증명을 env로 주입하는 개발 쪽 원칙
