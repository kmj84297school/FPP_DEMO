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
