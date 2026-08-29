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

let INDEX = [];
let currentSort = "ability";
let hasInteracted = false;

function deltaCls(v) {
  if (v === null || v === undefined || isNaN(v)) return "band-mid";
  if (v > 0) return "band-great";
  if (v < 0) return "band-bad";
  return "band-ok";
}

function kindTag(p) {
  const oor = p.out_of_range ? '<span class="badge tag small" title="모델 검증 범위 밖">범위 밖</span>' : "";
  if (p.kind === "growth") return '<span class="badge tag small">성장기 모델</span>' + oor;
  if (p.kind === "peak") return '<span class="badge tag small">성숙기 모델</span>' + oor;
  return "";
}

function valueCell(p, mode) {
  if (mode === "headroom") {
    const v = p.headroom;
    const sign = v > 0 ? "+" : "";
    return `<span class="badge ${deltaCls(v)}">${sign}${fmt1(v)}</span>`;
  }
  const v = mode === "ceiling" ? p.ceiling : p.ability;
  return `<span class="badge ${bandcls(v)}">${fmt1(v)}</span>`;
}

function render(rows, mode) {
  const body = document.getElementById("rosterBody");
  const empty = document.getElementById("emptyState");
  const count = document.getElementById("resultCount");
  const headValueCol = document.getElementById("headValueCol");

  headValueCol.textContent = SORT_MODES[mode].col;

  body.innerHTML = "";
  if (rows.length === 0) {
    empty.style.display = "block";
    count.textContent = "0명";
    return;
  }
  empty.style.display = "none";
  const scopeNote = SORT_MODES[mode].requiresEligible ? " (예측 대상만)" : "";
  const limit = hasInteracted ? MAX_ROWS : HIGHLIGHT_ROWS;
  if (hasInteracted) {
    count.textContent = `${rows.length}명 표시${scopeNote} · ${SORT_MODES[mode].label}`;
  } else {
    count.textContent = `대표 선수 ${Math.min(limit, rows.length)}명 · ${SORT_MODES[mode].label} — 검색하거나 정렬 탭을 누르면 전체 목록이 표시됩니다`;
  }

  const frag = document.createDocumentFragment();
  rows.slice(0, limit).forEach((p) => {
    const tr = document.createElement("tr");
    tr.onclick = () => { window.location.href = `player.html?id=${p.fbref_id}`; };
    tr.innerHTML = `
      <td class="name">${p.name}</td>
      <td class="muted">${p.squad || "—"}</td>
      <td class="muted">${p.pos_primary}</td>
      <td class="muted">${p.age ?? "—"}</td>
      <td class="muted">${p.style || "—"}</td>
      <td>${valueCell(p, mode)}</td>
      <td>${kindTag(p)}</td>
    `;
    frag.appendChild(tr);
  });
  body.appendChild(frag);
}

function search(q) {
  const mode = SORT_MODES[currentSort];
  const query = asciiFold(q.trim());

  let pool = INDEX;
  if (mode.requiresEligible) {
    pool = pool.filter((p) => p.eligible && p[mode.key] !== null && p[mode.key] !== undefined);
  }
  if (query) {
    pool = pool.filter((p) => p.name_ascii.includes(query) || asciiFold(p.squad || "").includes(query));
  }
  pool = [...pool].sort((a, b) => (b[mode.key] ?? -999) - (a[mode.key] ?? -999));
  render(pool, currentSort);
}

document.getElementById("sortTabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".sort-tab");
  if (!btn) return;
  hasInteracted = true;
  currentSort = btn.dataset.sort;
  document.querySelectorAll(".sort-tab").forEach((b) => b.classList.toggle("active", b === btn));
  const hintEl = document.getElementById("sortHint");
  const hint = SORT_HINTS[currentSort];
  hintEl.style.display = hint ? "block" : "none";
  hintEl.textContent = hint;
  search(document.getElementById("searchInput").value);
});

fetch("data/index.json")
  .then((r) => r.json())
  .then((data) => {
    INDEX = data;
    search("");
    document.getElementById("searchInput").addEventListener("input", (e) => {
      hasInteracted = true;
      search(e.target.value);
    });
  })
  .catch((err) => {
    document.getElementById("resultCount").textContent = "데이터 로드 실패";
    console.error(err);
  });

fetch("data/meta.json")
  .then((r) => r.json())
  .then((meta) => {
    const partialNote = meta.is_partial_season
      ? ` (${meta.target_year}시즌은 데이터 수집 시점상 부분 시즌이라, 원래 기준(${meta.original_pred_min_minutes}분)을 실제 관측된 최대 출전시간(${meta.season_max_minutes}분) 대비 동일 비율로 환산했습니다.)`
      : "";
    document.getElementById("eligibilityHint").innerHTML =
      `현재능력 점수는 전체 검색 대상에게 제공됩니다. 예측은 <b>2~3년 후 시점</b>의 능력이며(커리어 전성기가 아님), ` +
      `만 ${meta.pred_age_max}세 이하·${meta.pred_min_minutes}분 이상은 <b>성장기 모델</b>, ` +
      `만 ${meta.veteran.age_min}~${meta.veteran.age_max}세·${meta.veteran.pred_min_minutes}분 이상은 <b>성숙기 모델</b>이 적용됩니다.${partialNote}` +
      `<br>성숙기 모델이 성장기 모델보다 정확도가 높습니다 (MAE ${meta.veteran.mae} vs ${meta.u23_mae}, R² ${meta.veteran.r2} vs ${meta.u23_r2}, GroupKFold 5겹 검증).` +
      `<br>점수는 절대 기량이 아니라 <b>해당 시즌 같은 포지션 내 상대 순위</b> 기반입니다 — 점수 유지는 정체가 아니라 지위 유지를 뜻합니다.`;
  })
  .catch(() => {});
