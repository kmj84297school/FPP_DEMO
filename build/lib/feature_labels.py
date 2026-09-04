"""모델 피처(51개) → 화면용 한국어 라벨. A5 설명 패널과 자동 서술문이 공유한다."""
FEATURE_LABELS = {
    "age_y": "나이", "std_Min_Playing": "시즌 출전시간(분)",
    "grp_prod": "생산 그룹 점수", "grp_progress": "전진 그룹 점수", "grp_chance": "찬스 그룹 점수",
    "grp_stability": "안정 그룹 점수", "grp_defense": "수비 그룹 점수",
    "score_position": "포지션 렌즈 점수", "score_style": "스타일 렌즈 점수", "ability": "현재 능력",
    "style_confidence": "스타일 확신도",
    "npxG90": "비페널티 xG/90", "xAG90": "xAG/90", "SCA90": "슈팅 창출/90", "PrgPass90": "전진 패스/90",
    "PrgCarry90": "전진 운반/90", "TakeOn90": "성공 드리블/90", "TklInt90": "태클+인터셉트/90",
    "AttPenT90": "박스 터치/90", "KP90": "키패스/90", "PassPct": "패스 성공률", "AerPct": "공중볼 승률",
    "MinPct": "팀 출전시간 비중(%)",
    "has_prev": "직전 시즌 이력 보유", "d_ability": "능력 변화(전 시즌 대비)",
    "d_grp_prod": "생산 그룹 변화", "d_grp_progress": "전진 그룹 변화", "d_grp_chance": "찬스 그룹 변화",
    "d_grp_stability": "안정 그룹 변화", "d_grp_defense": "수비 그룹 변화",
    "d_npxG90": "npxG/90 변화", "d_xAG90": "xAG/90 변화", "d_SCA90": "SCA/90 변화",
    "d_PrgCarry90": "전진 운반/90 변화", "d_PrgPass90": "전진 패스/90 변화",
    "d_MinPct": "출전시간 비중 변화", "d_std_Min_Playing": "출전시간 변화(분)",
    "pos_DF": "포지션: DF", "pos_FW": "포지션: FW", "pos_MF": "포지션: MF",
    # A4 보강 피처
    "squad_mean_ability": "소속팀 평균 능력(팀 강도)", "ability_vs_squad": "팀 평균 대비 본인 능력",
    "squad_rank_in_league": "팀 강도 리그 내 순위(0=최강)", "starts_share": "선발 비율",
    "n_squads": "시즌 내 소속팀 수", "has_prev2": "2시즌 전 이력 보유", "min_prev2": "2시즌 전 출전시간(분)",
    "min_trend2": "2년 출전시간 추세(분)",
    "lg_Premier League": "리그: 프리미어리그", "lg_La Liga": "리그: 라리가", "lg_Serie A": "리그: 세리에A",
    "lg_Bundesliga": "리그: 분데스리가", "lg_Ligue 1": "리그: 리그1",
}
for _s in ("공격형 MF", "공격형 풀백", "돌파형 윙어", "딥 플레이메이커", "박스 포처", "볼 운반형",
           "빌드업 수비수", "수비형 파괴자", "스토퍼", "연결형 공격수", "타겟맨"):
    FEATURE_LABELS[f"sty_{_s}"] = f"스타일: {_s}"

# 값 표시 규칙: one-hot/플래그는 값 대신 "예/아니오", 나머지는 소수 1자리
FLAG_FEATURES = {"has_prev", "has_prev2"} | {k for k in FEATURE_LABELS if k.startswith(("pos_", "sty_", "lg_"))}
# 표시 스케일(SCALE)로 재조정해야 하는 값 — 능력 복합점수 계열
COMPOSITE_VALUE_FEATURES = {"ability", "score_position", "score_style", "d_ability", "squad_mean_ability", "ability_vs_squad"}


def feature_label(k):
    return FEATURE_LABELS.get(k, k)
