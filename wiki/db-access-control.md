---
title: 3-엔진 계정·권한 관리 표준
category: db운영
tags: [dba, security, access-control, mysql, postgresql, sqlserver]
summary: MySQL/PostgreSQL/SQL Server 공통 계정 설계 원칙 — Role/로그인 분리, 배포자 Role, 모니터링 전용 계정, break-glass, 엔진별 금지 권한.
sources: ["Notion: DB 운영 쿼리 인덱스 하위 권한 문서들 (2026-07-30)", "사용자 제공 PostgreSQL 운영 메모 (2026-08-15)", "사용자 제공 PostgreSQL 오브젝트 메모 (2026-08-16)", "PostgreSQL 공식 문서: Password Authentication·Schemas·System Information Functions (2026-08-16 대조)"]
status: reviewed
created: 2026-08-04
updated: 2026-08-16
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **금지 권한 목록이 권한 부여 자동화의 하드 필터다** — MySQL SUPER/FILE/SHUTDOWN/WITH GRANT OPTION, SQL Server 고정 롤(db_owner/db_ddladmin). 요청이 와도 통과시키지 않는다
> - **권한 변경은 부여로 끝나지 않고 실측 검증까지가 한 단위다** (`SHOW GRANTS`, `sys.database_permissions`). 부여·검증 쿼리는 [[db-permission-queries]]
> - **자격증명이 노출되면 문서 수정이 아니라 폐기·재발급이 조치다.** 과거 MySQL 스크립트 페이지에서 실제로 발생한 사고 — 이 원칙을 [[db-security-review-patterns]] 점검에 포함
> - PG 계정 삭제는 순서가 있다: REASSIGN OWNED → DROP OWNED → DROP USER. 건너뛰면 실패한다

# 3-엔진 계정·권한 관리 표준

## 공통 원칙

- Role과 로그인 분리. 운영 앱 계정 DDL 금지. 배포자(deployer) Role은 migration 창구에서만 사용.
- 모니터링 계정은 조회 전용: PG `pg_monitor` / MySQL PROCESS + performance_schema SELECT / SQL Server VIEW SERVER STATE (2022+는 VIEW SERVER PERFORMANCE STATE).
- break-glass(비상) 계정 분리 관리.
- 권한 변경 후 실측 검증: MySQL `SHOW GRANTS` / SQL Server `sys.database_permissions`.

## 엔진별

- **PG**: `ALTER DEFAULT PRIVILEGES`(객체 생성 Role을 `FOR ROLE`로 명시), public 스키마 CREATE 회수, extensions 전용 스키마, SECURITY DEFINER는 고정 `search_path`. 원격 인증은 최소 CIDR의 `hostssl` + SCRAM을 기본으로 하며 MD5·`trust`를 호환성 우회로 허용하지 않는다. 삭제 절차: REASSIGN OWNED → DROP OWNED → DROP USER. 세부 오픈 게이트는 [[postgresql-operations]].
- PG DDL 배포는 로그인 주체인 `session_user`와 권한 검사·소유권 주체인 `current_user`를 구분한다. [[postgresql-object-operations]]의 `SET ROLE <owner>` 패턴과 생성 후 owner 검증을 권한 자동화에 포함한다.
- **MySQL**: SUPER/FILE/SHUTDOWN/WITH GRANT OPTION 금지. DROP은 작업 단위 임시 부여. 인증 해시 추출·재사용 금지(신규 발급 원칙).
- **SQL Server**: 고정 롤(db_owner/db_ddladmin) 대신 사용자 정의 Role + 명시적 GRANT.

## 발견된 위험 (원본 교정 필요)

- 템플릿의 `PASSWORD ''`(빈 문자열)·`change-me` 자리표시자가 그대로 실행될 위험 → 시크릿 저장소 주입 표기로 교체.
- MySQL 스크립트 페이지에 과거 자격증명 노출 이력 존재(정화 완료, 재발급 고지됨) — 노출 시 문서 수정만으로 끝내지 말고 자격증명 폐기·재발급이 원칙.

## Related

- [[db-security-review-patterns]] — 권한 문서를 감사할 때 찾아야 할 위험 패턴 체크리스트
- [[db-permission-queries]] — 이 표준을 실행하는 감사·부여 쿼리. 원칙을 바꿀 때는 이 페이지를, 명령을 찾을 때는 저쪽을 본다
- [[db-change-safe-patterns]] — 권한 외 변경 명령(DDL·DML)의 같은 등급 안전 절차
- [[operational-queries]] — 읽기 전용 진단 쿼리
- [[postgresql-operations]] — PG 롤 설계와 계정 삭제 절차 상세
- [[mysql-operations]] · [[sqlserver-operations]] — 엔진별 권한 운영 맥락
- [[sqlserver-backup-procedure]] — `xp_cmdshell`을 켜지 않고 백업을 수행하도록 고친 사례. 운영 프로시저에 어디까지 권한을 요구할지의 판단 기준
- [[mysql-dump-load]] — 덤프·로드 전용 계정 권한 목록. `WITH GRANT OPTION` 보유 계정이 이관 후 남는 것이 여기 break-glass 원칙의 대표 위반 경로
- [[dev-tooling-standards]] — 자격증명을 env로 주입하는 개발 쪽 원칙
