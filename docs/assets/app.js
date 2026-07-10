const MAX_ROWS = 200;

const SORT_MODES = {
  ability: { label: "현재능력순", key: "ability", col: "현재능력", requiresEligible: false },
  mu: { label: "예측 잠재력순", key: "mu", col: "예측 잠재력", requiresEligible: true },
  delta: { label: "성장 예상순", key: "delta", col: "성장폭", requiresEligible: true },
};

const SORT_HINTS = {
  ability: "",
  mu: "예측 대상(연령·출전시간 기준 충족) 선수만 표시됩니다. 참고: 이 모델은 극단적으로 높은 현재 능력을 실제 데이터 패턴에 따라 다소 보수적으로 조정합니다(평균회귀) — 상위권 선수 상당수가 이런 경향을 보이며, 그래도 이 목록은 예측 잠재력이 가장 높게 나온 순서입니다.",
  delta: "예측 잠재력에서 현재 능력을 뺀 값(성장 예상폭)입니다. 예측 대상 선수만 표시됩니다. 값이 클수록 모델이 현재보다 더 성장할 것으로 보는 선수입니다.",
};

let INDEX = [];
let currentSort = "ability";

function deltaCls(v) {
  if (v === null || v === undefined || isNaN(v)) return "band-mid";
  if (v > 0) return "band-great";
  if (v < 0) return "band-bad";
  return "band-ok";
}

function valueCell(p, mode) {
  if (mode === "delta") {
    const v = p.delta;
    const sign = v > 0 ? "+" : "";
    return `<span class="badge ${deltaCls(v)}">${sign}${fmt1(v)}</span>`;
  }
  const v = mode === "mu" ? p.mu : p.ability;
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
      <td>${p.eligible ? '<span class="badge tag small">잠재력 예측</span>' : ""}</td>
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
    document.getElementById("eligibilityHint").textContent =
      `현재능력 점수는 전체 검색 대상에게, 잔존확률·미래잠재력·유사선수 비교는 만 ${meta.pred_age_max}세 이하·${meta.pred_min_minutes}분 이상 출전 선수에게만 제공됩니다.${partialNote}`;
  })
  .catch(() => {});
