# 카공지도 Geoapify Free 로컬 준비

사용자가 **Geoapify로 변경**을 선택했다. 카카오 준비 코드·비공개 파일은 보존하며 이번 실습에서는 사용하지 않는다. 키 준비는 실제 기획·배포 승인이 아니다.

## 프로젝트와 키

[MyProjects](https://myprojects.geoapify.com/)에서 프로젝트의 요금제가 **Free**인지 확인하고 API Keys의 API 키 하나를 사용한다. JavaScript/REST 키 종류를 따로 발급하지 않는다. 카드 등록은 필요 없다. 이 호스트 검색 어댑터에는 필수 SDK 도메인 등록 절차가 없다. 이미 설정한 IP/referrer/origin 제한은 임의 해제하지 않는다.

키는 아래 로컬 파일에만 저장한다. Finder에서 `⌘⇧G`로 경로에 이동하거나 `⌘⇧.`으로 숨김 폴더를 표시할 수 있다.

`/Users/seohyeokin/workspace/skala-AIMiniProject/.worktrees/codex-runtime/runtime-data/secrets/geoapify.json`

```json
{
  "api_key": "발급받은 키",
  "free_plan_confirmed": true
}
```

`free_plan_confirmed`는 실제 Free 플랜을 확인한 경우에만 true로 바꾼다. 현재 사용자 소유의 일반 파일·권한 600이어야 한다. 편집기가 권한을 바꾸면 다음 명령으로 복구한다.

```sh
chmod 600 /Users/seohyeokin/workspace/skala-AIMiniProject/.worktrees/codex-runtime/runtime-data/secrets/geoapify.json
```

`runtime-data/`는 Git 제외다. 키는 채팅·Git·스크린샷·모델 입력·생성 컨테이너·공개 기록에 넣지 않는다. 호스트가 `x-api-key` 헤더로 전송하며 URL에 넣지 않는다. 키 준비 뒤에는 값 대신 준비 완료 사실만 알린다.

## 무료 조건과 동의

2026-10-21 공식 조건은 Free 일 3,000credits·초 5요청이다. 지도 타일과 검색은 같은 프로젝트의 크레딧을 사용한다. Places는 최대 20개 결과 기준 1credit, 기본 geocoding은 1credit, 지도 타일은 0.25credit이다. 무료 한도는 soft limit이므로 공급자가 반드시 즉시 차단한다고 가정하지 않는다. 이 검색 어댑터는 geocoding+Places 합계 UTC 일 200회 시도 제한을 영속 저장하고, 429 이후 당일 추가 호출·자동 재시도·유료 전환을 차단한다. 프로젝트 전체 잔량이나 다른 앱의 사용량을 알 수는 없다. 지도 타일은 아직 이 어댑터에 연결하지 않았다.

화면에는 Geoapify와 OpenStreetMap 출처를 표시해야 한다. 지역/주소 검색어·사용자가 선택한 좌표를 Geoapify에 보내는 데 명시적으로 동의한 뒤 검색한다. 브라우저 위치 권한과 외부 전송 동의는 따로 처리하고 자동 GPS 요청하지 않는다. 시험용 공개 지역 검색은 실제 사용자 위치 수용을 대신하지 않는다.

## 구현과 남은 경계

`backend/geoapify.py`는 대한민국 지역/주소 검색의 후보를 반환하고, 사용자가 선택한 좌표 중심의 카페 검색·이름 필터·출처의 인터넷 태그 필터를 준비했다. 첫 지역 후보를 자동 선택하지 않는다. 한국 카페/한글 검색 품질은 실제 호출로 별도 확인한다. 조용함·콘센트·장시간 이용 적합성은 확인되지 않은 값이며 만들어 내지 않는다.

현재 어댑터는 API/worker/생성 앱 프리뷰와 미연결이다. `http://localhost:8017`은 신뢰 지도 화면을 위한 예약 주소이며 아직 기동하지 않았다. opaque 생성 앱 iframe의 격리를 해제하거나 키를 생성 코드에 주지 않는다. 신뢰 지도 화면·제한된 브로커·타일·위치 동의·독립 검토 경로를 연결한 뒤 새 기획을 검토하고 사용자가 직접 승인해야 한다. 준비 모듈/개발용 검색 확인을 제품 런타임의 앱 완주로 보고하지 않는다.

근거: [Free 가격](https://www.geoapify.com/pricing/), [API별 크레딧](https://www.geoapify.com/pricing-details/), [프로젝트 billing](https://myprojects.geoapify.com/help/billing/), [Places](https://apidocs.geoapify.com/docs/places/), [Geocoding](https://apidocs.geoapify.com/docs/geocoding/forward-geocoding/), [헤더 인증 안내](https://apidocs.geoapify.com/how-to/api-tooling-ai/generate-openapi-clients-sdks/).
