---
title: dbgw 메타DB 운영 쿼리
category: 업무기록
tags: [worklog, snippet, dbgw, mysql]
summary: dbgw 메타DB에서 인스턴스별 권한 현황을 뽑는 쿼리 모음. 업무 중 작성해 사용한 원본 그대로 보관.
sources: [사내 dbgw 메타DB 작업 (2026-08-06)]
status: draft
created: 2026-08-06
updated: 2026-08-16
notion_page_id: "3bdfb969-b8be-816d-953d-f15ad5c620cb"
notion_synced: "2026-08-15T18:53:45+0900"
---

> [!tip] 핵심 Takeaway
> - 권한 현황 조회를 매번 손으로 쓰지 말고 이 쿼리를 dbgw 정기 점검 자동화의 입력으로 고정한다
> - `databases`는 MySQL 예약어 — 백틱 없이 쓰면 실패한다. 메타DB 대상 쿼리를 생성하는 에이전트에 예약어 이스케이프를 넣어둘 것
> - 인스턴스 ID가 하드코딩돼 있다. 자동화로 옮길 때 파라미터로 빼는 것이 첫 작업

# dbgw 메타DB 운영 쿼리

업무 중 작성해 사용한 쿼리를 원본 그대로 보관한다.

## 인스턴스에 부여된 권한 목록 추출

DB별로 접근 권한이 부여된 사용자를 묶어서 조회한다.

```sql
select c.dbName, group_concat(b.userName)
from user_grants as a
join users as b on b.id = a.userId
join `databases` as c on c.instanceId = a.instanceId and a.dbId = c.dbId
where a.instanceId = 26
group by c.dbName;
```

- `a.instanceId`가 대상 dbgw 인스턴스. 위 예시는 26.
- `databases`는 MySQL 예약어라 백틱이 필요하다.

## Related

- [[worklog-kakaogames-2026|2026년 작업 내역]]
- [[operational-queries|운영 진단 쿼리 모음]] — 엔진 일반 진단 쿼리. 이 페이지는 dbgw 메타DB 전용이라는 점이 차이
