const GROUP_LABELS = { prod: "생산", progress: "전진", chance: "찬스", stability: "안정", defense: "수비" };
const GROUP_ORDER = ["prod", "progress", "chance", "stability", "defense"];

function contribRow(t) {
  const pos = t.contrib >= 0;
  return `
    <div class="contrib-row" role="listitem">
      <span class="contrib-lbl">${t.label}${t.value_text ? ` <span class="muted">= ${t.value_text}</span>` : ""}</span>
      <span class="contrib-bar ${pos ? "pos" : "neg"}" aria-hidden="true">
        <span class="contrib-fill" style="--w:${Math.min(100, Math.abs(t.contrib) / t._max * 100)}%"></span>
      </span>
      <span class="contrib-val ${pos ? "pos" : "neg"}">${pos ? "▲" : "▼"} ${t.contrib > 0 ? "+" : ""}${t.contrib.toFixed(2)}</span>
    </div>`;
}

function explanationHtml(p, c) {
  const e = p.explanation;
  const d = e.delta, sv = e.survival;
  const isGrowth = p.eligibility.kind === "growth";
  const survivalLabel = isGrowth ? "빅5 잔존확률" : "빅5 현역 유지확률";
  const dmax = Math.max(...d.top.map((t) => Math.abs(t.contrib)), Math.abs(d.rest), 0.01);
  const smax = Math.max(...sv.top.map((t) => Math.abs(t.contrib)), Math.abs(sv.rest), 0.01);
  const dtop = d.top.map((t) => ({ ...t, _max: dmax }));
  const stop = sv.top.map((t) => ({ ...t, _max: smax }));
  const restD = { label: "나머지 46개 피처 합", value_text: "", contrib: d.rest, _max: dmax };
  const restS = { label: "나머지 46개 피처 합", value_text: "", contrib: sv.rest, _max: smax };
  const deltaPred = p.prediction.mu - c.ability;
  return `
    <div class="panel explain">
      <div class="section-title">왜 이 예측인가 — 피처 기여도 (SHAP)</div>
      <div class="explain-flow">
        <span class="chip green">현재 ${fmt1(c.ability)}</span><span class="arrow">→</span>
        <span class="chip muted-chip">코호트 평균 변화 ${d.base >= 0 ? "+" : ""}${d.base.toFixed(1)}</span><span class="arrow">→</span>
        <span class="chip muted-chip">기여도 합 ${(d.total - d.base) >= 0 ? "+" : ""}${(d.total - d.base).toFixed(1)}</span><span class="arrow">→</span>
        <span class="chip gold">예측 중심값 ${fmt1(p.prediction.mu)} (${deltaPred >= 0 ? "+" : ""}${deltaPred.toFixed(1)})</span>
      </div>
      <div class="grid-2">
        <div>
          <div class="explain-sub">2~3년 후 변화량(점)에 대한 기여 — 상위 5개</div>
          <div role="list">${dtop.map(contribRow).join("")}${contribRow(restD)}</div>
        </div>
        <div>
          <div class="explain-sub">${survivalLabel}(로그오즈)에 대한 기여 — 코호트 기준 ${(sv.base_prob * 100).toFixed(0)}% → ${(sv.prob * 100).toFixed(1)}%</div>
          <div role="list">${stop.map(contribRow).join("")}${contribRow(restS)}</div>
        </div>
      </div>
      <div class="hint">${e.method}. 기여도는 이 선수 한 명에 대한 모델의 국소 설명이며 인과관계가 아닙니다. 같은 피처라도 다른 선수에게는 반대 방향으로 기여할 수 있습니다.</div>
    </div>`;
}

function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}

function groupBarsHtml(groups) {
  return GROUP_ORDER.map((k) => {
    const v = groups[k] ?? 0;
    return `
      <div class="stat-row">
        <span class="lbl">${GROUP_LABELS[k]}</span>
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="bar-track"><div class="bar-fill ${bandcls(v)}" style="--w:${Math.max(0, Math.min(100, v))}%"></div></div>
          <span>${fmt1(v)}</span>
        </div>
      </div>`;
  }).join("");
}

function metricBarsHtml(items) {
  if (!items || items.length === 0) return '<div class="hint">표시할 항목이 없습니다.</div>';
  return items.map((it) => `
    <div class="stat-row">
      <span class="lbl">${it.label}</span>
      <div style="display:flex;align-items:center;gap:10px;">
        <div class="bar-track"><div class="bar-fill ${bandcls(it.percentile)}" style="--w:${Math.max(0, Math.min(100, it.percentile))}%"></div></div>
        <span>${fmt1(it.percentile)}</span>
      </div>
    </div>`).join("");
}

function renderNotFound() {
  document.getElementById("content").innerHTML = `<div class="empty-state">선수를 찾을 수 없습니다. (검색 페이지에서 이름으로 찾아주세요 — 시즌 출전시간이 너무 적은 선수는 포함되지 않습니다)</div>`;
}

let META = null;

// 아바타(FBref 헤드샷 핫링크 + 이니셜 폴백)·등급 텍스트·비교 바구니는 common.js 공용.

function topBandText(isGrowth) {
  const tb = META && META.top_band ? META.top_band[isGrowth ? "u23" : "veteran"] : null;
  if (!tb) return "이 구간은 검증 표본이 매우 적어 오차 수치의 신뢰도가 낮습니다.";
  const sign = tb.bias > 0 ? "+" : "";
  return `이 구간은 검증 표본이 적어(현재능력 ${tb.threshold_display}+ 기준 ${tb.n}명, 폴드 밖) 오차 수치의 신뢰도가 낮습니다. 그 표본에서 실측된 MAE는 ${tb.mae}, 편향은 ${sign}${tb.bias}점(${tb.bias > 0 ? "약간 낙관" : "약간 비관"}), 80% 구간 커버리지는 ${(tb.ci80_coverage * 100).toFixed(0)}%입니다.`;
}

function renderPlayer(p) {
  const m = p.meta;
  const c = p.current;

  const pred = p.prediction;
  const kind = p.eligibility.kind;
  const stamps = [];
  if (kind === "growth") stamps.push('<span class="stamp growth">성장기 모델</span>');
  if (kind === "peak") stamps.push('<span class="stamp peak">성숙기 모델</span>');
  if (!kind) stamps.push('<span class="stamp none">예측 대상 아님</span>');
  if (p.eligibility.out_of_validated_range) stamps.push('<span class="stamp warn" title="현재 능력이 학습 라벨 상위 1%를 넘어 검증 표본이 적음">검증 범위 밖</span>');
  if (p.low_confidence) stamps.push('<span class="stamp low" title="유사 선수와의 거리가 멀어 비교 신뢰도가 낮음">비교 신뢰도 낮음</span>');

  let html = `
    <div class="panel player-hero reveal">
      ${avatarHtml(m.fbref_id, m.player_name, 112)}
      <div>
        <h1>${m.player_name}</h1>
        <div class="sub">${flagChip(m.nation)} ${m.squad || "—"} · ${m.comps || "—"}<br>${m.pos_primary}${m.role ? ` · ${m.role.label}${m.role.borderline ? "(경계)" : ""}` : ""} · 만 ${m.age_years}세 · 2024-25시즌 ${m.minutes_season}분 · ${p.style.primary || "스타일 미판정"}</div>
        <div class="stamps">${stamps.join("")}</div>
        <div style="margin-top:12px;max-width:360px;">${orbitGaugeHtml(c.ability, pred ? pred.ci80.hi : null)}</div>
      </div>
      <div class="head-right">
        <div class="rings">
          ${ringHtml(c.ability, "현재", "g", "현재 능력 (같은 포지션 내 상대 순위 기반)")}
          ${pred ? ringHtml(pred.ci80.hi, "2~3년 후 상한", "y", "2~3년 후 능력의 80% 신뢰구간 상단 (상위 10% 시나리오)") : ""}
        </div>
        <button type="button" class="btn-mini" data-cmp-id="${m.fbref_id}" data-cmp-name="${m.player_name}" aria-pressed="false">비교에 추가</button>
      </div>
    </div>

    <nav class="section-tabs" aria-label="섹션">
      <a href="#sec-ability" class="active">능력</a>
      <a href="#sec-style">스타일</a>
      ${p.qualitative ? '<a href="#sec-signal">정성 시그널</a>' : ""}
      <a href="#sec-predict">예측</a>
      ${pred && p.explanation ? '<a href="#sec-why">왜 이 예측인가</a>' : ""}
      ${pred ? '<a href="#sec-neighbors">유사 선수</a>' : ""}
      <a href="#sec-report">리포트</a>
    </nav>

    <section class="sec" id="sec-ability">
    <div class="grid-2">
      <div class="panel">
        <div class="section-title">현재 능력 (포지션 렌즈 ${fmt1(c.score_position)} / 스타일 렌즈 ${fmt1(c.score_style)})</div>
        ${groupBarsHtml(c.groups)}
        <div class="stat-row" style="margin-top:8px;">
          <span class="lbl">스타일</span>
          <span class="badge tag small">${p.style.primary || "—"} (확신도 ${fmt1(p.style.confidence)})</span>
        </div>
      </div>
      <div class="panel">
        <div class="section-title">능력 그룹 레이더</div>
        <canvas id="radarChart" height="220"></canvas>
      </div>
    </div>

    <div class="grid-2">
      <div class="panel">
        <div class="section-title">강점 Top</div>
        ${metricBarsHtml(p.report.strengths)}
      </div>
      <div class="panel">
        <div class="section-title">약점 (포지션 고려)</div>
        ${metricBarsHtml(p.report.weaknesses)}
      </div>
    </div>

    </section>
    <section class="sec" id="sec-style">
    <div class="grid-2">
      <div class="panel">
        <div class="section-title">플레이스타일 엔진</div>
        <div class="stat-row"><span class="lbl">대표 스타일</span><span class="badge tag small">${p.style.primary || "—"}</span></div>
        <div class="stat-row" style="align-items:flex-start;">
          <span class="lbl">Top 3 후보</span>
          <span>${p.report.top3_styles.map((s) => `${s.style} (z=${s.fit_z})`).join(" · ") || "—"}</span>
        </div>
        ${p.report.style_evidence.top.length ? `<div class="stat-row" style="align-items:flex-start;"><span class="lbl">판단 근거</span><span>${p.report.style_evidence.top.map((e) => `${e.label}(z=${e.z})`).join(", ")}</span></div>` : ""}
        ${p.report.style_evidence.bottom.length ? `<div class="stat-row" style="align-items:flex-start;"><span class="lbl">개선 필요</span><span>${p.report.style_evidence.bottom.map((e) => `${e.label}(z=${e.z})`).join(", ")}</span></div>` : ""}
      </div>
      <div class="panel">
        <div class="section-title">포지션 핵심지표 레이더</div>
        <canvas id="positionRadarChart" height="220"></canvas>
      </div>
    </div>
    </section>
  `;

  if (p.qualitative) {
    const q = p.qualitative;
    const consStd = q.consistency.ability_std;
    const consTxt = consStd === null ? "—"
      : consStd <= 3 ? `매우 꾸준 (시즌 간 ±${consStd})`
      : consStd <= 6 ? `보통 (시즌 간 ±${consStd})`
      : `기복 있음 (시즌 간 ±${consStd})`;
    html += `
      <section class="sec" id="sec-signal">
      <div class="panel">
        <div class="section-title">정성 시그널 (경기 기록 기반)</div>
        <div class="grid-2">
          <div>
            <div class="stat-row"><span class="lbl">경고 (per90)</span><span>${q.discipline.yellows_per90 ?? "—"}</span></div>
            <div class="stat-row"><span class="lbl">파울 (per90)</span><span>${q.discipline.fouls_per90 ?? "—"}</span></div>
            <div class="stat-row"><span class="lbl">퇴장 (2024-25시즌)</span><span>${q.discipline.reds_total_season ?? 0}회</span></div>
            <div class="stat-row"><span class="lbl">클린플레이 지수 (카드)</span><span class="badge ${bandcls(q.discipline.clean_pctl_cards)}">${fmt1(q.discipline.clean_pctl_cards)}</span></div>
            <div class="stat-row"><span class="lbl">클린플레이 지수 (파울)</span><span class="badge ${bandcls(q.discipline.clean_pctl_fouls)}">${fmt1(q.discipline.clean_pctl_fouls)}</span></div>
          </div>
          <div>
            <div class="stat-row"><span class="lbl">평균 팀 출전시간 점유율</span><span class="badge ${bandcls(q.availability.minpct_mean)}">${fmt1(q.availability.minpct_mean)}%</span></div>
            <div class="stat-row"><span class="lbl">관측 시즌 수</span><span>${q.availability.n_seasons}시즌</span></div>
            <div class="stat-row"><span class="lbl">꾸준함</span><span>${consTxt}</span></div>
          </div>
        </div>
        <div class="hint" style="margin-top:10px;">
          이 항목은 경기 기록에서 측정 가능한 대리 지표만 표시합니다. 클린플레이 지수는 같은 포지션 대비
          경고·파울이 적을수록 높습니다(높을수록 클린). 출전시간 점유율은 부상 빈도의 간접 지표이지만
          로테이션·이적과 부상을 구분하지 못하며, 실제 부상 기록·언론 평판·구단 내부 태도는 이 데이터셋에
          존재하지 않아 측정하지 않습니다.
        </div>
      </div>
      </section>
    `;
  }
  html += '<section class="sec" id="sec-predict">';

  if (!p.eligibility.eligible_for_prediction) {
    const reasonMap = {
      under_minutes: "출전시간 기준 미달",
      too_old_for_model: "검증된 모델의 연령 범위(38세) 밖 — 학습 표본이 너무 적어 신뢰할 수 없음",
      insufficient_data: "핵심 스탯 데이터 결측으로 현재 능력 자체를 계산할 수 없음",
    };
    const reasonText = reasonMap[p.eligibility.reason] || "기준 미달";
    html += `
      <div class="panel">
        <div class="section-title">2~3년 후 능력 예측</div>
        <div class="note">예측 모델 적용 대상 아님 — ${reasonText}. 현재 능력 점수만 제공됩니다.</div>
      </div>
      </section>`;
  } else {
    const isGrowth = p.eligibility.kind === "growth";
    const oor = p.eligibility.out_of_validated_range;
    const sectionTitle = isGrowth ? "2~3년 후 능력 예측 (성장기 모델)" : "2~3년 후 능력 예측 (성숙기 모델)";
    const survivalLabel = isGrowth ? "빅5 잔존확률" : "빅5 현역 유지확률";
    const regressionNote = isGrowth
      ? `예측 중심값(mu)이 현재능력보다 낮은 건 평균회귀 때문입니다 — 실제 데이터에서도 현재능력 상위권 선수 상당수가 2~3년 후 다소 낮아지는 경향이 있습니다. 80% 구간(${fmt1(pred.ci80.lo)}~${fmt1(pred.ci80.hi)})에 현재능력(${fmt1(c.ability)})이 포함된다면, 유지 가능성도 충분히 열려 있다는 뜻입니다.`
      : `예측 중심값(mu)이 현재능력보다 낮은 건 나이에 따른 자연스러운 기량 변화가 반영된 결과입니다. 이 전성기 유지 모델은 검증 결과 성장 예측 모델보다 정확도가 더 높습니다(MAE ${META && META.veteran ? META.veteran.mae : "?"} vs ${META ? META.u23_mae : "?"}, GroupKFold 5겹).`;
    html += `
      <div class="grid-2">
        <div class="panel">
          <div class="section-title">${sectionTitle}</div>
          <div class="stat-row" style="padding:12px 0;">
            <span class="lbl">2~3년 후 상한 (80% 구간 상단)</span>
            ${scoreBadge(pred.ci80.hi, "2~3년 후 상한", "show-tier")}
          </div>
          <div class="stat-row"><span class="lbl">${survivalLabel}</span><span>${(pred.survival_prob * 100).toFixed(1)}%</span></div>
          <div class="stat-row"><span class="lbl">예측 중심값 (mu)</span><span>${fmt1(pred.mu)}</span></div>
          <div class="stat-row"><span class="lbl">80% 구간</span><span>${fmt1(pred.ci80.lo)} ~ ${fmt1(pred.ci80.hi)}</span></div>
          <div class="stat-row"><span class="lbl">50% 구간</span><span>${fmt1(pred.ci50.lo)} ~ ${fmt1(pred.ci50.hi)}</span></div>
          ${oor ? `<div class="note" style="margin-top:10px;">모델 검증 범위 밖입니다 — 이 선수의 현재 능력(${fmt1(c.ability)})은 학습 데이터에서 관측된 2~3년 후 능력의 상위 1%를 넘습니다. ${topBandText(isGrowth)} 점추정과 함께 <b>유사 선수의 실제 결과</b>를 참고하세요.</div>` : ""}
          ${!oor && pred.mu < c.ability ? `<div class="hint" style="margin-top:10px;">${regressionNote}</div>` : ""}
          ${p.low_confidence ? '<div class="note" style="margin-top:10px;">유사 선수와의 거리가 멀어 비교 신뢰도가 낮습니다 (아웃라이어 가능성).</div>' : ""}
        </div>
        <div class="panel">
          <div class="section-title">현재 vs 예측 구간</div>
          <canvas id="ciChart" height="140"></canvas>
        </div>
      </div>

      </section>
      ${p.explanation ? `<section class="sec" id="sec-why">${explanationHtml(p, c)}</section>` : ""}

      <section class="sec" id="sec-neighbors">
      <div class="panel">
        <div class="section-title">유사 선수 (실제 2~3년 후 결과, k=${p.neighbors.length})</div>
        <table class="neighbors">
          <thead><tr><th>이름</th><th>클럽</th><th>시즌</th><th>당시 거리</th><th>빅5 잔존</th><th>실제 미래능력</th></tr></thead>
          <tbody>
            ${p.neighbors.map((n) => `
              <tr>
                <td>${n.player_name || n.fbref_id}</td>
                <td class="muted">${n.squad || "—"}</td>
                <td class="muted">${n.season}</td>
                <td class="muted">${n.distance}</td>
                <td class="muted">${n.survived ? "생존" : "이탈"}</td>
                <td>${n.fut_ability_v2 ?? "—"}</td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>
      </section>
    `;
  }

  html += '<section class="sec" id="sec-report">';
  if (p.narrative.current || p.narrative.potential) {
    html += `
      <div class="panel">
        <div class="section-title">서술 리포트</div>
        ${p.narrative.current ? `<p>${p.narrative.current}</p>` : ""}
        ${p.narrative.potential ? `<p>${p.narrative.potential}</p>` : ""}
      </div>
    `;
  }

  if (p.report.coaching.length || p.report.roadmap.length) {
    html += `
      <div class="grid-2">
        <div class="panel">
          <div class="section-title">코칭 제안</div>
          <div class="hint" style="margin-bottom:8px;">규칙 기반 제안입니다 — 검증된 예측이 아니라, 현재 퍼센타일을 근거로 한 참고용 훈련 방향입니다.</div>
          <ul style="margin:0;padding-left:18px;">
            ${p.report.coaching.map((t) => `<li style="margin-bottom:6px;">${t}</li>`).join("")}
          </ul>
        </div>
        <div class="panel">
          <div class="section-title">성장 로드맵</div>
          ${p.report.roadmap.map((r) => `
            <div class="stat-row" style="align-items:flex-start;">
              <span class="lbl">${r.phase}</span>
              <span>${r.focus}<br><span class="muted">${r.kpi}</span></span>
            </div>`).join("")}
        </div>
      </div>
    `;
  }

  html += "</section>";
  document.getElementById("content").innerHTML = html;
  renderCompareBar();
  if (window.FPPMotion) { window.FPPMotion.observe(); window.FPPMotion.rings(); window.FPPMotion.spy(); }

  new Chart(document.getElementById("radarChart"), {
    type: "radar",
    data: {
      labels: GROUP_ORDER.map((k) => GROUP_LABELS[k]),
      datasets: [{
        label: "능력 그룹 점수",
        data: GROUP_ORDER.map((k) => c.groups[k] ?? 0),
        backgroundColor: "rgba(0,255,133,0.18)",
        borderColor: "#19ffa7",
        pointBackgroundColor: "#19ffa7",
      }],
    },
    options: {
      scales: {
        r: {
          min: 0, max: 100,
          ticks: { color: "#7e8a97", backdropColor: "transparent" },
          grid: { color: "rgba(255,255,255,0.08)" },
          angleLines: { color: "rgba(255,255,255,0.08)" },
          pointLabels: { color: "#e9eef5" },
        },
      },
      plugins: { legend: { display: false } },
    },
  });

  const posRadarEl = document.getElementById("positionRadarChart");
  if (posRadarEl && p.report.position_radar.length) {
    new Chart(posRadarEl, {
      type: "radar",
      data: {
        labels: p.report.position_radar.map((s) => s.label),
        datasets: [{
          label: "포지션 핵심지표 퍼센타일",
          data: p.report.position_radar.map((s) => s.percentile),
          backgroundColor: "rgba(255,215,0,0.15)",
          borderColor: "#ffd700",
          pointBackgroundColor: "#ffd700",
        }],
      },
      options: {
        scales: {
          r: {
            min: 0, max: 100,
            ticks: { color: "#7e8a97", backdropColor: "transparent" },
            grid: { color: "rgba(255,255,255,0.08)" },
            angleLines: { color: "rgba(255,255,255,0.08)" },
            pointLabels: { color: "#e9eef5", font: { size: 10 } },
          },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  if (p.eligibility.eligible_for_prediction) {
    const pred = p.prediction;
    new Chart(document.getElementById("ciChart"), {
      data: {
        labels: ["2~3년 후 구간"],
        datasets: [
          {
            type: "bar", label: "80% 구간",
            data: [[pred.ci80.lo, pred.ci80.hi]],
            backgroundColor: "rgba(255,215,0,0.25)",
            borderColor: "rgba(255,215,0,0.6)", borderWidth: 1,
            barThickness: 28, borderSkipped: false,
          },
          {
            type: "bar", label: "50% 구간",
            data: [[pred.ci50.lo, pred.ci50.hi]],
            backgroundColor: "rgba(255,215,0,0.55)",
            borderColor: "#ffd700", borderWidth: 1,
            barThickness: 28, borderSkipped: false,
          },
          {
            type: "scatter", label: "예측(mu)",
            data: [{ x: pred.mu, y: 0 }],
            backgroundColor: "#ffd700", pointRadius: 6, pointStyle: "rectRot",
          },
          {
            type: "scatter", label: "현재 능력",
            data: [{ x: c.ability, y: 0 }],
            backgroundColor: "#19ffa7", pointRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        scales: {
          x: { min: 0, max: 100, ticks: { color: "#7e8a97" }, grid: { color: "rgba(255,255,255,0.08)" } },
          y: { ticks: { color: "#e9eef5" }, grid: { display: false } },
        },
        plugins: { legend: { labels: { color: "#e9eef5" } } },
      },
    });
  }
}

const id = qs("id");
if (!id) {
  renderNotFound();
} else {
  const metaFetch = fetch("data/meta.json").then((r) => r.json()).catch(() => null);
  const playerFetch = fetch(`data/players/${id}.json`).then((r) => {
    if (!r.ok) throw new Error("not found");
    return r.json();
  });
  Promise.all([metaFetch, playerFetch])
    .then(([meta, player]) => {
      META = meta;
      renderPlayer(player);
    })
    .catch(renderNotFound);
}
