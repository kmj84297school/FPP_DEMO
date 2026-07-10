FPP 학습용 피처 테이블 — 전처리 명세
=====================================
파일: fpp_features_2018_2023.csv
원천: worldfootballR 공개 아카이브 (FBref 빅5 리그 시즌 스탯)
      https://github.com/JaseZiv/worldfootballR_data
범위: Season_End_Year 2018~2023 (시즌 종료 연도 기준), 빅5 리그
규모: 15,522 선수-시즌 x 186열, 고유 선수 5,693명

[키]
- fbref_id: FBref 8자리 선수 ID (Url에서 추출) - 시즌 간 궤적 연결 키
- Season_End_Year: 시즌 종료 연도 (예: 2022-23 시즌 = 2023)

[병합 규칙]
1. 8개 카테고리(standard/shooting/passing/possession/gca/defense/misc/playing_time)를
   fbref_id + Season_End_Year 기준으로 병합. 접두어: std_/sho_/pas_/pos_/gca_/def_/msc_/pt_
2. 한 시즌 다중 팀(이적) 선수(전체의 4.1%) 처리:
   - 누적 스탯(골, 슈팅, 태클 등): 팀별 합산
   - 비율/평균 지표(성공률 %, per90, 평균 슈팅거리 등): 출전시간 가중평균
   - Squads/Comps 열에 소속팀 병기, n_clubs에 팀 수 기록
3. Mins_Per_90(=출전 90분 단위 수)은 누적 지표로 취급해 합산

[알려진 데이터 한계 - 반드시 인지]
1. 2023 시즌: FBref 데이터 제공사 교체(StatsBomb->Opta)로 일부 컬럼 사망
   - 압박(Pressures) 계열, 운반(Carries) 세부, 드리블 세부 등 (coverage_by_year.csv 참고)
   - 2023을 라벨 연도로만 쓰고 피처 연도로 쓰지 않으면 영향 최소화 가능
2. 골키퍼 전용 지표(keepers) 미포함 - GK 모델은 별도 구축 필요
3. 이 아카이브는 2023 시즌에서 갱신 중단 - 2024~2026 시즌은 Kaggle
   (hubertsidorowicz/football-players-stats 시리즈)로 보충 예정
4. 표본은 빅5 잔존 선수만 포함 - 빅5 이탈은 데이터에서 사라짐(생존편향).
   라벨 설계 시 '이탈'을 명시적 결과 범주로 처리할 것

[동반 파일]
- coverage_by_year.csv: 전체 피처 x 연도 커버리지 감사표

[정리 단계 추가 처리 (v2)]
- 카테고리 간 중복 컬럼 19개 제거 (출전시간류 반복, std와 겹치는 골/카드/xG 등)
- 컬럼명 정규화: 공백/특수문자를 snake_case로 (예: 'def_Def 3rd_Tackles' -> 'def_Def_3rd_Tackles', '%' -> pct)
- pos_primary(주 포지션), pos_multi(복수 포지션 여부) 파생
- GK 1,166행 분리 저장 (전용지표 부재로 별도 모델 대상): fpp_features_GK_2018_2023.csv
- 최종 필드플레이어 테이블: 14,356 선수-시즌 x 169열
- 키 중복 0건 확인
