/* LifeVerra app shell — shared header + navigation so the whole patient
   experience feels like one application instead of separate pages.
   Usage: include after api.js, then call renderShell('dashboard') with the
   key of the current page (see NAV below). Requires a page to already
   have requirePatientAuth() called, or pass {public:true}. */

const NAV = [
  { key: "dashboard", href: "dashboard.html", icon: "🏠", label: "Home", inTab: true },
  { key: "health", href: "medical-info.html", icon: "🩺", label: "My Health", inTab: false },
  { key: "emergency", href: "emergency-mode.html", icon: "🚨", label: "Emergency", inTab: true },
  { key: "hospitals", href: "hospitals.html", icon: "🏥", label: "Hospitals", inTab: true },
  { key: "qr", href: "qr-code.html", icon: "🔳", label: "QR Medical ID", inTab: true },
  { key: "contacts", href: "emergency-contacts.html", icon: "📇", label: "Emergency Contacts", inTab: false },
  { key: "history", href: "access-history.html", icon: "📜", label: "History", inTab: false },
  { key: "report", href: "report.html", icon: "🚩", label: "Report Unauthorized Access", inTab: false },
  { key: "settings", href: "settings.html", icon: "⚙️", label: "Profile", inTab: true },
];

function renderShell(activeKey) {
  document.body.classList.add("has-app-shell");

  // Remove any old plain .topbar so pages upgraded to the shell don't show two headers.
  const oldTopbar = document.querySelector(".topbar");
  if (oldTopbar) oldTopbar.remove();

  // Remove any old static bottom tab bar some pages used to hardcode -
  // navigation now lives in one place: the left drawer (hamburger menu),
  // plus the quick links already in the header on wider screens.
  const oldTabbar = document.querySelector("nav.tabbar");
  if (oldTabbar) oldTabbar.remove();

  const header = document.createElement("div");
  header.className = "app-header";
  header.innerHTML = `
    <button class="hamburger" id="lvrHamburger" aria-label="Menu">☰</button>
    <div class="logo">LVR</div>
    <div class="brand">LifeVerra<small>Your Health. Your Safety. Always Connected.</small></div>
    <nav class="app-topnav">
      ${NAV.filter(n => n.inTab).map(n => `<a href="${n.href}" class="${n.key === activeKey ? "active" : ""}">${n.label}</a>`).join("")}
    </nav>
    <div class="spacer"></div>
    <button class="sos-mini" onclick="location.href='emergency-mode.html'">🚨 SOS</button>
  `;
  document.body.prepend(header);

  const overlay = document.createElement("div");
  overlay.className = "drawer-overlay";
  overlay.id = "lvrDrawerOverlay";
  const drawer = document.createElement("div");
  drawer.className = "drawer";
  drawer.id = "lvrDrawer";
  drawer.innerHTML = `
    <div class="drawer-head"><strong>LifeVerra</strong><div style="font-size:11px;color:var(--muted);">Menu</div></div>
    ${NAV.map(n => `<a href="${n.href}" class="${n.key === activeKey ? "active" : ""}"><span>${n.icon}</span>${n.label}</a>`).join("")}
    <a href="#" onclick="logoutPatient();return false;">🚪 Logout</a>
  `;
  document.body.appendChild(overlay);
  document.body.appendChild(drawer);

  function openDrawer() { overlay.classList.add("open"); drawer.classList.add("open"); }
  function closeDrawer() { overlay.classList.remove("open"); drawer.classList.remove("open"); }
  document.getElementById("lvrHamburger").onclick = openDrawer;
  overlay.onclick = closeDrawer;
}

function logoutPatient() {
  localStorage.removeItem("lvr_patient_token");
  localStorage.removeItem("lvr_patient_id");
  location.href = "login.html";
}

function showToast(msg, ms = 3200) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

/* ---- Geolocation helper shared by every page that needs the patient's
   real position. Never falls back to a fake/default location - callers
   must handle the rejected promise and show a clear message instead. ---- */
function getLiveLocation({ highAccuracy = true, timeout = 10000 } = {}) {
  return new Promise((resolve, reject) => {
    if (!window.isSecureContext) {
      reject({ code: "insecure", message: "Location requires HTTPS (or localhost). Open LifeVerra over a secure connection to use GPS." });
      return;
    }
    if (!navigator.geolocation) {
      reject({ code: "unsupported", message: "Geolocation isn't supported by this browser." });
      return;
    }
    navigator.geolocation.getCurrentPosition(
      pos => resolve({
        latitude: pos.coords.latitude,
        longitude: pos.coords.longitude,
        accuracy: pos.coords.accuracy,
        timestamp: pos.timestamp,
      }),
      err => {
        const messages = {
          1: "Location permission denied. Allow location access for LifeVerra in your browser/device settings.",
          2: "Your location is currently unavailable. Try again in an open area.",
          3: "Getting your location timed out. Try again.",
        };
        reject({ code: err.code, message: messages[err.code] || err.message });
      },
      { enableHighAccuracy: highAccuracy, timeout, maximumAge: 0 }
    );
  });
}

/* tel: dialer helper - never fakes a call. Desktop browsers that can't
   launch a phone dialer get an honest message instead of a silent no-op. */
function dialNumber(rawNumber, label) {
  if (!rawNumber) {
    showToast(`No ${label || "phone"} number saved yet.`);
    return;
  }
  const isMobileLike = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const num = rawNumber.replace(/[^0-9+]/g, "");
  if (!isMobileLike) {
    showToast("Calling is available on supported mobile devices. Number: " + rawNumber);
  }
  window.location.href = "tel:" + num;
}
