const MAX_ROWS = 200;
const HIGHLIGHT_ROWS = 5;

const SORT_MODES = {
  ability: { label: "현재능력순", key: "ability", col: "현재능력", requiresEligible: false },
  ceiling: { label: "2~3년 후 상한순", key: "ceiling", col: "2~3년 후 상한(80%)", requiresEligible: true },
  headroom: { label: "상승 여력순", key: "headroom", col: "상승 여력", requiresEligible: true },
};
const SORT_HINTS = {
  ability: "",
  ceiling: "예측 대상만 표시됩니다. 80% 신뢰구간의 상단값이며, 실제 계산된 구간입니다(임의로 올린 숫자가 아님). 예측 시점은 '커리어 전성기'가 아니라 정확히 2~3년 후입니다.",
  headroom: "2~3년 후 상한(80% 구간 상단)에서 현재 능력을 뺀 값입니다. 값이 클수록 모델이 현재보다 더 올라갈 여지가 있다고 보는 선수입니다.",
};
const AGE_BANDS = {
  "u21": (a) => a <= 21, "22-23": (a) => a >= 22 && a <= 23, "24-27": (a) => a >= 24 && a <= 27,
  "28-31": (a) => a >= 28 && a <= 31, "32+": (a) => a >= 32,
};
const FILTER_IDS = { lg: "fLeague", pos: "fPos", role: "fRole", age: "fAge", sty: "fStyle", kind: "fKind" };

let INDEX = [];
let META = null;
const DEFAULT_STATE = { q: "", sort: "ability", lg: "", pos: "", role: "", age: "", sty: "", kind: "", view: "card", all: false };
let state = { ...DEFAULT_STATE };

// ── URL permalink ──
function readStateFromUrl() {
  const u = new URLSearchParams(window.location.search);
  for (const k of Object.keys(state)) {
    if (k === "all") { state.all = u.get("all") === "1"; continue; }
    if (u.has(k)) state[k] = u.get(k);
  }
  if (!SORT_MODES[state.sort]) state.sort = "ability";
  if (state.view !== "table") state.view = "card";
}
function writeStateToUrl() {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) {
    if (k === "all") { if (v) u.set("all", "1"); continue; }
    if (v && !(k === "sort" && v === "ability") && !(k === "view" && v === "card")) u.set(k, v);
  }
  const qs = u.toString();
  history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}
function hasInteracted() {
  return state.all || state.q || state.lg || state.pos || state.role || state.age || state.sty || state.kind || state.sort !== "ability";
}

function deltaCls(v) {
  if (v === null || v === undefined || isNaN(v)) return "band-mid";
  if (v > 0) return "band-great";
  if (v < 0) return "band-bad";
  return "band-ok";
}
function kindTag(p) {
  const oor = p.out_of_range ? ' <span class="badge tag small" title="현재 능력이 학습 라벨 상위 1%를 넘어 검증 표본이 적음">범위 밖</span>' : "";
  if (p.kind === "growth") return '<span class="badge tag small">성장기 모델</span>' + oor;
  if (p.kind === "peak") return '<span class="badge tag small">성숙기 모델</span>' + oor;
  return '<span class="muted small">—</span>';
}
function valueCell(p, mode) {
  if (mode === "headroom") {
    const v = p.headroom;
    const sign = v > 0 ? "+" : "";
    const t = v > 5 ? "상승 여지 큼" : v > 0 ? "상승 여지" : v > -3 ? "유지" : "하락 위험";
    return `<span class="badge ${deltaCls(v)}" aria-label="상승 여력 ${sign}${fmt1(v)}, ${t}" title="${t}">${sign}${fmt1(v)}<span class="tier">${t}</span></span>`;
  }
  return mode === "ceiling" ? scoreBadge(p.ceiling, "2~3년 후 상한") : scoreBadge(p.ability, "현재능력");
}
function roleLabel(code) {
  return META && META.role_labels && code ? META.role_labels[code] || code : (code || "");
}

function render(rows) {
  const mode = state.sort;
  const grid = document.getElementById("cardGrid");
  const table = document.getElementById("rosterTable");
  const body = document.getElementById("rosterBody");
  const empty = document.getElementById("emptyState");
  const count = document.getElementById("resultCount");
  const more = document.getElementById("moreHint");
  document.getElementById("headValueCol").textContent = SORT_MODES[mode].col;

  body.innerHTML = ""; grid.innerHTML = "";
  grid.hidden = state.view !== "card"; table.hidden = state.view !== "table";
  if (rows.length === 0) {
    empty.style.display = "block"; more.style.display = "none"; grid.hidden = true; table.hidden = true;
    count.textContent = "0명 — 필터를 완화해 보세요";
    return;
  }
  empty.style.display = "none";
  const scopeNote = SORT_MODES[mode].requiresEligible ? " (예측 대상만)" : "";
  const interacted = hasInteracted();
  const limit = interacted ? MAX_ROWS : HIGHLIGHT_ROWS;
  count.textContent = interacted
    ? `${rows.length}명${scopeNote} · ${SORT_MODES[mode].label}${rows.length > limit ? ` · 상위 ${limit}명 표시` : ""}`
    : `이번 시즌 대표 ${Math.min(limit, rows.length)}명 · ${SORT_MODES[mode].label}`;
  more.style.display = "block";
  more.innerHTML = interacted
    ? (rows.length > limit ? `상위 ${limit}명만 표시했습니다. 검색어나 필터로 범위를 좁혀 보세요.` : "")
    : `<a href="#" id="showAll">전체 ${rows.length}명 보기</a> · 검색·필터·정렬을 쓰면 전체 목록이 표시됩니다`;
  if (!more.innerHTML) more.style.display = "none";

  const shown = rows.slice(0, limit);
  if (state.view === "card") {
    grid.classList.remove("revealed");
    grid.innerHTML = shown.map((p) => playerCardHtml(p, roleLabel)).join("");
    if (window.FPPMotion) { window.FPPMotion.tilt(grid); window.FPPMotion.observe(grid.parentElement); }
  } else {
    const frag = document.createDocumentFragment();
    shown.forEach((p) => {
      const tr = document.createElement("tr");
      tr.tabIndex = 0;
      const go = () => { window.location.href = `player.html?id=${p.fbref_id}`; };
      tr.addEventListener("click", (e) => { if (!e.target.closest("[data-cmp-id]")) go(); });
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
      const role = p.role ? `<span class="muted small">${roleLabel(p.role)}</span>` : "";
      tr.innerHTML = `
        <td class="name" data-label="선수"><div class="name-cell">${avatarHtml(p.fbref_id, p.name, 30)}<span>${p.name}</span></div></td>
        <td class="muted" data-label="클럽">${p.squad || "—"}<span class="small league"> · ${p.league || ""}</span></td>
        <td class="muted" data-label="포지션">${p.pos_primary} ${role}</td>
        <td class="muted" data-label="나이">${p.age ?? "—"}</td>
        <td class="muted" data-label="스타일">${p.style || "—"}</td>
        <td data-label="${SORT_MODES[mode].col}">${valueCell(p, mode)}</td>
        <td data-label="모델">${kindTag(p)}</td>
        <td class="cmp-cell"><button type="button" class="btn-mini" data-cmp-id="${p.fbref_id}" data-cmp-name="${p.name}" aria-pressed="false">비교</button></td>
      `;
      frag.appendChild(tr);
    });
    body.appendChild(frag);
  }
  renderCompareBar();
  const showAll = document.getElementById("showAll");
  if (showAll) showAll.addEventListener("click", (e) => { e.preventDefault(); state.all = true; writeStateToUrl(); search(); });
}

function search() {
  const mode = SORT_MODES[state.sort];
  const query = asciiFold(state.q.trim());
  let pool = INDEX;
  if (mode.requiresEligible) pool = pool.filter((p) => p.eligible && p[mode.key] !== null && p[mode.key] !== undefined);
  if (state.lg) pool = pool.filter((p) => p.league === state.lg);
  if (state.pos) pool = pool.filter((p) => p.pos_primary === state.pos);
  if (state.role) pool = pool.filter((p) => p.role === state.role);
  if (state.age && AGE_BANDS[state.age]) pool = pool.filter((p) => p.age !== null && AGE_BANDS[state.age](p.age));
  if (state.sty) pool = pool.filter((p) => p.style === state.sty);
  if (state.kind === "any") pool = pool.filter((p) => p.eligible);
  else if (state.kind === "none") pool = pool.filter((p) => !p.eligible);
  else if (state.kind) pool = pool.filter((p) => p.kind === state.kind);
  if (query) pool = pool.filter((p) => p.name_ascii.includes(query) || p.squad_ascii.includes(query));
  pool = [...pool].sort((a, b) => (b[mode.key] ?? -999) - (a[mode.key] ?? -999));
  render(pool);
}

function applyStateToControls() {
  document.getElementById("searchInput").value = state.q;
  document.querySelectorAll(".sort-tab").forEach((b) => {
    const on = b.dataset.sort === state.sort;
    b.classList.toggle("active", on); b.setAttribute("aria-pressed", on ? "true" : "false");
  });
  const hintEl = document.getElementById("sortHint");
  hintEl.style.display = SORT_HINTS[state.sort] ? "block" : "none";
  hintEl.textContent = SORT_HINTS[state.sort];
  for (const [k, id] of Object.entries(FILTER_IDS)) document.getElementById(id).value = state[k];
  document.querySelectorAll(".view-btn").forEach((b) => {
    const on = b.dataset.view === state.view;
    b.classList.toggle("active", on); b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function fillSelect(id, values, labelFn) {
  const sel = document.getElementById(id);
  values.forEach((v) => { const o = document.createElement("option"); o.value = v; o.textContent = labelFn ? labelFn(v) : v; sel.appendChild(o); });
}

document.getElementById("sortTabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".sort-tab");
  if (!btn) return;
  state.sort = btn.dataset.sort; state.all = true;
  applyStateToControls(); writeStateToUrl(); search();
});
document.getElementById("filters").addEventListener("change", (e) => {
  const k = Object.keys(FILTER_IDS).find((key) => FILTER_IDS[key] === e.target.id);
  if (!k) return;
  state[k] = e.target.value; state.all = true;
  writeStateToUrl(); search();
});
document.querySelector(".view-toggle").addEventListener("click", (e) => {
  const btn = e.target.closest(".view-btn");
  if (!btn) return;
  state.view = btn.dataset.view;
  applyStateToControls(); writeStateToUrl(); search();
});
document.getElementById("fReset").addEventListener("click", () => {
  state = { ...DEFAULT_STATE, view: state.view };
  applyStateToControls(); writeStateToUrl(); search();
});
document.getElementById("searchInput").addEventListener("input", (e) => {
  state.q = e.target.value; writeStateToUrl(); search();
});
document.body.addEventListener("click", (e) => {
  const b = e.target.closest("[data-cmp-id]");
  if (!b) return;
  e.preventDefault(); e.stopPropagation();
  cmpToggle(b.dataset.cmpId, b.dataset.cmpName);
}, true);

readStateFromUrl();
Promise.all([fetch("data/index.json").then((r) => r.json()), fetch("data/meta.json").then((r) => r.json())])
  .then(([data, meta]) => {
    META = meta;
    const cols = data.cols;
    INDEX = data.rows.map((r) => {
      const p = {}; cols.forEach((c, i) => { p[c] = r[i]; });
      p.eligible = !!p.kind;
      p.headroom = p.ceiling !== null && p.ability !== null ? Math.round((p.ceiling - p.ability) * 10) / 10 : null;
      p.name_ascii = asciiFold(p.name); p.squad_ascii = asciiFold(p.squad || "");
      return p;
    });
    fillSelect("fLeague", meta.filters.leagues);
    fillSelect("fRole", meta.filters.roles, (v) => meta.role_labels[v] || v);
    fillSelect("fStyle", meta.filters.styles);
    applyStateToControls();
    search();
    const partialNote = meta.is_partial_season
      ? ` (${meta.target_year}시즌은 데이터 수집 시점상 부분 시즌이라, 원래 기준(${meta.original_pred_min_minutes}분)을 실제 관측된 최대 출전시간(${meta.season_max_minutes}분) 대비 동일 비율로 환산했습니다.)`
      : "";
    document.getElementById("eligibilityHint").innerHTML =
      `현재능력 점수는 전체 ${meta.n_players.toLocaleString()}명에게 제공됩니다. 카드의 <b>2~3년 후 상한</b>은 80% 신뢰구간의 상단(상위 10% 시나리오)이며 최댓값이 아닙니다. 예측은 <b>2~3년 후 시점</b>의 능력이며(커리어 전성기가 아님), ` +
      `만 ${meta.pred_age_max}세 이하·${meta.pred_min_minutes}분 이상은 <b>성장기 모델</b>, ` +
      `만 ${meta.veteran.age_min}~${meta.veteran.age_max}세·${meta.veteran.pred_min_minutes}분 이상은 <b>성숙기 모델</b>이 적용됩니다.${partialNote}` +
      `<br>성숙기 모델이 성장기 모델보다 정확도가 높습니다 (MAE ${meta.veteran.mae} vs ${meta.u23_mae}, R² ${meta.veteran.r2} vs ${meta.u23_r2}, GroupKFold 5겹 검증).` +
      `<br>점수는 절대 기량이 아니라 <b>해당 시즌 같은 포지션 내 상대 순위</b> 기반입니다 — 점수 유지는 정체가 아니라 지위 유지를 뜻합니다.`;
  })
  .catch((err) => {
    document.getElementById("resultCount").textContent = "데이터 로드 실패";
    console.error(err);
  });
