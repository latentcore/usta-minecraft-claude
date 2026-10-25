"use strict";
const CSRF = document.querySelector('meta[name=csrf]').content;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
async function api(path, method = "GET", body = null) {
  const opt = {method, headers: {}};
  if (method !== "GET") { opt.headers["X-Usta-CSRF"] = CSRF; opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body || {}); }
  const r = await fetch(path, opt);
  const t = r.headers.get("Content-Type") || "";
  return t.includes("json") ? r.json() : r.text();
}
function feed(msg) {
  const d = document.createElement("div");
  d.textContent = new Date().toLocaleTimeString("tr-TR") + "  " + msg;
  $("#feed").prepend(d);
  while ($("#feed").children.length > 80) $("#feed").lastChild.remove();
}
// ---------------------------------------------------------------- durum
async function status() {
  try {
    const s = await api("/api/status");
    const p = $("#status");
    if (s.game === "closed") { p.textContent = "oyun kapalı"; p.className = "pill bad"; return s; }
    p.textContent = `oyun açık · ${s.world || ""}${s.paused ? " · duraklatıldı" : ""}${s.active_job ? " · inşa %" + Math.round((s.active_job.progress || 0) * 100) : ""}`;
    p.className = "pill ok";
    return s;
  } catch (e) { $("#status").textContent = "panel bağlantısı yok"; }
}
// ---------------------------------------------------------------- harita
let mapInfo = null, center = null, sel = [];
async function loadMap() {
  const r = $("#radius").value;
  const q = center ? `&cx=${center[0]}&cz=${center[1]}` : "";
  mapInfo = await api(`/api/map.json?r=${r}${q}`);
  if (mapInfo.game === "closed") { feed("Oyun açık değil: harita yok."); return; }
  $("#map").src = `/api/map.jpg?r=${r}${q}&t=${Date.now()}`;
  drawSel();
}
function pxToWorld(ev) {
  const img = $("#map"), rect = img.getBoundingClientRect();
  const sx = img.naturalWidth / rect.width, sy = img.naturalHeight / rect.height;
  const px = (ev.clientX - rect.left) * sx, py = (ev.clientY - rect.top) * sy;
  const r = mapInfo.radius, W = 2 * r + 1, s = Math.max(1, Math.min(12, Math.floor(900 / W)));
  const x0 = mapInfo.center[0] - r, z0 = mapInfo.center[1] - r;
  return [Math.floor(x0 + (px - 46) / s), Math.floor(z0 + (py - 26) / s)];
}
function worldToPx(x, z) {
  const img = $("#map"), rect = img.getBoundingClientRect();
  const r = mapInfo.radius, W = 2 * r + 1, s = Math.max(1, Math.min(12, Math.floor(900 / W)));
  const x0 = mapInfo.center[0] - r, z0 = mapInfo.center[1] - r;
  const k = rect.width / img.naturalWidth;
  return [(46 + (x - x0) * s) * k, (26 + (z - z0) * s) * k];
}
function drawSel() {
  const b = $("#selbox");
  const has = sel.length === 2;
  ["#protect", "#buildhere", "#clearsel"].forEach((id) => ($(id).disabled = sel.length === 0 || (id !== "#clearsel" && !has)));
  if (!mapInfo || sel.length === 0) { b.style.display = "none"; $("#sel").textContent = "Haritaya tıkla: 1. köşe, 2. köşe"; return; }
  const a = sel[0], c = sel[1] || sel[0];
  const [x1, y1] = worldToPx(Math.min(a[0], c[0]), Math.min(a[1], c[1]));
  const [x2, y2] = worldToPx(Math.max(a[0], c[0]) + 1, Math.max(a[1], c[1]) + 1);
  Object.assign(b.style, {display: "block", left: x1 + "px", top: y1 + "px", width: (x2 - x1) + "px", height: (y2 - y1) + "px"});
  $("#sel").textContent = has ? `Seçim: ${a[0]},${a[1]} → ${c[0]},${c[1]} (${Math.abs(c[0] - a[0]) + 1}×${Math.abs(c[1] - a[1]) + 1})` : `1. köşe: ${a[0]},${a[1]}`;
}
$("#map").addEventListener("click", (ev) => { if (!mapInfo) return; const w = pxToWorld(ev); sel = sel.length >= 2 ? [w] : [...sel, w]; drawSel(); });
$("#map").addEventListener("dblclick", (ev) => { center = pxToWorld(ev); sel = []; loadMap(); });
$("#refresh").onclick = loadMap;
$("#center").onclick = () => { center = null; loadMap(); };
$("#radius").onchange = loadMap;
$("#clearsel").onclick = () => { sel = []; drawSel(); };
$("#protect").onclick = async () => {
  const name = prompt("Korunan bölgenin adı:", "evim"); if (!name) return;
  const [a, c] = sel;
  const r = await api("/api/protected", "POST", {name, x0: a[0], z0: a[1], x1: c[0], z1: c[1], y0: -64, y1: 320});
  feed(r.regions ? `Korunan bölge eklendi: ${name}` : (r.message || "olmadı")); loadProt(); loadMap();
};
$("#buildhere").onclick = () => {
  const [a, c] = sel;
  $("#req").value = `x ${Math.min(a[0], c[0])}..${Math.max(a[0], c[0])}, z ${Math.min(a[1], c[1])}..${Math.max(a[1], c[1])} alanına: ` + ($("#req").value || "");
  $("#req").focus();
};
// ---------------------------------------------------------------- istek ve olaylar
$("#send").onclick = async () => {
  const text = $("#req").value.trim(); if (!text) return;
  const r = await api("/api/request", "POST", {text});
  feed(r.id ? `İstek gönderildi: ${text}` : (r.message || "gönderilemedi"));
  $("#req").value = "";
};
$("#cancelreq").onclick = async () => { const r = await api("/api/agent/cancel", "POST"); feed(r.ok ? "İstek iptal edildi." : "İptal edilecek istek yok."); };
let since = 0;
async function pollEvents() {
  for (;;) {
    try {
      const r = await api(`/api/events?since=${since}`);
      if (r.last !== undefined) since = r.last;
      for (const e of r.events || []) {
        const d = e.data || {};
        if (e.type === "agent_status") feed(d.text);
        else if (e.type.startsWith("job_")) { feed(`${d.label || "iş"}: ${e.type.replace("job_", "")} ${d.progress !== undefined ? "%" + Math.round(d.progress * 100) : ""}`); loadJobs(); if (/done|cancelled|failed/.test(e.type)) loadHist(); }
        else if (e.type === "agent_finished") feed(`İstek bitti: ${d.final || d.state}`);
      }
      if (r.game === "closed") await new Promise((s) => setTimeout(s, 5000));
    } catch (e) { await new Promise((s) => setTimeout(s, 3000)); }
  }
}
// ---------------------------------------------------------------- sekmeler
document.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== "tab-" + b.dataset.tab));
  ({jobs: loadJobs, hist: loadHist, lib: loadLib, prot: loadProt, set: loadSet, health: loadHealth})[b.dataset.tab]();
}));
async function loadJobs() {
  const r = await api("/api/jobs"), el = $("#tab-jobs");
  if (r.game === "closed") { el.textContent = "Oyun açık değil."; return; }
  const jobs = [...(r.active ? [r.active] : []), ...(r.queued || [])];
  if (!jobs.length) { el.innerHTML = '<span class="muted">Süren ya da sırada iş yok.</span>'; return; }
  el.innerHTML = jobs.map((j) => `<div class="item"><div class="meta"><b>${esc(j.label)}</b> · ${esc(j.state)} · ${j.placed}/${j.total} blok
    <div class="bar"><i style="width:${Math.round((j.progress || 0) * 100)}%"></i></div>
    <div class="row"><button data-a="pause" data-id="${j.id}">Duraklat</button><button data-a="resume" data-id="${j.id}">Sürdür</button>
    <button data-a="speed" data-id="${j.id}">Anında bitir</button><button data-a="cancel" data-id="${j.id}">İptal</button>
    ${j.state === "AWAITING_CONFIRM" ? `<button class="primary" data-a="confirm" data-id="${j.id}">Onayla</button>` : ""}</div></div></div>`).join("");
  el.querySelectorAll("button[data-a]").forEach((b) => (b.onclick = async () => { await api(`/api/job/${b.dataset.id}/${b.dataset.a}`, "POST", {seconds: 0}); loadJobs(); }));
}
async function loadHist() {
  const r = await api("/api/history"), el = $("#tab-hist");
  if (r.game === "closed") { el.textContent = "Oyun açık değil."; return; }
  const es = r.entries || [];
  if (!es.length) { el.innerHTML = '<span class="muted">Henüz iş yok.</span>'; return; }
  el.innerHTML = es.map((e) => `<div class="item">${e.kind === "BUILD" ? `<img loading="lazy" src="/api/history/${e.id}/before.jpg" title="önce"><img loading="lazy" src="/api/history/${e.id}/after.jpg" title="sonra">` : ""}
    <div class="meta"><b>${esc(e.label)}</b> ${e.undone ? '<span class="muted">(geri alındı)</span>' : ""}<br><span class="muted">${new Date(e.created).toLocaleString("tr-TR")} · ${e.changed || 0} blok · ${esc(e.source || "")}</span>
    <div class="row">${e.undone ? `<button data-r="${e.id}">Yinele</button>` : `<button data-u="${e.id}">Geri al</button>`}</div></div></div>`).join("");
  el.querySelectorAll("button[data-u]").forEach((b) => (b.onclick = async () => { const x = await api("/api/undo", "POST", {id: b.dataset.u}); feed(x.ok ? "Geri alınıyor…" : x.message); setTimeout(loadHist, 1500); }));
  el.querySelectorAll("button[data-r]").forEach((b) => (b.onclick = async () => { const x = await api("/api/redo", "POST", {id: b.dataset.r}); feed(x.ok ? "Yineleniyor…" : x.message); setTimeout(loadHist, 1500); }));
}
async function loadLib() {
  const r = await api("/api/library"), el = $("#tab-lib");
  const items = r.items || [];
  if (!items.length) { el.innerHTML = '<span class="muted">Kütüphane boş. Oyunda bir yapının [Kaydet] düğmesiyle eklenir.</span>'; return; }
  el.innerHTML = items.map((i) => `<div class="item"><img loading="lazy" src="/api/library/${i.id}/preview.jpg"><div class="meta"><b>${esc(i.name)}</b><br>
    <span class="muted">${i.size.join("×")} · ${i.blocks} blok ${(i.tags || []).map(esc).join(", ")}</span>
    <div class="row"><button data-p="${i.id}" class="primary">Önüme kur</button><button data-d="${i.id}">Sil</button></div></div></div>`).join("");
  el.querySelectorAll("button[data-p]").forEach((b) => (b.onclick = async () => { const x = await api(`/api/library/${b.dataset.p}/place`, "POST", {}); feed(x.state ? `Kuruluyor: ${x.label}` : (x.message || "olmadı")); }));
  el.querySelectorAll("button[data-d]").forEach((b) => (b.onclick = async () => { if (confirm("Kütüphaneden silinsin mi?")) { await api(`/api/library/${b.dataset.d}`, "DELETE"); loadLib(); } }));
}
async function loadProt() {
  const r = await api("/api/protected"), el = $("#tab-prot");
  const rs = r.regions || [];
  el.innerHTML = rs.length ? rs.map((x) => `<div>• <b>${esc(x.name)}</b> ${x.x0},${x.z0} → ${x.x1},${x.z1}</div>`).join("") : '<span class="muted">Korunan bölge yok. Haritada iki köşe seçip "Seçimi koru".</span>';
}
async function loadSet() {
  const s = await api("/api/settings");
  if (s.game === "closed") return;
  $("#s-mode").value = s.defaultMode; $("#s-sec").value = s.defaultSeconds; $("#s-eff").checked = s.effects; $("#s-cel").checked = s.celebration; $("#s-model").value = s.model;
}
$("#s-save").onclick = async () => {
  await api("/api/settings", "POST", {defaultMode: $("#s-mode").value, defaultSeconds: +$("#s-sec").value, effects: $("#s-eff").checked, celebration: $("#s-cel").checked, model: $("#s-model").value});
  feed("Ayarlar kaydedildi.");
};
async function loadHealth() {
  const h = await api("/api/health"), l = await api("/api/logs");
  $("#tab-health").innerHTML = Object.entries(h).map(([k, v]) => `<div>${v ? "🟢" : "🔴"} ${esc(k)}: ${esc(v)}</div>`).join("") +
    `<pre style="max-height:240px;overflow:auto;font-size:11px">${esc((l.lines || []).join("\n"))}</pre>`;
}
// ---------------------------------------------------------------- baslangic
(async () => { await status(); loadMap(); loadJobs(); pollEvents(); setInterval(status, 5000); })();
