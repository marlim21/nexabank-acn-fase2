// Consola del agente: se comunica con la API REST del ACN.
// API_BASE vacío = mismo origen (FastAPI sirve el frontend, o nginx hace de proxy hacia /api).
const API_BASE = (window.ACN_API_BASE || "").replace(/\/$/, "");
const MAX_CHARS = 2000;
const TIMEOUT_MS = 15000;

const $ = (id) => document.getElementById(id);
let currentSuggestionId = null;

async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(describeError(res.status, data));
    return data;
  } catch (err) {
    if (err.name === "AbortError") throw new Error("El servicio tardó demasiado en responder. Intenta de nuevo.");
    if (err instanceof TypeError) throw new Error("No hay comunicación con el backend. Verifica que el servicio esté activo.");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function describeError(status, data) {
  if (status === 422 && Array.isArray(data.detalle)) {
    return "Datos inválidos: " + data.detalle.map((d) => `${d.campo}: ${d.error}`).join("; ");
  }
  if (status === 503 && data.error === "modelo_no_disponible") return "El modelo no está disponible en este momento (503).";
  if ([502, 503, 504].includes(status)) return `No hay comunicación con el backend (${status}). Verifica que el servicio esté activo.`;
  if (status === 413) return "La solicitud es demasiado grande.";
  return `Error ${status}: ${data.detalle || data.error || "respuesta inesperada"}`;
}

function setList(el, items, render = (x) => x) {
  el.replaceChildren(...items.map((item) => {
    const li = document.createElement("li");
    li.textContent = render(item);
    return li;
  }));
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = !message;
}

// ---------- Estado del servicio ----------
async function refreshStatus() {
  const status = $("status");
  try {
    const health = await api("/health");
    status.textContent = `Servicio activo · generación ${health.modo_generacion}`;
    status.className = "status status--ok";
    const info = await api("/api/v1/model/info");
    $("model-info").textContent = `Modelo: ${info.nombre_modelo} v${info.version_modelo} · accuracy test ${info.metricas_test.accuracy}`;
    refreshAdoption();
  } catch (err) {
    status.textContent = "Servicio no disponible";
    status.className = "status status--down";
  }
}

async function refreshAdoption() {
  try {
    const kpi = await api("/api/v1/metrics/adoption");
    $("adoption").textContent = `Tasa de aceptación: ${(kpi.tasa_aceptacion * 100).toFixed(0)}% (${kpi.total} decisiones)`;
  } catch { /* KPI opcional */ }
}

// ---------- Sugerencia ----------
const mensaje = $("mensaje");
mensaje.addEventListener("input", () => { $("char-count").textContent = mensaje.value.length; });
document.querySelectorAll("[data-example]").forEach((chip) =>
  chip.addEventListener("click", () => { mensaje.value = chip.dataset.example; mensaje.dispatchEvent(new Event("input")); mensaje.focus(); }));

$("suggest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = mensaje.value.trim();
  const errorEl = $("suggest-error");
  if (text.length < 3) return showError(errorEl, "Escribe el mensaje del cliente (mínimo 3 caracteres).");
  if (text.length > MAX_CHARS) return showError(errorEl, `El mensaje excede ${MAX_CHARS} caracteres.`);
  showError(errorEl, "");
  const btn = $("suggest-btn");
  btn.disabled = true; btn.textContent = "Consultando…";
  try {
    const data = await api("/api/v1/suggest", { method: "POST", body: JSON.stringify({ mensaje: text, top_k: Number($("top_k").value) }) });
    renderSuggestion(data);
  } catch (err) {
    showError(errorEl, err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Obtener sugerencia";
  }
});

function renderSuggestion(d) {
  currentSuggestionId = d.id_sugerencia;
  $("suggest-result").hidden = false;
  $("escalation").hidden = !d.escalamiento_requerido;
  $("lowconf").hidden = !d.motivo.confianza_baja;
  $("r-motivo").textContent = d.motivo.etiqueta;
  const pct = Math.round(d.motivo.confianza * 100);
  $("r-conf").textContent = `${pct}%`;
  $("r-bar").style.width = `${pct}%`;
  $("r-mode").textContent = `· modo ${d.modo_generacion}`;
  $("r-sugerencia").value = d.sugerencia;
  setList($("r-fuentes"), d.fuentes, (f) => `${f.id} · ${f.titulo} (score ${f.score.toFixed(3)})`);
  setList($("r-acciones"), d.acciones_sugeridas);
  $("r-masked").textContent = d.mensaje_enmascarado;
  $("r-meta").textContent = `id=${d.id_sugerencia} · latencia=${d.latencia_ms} ms · alternativas: ${d.motivo.alternativas.map((a) => `${a.intent} ${(a.confianza * 100).toFixed(0)}%`).join(", ")}`;
  $("feedback-msg").textContent = "";
  document.querySelectorAll("[data-decision]").forEach((b) => (b.disabled = false));
}

document.querySelectorAll("[data-decision]").forEach((btn) =>
  btn.addEventListener("click", async () => {
    if (!currentSuggestionId) return;
    try {
      const res = await api("/api/v1/feedback", { method: "POST", body: JSON.stringify({ id_sugerencia: currentSuggestionId, decision: btn.dataset.decision }) });
      $("feedback-msg").textContent = `Decisión registrada: ${btn.dataset.decision}. Tasa de aceptación acumulada: ${(res.estadisticas.tasa_aceptacion * 100).toFixed(0)}%`;
      document.querySelectorAll("[data-decision]").forEach((b) => (b.disabled = true));
      refreshAdoption();
    } catch (err) {
      $("feedback-msg").textContent = err.message;
    }
  }));

// ---------- Resumen ----------
const EXAMPLE_CONVERSATION = [
  "Cliente: Hola, me cobraron dos veces 899 pesos en Netflix el 3 de octubre.",
  "Agente: Lamento la situación. ¿Me confirma los últimos 4 dígitos de su tarjeta?",
  "Cliente: Sí, termina en 4821. Solo hice un pago, el otro no lo reconozco.",
  "Agente: Listo, registré la aclaración por el cargo duplicado con folio 55821.",
].join("\n");
$("summary-example").addEventListener("click", () => { $("conversacion").value = EXAMPLE_CONVERSATION; });

function parseConversation(raw) {
  return raw.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
    const m = line.match(/^(cliente|agente)\s*:\s*(.+)$/i);
    if (!m) throw new Error(`Línea sin formato válido: "${line.slice(0, 40)}…" (usa "Cliente:" o "Agente:")`);
    return { rol: m[1].toLowerCase(), texto: m[2] };
  });
}

$("summary-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorEl = $("summary-error");
  let turnos;
  try {
    turnos = parseConversation($("conversacion").value);
    if (!turnos.length) throw new Error("Escribe la conversación a resumir.");
  } catch (err) {
    return showError(errorEl, err.message);
  }
  showError(errorEl, "");
  const btn = $("summary-btn");
  btn.disabled = true;
  try {
    const d = await api("/api/v1/summarize", { method: "POST", body: JSON.stringify({ turnos }) });
    $("summary-result").hidden = false;
    $("s-escalation").hidden = !d.escalamiento_requerido;
    $("s-motivo").textContent = `${d.motivo.etiqueta} (${Math.round(d.motivo.confianza * 100)}%)`;
    $("s-resumen").value = d.resumen;
    setList($("s-entidades"), [...d.entidades.montos.map((m) => `Monto: ${m}`), ...d.entidades.fechas.map((f) => `Fecha: ${f}`)]);
    setList($("s-acciones"), d.acciones_sugeridas);
  } catch (err) {
    showError(errorEl, err.message);
  } finally {
    btn.disabled = false;
  }
});

// ---------- Pestañas ----------
document.querySelectorAll(".tab").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => { t.classList.toggle("is-active", t === tab); t.setAttribute("aria-selected", t === tab); });
    $("panel-suggest").hidden = tab.dataset.tab !== "suggest";
    $("panel-summary").hidden = tab.dataset.tab !== "summary";
  }));

refreshStatus();
