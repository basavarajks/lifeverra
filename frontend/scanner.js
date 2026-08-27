/* Reusable full-screen camera QR-code scanner for LifeVerra.
   Requires html5-qrcode (loaded on demand from CDN).
   Usage: openQrScanner(decodedText => { ... }) */

function openQrScanner(onResult) {
  const overlay = document.createElement('div');
  overlay.id = 'qr-scan-overlay';
  overlay.style.cssText = `
    position:fixed;inset:0;background:#05101f;z-index:9999;
    display:flex;flex-direction:column;align-items:center;justify-content:center;
    padding:0;
  `;
  overlay.innerHTML = `
    <div style="width:100%;height:100%;display:flex;flex-direction:column;">
      <div style="padding:16px 18px;display:flex;align-items:center;gap:10px;color:#fff;">
        <div style="flex:1;">
          <div style="font-weight:700;font-size:15px;">Scan LifeVerra QR Code</div>
          <div style="font-size:12px;color:#9fb3ca;">Place the QR code inside the frame</div>
        </div>
        <button id="qr-scan-cancel" style="background:rgba(255,255,255,.12);border:none;color:#fff;width:34px;height:34px;border-radius:50%;font-size:16px;cursor:pointer;">✕</button>
      </div>
      <div style="flex:1;position:relative;display:flex;align-items:center;justify-content:center;overflow:hidden;">
        <div id="qr-reader" style="width:100%;height:100%;"></div>
        <div id="qr-scan-frame" style="position:absolute;pointer-events:none;border:3px solid #16c79a;border-radius:18px;box-shadow:0 0 0 2000px rgba(5,16,31,.55);"></div>
        <div id="qr-scan-line" style="position:absolute;height:2px;background:#16c79a;box-shadow:0 0 8px #16c79a;pointer-events:none;"></div>
      </div>
      <div id="qr-scan-error" style="display:none;color:#ff8b83;font-size:13px;text-align:center;padding:0 20px 8px;"></div>
      <div style="display:flex;gap:10px;padding:14px 18px 22px;flex-wrap:wrap;justify-content:center;">
        <button id="qr-switch-cam" style="flex:1;min-width:110px;padding:12px;border:none;border-radius:10px;background:#132b4d;color:#fff;font-weight:600;font-size:13px;cursor:pointer;">🔄 Switch Camera</button>
        <button id="qr-torch" style="flex:1;min-width:110px;padding:12px;border:none;border-radius:10px;background:#132b4d;color:#fff;font-weight:600;font-size:13px;cursor:pointer;display:none;">🔦 Torch</button>
        <button id="qr-cancel-2" style="flex:1;min-width:110px;padding:12px;border:none;border-radius:10px;background:#e0473e;color:#fff;font-weight:700;font-size:13px;cursor:pointer;">Cancel</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // Size the scan frame: large and centered, responsive to viewport.
  const frameEl = document.getElementById('qr-scan-frame');
  const lineEl = document.getElementById('qr-scan-line');
  function sizeFrame() {
    const box = Math.min(window.innerWidth, window.innerHeight) * 0.72;
    frameEl.style.width = box + 'px';
    frameEl.style.height = box + 'px';
    frameEl.style.top = '50%';
    frameEl.style.left = '50%';
    frameEl.style.transform = 'translate(-50%,-50%)';
    lineEl.style.width = box + 'px';
    lineEl.style.left = '50%';
    lineEl.style.top = '50%';
    lineEl.style.marginLeft = -(box / 2) + 'px';
  }
  sizeFrame();
  window.addEventListener('resize', sizeFrame);

  // Animate the scan line.
  let lineOffset = 0, lineDir = 1, lineAnim;
  function animateLine() {
    const box = frameEl.offsetHeight;
    lineOffset += lineDir * 2.4;
    if (lineOffset > box - 2 || lineOffset < 0) lineDir *= -1;
    lineEl.style.marginTop = (-(box / 2) + lineOffset) + 'px';
    lineAnim = requestAnimationFrame(animateLine);
  }
  animateLine();

  let html5QrCode;
  let stopped = false;
  let lastResult = null, lastResultAt = 0;
  let currentCameraId = null;
  let cameras = [];
  let torchOn = false;

  function cleanup() {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(lineAnim);
    window.removeEventListener('resize', sizeFrame);
    if (html5QrCode) {
      html5QrCode.stop().then(() => html5QrCode.clear()).catch(() => {});
    }
    overlay.remove();
  }
  document.getElementById('qr-scan-cancel').onclick = cleanup;
  document.getElementById('qr-cancel-2').onclick = cleanup;

  function onDecoded(decodedText) {
    // Duplicate-result prevention: ignore the same code re-firing within 2s.
    const now = Date.now();
    if (decodedText === lastResult && now - lastResultAt < 2000) return;
    lastResult = decodedText;
    lastResultAt = now;
    stopped = true;
    cancelAnimationFrame(lineAnim);
    html5QrCode.stop().then(() => html5QrCode.clear()).catch(() => {});
    overlay.remove();
    onResult(decodedText);
  }

  function startWithCamera(cameraId) {
    currentCameraId = cameraId;
    const config = {
      fps: 15,
      qrbox: (vw, vh) => {
        const size = Math.floor(Math.min(vw, vh) * 0.72);
        return { width: size, height: size };
      },
      aspectRatio: 1.0,
      // Restrict to QR-only decoding where the library supports it, for speed/accuracy.
      formatsToSupport: (window.Html5QrcodeSupportedFormats && [window.Html5QrcodeSupportedFormats.QR_CODE]) || undefined,
    };
    html5QrCode.start(cameraId, config, onDecoded, () => { /* per-frame miss, ignore */ })
      .then(() => {
        // Torch support detection (best-effort — not all browsers/devices expose this).
        try {
          const capabilities = html5QrCode.getRunningTrackCapabilities && html5QrCode.getRunningTrackCapabilities();
          if (capabilities && capabilities.torch) {
            document.getElementById('qr-torch').style.display = 'block';
          }
        } catch (e) { /* not supported */ }
      })
      .catch(showCamError);
  }

  function showCamError() {
    const errEl = document.getElementById('qr-scan-error');
    errEl.style.display = 'block';
    errEl.textContent = "Couldn't access the camera. Check camera permissions in your browser/device settings, or use manual entry.";
  }

  function startScanning() {
    html5QrCode = new Html5Qrcode("qr-reader", { verbose: false });
    Html5Qrcode.getCameras().then(devices => {
      cameras = devices || [];
      if (!cameras.length) { showCamError(); return; }
      // Prefer the rear/environment camera for scanning.
      const rear = cameras.find(c => /back|rear|environment/i.test(c.label)) || cameras[cameras.length - 1];
      startWithCamera(rear.id);
    }).catch(() => {
      // Fallback: some browsers only support facingMode without enumeration.
      html5QrCode.start({ facingMode: "environment" }, { fps: 15, qrbox: 260 }, onDecoded, () => {}).catch(showCamError);
    });
  }

  document.getElementById('qr-switch-cam').onclick = () => {
    if (cameras.length < 2 || !html5QrCode) { showToastLike("Only one camera available."); return; }
    const idx = cameras.findIndex(c => c.id === currentCameraId);
    const next = cameras[(idx + 1) % cameras.length];
    html5QrCode.stop().then(() => {
      document.getElementById('qr-torch').style.display = 'none';
      startWithCamera(next.id);
    }).catch(() => {});
  };

  document.getElementById('qr-torch').onclick = () => {
    if (!html5QrCode) return;
    torchOn = !torchOn;
    html5QrCode.applyVideoConstraints({ advanced: [{ torch: torchOn }] }).catch(() => {
      showToastLike("Torch isn't supported on this device.");
      torchOn = !torchOn;
    });
  };

  function showToastLike(msg) {
    const errEl = document.getElementById('qr-scan-error');
    errEl.style.display = 'block';
    errEl.style.color = '#9fd8cd';
    errEl.textContent = msg;
    setTimeout(() => { errEl.style.display = 'none'; }, 2500);
  }

  if (typeof Html5Qrcode === 'undefined') {
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
    script.onload = startScanning;
    script.onerror = () => {
      const errEl = document.getElementById('qr-scan-error');
      errEl.style.display = 'block';
      errEl.textContent = "Scanner library failed to load. Check your internet connection, or use manual entry below.";
    };
    document.head.appendChild(script);
  } else {
    startScanning();
  }
}

/* Extracts the LifeVerra ID from decoded QR text.
   QR content is a full URL "https://.../emergency.html?lv=LVERRA-2026-XXXXX"
   (preferred, so phone camera apps open it directly) - also tolerates a
   raw ID, or the legacy "LIFEVERRA:ID" text format. */
function extractLifeVerraId(decodedText) {
  const text = decodedText.trim();
  const urlMatch = text.match(/[?&]lv=([^&]+)/i);
  if (urlMatch) return decodeURIComponent(urlMatch[1]);
  const prefixMatch = text.match(/LIFEVERRA:(\S+)/i);
  if (prefixMatch) return prefixMatch[1];
  const idMatch = text.match(/LVERRA-\d{4}-\d+/i);
  if (idMatch) return idMatch[0];
  return text; // fall back to whatever was scanned
}

/* Validates that a decoded/entered value actually looks like a LifeVerra ID
   before the app tries to use it - avoids treating arbitrary scanned text
   as a medical QR. */
function isValidLifeVerraId(id) {
  return typeof id === 'string' && /^LVERRA-\d{4}-\d+$/i.test(id.trim());
}
