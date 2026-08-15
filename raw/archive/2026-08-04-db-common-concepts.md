---
title: DBMS 공통 개념·3사 비교·SQL 작성 원칙 (Notion 심층 수집)
tags: [dba, sql, comparison, best-practice]
topics: [dba]
summary: >-
  3대 엔진(MySQL/PostgreSQL/SQL Server) 저장 단위·격리수준·MVCC·문법 비교,
  SQL 안티패턴 체크리스트, 조인 알고리즘 선택 기준.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: DB 공통 개념 인덱스 트리 (https://app.notion.com/p/32ffb969b8be81d6a0dbdf48032633bc, 2026-07-30)"
---

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
