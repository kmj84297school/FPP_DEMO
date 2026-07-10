const MAX_ROWS = 200;

let INDEX = [];

function render(rows) {
  const body = document.getElementById("rosterBody");
  const empty = document.getElementById("emptyState");
  const count = document.getElementById("resultCount");

  body.innerHTML = "";
  if (rows.length === 0) {
    empty.style.display = "block";
    count.textContent = "0명";
    return;
  }
  empty.style.display = "none";
  count.textContent = `${rows.length}명 표시 (전체 ${INDEX.length}명 중, 능력점수 내림차순)`;

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
      <td><span class="badge ${bandcls(p.ability)}">${fmt1(p.ability)}</span></td>
      <td>${p.eligible ? '<span class="badge tag small">잠재력 예측</span>' : ""}</td>
    `;
    frag.appendChild(tr);
  });
  body.appendChild(frag);
}

function search(q) {
  const query = asciiFold(q.trim());
  if (!query) {
    render([...INDEX].sort((a, b) => (b.ability ?? 0) - (a.ability ?? 0)));
    return;
  }
  const matched = INDEX.filter(
    (p) => p.name_ascii.includes(query) || asciiFold(p.squad || "").includes(query)
  );
  matched.sort((a, b) => (b.ability ?? 0) - (a.ability ?? 0));
  render(matched);
}

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
