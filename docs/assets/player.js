const GROUP_LABELS = { prod: "생산", progress: "전진", chance: "찬스", stability: "안정", defense: "수비" };
const GROUP_ORDER = ["prod", "progress", "chance", "stability", "defense"];

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
          <div class="bar-track"><div class="bar-fill ${bandcls(v)}" style="width:${Math.max(0, Math.min(100, v))}%"></div></div>
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
        <div class="bar-track"><div class="bar-fill ${bandcls(it.percentile)}" style="width:${Math.max(0, Math.min(100, it.percentile))}%"></div></div>
        <span>${fmt1(it.percentile)}</span>
      </div>
    </div>`).join("");
}

function renderNotFound() {
  document.getElementById("content").innerHTML = `<div class="empty-state">선수를 찾을 수 없습니다. (검색 페이지에서 이름으로 찾아주세요 — 2023시즌 출전시간이 너무 적은 선수는 포함되지 않습니다)</div>`;
}

let META = null;

function renderPlayer(p) {
  const m = p.meta;
  const c = p.current;

  let html = `
    <div class="panel player-head">
      <div>
        <h1>${m.player_name}</h1>
        <div class="sub">${m.squad || "—"} · ${m.comps || "—"} · ${m.pos_primary} · ${m.nation || "—"} · 만 ${m.age_years}세 · 2023시즌 ${m.minutes_2023}분</div>
      </div>
      <span class="badge ${bandcls(c.ability)}" style="font-size:1.3rem;padding:8px 16px;">${fmt1(c.ability)}</span>
    </div>

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
        <div class="section-title">Top Strengths</div>
        ${metricBarsHtml(p.report.strengths)}
      </div>
      <div class="panel">
        <div class="section-title">Weaknesses (포지션 고려)</div>
        ${metricBarsHtml(p.report.weaknesses)}
      </div>
    </div>

    <div class="grid-2">
      <div class="panel">
        <div class="section-title">Playstyle Engine</div>
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
  `;

  if (!p.eligibility.eligible_for_prediction) {
    const reasonMap = {
      under_minutes: "출전시간 기준 미달",
      too_old_for_model: "검증된 모델의 연령 범위(38세) 밖 — 학습 표본이 너무 적어 신뢰할 수 없음",
      insufficient_data: "핵심 스탯 데이터 결측으로 현재 능력 자체를 계산할 수 없음",
    };
    const reasonText = reasonMap[p.eligibility.reason] || "기준 미달";
    html += `
      <div class="panel">
        <div class="note">예측 모델 적용 대상 아님 — ${reasonText}. 현재 능력 점수만 제공됩니다.</div>
      </div>`;
  } else {
    const pred = p.prediction;
    const isGrowth = p.eligibility.kind === "growth";
    const sectionTitle = isGrowth ? "2~3년 후 성장 예측" : "2~3년 후 전성기 유지 예측";
    const survivalLabel = isGrowth ? "빅5 잔존확률" : "빅5 현역 유지확률";
    const regressionNote = isGrowth
      ? `예측 중심값(mu)이 현재능력보다 낮은 건 평균회귀 때문입니다 — 실제 데이터에서도 현재능력 상위권 선수 상당수가 2~3년 후 다소 낮아지는 경향이 있습니다. 80% 구간(${fmt1(pred.ci80.lo)}~${fmt1(pred.ci80.hi)})에 현재능력(${fmt1(c.ability)})이 포함된다면, 유지 가능성도 충분히 열려 있다는 뜻입니다.`
      : `예측 중심값(mu)이 현재능력보다 낮은 건 나이에 따른 자연스러운 기량 변화가 반영된 결과입니다. 이 전성기 유지 모델은 검증 결과 성장 예측 모델보다 정확도가 더 높습니다(MAE ${META && META.veteran ? META.veteran.mae : "?"} vs ${META ? META.u23_mae : "?"}, GroupKFold 5겹).`;
    html += `
      <div class="grid-2">
        <div class="panel">
          <div class="section-title">${sectionTitle}</div>
          <div class="stat-row" style="padding:12px 0;">
            <span class="lbl">잠재력 상한 (80% 구간 상단)</span>
            <span class="badge ${bandcls(pred.ci80.hi)}" style="font-size:1.15rem;padding:6px 14px;">${fmt1(pred.ci80.hi)}</span>
          </div>
          <div class="stat-row"><span class="lbl">${survivalLabel}</span><span>${(pred.survival_prob * 100).toFixed(1)}%</span></div>
          <div class="stat-row"><span class="lbl">예측 중심값 (mu)</span><span>${fmt1(pred.mu)}</span></div>
          <div class="stat-row"><span class="lbl">80% 구간</span><span>${fmt1(pred.ci80.lo)} ~ ${fmt1(pred.ci80.hi)}</span></div>
          <div class="stat-row"><span class="lbl">50% 구간</span><span>${fmt1(pred.ci50.lo)} ~ ${fmt1(pred.ci50.hi)}</span></div>
          ${pred.mu < c.ability ? `<div class="hint" style="margin-top:10px;">${regressionNote}</div>` : ""}
          ${p.low_confidence ? '<div class="note" style="margin-top:10px;">유사 선수와의 거리가 멀어 비교 신뢰도가 낮습니다 (아웃라이어 가능성).</div>' : ""}
        </div>
        <div class="panel">
          <div class="section-title">현재 vs 예측 구간</div>
          <canvas id="ciChart" height="140"></canvas>
        </div>
      </div>

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
    `;
  }

  if (p.narrative.current || p.narrative.potential) {
    html += `
      <div class="panel">
        <div class="section-title">Narrative Report</div>
        ${p.narrative.current ? `<p>${p.narrative.current}</p>` : ""}
        ${p.narrative.potential ? `<p>${p.narrative.potential}</p>` : ""}
      </div>
    `;
  }

  if (p.report.coaching.length || p.report.roadmap.length) {
    html += `
      <div class="grid-2">
        <div class="panel">
          <div class="section-title">Coaching 추천</div>
          <div class="hint" style="margin-bottom:8px;">규칙 기반 제안입니다 — 검증된 예측이 아니라, 현재 퍼센타일을 근거로 한 참고용 훈련 방향입니다.</div>
          <ul style="margin:0;padding-left:18px;">
            ${p.report.coaching.map((t) => `<li style="margin-bottom:6px;">${t}</li>`).join("")}
          </ul>
        </div>
        <div class="panel">
          <div class="section-title">Growth Roadmap</div>
          ${p.report.roadmap.map((r) => `
            <div class="stat-row" style="align-items:flex-start;">
              <span class="lbl">${r.phase}</span>
              <span>${r.focus}<br><span class="muted">${r.kpi}</span></span>
            </div>`).join("")}
        </div>
      </div>
    `;
  }

  document.getElementById("content").innerHTML = html;

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
          grid: { color: "#232a33" },
          angleLines: { color: "#232a33" },
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
            grid: { color: "#232a33" },
            angleLines: { color: "#232a33" },
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
        labels: ["잠재력 구간"],
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
          x: { min: 0, max: 100, ticks: { color: "#7e8a97" }, grid: { color: "#232a33" } },
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
