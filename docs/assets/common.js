// legacy dashboard.html의 bandcls(v) 매크로를 JS로 이식
function bandcls(v) {
  if (v === null || v === undefined || isNaN(v)) return "band-mid";
  if (v >= 85) return "band-elite";
  if (v >= 75) return "band-great";
  if (v >= 60) return "band-good";
  if (v >= 45) return "band-ok";
  if (v >= 30) return "band-mid";
  return "band-bad";
}

function asciiFold(s) {
  if (!s) return "";
  return s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function fmt1(v) {
  return v === null || v === undefined || isNaN(v) ? "—" : Number(v).toFixed(1);
}

// ── 등급 텍스트(색만으로 정보를 전달하지 않기 위해 배지에 병기/aria) ──
function tierText(v) {
  if (v === null || v === undefined || isNaN(v)) return "정보 없음";
  if (v >= 85) return "엘리트";
  if (v >= 75) return "최상위";
  if (v >= 60) return "상위";
  if (v >= 45) return "중위";
  if (v >= 30) return "하위";
  return "최하위";
}
function scoreBadge(v, label, extraCls) {
  const t = tierText(v);
  return `<span class="badge ${bandcls(v)} ${extraCls || ""}" title="${label} ${fmt1(v)} · ${t}" aria-label="${label} ${fmt1(v)}, ${t}">${fmt1(v)}<span class="tier">${t}</span></span>`;
}

// ── 이니셜 아바타: 이름 해시로 색을 정해 사진 없는 선수도 일관된 시각 위계를 갖게 ──
function initialsOf(name) {
  if (!name) return "?";
  const parts = name.replace(/[^\p{L}\s-]/gu, "").split(/[\s-]+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}
function avatarHue(name) {
  let h = 0;
  for (const ch of name || "") h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}
function avatarHtml(fbrefId, name, size) {
  const hue = avatarHue(name);
  const synthetic = /^n\d{2}/.test(fbrefId || "");
  const px = size || 64;
  const fallback = `<div class="avatar-fallback" style="--h:${hue};${synthetic ? "" : "display:none;"}" aria-hidden="true">${initialsOf(name)}</div>`;
  const img = synthetic ? "" : `<img class="avatar-img" src="https://fbref.com/req/202302030/images/headshots/${fbrefId}_2022.jpg" alt="" referrerpolicy="no-referrer" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex';">`;
  return `<div class="avatar" style="width:${px}px;height:${px}px;">${img}${fallback}</div>`;
}

// ── 비교 바구니 (localStorage, 최대 2명) ──
const CMP_KEY = "fpp_compare";
function cmpGet() {
  try { return JSON.parse(localStorage.getItem(CMP_KEY) || "[]"); } catch (e) { return []; }
}
function cmpSet(list) {
  try { localStorage.setItem(CMP_KEY, JSON.stringify(list.slice(0, 2))); } catch (e) {}
  renderCompareBar();
}
function cmpToggle(id, name) {
  let list = cmpGet().filter((x) => x.id !== id);
  if (list.length === cmpGet().length) list = [...list, { id, name }].slice(-2);
  cmpSet(list);
  return list.some((x) => x.id === id);
}
function renderCompareBar() {
  const bar = document.getElementById("compareBar");
  if (!bar) return;
  const list = cmpGet();
  bar.hidden = list.length === 0;
  if (list.length === 0) return;
  const link = list.length === 2 ? `compare.html?a=${list[0].id}&b=${list[1].id}` : null;
  bar.innerHTML = `
    <span>비교: ${list.map((x) => `<b>${x.name}</b>`).join(" vs ")}${list.length < 2 ? ' <span class="muted">(한 명 더 선택)</span>' : ""}</span>
    <span class="compare-actions">
      ${link ? `<a class="btn" href="${link}">비교 보기 →</a>` : ""}
      <button class="btn-ghost" type="button" onclick="cmpSet([])">비우기</button>
    </span>`;
  document.querySelectorAll("[data-cmp-id]").forEach((el) => {
    const on = list.some((x) => x.id === el.dataset.cmpId);
    el.classList.toggle("on", on);
    el.setAttribute("aria-pressed", on ? "true" : "false");
    el.textContent = on ? "비교 ✓" : "비교";
  });
}

// ── 국가 코드 칩 (이미지 없이 텍스트) ──
function flagChip(iso) {
  return iso ? `<span class="flag"><span class="iso">${iso}</span></span>` : "";
}

// ── 궤도 게이지: 현재(초록 점) → 중심값(속 빈 원) → 2~3년 후 상한(금색 별) ──
// 상한만 보고 판단하지 않도록 중심값(가장 가능성 높은 값)을 같은 궤도 위에 함께 찍는다.
function orbitGaugeHtml(now, fut, opts) {
  const o = opts || {};
  const mu = o.mu === null || o.mu === undefined ? null : o.mu;
  const W = 200, H = 26, y = 14;
  const x = (v) => 6 + Math.max(0, Math.min(100, v ?? 0)) / 100 * (W - 12);
  const hasFut = fut !== null && fut !== undefined;
  const a = x(now), b = hasFut ? x(fut) : a;
  const lo = Math.min(a, b), hi = Math.max(a, b);
  const aria = `현재 ${fmt1(now)}${mu !== null ? `, 예측 중심값 ${fmt1(mu)}` : ""}${hasFut ? `, 2~3년 후 상한 ${fmt1(fut)}` : ""}`;
  let lbls = "";
  if (o.labels !== false) {
    const mid = mu !== null ? `<span class="mid">중심 ${fmt1(mu)}</span>` : "";
    // "mu-only": 카드처럼 현재·상한이 이미 큰 숫자로 있는 곳에서는 중심값만 덧붙인다.
    lbls = o.labels === "mu-only"
      ? (mu !== null ? `<div class="lbls mu-only">${mid}</div>` : "")
      : `<div class="lbls"><span>현재 ${fmt1(now)}</span>${mid}<span>${hasFut ? `2~3년 후 상한 ${fmt1(fut)}` : "예측 없음"}</span></div>`;
  }
  return `
    <div class="orbit-gauge" role="img" aria-label="${aria}">
      <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <path class="track" d="M6 ${y} Q ${W / 2} ${y - 9} ${W - 6} ${y}"/>
        ${hasFut ? `<path class="arc" d="M${lo} ${y - 4} Q ${(lo + hi) / 2} ${y - 9} ${hi} ${y - 4}"/>` : ""}
        <circle class="dot-now" cx="${a}" cy="${y - 4}" r="4"/>
        ${mu !== null ? `<circle class="dot-mu" cx="${x(mu)}" cy="${y - 4}" r="3.4"><title>예측 중심값 ${fmt1(mu)}</title></circle>` : ""}
        ${hasFut ? `<path class="dot-fut" transform="translate(${b} ${y - 4})" d="M0 -6 L1.8 -1.8 L6 0 L1.8 1.8 L0 6 L-1.8 1.8 L-6 0 L-1.8 -1.8 Z"/>` : ""}
      </svg>
      ${lbls}
    </div>`;
}

// ── 원형 링 게이지 (상세 헤더) ──
function ringHtml(value, label, cls, title) {
  const v = value === null || value === undefined ? null : value;
  return `
    <div class="ring ${cls}" title="${title || label}" role="img" aria-label="${label} ${fmt1(v)}, ${tierText(v)}">
      <svg viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="42"/><circle class="fg" cx="50" cy="50" r="42" data-value="${v ?? 0}"/></svg>
      <div class="num"><span data-countup="${v ?? 0}" data-dec="1">${v === null ? "—" : "0.0"}</span><small>${label}</small></div>
    </div>`;
}

// ── FC26식 선수 카드 (목록용) ──
function playerCardHtml(p, roleLabelFn) {
  const kind = p.kind || "none";
  const futVal = p.ceiling;
  const role = p.role && roleLabelFn ? roleLabelFn(p.role) : "";
  const tags = [];
  if (p.kind === "growth") tags.push('<span class="badge tag small">성장기 모델</span>');
  if (p.kind === "peak") tags.push('<span class="badge tag small">성숙기 모델</span>');
  if (p.out_of_range) tags.push('<span class="badge tag small" title="현재 능력이 학습 라벨 상위 1%를 넘어 검증 표본이 적음">범위 밖</span>');
  return `
    <a class="pcard kind-${kind}" href="player.html?id=${p.fbref_id}" aria-label="${p.name}, 현재 ${fmt1(p.ability)}${futVal != null ? `, 2~3년 후 상한 ${fmt1(futVal)}` : ""}">
      <div class="pc-top">
        <div class="pc-num" title="현재 능력 (2024-25 시즌, 같은 포지션 내 상대 순위 기반)">
          <span class="lbl">현재</span><span class="val g">${fmt1(p.ability)}</span><span class="tier">${tierText(p.ability)}</span>
        </div>
        <button type="button" class="btn-mini pc-cmp" data-cmp-id="${p.fbref_id}" data-cmp-name="${p.name}" aria-pressed="false">비교</button>
        <div class="pc-num" title="2~3년 후 능력의 80% 신뢰구간 상단 — 최댓값이 아니라 상위 10% 시나리오. 가장 가능성이 높은 값은 아래 '중심'입니다.">
          <span class="lbl">2~3년 후 상한</span><span class="val ${futVal != null ? "y" : "n"}">${futVal != null ? fmt1(futVal) : "—"}</span><span class="tier">${futVal != null ? tierText(futVal) : "예측 없음"}</span>
        </div>
      </div>
      <div class="pc-avatar">${avatarHtml(p.fbref_id, p.name, 84)}</div>
      <div class="pc-name">${p.name}</div>
      <div class="pc-meta">${flagChip(p.nation)}<b>${p.pos_primary}</b>${role ? `<span>${role}</span>` : ""}<span>· ${p.age ?? "—"}세</span></div>
      <div class="pc-meta"><span>${p.squad || "—"}</span></div>
      <div class="pc-orbit">${orbitGaugeHtml(p.ability, futVal, { mu: p.mu, labels: p.mu != null ? "mu-only" : false })}</div>
      ${tags.length ? `<div class="pc-tags">${tags.join("")}</div>` : ""}
    </a>`;
}
