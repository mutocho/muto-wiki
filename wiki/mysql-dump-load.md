---
title: MySQL 논리 백업·적재 — mysqldump / MySQL Shell
category: db운영
tags: [mysql, aurora, rds, backup, migration, mysqlsh, mysqldump]
summary: 논리 덤프·로드 실무 레퍼런스. 도구 분기 기준, mysqldump·MySQL Shell 옵션, 관리형 DB(RDS/Aurora) 고정 옵션 세트, S3 직접 덤프, binlog 증분, 필요 권한, 사고 다발 지점과 에러 대응.
sources:
  - "사내 MySQL Dump & Load 가이드 메모 (2026-08-15 적재)"
  - "MySQL Shell 9.7 Utilities 문서 — https://dev.mysql.com/doc/mysql-shell/9.7/en/mysql-shell-utilities.html"
  - "mysqldump 8.4 매뉴얼 — https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html"
status: draft
created: 2026-08-15
updated: 2026-08-15
notion_page_id: "3bdfb969-b8be-8194-ab94-d13e8a394022"
notion_synced: "2026-08-15T22:30:00+0900"
---

> [!tip] 핵심 Takeaway
> - **관리형 DB(RDS/Aurora) 대상이면 옵션 5종은 환경 무관 고정값이다** — mysqldump `--set-gtid-purged=OFF` `--no-tablespaces`, Shell `compatibility:["strip_definers","strip_restricted_grants"]` `users:false`, 타깃 `local_infile=1`. 이관 자동화에 그대로 박고, 빠지면 실행 전에 막는다
> - **`--databases`를 빼면 덤프에 `CREATE DATABASE`/`USE`가 없어 접속한 DB에 그대로 쏟아진다.** 사고 1순위. 로드 스크립트는 대상 호스트와 스키마를 실행 직전에 다시 확인하는 단계를 필수로 둔다
> - **이관·대용량은 도구 선택 여지가 없다 — MySQL Shell이다.** mysqldump는 실패 시 처음부터이고, Shell만 재시작(`progressFile`)·멀티스레드·S3를 가진다. 크기가 아니라 **재시작 필요 여부**가 진짜 분기점^[inferred]
> - **`consistent: false`는 정합성 포기 선언이다.** 락 권한이 없다는 이유로 자동화 기본값에 넣지 않는다 — 넣으려면 백업이 아니라 "참고용 사본"으로 등급을 낮춰 기록한다

# MySQL 논리 백업·적재

물리 백업(스냅샷, XtraBackup)이 가능하면 대용량에서는 언제나 그쪽이 빠르다.
이 페이지는 **스키마 단위 이관, 부분 복구, 버전·이기종 간 이관**을 전제로 한다.
규모별 도구 분기의 상위 판단은 [[mysql-operations]]의 백업 표준에 있다.

## 1. 도구 분기

| 항목 | `mysqldump` | MySQL Shell (`mysqlsh`) |
|---|---|---|
| 병렬 처리 | 단일 스레드 | 멀티 스레드 (dump/load 양쪽) |
| 출력 형식 | 단일 `.sql` 텍스트 | 청크 분할 + 메타데이터 디렉터리 |
| 재시작 | **불가 — 처음부터** | 가능 (`progressFile` 이어받기) |
| 압축 | 외부 파이프(`gzip`/`pigz`) | 내장 (`zstd`/`gzip`) |
| 클라우드 스토리지 | 미지원 | S3 / OCI / Azure Blob 직접 |
| 부분 복구 | 낮음 (텍스트 grep) | 높음 (테이블별 파일 분리) |
| 호환성 변환 | 없음 | `compatibility` 옵션 |
| 설치 | 기본 포함 | 별도 설치 |
| 권장 규모 | **수 GB 이하** ^[ambiguous] | 수십 GB 이상, 이관 전반 |

- 소규모 스키마 백업, 기존 스크립트 호환 → `mysqldump`
- 이관·대용량·재시작 필요·S3 연동 → **MySQL Shell**
- `mysqlpump`는 deprecated이며 **8.4에서 제거됐다. 신규 채택 금지**

> **mysqldump 상한에 두 기준이 있다** ^[ambiguous] — 기존 사내 판단은 **수 GB 이하**([[mysql-operations]] 백업 표준),
> 이 페이지의 원본 메모는 **수십 GB까지**로 적었다. 30 GB대에서 답이 갈린다.
> **보수적인 쪽(수 GB 이하)을 운영 기본값으로 둔다** — Shell을 불필요하게 고르면 설치 수고로 끝나지만,
> mysqldump로 갔다가 실패하면 재시작이 없어 처음부터다. 비대칭이 명확한 선택이다.^[inferred]
> 실측 기준을 잡기 전까지 이 표의 값은 확정이 아니다 → Open Questions

## 2. mysqldump

### 2.1 기본형

```bash
# 특정 스키마
mysqldump -h ${HOST} -u ${USER} -p \
  --single-transaction \
  --set-gtid-purged=OFF \
  --no-tablespaces \
  --routines --triggers --events \
  --databases mydb > mydb.sql

# 특정 테이블만
mysqldump ... mydb tbl_a tbl_b > tables.sql

# DDL만 / 데이터만
mysqldump ... --no-data      --databases mydb > schema_only.sql
mysqldump ... --no-create-info --databases mydb > data_only.sql
```

> [[mysql-operations]]의 백업 표준은 여기에 `--quick`·`--hex-blob`을 더한 형태를 기본으로 둔다.
> 대용량 테이블에서 클라이언트 메모리 적재를 막는 `--quick`은 표준 조합에 유지한다.

### 2.2 옵션

| 옵션 | 설명 |
|---|---|
| `--single-transaction` | InnoDB 일관성 스냅샷. 테이블 락 없이 덤프 — **필수** |
| `--set-gtid-purged=OFF` | `SET @@GLOBAL.gtid_purged` 구문 제거. RDS/Aurora 복구 시 필수 |
| `--no-tablespaces` | 8.0에서 `PROCESS` 권한 없을 때의 에러 회피 |
| `--routines` | 프로시저·함수 포함 — **기본 미포함** |
| `--events` | 이벤트 스케줄러 포함 — **기본 미포함**, `EVENT` 권한 필요 |
| `--triggers` | 트리거 포함 (기본 활성) |
| `--hex-blob` | 바이너리 컬럼 hex 인코딩. 깨짐 방지 |
| `--default-character-set=utf8mb4` | 인코딩 명시 |
| `--source-data=2` | binlog 좌표를 주석으로 기록 (8.0.26+, 구 `--master-data`). `RELOAD` 권한 필요 |
| `--where=` / `--ignore-table=db.tbl` | 조건부 덤프 / 테이블 제외(반복 지정) |
| `--column-statistics=0` | 8.0 클라이언트로 5.7 서버를 덤프할 때 필요 |
| `--compress` | 네트워크 구간 압축 |

압축 저장은 파이프로 처리하되 **병렬 압축이 체감차가 크다**.

```bash
mysqldump ... --databases mydb | pigz -p 8 > mydb_$(date +%Y%m%d).sql.gz
```

### 2.3 로드

```bash
mysql -h ${HOST} -u ${USER} -p < mydb.sql
zcat mydb.sql.gz | mysql -h ${HOST} -u ${USER} -p
pv mydb.sql | mysql -h ${HOST} -u ${USER} -p     # 진행률
```

세션 변수로 제약 검사를 끄면 적재가 빨라진다.

```bash
{ echo "SET SESSION foreign_key_checks=0; SET SESSION unique_checks=0;"; \
  zcat mydb.sql.gz; } | mysql -h ${HOST} -u ${USER} -p
```

`SET SESSION sql_log_bin = 0`은 **RDS/Aurora에서 권한이 없어 쓸 수 없다.** 온프레미스에서만 고려한다.
끈 검사는 로드 후 되돌리고, `foreign_key_checks=0` 구간에 들어온 위반 행은 자동으로 드러나지 않으므로
로드 후 FK 유효성을 별도 확인한다.^[inferred]

### 2.4 사고 다발 지점

> [!warning]
> - `--add-drop-database` / `--add-drop-table`은 **기존 객체를 삭제**한다. 운영 복구 시 대상 호스트 재확인 필수
> - **`--databases`를 빼면** 덤프에 `CREATE DATABASE`/`USE`가 없어 **접속한 DB에 그대로 적재된다.** 가장 잦은 사고
> - `mysqlpump`는 8.4에서 제거 — 기존 스크립트가 있으면 교체 대상

이 둘은 [[db-security-review-patterns]]가 말하는 "일상 절차에 파괴적 단계가 섞여 있는" 유형이다.
백업 스크립트를 검토 1순위로 두는 이유가 여기서도 반복된다.

## 3. MySQL Shell

### 3.1 덤프

```bash
mysqlsh ${USER}@${HOST}:3306 -- util dump-instance /backup/dump --threads=8 --compression=zstd
mysqlsh ${USER}@${HOST}:3306 -- util dump-schemas mydb otherdb --outputUrl=/backup/dump --threads=8
mysqlsh ${USER}@${HOST}:3306 -- util dump-tables mydb tbl_a tbl_b --outputUrl=/backup/dump --threads=8
```

`dump-instance`는 system schema를 자동 제외한다. 스크립트에는 옵션 가독성 때문에 JS 모드를 권장한다.

```javascript
util.dumpInstance("/backup/dump", {
  threads: 8,
  compression: "zstd",
  bytesPerChunk: "128M",
  consistent: true,
  users: false,                                          // RDS/Aurora 대상이면 false
  compatibility: ["strip_definers", "strip_restricted_grants"],
  excludeSchemas: ["tmp_db"],
  dryRun: false
})
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `threads` | 4 | 소스 서버 코어 수 이하로 |
| `chunking` / `bytesPerChunk` | `true` / `64M` | 대용량은 `128M`~`256M` |
| `compression` | `zstd` | `zstd` / `gzip` / `none` |
| `consistent` | `true` | FTWRL + `LOCK INSTANCE FOR BACKUP` |
| `users` | `true` (dumpInstance) | 계정·권한 포함 여부 |
| `compatibility` | `[]` | DDL 변환 플래그 (아래) |
| `ocimds` | `false` | HeatWave 호환성 검사 |
| `dryRun` | `false` | **실행 전 반드시 한 번** |
| `where` / `partitions` | — | 조건부·파티션 단위 |
| `excludeSchemas` / `excludeTables` | — | 제외 대상 |
| `s3BucketName` | — | S3 직접 업로드 |

**`compatibility` 플래그**

| 값 | 동작 |
|---|---|
| `strip_definers` | `DEFINER=` 절 제거 — **관리형 DB 대상이면 사실상 필수** |
| `strip_restricted_grants` | 관리형 DB에서 부여 불가한 권한 제거 |
| `force_innodb` | 다른 스토리지 엔진을 InnoDB로 변경 |
| `skip_invalid_accounts` | 인증 플러그인 미지원 계정 스킵 |
| `strip_tablespaces` | `TABLESPACE=` 절 제거 |
| `create_invisible_pks` | PK 없는 테이블에 invisible PK 생성 |
| `ignore_wildcard_grants` | 와일드카드 GRANT 경고 무시 |

> `skip_invalid_accounts`가 필요해지는 상황은 대개 `mysql_native_password` 계정이다.
> 8.4 기본 비활성 → 9.0 제거 경로에 걸려 있으므로 ([[mysql-operations]] 버전 이정표),
> 스킵으로 넘기지 말고 **이관 전에 인증 플러그인을 정리하는 것이 순서다**.^[inferred]

S3로 바로 올릴 수 있다 — 중간 디스크가 필요 없어진다.

```javascript
util.dumpSchemas(["mydb"], "prod/mydb/20260815", {
  s3BucketName: "my-db-backup", s3Region: "ap-northeast-2", s3Profile: "prod",
  threads: 8, compression: "zstd",
  compatibility: ["strip_definers", "strip_restricted_grants"]
})
```

### 3.2 로드

```javascript
util.loadDump("/backup/dump", {
  threads: 8,
  deferTableIndexes: "all",      // 데이터 적재 후 인덱스 생성 → 대폭 빠름
  analyzeTables: "on",
  ignoreExistingObjects: false,
  loadUsers: false,
  maxBytesPerTransaction: "128M",
  resetProgress: false,          // true면 진행상황 초기화 후 처음부터
  dryRun: false
})
```

| 옵션 | 설명 |
|---|---|
| `deferTableIndexes` | `off` / `fulltext`(기본) / `all` — **대용량은 `all`** |
| `analyzeTables` | `off` / `on` / `histogram` |
| `ignoreExistingObjects` | 이미 존재하는 객체 무시 |
| `ignoreVersion` | 소스/타깃 버전 불일치 허용 |
| `resetProgress` / `progressFile` | 진행 파일 초기화 / 저장 위치(기본: 덤프 디렉터리) |
| `maxBytesPerTransaction` | 트랜잭션 크기 제한. **Aurora binlog 부하 완화에 유용** |
| `updateGtidSet` | `off` / `append` / `replace` |
| `skipBinlog` | binlog 기록 생략 — **RDS/Aurora는 권한 없어 사용 불가** |
| `waitDumpTimeout` | 진행 중인 덤프를 동시 로드할 때 대기 |

> [!important]
> 타깃의 `local_infile`이 **`1`(ON)** 이어야 한다. Aurora/RDS는 파라미터 그룹에서 설정한 뒤
> **적용 상태(pending-reboot 여부)까지 확인**한다. 이것 하나로 로드가 즉시 실패한다.

### 3.3 중간 저장소 없는 직접 복사 (Shell 8.0.32+)

```javascript
util.copyInstance("mysql://user@target-host:3306", { threads: 8 })
util.copySchemas(["mydb"], "mysql://user@target-host:3306", { threads: 8 })
util.copyTables("mydb", ["tbl_a"], "mysql://user@target-host:3306")
```

디스크가 부족하거나 일회성 이관일 때 쓴다. **실패 시 재시작 이점이 없다** —
장시간 이관에 쓰면 Shell을 고른 이유가 사라진다.

### 3.4 binlog 증분 (Shell 9.2.0+)

binlog 덤프/로드 유틸리티는 `mysqlbinlog`와 같은 기능에 멀티스레드·압축·원격 스토리지를 더한 것으로,
`util.dumpInstance()`로 적재한 타깃에 소스 변경분을 적용해 시점 복구를 가능하게 한다.

```javascript
util.dumpBinlogs("/backup/binlog_dump", { since: "/backup/dump", threads: 4 })
util.loadBinlogs("/backup/binlog_dump")
```

전제 조건이 까다롭다.

- 소스 binlog 활성화, `gtid_mode`가 `OFF`/`OFF_PERMISSIVE`가 아닐 것
- `since`로 지정하는 덤프는 **MySQL Shell 9.2.0 이상에서 생성된 완료·일관성 있는 덤프**여야 하며,
  `ocimds:true`나 `compatibility` 옵션을 사용한 덤프는 예외가 발생한다
- 타깃의 `gtid_executed`가 로드할 첫 binlog 파일의 `gtid_executed`를 완전히 포함해야 한다

> **관리형 DB 이관과 증분 복구는 양립하지 않는다.** §4의 고정 세트는 `compatibility`를 요구하는데,
> `since`는 `compatibility`를 쓴 덤프를 거부한다. RDS/Aurora 대상에서 논리 덤프 기반 시점 복구를
> 설계하려면 이 충돌을 먼저 해소해야 한다 → Open Questions

## 4. Aurora / RDS 특이사항

| 이슈 | 증상 | 대응 |
|---|---|---|
| GTID 구문 | 복구 시 `SUPER` 권한 에러 | `--set-gtid-purged=OFF` |
| DEFINER | 정의자 계정 없음/권한 부족 | `compatibility: ["strip_definers"]` |
| 계정 덤프 | 부여 불가 권한으로 실패 | `users: false` 후 계정은 별도 이관 |
| 일관성 락 | `consistent: true` 락 획득 실패 | 권한 확인. 불가 시 `consistent: false` — **정합성 보장 안 됨** |
| `local_infile` | load 즉시 실패 | 파라미터 그룹에서 `1` |
| binlog 부하 | load 중 writer 부하 급증 | `maxBytesPerTransaction` 조정 |
| Reader 덤프 | 락 관련 제약 | writer에서 수행하거나 `consistent: false` 검토 |
| 대용량 이관 | 논리 백업이 너무 느림 | XtraBackup → S3 → Aurora 복원, 또는 DMS |

Reader에서 덤프가 제약을 받는 것은 Aurora가 공유 스토리지 위에서 redo를 적용하는 구조라
Reader가 독립적으로 락을 잡을 수 없기 때문이다 → [[aurora-vs-mysql-replication-architecture]].^[inferred]
스토리지 계층 특성은 [[cloud-platform-knowledge]]에 정리돼 있다.

**Aurora → Aurora 표준 조합**

```javascript
// 소스
util.dumpSchemas(["mydb"], "s3-prefix/mydb", {
  s3BucketName: "db-migration", s3Region: "ap-northeast-2",
  threads: 8, users: false,
  compatibility: ["strip_definers", "strip_restricted_grants"]
})
// 타깃
util.loadDump("s3-prefix/mydb", {
  s3BucketName: "db-migration", s3Region: "ap-northeast-2",
  threads: 8, deferTableIndexes: "all", analyzeTables: "on",
  maxBytesPerTransaction: "128M"
})
```

## 5. 필요 권한

```sql
-- Dump 계정
GRANT SELECT, SHOW VIEW, EVENT, TRIGGER, LOCK TABLES, PROCESS
  ON *.* TO 'dump_user'@'%';
-- RELOAD        : --source-data 사용 시
-- BACKUP_ADMIN  : MySQL Shell consistent 덤프 시 (8.0+)
```

Load 계정은 대상 스키마에 `CREATE, ALTER, INSERT, INDEX, DROP, REFERENCES`가 필요하고,
계정까지 복원한다면 `CREATE USER` + 부여할 권한을 `WITH GRANT OPTION`으로 보유해야 한다.

> **`WITH GRANT OPTION` 보유 계정은 상시 존재해서는 안 된다.** [[db-access-control]]의
> break-glass 원칙대로 이관 기간에만 발급하고 회수한다 — 이관 전용 계정이 남는 것이
> 권한 잔재의 전형적 경로다.^[inferred]

## 6. 체크리스트

**덤프 전**
- [ ] `dryRun: true` 또는 `mysqldump --no-data`로 대상 범위 확인
- [ ] 디스크 여유 공간 확인 (압축 전 기준으로 추정)
- [ ] `--routines --triggers --events` 포함 여부 결정
- [ ] 소스 부하 시간대 확인 (`consistent` 덤프는 순간 락 발생)
- [ ] 백업 창과 배포(DDL) 창이 겹치지 않는지 — `--single-transaction` 중 DDL은 일관성을 깬다

**로드 전**
- [ ] **타깃 호스트·스키마 재확인** (운영 오적재 사고 1순위)
- [ ] `local_infile=1` 확인 및 적용 상태 확인
- [ ] 기존 데이터 처리 방침 (덮어쓰기 / 신규 / 병합)
- [ ] 문자셋·콜레이션 일치 확인

**로드 후**
- [ ] 테이블 수 / row count 대조
- [ ] `SHOW PROCEDURE STATUS`, `SHOW TRIGGERS`, `SHOW EVENTS` 대조
- [ ] `ANALYZE TABLE` 수행 여부
- [ ] `event_scheduler` 상태 및 이벤트 활성화 여부
- [ ] FK 제약 유효성
- [ ] 애플리케이션 계정 권한 재부여

이 대조 항목이 곧 [[mysql-operations]]가 말하는 "성공 로그가 아니라 객체 수·행 수 대조까지가
백업 검증 한 단위"의 실행 형태다. 주간 점검 에이전트의 복원 테스트 단계에 그대로 옮길 수 있다.

## 7. 자주 겪는 에러

| 에러 | 원인 | 해결 |
|---|---|---|
| `Access denied; you need SUPER privilege` | GTID 또는 DEFINER 구문 | `--set-gtid-purged=OFF` / `strip_definers` |
| `Access denied; you need PROCESS privilege` | 8.0 tablespace 조회 | `--no-tablespaces` |
| `Unknown table 'COLUMN_STATISTICS'` | 8.0 클라이언트 ↔ 5.7 서버 | `--column-statistics=0` |
| `Loading local data is disabled` | `local_infile=OFF` | 파라미터 그룹에서 `1` |
| `The target directory must be empty` | 덤프 디렉터리에 기존 파일 | 새 경로 지정 |
| `Unable to acquire global read lock` | 권한 부족 | 권한 확인 후 `consistent: false` 검토 |
| `MySQL server has gone away` | 패킷 크기 초과 | 타깃 `max_allowed_packet` 상향 |
| `Duplicate entry` (load 재시도) | 진행 상태 꼬임 | `resetProgress: true` 후 재실행 |

> 앞 3개는 전부 **관리형 DB의 권한 제약**이 원인이다. §1의 고정 세트를 적용하면 사전에 사라진다 —
> 에러를 만나고 대응하는 대신 이관 템플릿에 박아두는 것이 자동화 관점의 정답이다.^[inferred]

## Open Questions

- **mysqldump 상한 수치.** 사내 판단 "수 GB 이하"와 원본 메모 "수십 GB"가 어긋난다 ^[ambiguous].
  덤프 시간·복구 시간을 실측해 **분(分) 단위 RTO 기준으로 재정의**하는 것이 맞다 — 크기는 대리 지표일 뿐이다^[inferred]
- **`dumpBinlogs`의 `compatibility` 배타 조건.** RDS/Aurora 대상은 `strip_definers`가 사실상 필수인데
  `since` 덤프는 `compatibility` 사용 시 예외가 난다. 관리형 DB에서 논리 덤프 기반 시점 복구가
  성립하는지 미확인 — 실기 검증 필요
- **Aurora binlog 접근 방식.** 원문도 "Aurora는 binlog 접근 방식이 다르므로 실제 적용 전 검증 필요"로
  남겼다. `dumpBinlogs`가 Aurora writer에서 동작하는지 미확인
- **`consistent: false` 사용 등급.** 정합성이 보장되지 않는 덤프를 "백업"으로 부를지, 별도 등급으로
  기록할지 정해지지 않았다. 정하지 않으면 복구 시점에 신뢰도를 알 수 없다
- **실기 검증 전.** 이 페이지의 옵션 조합은 아직 개발/QA 인스턴스에서 실행 확인을 거치지 않았다 →
  [[verbal-source-verification-policy]] 기준으로 `draft` 유지

## Sources

- 사내 MySQL Dump & Load 가이드 메모 (2026-08-15 적재)
- [MySQL Shell Utilities](https://dev.mysql.com/doc/mysql-shell/9.7/en/mysql-shell-utilities.html)
- [Instance/Schema/Table Dump Utility](https://dev.mysql.com/doc/mysql-shell/9.7/en/mysql-shell-utilities-dump-instance-schema.html)
- [Binary Log Dump/Load](https://dev.mysql.com/doc/mysql-shell/9.7/en/mysql-shell-utilities-dump-load-binlogs.html)
- [mysqldump](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)
