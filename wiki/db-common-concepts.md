---
title: DBMS 공통 개념·3사 비교·SQL 작성 원칙
category: db운영
tags: [dba, sql, comparison, best-practice, mysql, postgresql, sqlserver]
summary: 3대 엔진(MySQL/PostgreSQL/SQL Server) 저장 단위·격리수준·MVCC·문법 비교표, SQL 안티패턴 체크리스트, 조인 알고리즘 선택 기준.
sources: ["Notion: DB 공통 개념 인덱스 트리 (2026-07-30)"]
status: draft
created: 2026-08-04
updated: 2026-08-04
notion_page_id: "3bdfb969-b8be-81df-907f-f5f32fd9914b"
notion_synced: "2026-08-15T19:05:47+0900"
---

> [!tip] 핵심 Takeaway
> - **3사 비교표가 이 위키에서 가장 재사용 빈도가 높은 자산이다.** 엔진 간 이관·다중 엔진 툴 개발 시 기본 격리수준(MySQL만 RR), MVCC 구현, UPSERT 문법, 락 스킵 구문 차이를 여기서 확인한다
> - **안티패턴 체크리스트를 쿼리 리뷰 자동화의 룰셋으로 옮긴다** — WHERE 컬럼 함수, 암묵적 형변환, `SELECT *`, OFFSET 페이지네이션, `NOT IN` + NULL, LEFT JOIN 조건을 WHERE에 두기. 전부 정적 검출 가능하다
> - **`NOT IN` + NULL은 조용히 빈 결과를 낸다** → `NOT EXISTS`. 오류가 안 나서 가장 늦게 발견되는 유형
> - **MySQL DDL은 implicit commit이다** — 롤백을 전제로 한 마이그레이션 스크립트를 MySQL에 그대로 쓰면 안 된다. PG는 DDL 롤백 가능(일부 예외)
> - 통계 갱신은 "추정 오류가 실제 원인인지" 확인 후 문제 객체만 좁혀서 한다. 전체 갱신부터 하는 대응은 원인을 지운다

# DBMS 공통 개념·3사 비교

## 엔진 기본 차이

| 항목 | MySQL(InnoDB) | PostgreSQL | SQL Server |
|---|---|---|---|
| 페이지 크기 | 16KiB (초기화 후 변경 불가) | 8KiB (빌드 시 변경 가능) | 8KiB 고정 (+64KiB extent) |
| 기본 격리수준 | REPEATABLE READ | READ COMMITTED | READ COMMITTED |
| MVCC 구현 | Undo Log | Dead Tuple(heap 내) + VACUUM | RCSI 버전 저장(tempdb) |
| UPSERT | ON DUPLICATE KEY | ON CONFLICT | MERGE(동시성 주의) |
| 자동증가 | AUTO_INCREMENT | GENERATED AS IDENTITY | IDENTITY |
| 락 스킵 | SKIP LOCKED | SKIP LOCKED | READPAST |
| 세션 뷰 | processlist | pg_stat_activity | dm_exec_requests |

- Durability: `innodb_flush_log_at_trx_commit` 1(안전) / 2(최대 1초 손실).

## SQL 작성 공통 원칙 (안티패턴 체크리스트)

- WHERE 컬럼에 함수 금지 → 범위 조건으로 변환. 암묵적 형변환 금지. SELECT * 금지.
- OFFSET 페이지네이션 대신 Keyset(seek) 방식.
- **NOT IN + NULL 함정 → NOT EXISTS 사용.**
- LEFT JOIN에서 우측 테이블 조건을 WHERE에 쓰면 INNER JOIN으로 강등.
- 트랜잭션 내 외부 API 호출 금지. 대량 DML은 청크 분할.
- 복합 인덱스: leftmost prefix + 등호→범위→정렬 순서.
- MySQL 함정: zero date, ONLY_FULL_GROUP_BY, 자기참조 DELETE 서브쿼리(ERROR 1093), MySQL DDL은 implicit commit(롤백 전제 금지).

## 조인 알고리즘 선택

- Nested Loop: 소량 + 인덱스. Hash: 대용량 등치(메모리). Merge: 정렬된 입력.
- 드라이빙 테이블은 소량 배치. N+1은 JOIN/Eager Loading으로 해소.

## 통계

갱신 전 "추정 오류가 실제 원인인지" 확인 → 문제 객체만 좁혀 갱신 → 전후 실행 계획 비교. (SQL Server 자동갱신 임계 row 10만/5% 메모는 구식 — 최신 버전은 동적 임계.)

## 발견된 품질 이슈 (원본 교정 필요)

- 여러 페이지에 인코딩 깨진 한글·AI 생성물 미검수 흔적.
- "READ COMMITTED는 읽는 로우에 S lock" 서술은 InnoDB MVCC(일반 SELECT 무락)와 상충하는 구식 설명.
- 인덱스 페이지에 만료되는 S3 서명 이미지 URL(링크 부패). 페이지 크기 비교 서술 부정확(SQL Server 8KB 고정).

## Related

- [[mysql-operations]] · [[postgresql-operations]] · [[sqlserver-operations]] — 이 비교표의 엔진별 상세
- [[operational-queries]] — 같은 목적을 3사 문법으로 대조한 쿼리 모음
- [[sqlserver-xevent-sessions]] — "느린 쿼리를 남긴다"는 같은 목적을 엔진별로 다르게 푸는 예: MySQL slow query log, PG `log_min_duration_statement`, SQL Server는 XEvent 세션
- [[aurora-dsql]] — PG 호환이지만 격리수준이 Repeatable Read로 고정된 예외 사례
