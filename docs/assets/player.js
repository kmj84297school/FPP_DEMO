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

function renderNotFound() {
  document.getElementById("content").innerHTML = `<div class="empty-state">선수를 찾을 수 없습니다. (검색 대상은 2023시즌 600분 이상 출전 선수만 포함됩니다)</div>`;
}

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
  `;

  if (!p.eligibility.eligible_for_prediction) {
    const reasonMap = { over_age: "연령(23세 초과)", under_minutes: "출전시간(900분 미만)" };
    const reasons = (p.eligibility.reason || "").split(";").filter(Boolean).map((r) => reasonMap[r] || r).join(", ");
    html += `
      <div class="panel">
        <div class="note">예측 모델 적용 대상 아님 — 학습 코호트 기준(23세 이하, 900분 이상) 초과: ${reasons || "기준 미달"}.
        현재 능력 점수만 제공됩니다.</div>
      </div>`;
  } else {
    const pred = p.prediction;
    html += `
      <div class="grid-2">
        <div class="panel">
          <div class="section-title">2~3년 후 예측</div>
          <div class="stat-row"><span class="lbl">빅5 잔존확률</span><span>${(pred.survival_prob * 100).toFixed(1)}%</span></div>
          <div class="stat-row"><span class="lbl">예측 능력 (mu)</span><span class="badge ${bandcls(pred.mu)}">${fmt1(pred.mu)}</span></div>
          <div class="stat-row"><span class="lbl">80% 구간</span><span>${fmt1(pred.ci80.lo)} ~ ${fmt1(pred.ci80.hi)}</span></div>
          <div class="stat-row"><span class="lbl">50% 구간</span><span>${fmt1(pred.ci50.lo)} ~ ${fmt1(pred.ci50.hi)}</span></div>
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
  fetch(`data/players/${id}.json`)
    .then((r) => { if (!r.ok) throw new Error("not found"); return r.json(); })
    .then(renderPlayer)
    .catch(renderNotFound);
}
