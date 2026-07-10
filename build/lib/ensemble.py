"""src/boot_ci.py의 부트스트랩 앙상블 학습 로직을 재사용 가능한 함수로 추출.

원본은 GroupKFold 검증(폭 밖 커버리지 실측)이 목적이었지만, 서빙용 빌드에서는
검증이 아니라 '신뢰구간 폭 추정'이 목적이므로 전체 생존 코호트로 B개 모델을
한 번 학습해 앙상블을 만든다. sigma_residual(7.49)은 원본 검증에서 이미
산출된 models/bootstrap_resid_sigma.npy를 그대로 재사용한다.
"""
import numpy as np
from xgboost import XGBRegressor

DEFAULT_PARAMS = dict(
    n_estimators=150, max_depth=4, learning_rate=0.08,
    subsample=0.8, colsample_bytree=0.8, tree_method="hist", n_jobs=-1,
)


def fit_ensemble(X, y, groups, B=60, seed=2026, params=None):
    """선수 단위 클러스터 복원추출로 B개 부트스트랩 회귀모델 학습."""
    params = {**DEFAULT_PARAMS, **(params or {})}
    rng = np.random.default_rng(seed)
    players = np.unique(groups)
    pl_idx = {p: np.where(groups == p)[0] for p in players}

    models = []
    for b in range(B):
        sel = rng.choice(players, size=len(players), replace=True)
        idx = np.concatenate([pl_idx[p] for p in sel])
        m = XGBRegressor(random_state=seed + b, **params)
        m.fit(X.iloc[idx], y[idx])
        models.append(m)
    return models


def predict_ensemble(models, X):
    """앙상블 예측 평균/표준편차 (sigma_model)."""
    preds = np.stack([m.predict(X) for m in models], axis=0)
    return preds.mean(axis=0), preds.std(axis=0)
