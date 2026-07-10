import pandas as pd, numpy as np, time
from xgboost import XGBRegressor
from sklearn.model_selection import GroupKFold
import warnings; warnings.filterwarnings("ignore")
rng = np.random.default_rng(2026)

M = pd.read_csv("fpp_train_matrix_v2.csv")
S = M[M["survived"]==1].reset_index(drop=True)
Xcols = [c for c in S.columns if c not in ("fbref_id","season","survived","fut_ability_v2")]
X, y, g = S[Xcols].astype(float), S["fut_ability_v2"].values, S["fbref_id"].values
B = 60

def fit_predict(Xtr, ytr, Xte, seed):
    m = XGBRegressor(n_estimators=150, max_depth=4, learning_rate=0.08,
                     subsample=0.8, colsample_bytree=0.8, tree_method="hist",
                     random_state=seed, n_jobs=-1)
    m.fit(Xtr, ytr, verbose=False)
    return m.predict(Xte)

gkf = GroupKFold(5)
rows = []
t0 = time.time()
fold_preds = []  # (te_idx, preds[B, n_te])
for fi,(tr, te) in enumerate(gkf.split(X, y, g)):
    gtr = g[tr]; players = np.unique(gtr)
    pl_idx = {p: np.where(gtr==p)[0] for p in players}
    preds = np.zeros((B, len(te)))
    for b in range(B):
        sel = rng.choice(players, size=len(players), replace=True)
        idx = np.concatenate([pl_idx[p] for p in sel])
        preds[b] = fit_predict(X.iloc[tr].iloc[idx], y[tr][idx], X.iloc[te], seed=b)
    fold_preds.append((te, preds))
    print(f"fold {fi+1}/5 완료 ({time.time()-t0:.0f}s)", flush=True)

# 잔차 sigma (전 폴드 out-of-fold)
resid = np.concatenate([y[te]-p.mean(axis=0) for te,p in fold_preds])
sig_r = resid.std()

z80, z50 = 1.2816, 0.6745
res = {"pure80":[], "pure50":[], "purew":[], "adj80":[], "adj50":[], "adjw":[]}
for te, preds in fold_preds:
    yt = y[te]
    lo80, hi80 = np.percentile(preds,[10,90],axis=0); lo50, hi50 = np.percentile(preds,[25,75],axis=0)
    res["pure80"].append(((yt>=lo80)&(yt<=hi80)).mean()); res["pure50"].append(((yt>=lo50)&(yt<=hi50)).mean())
    res["purew"].append((hi80-lo80).mean())
    mu, sm = preds.mean(axis=0), preds.std(axis=0)
    sig = np.sqrt(sm**2+sig_r**2)
    res["adj80"].append(((yt>=mu-z80*sig)&(yt<=mu+z80*sig)).mean()); res["adj50"].append(((yt>=mu-z50*sig)&(yt<=mu+z50*sig)).mean())
    res["adjw"].append((2*z80*sig).mean())

print(f"\n검증 잔차 sigma = {sig_r:.2f}")
print(f"[순수 부트스트랩]   80% 커버리지 {np.mean(res['pure80']):.1%} | 50% {np.mean(res['pure50']):.1%} | 평균 폭 {np.mean(res['purew']):.1f}점")
print(f"[잔차 결합 보정]    80% 커버리지 {np.mean(res['adj80']):.1%} | 50% {np.mean(res['adj50']):.1%} | 평균 폭 {np.mean(res['adjw']):.1f}점")
np.save("bootstrap_resid_sigma.npy", sig_r)
