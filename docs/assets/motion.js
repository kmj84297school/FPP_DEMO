/* FPP motion — 모션 유틸(리빌·카운트업·카드 틸트·페이지 전환·인트로·배경). 의존성 없음.
   prefers-reduced-motion이면 body.no-motion을 붙이고 전부 정적으로 동작한다. */
(function () {
  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mobile = window.matchMedia && window.matchMedia("(max-width: 640px)").matches;
  if (reduced) document.documentElement.classList.add("no-motion");

  // ── 로고 심볼 (inline <svg><use>) ──
  const LOGO_SYMBOL = `
    <svg width="0" height="0" style="position:absolute" aria-hidden="true">
      <defs>
        <linearGradient id="logoGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#19ffa7"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
        <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#19ffa7"/><stop offset="1" stop-color="#ffd700"/></linearGradient>
        <linearGradient id="orbitGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#19ffa7"/><stop offset="1" stop-color="#a78bfa"/></linearGradient>
        <symbol id="fpp-logo" viewBox="0 0 120 120">
          <g class="fpp-og fpp-og-a"><ellipse class="fpp-orbit" cx="60" cy="60" rx="50" ry="20" transform="rotate(-28 60 60)"/></g>
          <g class="fpp-og fpp-og-b"><ellipse class="fpp-orbit" cx="60" cy="60" rx="50" ry="20" transform="rotate(40 60 60)" stroke-dasharray="380 120"/></g>
          <path class="fpp-star" d="M60 36 L66 54 L84 60 L66 66 L60 84 L54 66 L36 60 L54 54 Z"/>
          <circle class="fpp-sat fpp-sat-now" cx="17" cy="82" r="5"/>
          <circle class="fpp-sat" cx="98" cy="22" r="5"/>
        </symbol>
      </defs>
    </svg>`;
  document.body.insertAdjacentHTML("afterbegin", LOGO_SYMBOL);

  // ── 배경 궤도 레이어 ──
  const sparks = mobile ? "" : Array.from({ length: 10 }, (_, i) =>
    `<span class="spark" style="left:${(i * 37 + 11) % 100}%;top:${(i * 53 + 17) % 100}%;animation-delay:${(i * 0.9).toFixed(1)}s"></span>`).join("");
  document.body.insertAdjacentHTML("afterbegin", `
    <div class="bg" aria-hidden="true">
      <svg class="orbits" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice">
        <ellipse class="o o1" cx="500" cy="500" rx="480" ry="170" transform="rotate(-22 500 500)"/>
        <ellipse class="o o2" cx="500" cy="500" rx="420" ry="140" transform="rotate(35 500 500)"/>
        <ellipse class="o o3" cx="500" cy="500" rx="330" ry="110" transform="rotate(-70 500 500)"/>
      </svg>${sparks}
    </div>`);

  // ── 페이지 전환 오버레이 ──
  const veil = document.createElement("div");
  veil.className = "page-veil"; veil.setAttribute("aria-hidden", "true");
  veil.innerHTML = '<svg class="logo"><use href="#fpp-logo"/></svg>';
  document.body.appendChild(veil);
  document.addEventListener("click", (e) => {
    if (reduced) return;
    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || e.metaKey || e.ctrlKey || e.shiftKey || a.hasAttribute("download")) return;
    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin || url.pathname === location.pathname && url.hash) return;
    if (!/\.html$/.test(url.pathname) && url.pathname !== location.pathname) return;
    e.preventDefault();
    veil.classList.add("on");
    setTimeout(() => { location.href = url.href; }, 230);
  });
  window.addEventListener("pageshow", () => veil.classList.remove("on"));

  // ── 로고 인트로 (세션당 1회, 랜딩만) ──
  try {
    if (!reduced && document.body.dataset.intro === "1" && !sessionStorage.getItem("fpp_intro")) {
      sessionStorage.setItem("fpp_intro", "1");
      document.body.insertAdjacentHTML("afterbegin", `
        <div class="intro" aria-hidden="true">
          <svg class="logo"><use href="#fpp-logo"/></svg>
          <div class="word">F<span>P</span>P</div>
        </div>`);
      setTimeout(() => { const el = document.querySelector(".intro"); if (el) el.remove(); }, 2000);
    }
  } catch (e) { /* storage 불가 환경 */ }

  // ── 리빌 (IntersectionObserver) ──
  const io = ("IntersectionObserver" in window) ? new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) {
        en.target.classList.add("revealed");
        if (en.target.dataset.countup !== undefined) countUpIn(en.target);
        io.unobserve(en.target);
      }
    });
  }, { threshold: 0, rootMargin: "0px 0px -8% 0px" }) : null;  // 키 큰 패널도 일부만 보이면 리빌

  function observe(root) {
    const scope = root || document;
    scope.querySelectorAll(".reveal, .stagger, .panel, [data-countup]").forEach((el) => {
      if (el.classList.contains("revealed")) return;
      if (!el.classList.contains("reveal") && !el.classList.contains("stagger") && el.dataset.countup === undefined) el.classList.add("reveal");
      if (reduced || !io) { el.classList.add("revealed"); if (el.dataset.countup !== undefined) countUpIn(el, true); }
      else io.observe(el);
    });
    // stagger 자식 지연
    scope.querySelectorAll(".stagger").forEach((s) => {
      Array.from(s.children).forEach((c, i) => { c.style.transitionDelay = reduced ? "0ms" : `${Math.min(i, 12) * 55}ms`; });
    });
  }

  // ── 카운트업 ──
  function countUpIn(el, instant) {
    const to = parseFloat(el.dataset.countup), dec = parseInt(el.dataset.dec || "1", 10);
    if (isNaN(to)) return;
    if (instant || reduced) { el.textContent = to.toFixed(dec); return; }
    const t0 = performance.now(), dur = 900;
    (function tick(now) {
      const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      el.textContent = (to * e).toFixed(dec);
      if (p < 1) requestAnimationFrame(tick);
    })(t0);
  }

  // ── 카드 틸트 + 광택 ──
  function tilt(root) {
    if (reduced || mobile) return;
    (root || document).querySelectorAll(".pcard").forEach((card) => {
      if (card.dataset.tilt) return; card.dataset.tilt = "1";
      card.addEventListener("mousemove", (e) => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        card.style.setProperty("--mx", `${x * 100}%`); card.style.setProperty("--my", `${y * 100}%`);
        card.style.transform = `rotateY(${(x - 0.5) * 14}deg) rotateX(${(0.5 - y) * 12}deg) translateY(-4px)`;
        card.style.transition = "transform 60ms linear";
      });
      card.addEventListener("mouseleave", () => { card.style.transform = ""; card.style.transition = ""; });
    });
  }

  // ── 링 게이지 채우기 ──
  function rings(root) {
    (root || document).querySelectorAll(".ring .fg").forEach((fg) => {
      const v = parseFloat(fg.dataset.value); if (isNaN(v)) return;
      const len = 2 * Math.PI * parseFloat(fg.getAttribute("r"));
      fg.style.strokeDasharray = `${len}`;
      fg.style.strokeDashoffset = `${len}`;
      requestAnimationFrame(() => requestAnimationFrame(() => { fg.style.strokeDashoffset = `${len * (1 - Math.max(0, Math.min(100, v)) / 100)}`; }));
    });
  }

  // ── 섹션 탭 스크롤 스파이 ──
  function spy() {
    const tabs = document.querySelectorAll(".section-tabs a[href^='#']");
    if (!tabs.length || !("IntersectionObserver" in window)) return;
    const map = new Map();
    tabs.forEach((a) => { const sec = document.querySelector(a.getAttribute("href")); if (sec) map.set(sec, a); });
    const so = new IntersectionObserver((entries) => {
      entries.forEach((en) => { if (en.isIntersecting) { tabs.forEach((t) => t.classList.remove("active")); map.get(en.target).classList.add("active"); } });
    }, { rootMargin: "-40% 0px -55% 0px" });
    map.forEach((_, sec) => so.observe(sec));
  }

  window.FPPMotion = { observe, tilt, rings, spy, countUpIn, reduced, mobile };
  document.addEventListener("DOMContentLoaded", () => { observe(); tilt(); rings(); spy(); });
})();
