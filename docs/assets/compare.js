const GROUP_LABELS = { prod: "생산", progress: "전진", chance: "찬스", stability: "안정", defense: "수비" };
const GROUP_ORDER = ["prod", "progress", "chance", "stability", "defense"];
const COLORS = { a: "#19ffa7", b: "#ffd700" };

let INDEX = [];
let META = null;
let charts = [];

function qs(name) { return new URLSearchParams(window.location.search).get(name); }
function setUrl(a, b) {
  const u = new URLSearchParams();
  if (a) u.set("a", a);
  if (b) u.set("b", b);
  history.replaceState(null, "", u.toString() ? `?${u}` : window.location.pathname);
}

function bindPicker(inputId, listId, slot) {
  const input = document.getElementById(inputId), list = document.getElementById(listId);
  input.addEventListener("input", () => {
    const q = asciiFold(input.value.trim());
    if (!q) { list.hidden = true; return; }
    const hits = INDEX.filter((p) => p.name_ascii.includes(q) || p.squad_ascii.includes(q)).slice(0, 12);
    list.innerHTML = hits.map((p) => `<li data-id="${p.fbref_id}" data-name="${p.name}">${p.name} <span class="muted small">· ${p.squad || "—"} · ${p.pos_primary} · ${fmt1(p.ability)}</span></li>`).join("");
    list.hidden = hits.length === 0;
  });
  list.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (!li) return;
    input.value = li.dataset.name; list.hidden = true;
    const cur = { a: qs("a"), b: qs("b") };
    cur[slot] = li.dataset.id;
    setUrl(cur.a, cur.b);
    load();
  });
  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 150));
}

function diffCell(a, b, higherBetter = true) {
  if (a === null || b === null || a === undefined || b === undefined) return `<td class="diff">—</td>`;
  const d = Math.round((a - b) * 10) / 10;
  const big = Math.abs(d) >= 10;
  const sign = d > 0 ? "+" : "";
  return `<td class="diff ${big ? "big" : ""}" aria-label="차이 ${sign}${d}">${sign}${d}${big ? " ●" : ""}</td>`;
}
function row(label, a, b, fmt = fmt1, higherBetter = true) {
  const va = a === null || a === undefined ? null : a, vb = b === null || b === undefined ? null : b;
  const winA = va !== null && vb !== null && (higherBetter ? va > vb : va < vb);
  const winB = va !== null && vb !== null && (higherBetter ? vb > va : vb < va);
  return `<tr><td>${label}</td><td class="${winA ? "win" : ""}">${fmt(va)}</td>${diffCell(va, vb)}<td class="${winB ? "win" : ""}">${fmt(vb)}</td></tr>`;
}
const pct = (v) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`);

function radar(canvasId, labels, dataA, dataB, nameA, nameB) {
  charts.push(new Chart(document.getElementById(canvasId), {
    type: "radar",
    data: { labels, datasets: [
      { label: nameA, data: dataA, backgroundColor: "rgba(25,255,167,0.15)", borderColor: COLORS.a, pointBackgroundColor: COLORS.a },
      { label: nameB, data: dataB, backgroundColor: "rgba(255,215,0,0.15)", borderColor: COLORS.b, pointBackgroundColor: COLORS.b },
    ] },
    options: { scales: { r: { min: 0, max: 100, ticks: { color: "#7e8a97", backdropColor: "transparent" }, grid: { color: "rgba(255,255,255,0.08)" }, angleLines: { color: "rgba(255,255,255,0.08)" }, pointLabels: { color: "#e9eef5" } } },
      plugins: { legend: { labels: { color: "#e9eef5" } } } },
  }));
}

function headCard(p, slot) {
  const m = p.meta, c = p.current, pr = p.prediction;
  return `
    <div class="panel cmp-card ${slot} reveal">
      ${avatarHtml(m.fbref_id, m.player_name, 60)}
      <div style="flex:1;min-width:0;">
        <h2><a href="player.html?id=${m.fbref_id}">${m.player_name}</a></h2>
        <div class="sub muted small">${flagChip(m.nation)} ${m.squad || "—"} · ${m.pos_primary}${m.role ? ` (${m.role.label})` : ""} · 만 ${m.age_years}세</div>
        <div style="margin-top:8px;">${orbitGaugeHtml(c.ability, pr ? pr.ci80.hi : null, { mu: pr ? pr.mu : null })}</div>
      </div>
    </div>`;
}

function render(A, B) {
  charts.forEach((ch) => ch.destroy()); charts = [];
  const nA = A.meta.player_name, nB = B.meta.player_name;
  const samePos = A.meta.pos_primary === B.meta.pos_primary;
  const pa = A.prediction, pb = B.prediction;
  const keysA = A.report.position_radar.map((s) => s.key);
  const radarKeys = samePos ? keysA : [];
  const mapA = Object.fromEntries(A.report.position_radar.map((s) => [s.key, s]));
  const mapB = Object.fromEntries(B.report.position_radar.map((s) => [s.key, s]));

  let html = `
    <div class="cmp-head">${headCard(A, "a")}<div class="vs-badge" aria-hidden="true">VS</div>${headCard(B, "b")}</div>
    <div class="grid-2">
      <div class="panel"><div class="section-title">능력 그룹 레이더 (겹침)</div><canvas id="cmpRadar" height="240"></canvas></div>
      <div class="panel"><div class="section-title">포지션 핵심 지표 퍼센타일${samePos ? "" : " — 포지션이 달라 겹치지 않음"}</div>
        ${samePos ? '<canvas id="cmpPosRadar" height="240"></canvas>' : '<div class="hint">같은 포지션 그룹끼리만 같은 지표 축을 씁니다. 아래 표에서 각자의 핵심 지표를 따로 확인하세요.</div>'}
      </div>
    </div>
    <div class="panel">
      <div class="section-title">항목별 비교 — 초록 = 우세, ● = 10점 이상 차이</div>
      <table class="cmp-table">
        <thead><tr><th>항목</th><th style="color:${COLORS.a}">${nA}</th><th>차이(A−B)</th><th style="color:${COLORS.b}">${nB}</th></tr></thead>
        <tbody>
          ${row("현재 능력", A.current.ability, B.current.ability)}
          ${row("포지션 렌즈", A.current.score_position, B.current.score_position)}
          ${row("스타일 렌즈", A.current.score_style, B.current.score_style)}
          ${GROUP_ORDER.map((k) => row(`${GROUP_LABELS[k]} 그룹`, A.current.groups[k], B.current.groups[k])).join("")}
          <tr><td>대표 스타일</td><td>${A.style.primary || "—"}</td><td class="diff"></td><td>${B.style.primary || "—"}</td></tr>
          ${samePos ? radarKeys.map((k) => row(mapA[k].label + " (pct)", mapA[k].percentile, mapB[k] ? mapB[k].percentile : null)).join("") : ""}
          <tr><td colspan="4" class="muted small" style="text-align:left;padding-top:12px;">2~3년 후 예측 (${pa ? (A.eligibility.kind === "growth" ? "성장기" : "성숙기") : "대상 아님"} / ${pb ? (B.eligibility.kind === "growth" ? "성장기" : "성숙기") : "대상 아님"} 모델)</td></tr>
          ${row("예측 중심값 (가장 가능성 높은 값)", pa ? pa.mu : null, pb ? pb.mu : null)}
          ${row("80% 구간 상단 (상위 10% 시나리오)", pa ? pa.ci80.hi : null, pb ? pb.ci80.hi : null)}
          ${row("80% 구간 하단", pa ? pa.ci80.lo : null, pb ? pb.ci80.lo : null)}
          ${row("빅5 잔존/유지 확률", pa ? pa.survival_prob : null, pb ? pb.survival_prob : null, pct)}
          ${A.eligibility.out_of_validated_range || B.eligibility.out_of_validated_range ? `<tr><td colspan="4" class="muted small" style="text-align:left;">※ ${[A, B].filter((p) => p.eligibility.out_of_validated_range).map((p) => p.meta.player_name).join(", ")}: 모델 검증 범위 밖(상세 페이지 참조)</td></tr>` : ""}
          ${!samePos ? `<tr><td colspan="4" class="muted small" style="text-align:left;padding-top:12px;">핵심 지표 (포지션별 축이 달라 각자 표시)</td></tr>
            <tr><td>${nA}</td><td colspan="3" style="text-align:left;">${A.report.position_radar.map((s) => `${s.label} ${s.percentile}`).join(" · ")}</td></tr>
            <tr><td>${nB}</td><td colspan="3" style="text-align:left;">${B.report.position_radar.map((s) => `${s.label} ${s.percentile}`).join(" · ")}</td></tr>` : ""}
        </tbody>
      </table>
      <div class="hint">퍼센타일은 같은 시즌·같은 포지션 풀(600분+) 내 순위입니다. 능력점수는 전 시즌 최고 복합점수를 100으로 재조정한 표시 스케일입니다.</div>
    </div>`;
  document.getElementById("content").innerHTML = html;
  if (window.FPPMotion) window.FPPMotion.observe();
  document.querySelectorAll(".cmp-table tbody tr").forEach((tr, i) => { tr.style.transitionDelay = `${Math.min(i, 20) * 40}ms`; });
  radar("cmpRadar", GROUP_ORDER.map((k) => GROUP_LABELS[k]), GROUP_ORDER.map((k) => A.current.groups[k] ?? 0), GROUP_ORDER.map((k) => B.current.groups[k] ?? 0), nA, nB);
  if (samePos) radar("cmpPosRadar", radarKeys.map((k) => mapA[k].label), radarKeys.map((k) => mapA[k].percentile), radarKeys.map((k) => (mapB[k] ? mapB[k].percentile : 0)), nA, nB);
}

function load() {
  const a = qs("a"), b = qs("b");
  const content = document.getElementById("content");
  if (!a || !b) {
    content.innerHTML = `<div class="empty-state">${a || b ? "한 명 더 선택하세요." : "두 선수를 선택하세요."}</div>`;
    return;
  }
  if (a === b) { content.innerHTML = '<div class="empty-state">같은 선수입니다. 다른 선수를 선택하세요.</div>'; return; }
  content.innerHTML = '<div class="empty-state">불러오는 중…</div>';
  Promise.all([a, b].map((id) => fetch(`data/players/${id}.json`).then((r) => { if (!r.ok) throw new Error(id); return r.json(); })))
    .then(([A, B]) => {
      document.getElementById("pickA").value = A.meta.player_name;
      document.getElementById("pickB").value = B.meta.player_name;
      cmpSet([{ id: a, name: A.meta.player_name }, { id: b, name: B.meta.player_name }]);
      render(A, B);
    })
    .catch((err) => { content.innerHTML = `<div class="empty-state">선수 데이터를 찾을 수 없습니다 (${err.message}).</div>`; });
}

Promise.all([fetch("data/index.json").then((r) => r.json()), fetch("data/meta.json").then((r) => r.json())])
  .then(([data, meta]) => {
    META = meta;
    INDEX = data.rows.map((r) => { const p = {}; data.cols.forEach((c, i) => { p[c] = r[i]; }); p.name_ascii = asciiFold(p.name); p.squad_ascii = asciiFold(p.squad || ""); return p; });
    bindPicker("pickA", "listA", "a"); bindPicker("pickB", "listB", "b");
    // 바구니에서 넘어온 경우
    if (!qs("a") && !qs("b")) { const c = cmpGet(); if (c.length === 2) setUrl(c[0].id, c[1].id); }
    load();
  });
