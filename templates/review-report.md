# 리뷰 리포트: {{slug}} (spec-v{{version}}, review #{{seq}})

- 리뷰 대상 명세: `{{specPath}}`
- 리뷰 깊이: {{depth}}
- 종합 판정: **{{approved 또는 changes-requested}}**

## 리뷰어별 판정

{{reviewerRows}}

하나라도 `changes-requested`면 종합 판정은 `changes-requested`다 (평균 내지 않는다).

## 명세 준수

{{spec-reviewer: 구현이 명세를 따르는지 요약. 벗어난 부분이 있으면 명시}}

## 인수 기준 커버리지

{{acRows}}

## 오류 케이스 커버리지

{{ecRows}}

## 스펙 밖 구현

- {{명세에 없는데 추가된 것. 없으면 "없음"}}

## 코드 품질

{{codeReviewSection}}

## 보안

{{securityReviewSection}}

## 성능

{{perfReviewSection}}

## 게이트 위반

{{guardRows}}

## 발견된 갭

- {{명세와 구현이 어긋나는 지점. severity high 지적을 함께 적는다}}

## 개선 제안

- {{severity medium/low 지적과 명확성·단순화 제안. 자동 재시도를 유발하지 않는다}}

## 결론

{{완료 처리 가능 여부와 근거 한 문단}}
