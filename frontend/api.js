const API = "";  // same-origin, backend serves the frontend too

async function apiFetch(path, { method = "GET", body, auth = true, isForm = false } = {}) {
  const headers = {};
  if (!isForm) headers["Content-Type"] = "application/json";
  const tokenKey = auth === "doctor" ? "lvr_doctor_token" : "lvr_patient_token";
  const token = localStorage.getItem(tokenKey);
  if (auth && token) headers["Authorization"] = "Bearer " + token;

  const res = await fetch(API + path, {
    method,
    headers,
    body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
  });

  let data = null;
  try { data = await res.json(); } catch (e) { /* no body */ }

  if (!res.ok) {
    let msg = (data && data.detail) ? data.detail : `Request failed (${res.status})`;
    // Codes like 521/522/523/530/502/504 with no JSON body come from the
    // tunnel/proxy in front of the backend, not from the app itself — the
    // backend process isn't reachable at all (stopped, crashed, tunnel URL
    // expired, laptop asleep, etc.), so surface that clearly instead of a
    // bare status code.
    const tunnelCodes = [502, 503, 504, 521, 522, 523, 524, 530];
    if (!data && tunnelCodes.includes(res.status)) {
      msg = `Can't reach the server right now (error ${res.status}). This usually means the backend isn't running or the tunnel/HTTPS URL has expired — restart "uvicorn app:app" and your Cloudflare tunnel, then reload this page.`;
    }
    throw new Error(msg);
  }
  return data;
}

function requirePatientAuth() {
  if (!localStorage.getItem("lvr_patient_token")) {
    window.location.href = "login.html";
  }
}

function requireDoctorAuth() {
  if (!localStorage.getItem("lvr_doctor_token")) {
    window.location.href = "doctor-login.html";
  }
}

function showError(el, msg) {
  el.textContent = msg;
  el.style.display = "block";
}
function hideError(el) {
  el.style.display = "none";
}

// Registered site-wide (not just on the QR page) so the browser has as
// much time as possible to satisfy its installability checks before
// someone taps "Quick Access from Home Screen" - registering it late,
// only on that one page, right before checking for the install prompt,
// is often too late for Chrome to have decided the site is installable yet.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
