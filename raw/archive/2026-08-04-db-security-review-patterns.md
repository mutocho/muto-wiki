---
title: DB 문서 보안 검토에서 반복 발견된 위험 패턴
tags: [dba, security, gotcha]
topics: [dba]
summary: >-
  Notion 지식베이스 보안 검토(1~6차)에서 반복 발견된 위험 패턴 목록 —
  고정 비밀번호, Database Mail 자격증명, 무조건 인덱스 리빌드, TDE 해제 단계 혼입 등.
project: second-brain
base_confidence: 0.85
provenance:
  extracted: 0.9
  inferred: 0.1
lifecycle_changed: 2026-08-04
sources:
  - "Notion: 정리 및 보안 검토 보고서 (2026-07-30)"
---

# DB 문서 보안 검토에서 반복 발견된 위험 패턴

문서·스크립트 감사 시 체크리스트로 재사용할 것.

## 자격증명·비밀정보

- 실제 비밀번호 형태 문자열이 계정 설정 문서에 그대로 저장됨 → 발견 즉시 제거 + **해당 자격증명 폐기·재발급** (문서에서 지우는 것만으로는 불충분).
- `1234`, `password`, `change-me` 같은 자리표시자도 위험: 복사 후 그대로 운영 반영될 수 있음 → `<INJECT_FROM_SECRET_STORE>` 또는 환경변수 표기로 통일.
- SMTP·복제·Slack Webhook·클라우드 자격증명은 값이 비어 있는 템플릿만 유지.
- 개인 계정명, 사내 호스트명, 로컬 키 경로, 개인 이메일도 내부정보 노출 — placeholder로 치환.
- OS 명령 예제: 생성된 비밀번호의 화면 출력 금지, 프로세스 인자·내부 포트는 공유 전 마스킹.

## 위험한 절차·스크립트 패턴

- **일반 백업 절차에 TDE 해제·암호화 키 삭제 단계가 섞여 있던 사례** — 보안통제 약화 단계가 일상 절차에 혼입되는 전형적 위험. 절차 문서는 보안 상태를 바꾸는 단계를 분리·격리할 것.
- SQL Server 인덱스 리빌드 스크립트: 조각화율만으로 전체 대상에 `REBUILD WITH (MAXDOP=0, SORT_IN_TEMPDB=ON)` 생성 → **자동 실행 금지** 분류. 페이지 수·워크로드·에디션(온라인 리빌드 가능 여부) 고려 필요.
- SQL Server Database Mail: `public` 기본 프로필, `RECONFIGURE WITH OVERRIDE`, SMTP 자격증명 직접 입력 패턴은 교정 대상.
- MySQL 인증 해시를 추출해 사용자 생성문을 재구성하는 스크립트는 제한된 절차로 격리.
- Docker 전체 컨테이너 강제 삭제·볼륨 삭제 명령은 고위험 격리 + 안전한 prune 기준 별도 문서화.
- 비밀번호 정책 비활성화, 상시 `sysadmin` 부여 예제 → 최소 권한·시크릿 저장소 기준으로 교정.

## 버전·환경 분리 기준 (검증된 사실)

- MySQL `mysql_native_password`: 8.0.34 deprecated → 8.4 기본 비활성 → 9.0 제거.
- Kafka 4.x는 KRaft 전용, ZooKeeper 문서는 3.x 레거시 마이그레이션 자료로만 유지.
- PostgreSQL: OSS / RDS / Aurora의 superuser·extension·parameter·스토리지 차이를 항상 분리 기술.

## 보완 사항 (분석 결과)

- **[보완] 검토 주기 부재**: 1~6차 검토가 모두 2026-07-30 하루에 몰려 있음. "마지막 검증일 + N개월" 형태의 재검증 주기 규칙(예: 운영 Runbook 6개월, 버전 의존 문서는 메이저 릴리스 시)을 정해야 일회성 대청소로 끝나지 않는다. ^[inferred]
