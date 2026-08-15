---
title: DBA 운영 표준 — 장애 대응 흐름·모니터링·문서 생명주기
tags: [dba, incident-response, monitoring, runbook]
topics: [dba]
summary: >-
  표준 장애 대응 5단계, 계층형 모니터링(SLO→클라우드→DB엔진→SQL), 고정 임계치 금지,
  AWS Database Insights 전환, 문서 생명주기 기준.
project: second-brain
base_confidence: 0.8
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: 운영 및 모니터링 (2026-07-30)"
  - "Notion: 정제된 핵심 가이드 (2026-07-30)"
---

# DBA 운영 표준

## 표준 장애 대응 흐름

1. 증상과 영향 범위 기록
2. 변경 이력·인프라 지표 확인
3. DB 대기 이벤트, 잠금, 실행 계획 확인
4. **임시 완화와 근본 조치를 분리**
5. 재현·검증 결과와 재발 방지 항목 기록

장애 분석은 계층 순서로: SLO → 클라우드/호스트 지표 → DB 엔진 내부 지표 → SQL 단위 분석. RDS/Aurora·온프레미스·Azure SQL MI는 환경별로 분리해서 판단한다.

## 모니터링 원칙

- 고정 임계치는 절대 기준이 아니다. 인스턴스 크기·워크로드 기준선·서비스 SLO 기준으로 조정.
- AWS 모니터링 문서는 Performance Insights 콘솔이 아니라 **CloudWatch Database Insights** 전환 기준으로 관리.

## 문서 생명주기

- 제품 버전·최종 검증일 없는 설정 문서는 `검토 필요`로 분류.
- 비권장 구성은 삭제하지 않고 역사 자료로 `보관` + 대체 문서 연결.
- 실행 명령에는 사전 조건, 영향, 롤백, 검증 방법을 포함.

## 보완 사항 (분석 결과)

- **[보완] DBA 업무 체크리스트의 재작성 방향이 좋은 패턴**: 단순 일/주/월 목록 → 서비스 SLO, RPO/RTO, 담당자, 증적, 자동화 여부, 에스컬레이션, restore/DR 실증을 포함한 Runbook 형태. 로컬 볼트의 런북 템플릿(`tags: [runbook]`)에도 이 필드 구성을 채택할 것. ^[inferred]
- **[보완] 장애 대응 흐름에 커뮤니케이션 단계 누락**: 심각도 판정과 이해관계자 공지(누구에게, 언제, 어떤 채널) 단계가 없음. 실제 장애에서는 기술 분석과 병행되는 필수 트랙이므로 추가 권장. ^[inferred]
