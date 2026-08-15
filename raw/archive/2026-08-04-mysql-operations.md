---
title: MySQL/Aurora MySQL 운영 지식 (Notion 심층 수집)
tags: [dba, mysql, backup, troubleshooting]
topics: [dba]
summary: >-
  mysqldump/MySQL Shell 백업 표준, Undo·장기 트랜잭션, 락, 임시테이블 5.7→8.0,
  버전별 이정표(회수 릴리스 포함), 모니터링 판단 기준.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: MySQL 지식 인덱스 트리 (https://app.notion.com/p/9637d1b295014a94a918de62de98ddd0, 2026-07-30)"
---

# MySQL/Aurora MySQL 운영 지식

## 백업 표준 (MySQL 8.0/8.4 LTS/Aurora 3, 검증 2026-07-30)

- InnoDB 단일 DB: `mysqldump --single-transaction --quick --events --routines --triggers --hex-blob --set-gtid-purged=OFF` 기본.
- `--single-transaction` 도중 DDL(ALTER/DROP/RENAME/TRUNCATE) 실행 시 일관성 깨짐.
- 비밀번호는 `mysql_config_editor`(login-path)로 관리.
- 대용량은 MySQL Shell `util.dumpInstance/dumpSchemas/loadDump` (threads, zstd, dryRun, 재개 지원). RDS/Aurora 복원 시 `users:false`/`loadUsers:false` 기본.
- 판단 기준: 수 GB 이하 mysqldump / 수십 GB+ Shell / 초대형+짧은 RTO는 물리백업(xtrabackup)·DMS.
- 검증은 성공 로그가 아니라 파일·객체 수·행 수·별도 환경 복원 테스트로 한다.

## Undo·장기 트랜잭션

긴 트랜잭션은 Purge를 막아 ① Undo tablespace 폭증(트랜잭션 보유 중엔 truncate 불가) ② History List Length 증가로 읽기 성능 저하 ③ 종료 시 롤백·purge 폭탄. 확인: `SHOW ENGINE INNODB STATUS`, `information_schema.INNODB_TRX`(trx_started). `innodb_purge_threads`/`batch_size`는 원인 확인 전 조정 금지.

## 락·격리수준

- RR 기본에서 Next-Key(레코드+갭) 락. RC는 갭 락 없음 → INSERT 경합 가능·팬텀 허용. RR 갭락 데드락 완화 목적의 RC 전환은 팬텀 허용 트레이드오프를 반드시 명시할 것.
- `innodb_autoinc_lock_mode` 0/1/2.
- PK 없으면 UNIQUE 인덱스 → 그것도 없으면 GEN_CLUST_INDEX 자동 생성.
- ON DUPLICATE KEY UPDATE는 유니크 인덱스 2개 이상이면 회피(공식 문서 명시).

## 임시 테이블 (5.7→8.0)

MEMORY(고정길이, BLOB/TEXT 즉시 디스크 MyISAM) → TempTable(가변길이, BLOB/TEXT/JSON 메모리 처리, spill 시 세션별 InnoDB 임시 테이블스페이스). `temptable_max_ram` 기본 1GB.

## 실행 계획·모니터링

- `EXPLAIN ANALYZE`는 8.0.18+. type 우선순위 `const>eq_ref>ref>range>index>ALL`, Extra 위험신호 `Using filesort/temporary/join buffer`.
- Handler_* 해석: read_key 높음=양호, read_rnd_next 높음=풀스캔.
- 단일 임계값 대신 기준선·지속시간·변화율로 판단. buffer pool hit 99%+, history list length 수십만↑=장기 트랜잭션, `Innodb_log_waits>0`=log 부족, Threads_running이 실제 부하.
- sysbench: 운영 DB 금지, prepare/run/cleanup 3단계, p95/p99·lock wait 병행 기록.

## 버전 이정표 (5.7.44~8.4.9)

- **회수(사용 금지) 릴리스: 8.0.29** (instant column 결함), **8.0.38/8.4.1** (8001+ 테이블 재시작 실패).
- 8.0.13 함수형 인덱스/Skip Scan · 8.0.16 CHECK 제약 실적용/TLS1.3 · 8.0.17 Clone Plugin · 8.0.18 Hash Join/EXPLAIN ANALYZE · 8.0.23 Invisible Column · 8.0.27 MFA/병렬 DDL · 8.0.28 TLS1.0/1.1 제거 · 8.0.30 GIPK/`innodb_redo_log_capacity` · 8.0.31 INTERSECT/EXCEPT · 8.0.32 (8.0.28→업그레이드 시 INSTANT 컬럼 손상 수정) · 8.0.41/8.4.4 공간 인덱스 재생성 권장 · 8.4.0 `mysql_native_password` 기본 비활성·구 복제 구문 제거. 8.0/8.4가 LTS.
- `mysql_native_password`: 8.0.34 deprecated → 8.4 기본 비활성 → 9.0 제거.
- NUMA는 `numactl --interleave`로 스왑 유발 방지. ONLINE DDL 가능 여부는 버전별 공식 표 확인.

## 발견된 위험 자료 (원본 교정 필요)

- 2023 보존 my.cnf에 내구성 포기 설정이 경고 없이 존재: `innodb_flush_log_at_trx_commit=0`, `sync_binlog=0`, `innodb_doublewrite=0`, `skip_ssl`, 8.0에서 제거된 `query_cache`/`innodb_file_format` — 예시로도 유해.
- mydumper 페이지에 실제 QA RDS 호스트명 노출 + `--no-locks`(일관성 리스크), 롤백·검증 절차 없음.
- 복제 문서는 구 용어(`show slave status`)만 있고 8.0.22+ `SHOW REPLICA STATUS` 병기 없음.
- Aurora MySQL·MySQL 5.7.24 설정 페이지는 공백.
