const MAX_ROWS = 200;

const SORT_MODES = {
  ability: { label: "현재능력순", key: "ability", col: "현재능력", requiresEligible: false },
  ceiling: { label: "잠재력 상한순", key: "ceiling", col: "잠재력 상한(80%)", requiresEligible: true },
  headroom: { label: "성장 여력순", key: "headroom", col: "성장 여력", requiresEligible: true },
};

const SORT_HINTS = {
  ability: "",
  ceiling: "23세 이하 성장 예측 + 24세 이상 전성기 유지 예측 대상만 표시됩니다. '잠재력 상한'은 80% 신뢰구간의 상단값입니다 (실제 계산된 구간이며, 임의로 올린 숫자가 아닙니다).",
  headroom: "잠재력 상한(80% 구간 상단)에서 현재 능력을 뺀 값입니다. 값이 클수록 모델이 현재보다 더 성장/개선될 여지가 있다고 보는 선수입니다.",
};

let INDEX = [];
let currentSort = "ability";

function deltaCls(v) {
  if (v === null || v === undefined || isNaN(v)) return "band-mid";
  if (v > 0) return "band-great";
  if (v < 0) return "band-bad";
  return "band-ok";
}

function kindTag(kind) {
  if (kind === "growth") return '<span class="badge tag small">성장 예측</span>';
  if (kind === "peak") return '<span class="badge tag small">전성기 유지 예측</span>';
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
  count.textContent = `${rows.length}명 표시${scopeNote} · ${SORT_MODES[mode].label}`;

  const frag = document.createDocumentFragment();
  rows.slice(0, MAX_ROWS).forEach((p) => {
    const tr = document.createElement("tr");
    tr.onclick = () => { window.location.href = `player.html?id=${p.fbref_id}`; };
    tr.innerHTML = `
      <td class="name">${p.name}</td>
      <td class="muted">${p.squad || "—"}</td>
      <td class="muted">${p.pos_primary}</td>
      <td class="muted">${p.age ?? "—"}</td>
      <td class="muted">${p.style || "—"}</td>
      <td>${valueCell(p, mode)}</td>
      <td>${kindTag(p.kind)}</td>
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
    document.getElementById("searchInput").addEventListener("input", (e) => search(e.target.value));
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
      `현재능력 점수는 전체 검색 대상에게 제공됩니다. 만 ${meta.pred_age_max}세 이하·${meta.pred_min_minutes}분 이상은 <b>성장 예측</b>(2~3년 후 능력), ` +
      `만 ${meta.veteran.age_min}~${meta.veteran.age_max}세·${meta.veteran.pred_min_minutes}분 이상은 <b>전성기 유지 예측</b>을 받습니다.${partialNote} ` +
      `<br>전성기 유지 예측은 검증 결과 성장 예측보다 정확도가 더 높습니다 (MAE ${meta.veteran.mae} vs 6.19, R² ${meta.veteran.r2} vs 0.231, GroupKFold 5겹 검증).`;
  })
  .catch(() => {});
