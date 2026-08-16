---
title: 3-엔진 권한 감사·부여 쿼리 (MySQL·PostgreSQL·SQL Server)
category: db운영
tags: [dba, security, access-control, mysql, postgresql, sqlserver, snippet]
summary: 권한 감사(읽기 전용)와 권한 부여(변경 — 승인 필요) 쿼리를 엔진별로 대조. 롤 묶음 부여 원칙, 부여 후 실측 검증, 해시 컬럼 제외 규칙 포함. 실행 검증 전이므로 버전·조합 확인 필수.
sources: [표준 시스템 뷰·카탈로그 기반 자체 작성 (2026-08-04), "operational-queries에서 분리 (2026-08-16)"]
status: draft
created: 2026-08-16
updated: 2026-08-16
notion_page_id: null
notion_synced: null
---

> [!tip] 핵심 Takeaway
> - **권한은 묶음 롤에 부여하고 로그인 계정에는 롤만 준다.** 계정에 직접 부여하면 계정이 늘 때마다 누락이 생긴다 — 권한 자동화의 기본 형태
> - **부여 성공 ≠ 의도한 권한.** 변경 후 실측 조회 검증까지가 한 단위다 (PG `has_table_privilege` / MySQL `SHOW GRANTS ... USING` / MSSQL `fn_my_permissions`)
> - **비밀번호 해시 컬럼은 어떤 쿼리에도 넣지 않는다** — `SELECT *` 한 번에 해시가 터미널·로그에 남는다. MySQL `authentication_string`, PG `rolpassword`, MSSQL `password_hash`
> - 자동화가 조용히 실패하는 두 지점: PG `ALTER DEFAULT PRIVILEGES`는 `FOR ROLE <생성자>`가 없으면 신규 테이블에 무효, MySQL은 `SET DEFAULT ROLE`을 빠뜨리면 접속 직후 권한이 0이다
> - **감사(1절)는 읽기 전용, 부여(2절)는 변경 명령이다.** 부여 쪽은 승인 게이트를 반드시 거친다 — 진단 에이전트에 그대로 실지 않는다
> - 아직 실행 검증 전(`draft`)이다. 개발/QA 인스턴스에서 확인한 뒤 자동화에 태운다

# 3-엔진 권한 감사·부여 쿼리

[[db-access-control]]이 **원칙**(롤 설계·금지 권한·break-glass)이라면 이 페이지는 그 원칙을 실행하는 **쿼리**다. 원칙을 바꿀 때는 저쪽을, 명령을 찾을 때는 이쪽을 본다. 진단 쿼리는 [[operational-queries]], 변경 명령 일반의 안전 절차는 [[db-change-safe-patterns]]에 있다.

- **작성 근거는 각 엔진의 표준 시스템 뷰·카탈로그이며, 이 환경의 실제 인스턴스에서 실행 검증하지 않았다.**
- **운영 DB에 처음 붙이기 전 개발·QA 인스턴스에서 먼저 실행**하고, 결과 컬럼과 버전 호환을 확인한 뒤 쓴다. 컬럼명·뷰 위치는 버전마다 바뀐다.
- **2절의 부여 명령은 그대로 복붙해 실행하는 용도가 아니다.** 대상 확인 → 부여 → 실측 검증을 포함한 골격이며, 운영 적용은 승인·점검 절차를 따른다.

## 1. 권한 감사 (읽기 전용)

**공통 원칙** — [[db-access-control]]의 표준과 짝을 이룬다. 권한 변경 후에는 **반드시 실측 조회로 검증**한다(부여 성공 ≠ 의도한 권한).

> **비밀번호 해시 컬럼은 조회하지 않는다.** MySQL `mysql.user.authentication_string`, PG `pg_authid.rolpassword`, MSSQL `sys.sql_logins.password_hash`는 이 페이지의 모든 쿼리에서 제외했다. `SELECT *`로 이 테이블들을 훑으면 해시가 터미널·로그에 남는다.

**PostgreSQL**

```sql
-- 롤 목록·속성 (슈퍼유저·LOGIN 여부 감사)
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb,
       rolcanlogin, rolreplication, rolbypassrls,
       rolconnlimit, rolvaliduntil
FROM pg_roles
WHERE rolname NOT LIKE 'pg\_%'
ORDER BY rolsuper DESC, rolname;

-- 롤 멤버십 (권한 묶음 상속 관계)
SELECT m.rolname AS member, g.rolname AS granted_role, am.admin_option
FROM pg_auth_members am
JOIN pg_roles m ON m.oid = am.member
JOIN pg_roles g ON g.oid = am.roleid
ORDER BY member, granted_role;

-- 테이블 권한
SELECT table_schema, table_name, grantee, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee;

-- 스키마 권한
SELECT n.nspname AS schema_name,
       pg_get_userbyid(a.grantee) AS grantee,
       a.privilege_type, a.is_grantable
FROM pg_namespace n
CROSS JOIN LATERAL aclexplode(n.nspacl) a
WHERE n.nspname NOT LIKE 'pg\_%'
  AND n.nspname <> 'information_schema'
ORDER BY schema_name, grantee;
```

> `nspacl`이 NULL(기본 ACL 그대로)인 스키마는 `CROSS JOIN LATERAL`에서 행이 사라진다. 누락 여부는 `SELECT nspname, nspacl FROM pg_namespace`로 별도 확인한다.

**DEFAULT PRIVILEGES 확인** — `GRANT ON ALL TABLES`는 현재 객체만 적용되므로([[postgresql-operations]]) 이 조회가 실제 운영 여부를 가른다:

```sql
SELECT pg_get_userbyid(d.defaclrole) AS for_owner_role,
       n.nspname AS schema_name,
       CASE d.defaclobjtype WHEN 'r' THEN 'table'    WHEN 'S' THEN 'sequence'
                            WHEN 'f' THEN 'function' WHEN 'T' THEN 'type'
                            WHEN 'n' THEN 'schema'   ELSE d.defaclobjtype::text END AS obj_type,
       d.defaclacl AS default_acl
FROM pg_default_acl d
LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
ORDER BY for_owner_role, schema_name, obj_type;
```

특정 권한 유효성 단건 확인:

```sql
SELECT has_table_privilege('svcsel', 'app.orders', 'SELECT')  AS can_select,
       has_schema_privilege('svcsel', 'app', 'USAGE')          AS has_usage,
       has_table_privilege('svcsel', 'app.orders', 'UPDATE')   AS can_update;  -- 조회 계정은 false여야 정상
```

롤별 `search_path` 등록값 확인:

```sql
SELECT r.rolname, d.datname, s.setconfig
FROM pg_db_role_setting s
LEFT JOIN pg_roles    r ON r.oid = s.setrole
LEFT JOIN pg_database d ON d.oid = s.setdatabase;
```

> `setrole = 0`이면 데이터베이스 전체 설정(`ALTER DATABASE ... SET`), `setdatabase = 0`이면 롤 전역 설정이다. 두 값이 모두 있으면 `ALTER ROLE ... IN DATABASE ... SET`.

**MySQL**

```sql
-- 계정 목록·상태 (해시 컬럼 제외)
SELECT user, host, account_locked, password_expired,
       password_lifetime, password_last_changed, plugin
FROM mysql.user
ORDER BY user, host;

-- 특정 계정의 실제 권한
SHOW GRANTS FOR 'svcapp'@'10.%';

-- 권한 전수 조회
SELECT * FROM information_schema.user_privileges;    -- 글로벌
SELECT * FROM information_schema.schema_privileges;  -- 스키마
SELECT * FROM information_schema.table_privileges;   -- 테이블
```

8.0 롤 매핑:

```sql
SELECT from_user AS role_name, from_host, to_user AS member, to_host, with_admin_option
FROM mysql.role_edges
ORDER BY role_name, member;

SELECT * FROM mysql.default_roles;
```

> 버전 주의: **롤은 8.0+**. 5.7은 롤 개념이 없어 권한을 계정에 직접 부여해야 하며, `mysql.role_edges`·`mysql.default_roles`가 존재하지 않는다.
> `SHOW GRANTS`는 롤을 통해 상속된 권한을 기본으로 펼치지 않는다. 유효 권한은 `SHOW GRANTS FOR 'svcapp'@'10.%' USING 'app_rw';`로 롤을 지정해 확인한다.

**SQL Server**

```sql
-- DB 수준 권한
SELECT dp.name AS principal_name, dp.type_desc, dp.authentication_type_desc,
       perm.class_desc, perm.permission_name, perm.state_desc,
       OBJECT_SCHEMA_NAME(perm.major_id) AS schema_name,
       OBJECT_NAME(perm.major_id)        AS object_name
FROM sys.database_permissions perm
JOIN sys.database_principals dp ON dp.principal_id = perm.grantee_principal_id
WHERE dp.name NOT LIKE '##%'
ORDER BY principal_name, permission_name;

-- DB 롤 멤버십
SELECT r.name AS role_name, m.name AS member_name, m.type_desc
FROM sys.database_role_members drm
JOIN sys.database_principals r ON r.principal_id = drm.role_principal_id
JOIN sys.database_principals m ON m.principal_id = drm.member_principal_id
ORDER BY role_name, member_name;

-- 서버 롤 멤버십 (sysadmin 감사)
SELECT sp.name AS login_name, sp.type_desc, sp.is_disabled,
       r.name AS server_role
FROM sys.server_principals sp
LEFT JOIN sys.server_role_members srm ON srm.member_principal_id = sp.principal_id
LEFT JOIN sys.server_principals    r  ON r.principal_id = srm.role_principal_id
WHERE sp.name NOT LIKE '##%'
ORDER BY server_role, login_name;
```

유효 권한 확인 (본인 / 특정 사용자로 가정):

```sql
SELECT * FROM fn_my_permissions('app.orders', 'OBJECT');

EXECUTE AS USER = 'svcsel';
  SELECT * FROM fn_my_permissions('app.orders', 'OBJECT');
REVERT;
```

고아 사용자 (대응 로그인이 없는 DB 사용자 — 복원 후 흔히 발생):

```sql
SELECT dp.name, dp.type_desc, dp.sid
FROM sys.database_principals dp
LEFT JOIN sys.server_principals sp ON sp.sid = dp.sid
WHERE dp.type IN ('S','U','G')
  AND dp.principal_id > 4
  AND sp.sid IS NULL;
```

## 2. 권한 부여 (변경 — 승인 필요)

**설계 원칙** ([[db-access-control]], [[postgresql-operations]])

- 롤 분리: 소유 `svc` / 서비스 `svcapp` / 배치 `svcbat` / 조회 `svcsel` / 모니터링 `svcmon`
- **권한은 묶음 롤에 부여하고, 로그인 계정에는 롤만 준다.** 계정에 직접 부여하면 계정이 늘 때마다 누락이 생긴다
- 금지: 앱 계정에 슈퍼유저 / `sysadmin` / `db_owner` — 시스템 롤로 대체
- 비밀번호는 코드·문서에 남기지 않고 시크릿 저장소에서 주입

**PostgreSQL**

```sql
-- 1) 권한 묶음 롤 (로그인 불가)
CREATE ROLE app_rw NOLOGIN;
CREATE ROLE app_ro NOLOGIN;

-- 2) 스키마 사용 권한
GRANT USAGE ON SCHEMA app TO app_rw, app_ro;

-- 3) 현재 존재하는 객체
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES    IN SCHEMA app TO app_rw;
GRANT USAGE, SELECT                  ON ALL SEQUENCES IN SCHEMA app TO app_rw;
GRANT SELECT                         ON ALL TABLES    IN SCHEMA app TO app_ro;

-- 4) 앞으로 생성될 객체 — 3)만으로는 신규 테이블에 권한이 없다
ALTER DEFAULT PRIVILEGES FOR ROLE svc IN SCHEMA app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE svc IN SCHEMA app
  GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE svc IN SCHEMA app
  GRANT SELECT ON TABLES TO app_ro;

-- 5) 로그인 롤에 묶음 부여
GRANT app_rw TO svcapp, svcbat;
GRANT app_ro TO svcsel;

-- 6) 검증 (1절)
SELECT has_table_privilege('svcsel', 'app.orders', 'UPDATE');  -- false 기대
```

> **`ALTER DEFAULT PRIVILEGES`는 `FOR ROLE <소유자>`가 핵심이다.** 기본 권한은 *객체를 생성한 롤* 기준으로 적용되므로, 마이그레이션 도구가 `svc`가 아닌 다른 롤로 테이블을 만들면 4)가 적용되지 않는다. 생성 주체를 `SET ROLE svc;`로 고정한다.

단일 스키마 구성이라 스키마 명시 없이 쿼리하려면 `search_path`를 등록한다:

```sql
-- 데이터베이스 전체 (모든 롤 + 향후 추가될 롤까지 한 번에)
ALTER DATABASE <db> SET search_path = app, extensions, pg_temp;

-- 롤별로 달라야 할 때만
ALTER ROLE svcapp IN DATABASE <db> SET search_path = app, extensions, pg_temp;
```

> `pg_temp`를 명시하지 않으면 **암묵적으로 맨 앞**에서 검색되어, 임시 객체로 `app.*`를 가로챌 여지가 생긴다. 끝에 명시해 우선순위를 낮춘다. `pg_catalog`는 항상 맨 앞이므로 신경 쓰지 않아도 된다.
> 로그인 시점에 적용되므로 **기존 세션에는 반영되지 않는다.** 재접속 후 `SHOW search_path;`로 확인. role-level 설정은 *인증한 롤* 기준이라 `SET ROLE`로 전환한 롤의 값으로 바뀌지 않는다.

모니터링 계정 (슈퍼유저 대신 시스템 롤):

```sql
CREATE ROLE svcmon LOGIN;
GRANT pg_monitor TO svcmon;             -- 10+
GRANT pg_read_all_data TO svcmon;       -- 14+ (조회 전용 감사에 필요할 때만)
```

계정 삭제 — 순서를 지켜야 소유 객체가 고아가 되지 않는다:

```sql
-- 1) 남은 권한 확인 (1절의 role_table_grants)
-- 2) 소유 객체 이관
REASSIGN OWNED BY old_role TO svc;
-- 3) 남은 권한 부여 내역 제거
DROP OWNED BY old_role;
-- 4) 삭제
DROP ROLE old_role;
```

**MySQL**

```sql
-- 1) 롤 생성·권한 부여 (8.0+)
CREATE ROLE 'app_rw', 'app_ro';
GRANT SELECT, INSERT, UPDATE, DELETE ON app.* TO 'app_rw';
GRANT SELECT                         ON app.* TO 'app_ro';

-- 2) 계정에 롤 부여 + 기본 롤 활성화
GRANT 'app_rw' TO 'svcapp'@'10.%';
GRANT 'app_ro' TO 'svcsel'@'10.%';
SET DEFAULT ROLE ALL TO 'svcapp'@'10.%', 'svcsel'@'10.%';

-- 3) 검증
SHOW GRANTS FOR 'svcsel'@'10.%' USING 'app_ro';
```

> **`SET DEFAULT ROLE`을 빼먹으면 접속 직후 권한이 0이다.** 롤을 부여해도 세션에서 활성화되지 않으면 적용되지 않는다(또는 앱이 매 접속마다 `SET ROLE`을 호출해야 한다).
> 5.7은 롤이 없으므로 계정에 직접 부여한다.

모니터링 계정 (조회 전용 — [[db-access-control]]):

```sql
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'svcmon'@'10.%';
GRANT SELECT ON performance_schema.* TO 'svcmon'@'10.%';
```

**SQL Server**

```sql
-- 1) DB 롤 + 스키마 단위 권한
CREATE ROLE app_rw;
CREATE ROLE app_ro;
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::app TO app_rw;
GRANT SELECT                         ON SCHEMA::app TO app_ro;

-- 2) 멤버 추가
ALTER ROLE app_rw ADD MEMBER svcapp;
ALTER ROLE app_ro ADD MEMBER svcsel;

-- 3) 검증 (1절의 database_role_members / fn_my_permissions)
```

> **스키마 단위(`ON SCHEMA::app`) 부여가 테이블 단위보다 안전하다** — 신규 테이블에 권한이 자동 적용되어 PG의 `ALTER DEFAULT PRIVILEGES`와 같은 역할을 한다.

모니터링 계정 — 버전에 따라 권한 이름이 다르다:

```sql
GRANT VIEW SERVER STATE TO svcmon;              -- 2019 이하
GRANT VIEW SERVER PERFORMANCE STATE TO svcmon;  -- 2022+ (세분화됨)
GRANT VIEW ANY DEFINITION TO svcmon;            -- 2022+, 스키마 조회가 필요할 때
```

sa 비활성화 + 명명 관리자 계정 ([[sqlserver-operations]]):

```sql
ALTER LOGIN sa DISABLE;
-- 관리자 계정은 CHECK_POLICY / CHECK_EXPIRATION ON으로 생성, 비밀번호는 시크릿 저장소 주입
```

## 후속 / 미수록

- **실제 사용 중인 쿼리로 대체·검증 필요.** 위는 표준 뷰 기반 일반형이므로, 현장에서 쓰는 버전이 있으면 그것으로 교체하고 `status`를 올린다.
- 미수록: 행 수준 보안(RLS)·컬럼 마스킹 설정, 권한 변경 이력 감사(감사 로그 연동).
- 2절의 부여 명령은 **개발/QA에서 실행 확인 후 운영 절차서로 승격**할 대상이다.
- 권한 문서 자체를 감사할 때 찾아야 할 위험 패턴(자리표시자 비밀번호, 자격증명 노출)은 [[db-security-review-patterns]].

## Related

- [[db-access-control|3-엔진 계정·권한 관리 표준]] — 이 쿼리들이 구현하는 설계 원칙. 금지 권한 목록이 부여 자동화의 하드 필터다
- [[operational-queries|운영 진단 쿼리 모음]] — 같은 3사 대조 형식의 읽기 전용 진단 쿼리
- [[db-change-safe-patterns|DDL·DML 안전 실행 패턴]] — 같은 "승인 게이트 필수" 등급의 변경 명령
- [[db-security-review-patterns|DB 문서 보안 검토 위험 패턴]] — 권한 문서를 감사할 때의 체크리스트
- [[postgresql-operations|PostgreSQL 운영 지식]] — Role 설계와 계정 삭제 절차 상세
- [[mysql-operations|MySQL/Aurora MySQL 운영 지식]] · [[sqlserver-operations|SQL Server 운영 지식]] — 엔진별 권한 운영 맥락
