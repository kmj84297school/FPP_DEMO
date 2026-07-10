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
