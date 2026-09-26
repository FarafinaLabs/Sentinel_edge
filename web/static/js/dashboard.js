/**
 * Sentinel-Edge — Script du Dashboard d'Ingestion Vidéo
 * Auteur : AMADOU H TRAORE (Pôle IA)
 */

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    lucide.createIcons();
  }

  // Événements boutons
  const btnSnapshotHeader = document.getElementById("btn-snapshot-header");
  if (btnSnapshotHeader) {
    btnSnapshotHeader.addEventListener("click", takeSnapshot);
  }

  // Démarrage des boucles de télémétrie
  fetchTelemetry();
  setInterval(fetchTelemetry, 1000);

  fetchLogs();
  setInterval(fetchLogs, 3000);

  fetchSnapshots();
});

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  const colors = {
    info: "border-cyan-500/50 bg-slate-900/90 text-cyan-300",
    success: "border-emerald-500/50 bg-slate-900/90 text-emerald-300",
    warning: "border-amber-500/50 bg-slate-900/90 text-amber-300",
    error: "border-red-500/50 bg-slate-900/90 text-red-300",
  };

  toast.className = `pointer-events-auto flex items-center space-x-2 px-4 py-2.5 rounded-xl border text-xs shadow-xl backdrop-blur-md transition-all duration-300 transform translate-y-2 opacity-0 ${colors[type] || colors.info}`;
  toast.innerHTML = `<span>${message}</span>`;

  container.appendChild(toast);

  // Animation d'apparition
  requestAnimationFrame(() => {
    toast.classList.remove("translate-y-2", "opacity-0");
  });

  // Disparition après 3.5s
  setTimeout(() => {
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Récupération de la télémétrie en temps réel
async function fetchTelemetry() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error("HTTP error " + res.status);
    const data = await res.json();

    // Mise à jour des badges Header & Status
    const statusText = document.getElementById("header-status-text");
    const statusIndicator = document.getElementById("header-status-indicator");
    const headerFps = document.getElementById("header-fps");
    const toolbarFps = document.getElementById("toolbar-fps");
    const overlaySource = document.getElementById("overlay-source");
    const overlayResolution = document.getElementById("overlay-resolution");
    const sourceBadgeType = document.getElementById("source-badge-type");

    if (statusText) statusText.textContent = data.state;
    if (headerFps) headerFps.textContent = `${data.fps} FPS`;
    if (toolbarFps) toolbarFps.textContent = `${data.fps} FPS`;
    if (overlaySource) overlaySource.textContent = `Source: ${data.source}`;
    if (overlayResolution) overlayResolution.textContent = data.resolution;
    if (sourceBadgeType) sourceBadgeType.textContent = data.source_type;

    const customInput = document.getElementById("custom-source-input");
    if (customInput && document.activeElement !== customInput && typeof data.source === "string" && data.source.startsWith("http")) {
      customInput.value = data.source;
    }

    // Statut & couleurs du voyant
    if (statusIndicator) {
      statusIndicator.className = "w-2.5 h-2.5 rounded-full animate-pulse";
      if (data.state === "CONNECTED") {
        statusIndicator.classList.add("bg-emerald-500");
      } else if (data.state === "RECONNECTING" || data.state === "CONNECTING") {
        statusIndicator.classList.add("bg-amber-500");
      } else {
        statusIndicator.classList.add("bg-red-500");
      }
    }

    // Statistiques rapides
    const statFps = document.getElementById("stat-fps");
    const statFrames = document.getElementById("stat-frames");
    const statDrops = document.getElementById("stat-drops");
    const statUptime = document.getElementById("stat-uptime");

    if (statFps) statFps.textContent = `${data.fps}`;
    if (statFrames) statFrames.textContent = data.total_frames.toLocaleString();
    if (statDrops) statDrops.textContent = data.dropped_frames.toLocaleString();
    if (statUptime) statUptime.textContent = `${data.uptime_seconds}s`;

    // État de l'IA
    const aiBadge = document.getElementById("overlay-ai-badge");
    const aiCheckbox = document.getElementById("toggle-ai-checkbox");
    if (aiBadge) {
      if (data.ai_enabled) {
        aiBadge.textContent = "IA YOLOv8: ACTIF";
        aiBadge.className = "bg-emerald-500/20 backdrop-blur-md border border-emerald-500/50 text-emerald-300 text-xs font-mono font-semibold px-2.5 py-1 rounded-md";
      } else {
        aiBadge.textContent = "IA YOLOv8: OFF";
        aiBadge.className = "bg-black/60 backdrop-blur-md border border-slate-700 text-slate-400 text-xs font-mono px-2.5 py-1 rounded-md";
      }
    }
    if (aiCheckbox && document.activeElement !== aiCheckbox) {
      aiCheckbox.checked = Boolean(data.ai_enabled);
    }

  } catch (err) {
    console.debug("Telemetry polling skipped:", err);
  }
}

// Changement de source vidéo
async function setSource(sourceValue) {
  try {
    const res = await fetch("/api/source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: sourceValue }),
    });
    const json = await res.json();
    if (json.success) {
      showToast(`Source vidéo basculée vers : ${sourceValue}`, "success");
      reloadStream();
    } else {
      showToast(`Erreur : ${json.error}`, "error");
    }
  } catch (e) {
    showToast("Échec du changement de source", "error");
  }
}

// Soumission du formulaire d'URL personnalisée (Smartphone)
function submitCustomSource() {
  const input = document.getElementById("custom-source-input");
  if (!input || !input.value.trim()) {
    showToast("Veuillez saisir une URL valide", "warning");
    return;
  }
  setSource(input.value.trim());
}

// Rechargement du flux vidéo (force refresh)
function reloadStream() {
  const img = document.getElementById("video-stream");
  if (img) {
    const container = img.parentNode;
    // Supprimer l'ancienne image pour forcer le navigateur à couper la socket HTTP
    img.src = "";
    img.remove();
    
    // Attendre un peu pour permettre au backend de se connecter à la nouvelle source
    setTimeout(() => {
      const newImg = document.createElement("img");
      newImg.id = "video-stream";
      newImg.alt = "Flux Vidéo Sentinel-Edge";
      newImg.className = "w-full h-full object-contain";
      newImg.src = "/video_feed?t=" + new Date().getTime();
      
      // Réinsérer au début du conteneur
      container.insertBefore(newImg, container.firstChild);
    }, 800); // Délai de 800ms pour laisser le temps à la caméra IP de répondre
  }
}

// Prise de Snapshot instantané
async function takeSnapshot() {
  try {
    const res = await fetch("/api/snapshot", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(`Cliché capturé : ${data.filename}`, "success");
      fetchSnapshots();
    } else {
      showToast("Erreur lors de la capture", "error");
    }
  } catch (e) {
    showToast("Erreur réseau lors du snapshot", "error");
  }
}

// Bascule Détection IA YOLOv8
async function toggleAI() {
  const checkbox = document.getElementById("toggle-ai-checkbox");
  const targetState = checkbox ? checkbox.checked : false;

  try {
    const res = await fetch("/api/toggle_ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: targetState }),
    });
    const data = await res.json();
    if (data.success) {
      showToast(
        data.ai_enabled ? "Détecteur YOLOv8 activé" : "Détecteur YOLOv8 désactivé",
        data.ai_enabled ? "warning" : "info"
      );
    }
  } catch (e) {
    showToast("Échec de la bascule IA", "error");
  }
}

// Récupération de la galerie de snapshots
async function fetchSnapshots() {
  try {
    const res = await fetch("/api/snapshots");
    if (!res.ok) return;
    const snapshots = await res.json();

    const gallery = document.getElementById("snapshots-gallery");
    const countLabel = document.getElementById("snapshot-count");
    if (!gallery) return;

    if (countLabel) {
      countLabel.textContent = `${snapshots.length} enregistré(s)`;
    }

    if (!snapshots.length) {
      gallery.innerHTML = `
        <div class="col-span-full py-8 text-center text-xs text-slate-500">
          Aucun snapshot pris pour le moment. Cliquez sur "Snapshot" pour capturer une frame.
        </div>`;
      return;
    }

    gallery.innerHTML = snapshots
      .map(
        (s) => `
      <div class="group relative rounded-xl overflow-hidden border border-slate-800 bg-slate-950 aspect-video">
        <img src="${s.url}" alt="${s.filename}" class="w-full h-full object-cover">
        <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-between p-2">
          <div class="text-[10px] font-mono text-cyan-300 truncate">${s.filename}</div>
          <div class="flex items-center justify-between">
            <span class="text-[9px] text-slate-400">${s.created_at}</span>
            <a href="${s.url}" target="_blank" download class="text-[10px] bg-cyan-500 text-black font-semibold px-2 py-0.5 rounded">
              Télécharger
            </a>
          </div>
        </div>
      </div>
    `
      )
      .join("");
  } catch (e) {
    console.debug("Error fetching snapshots:", e);
  }
}

// Récupération des logs
async function fetchLogs() {
  try {
    const res = await fetch("/api/logs");
    if (!res.ok) return;
    const logs = await res.json();

    const container = document.getElementById("log-container");
    if (!container) return;

    const colors = {
      INFO: "text-slate-400",
      SUCCESS: "text-emerald-400",
      WARNING: "text-amber-400",
      ERROR: "text-red-400",
    };

    container.innerHTML = logs
      .map(
        (l) =>
          `<div><span class="text-slate-500">[${l.time}]</span> <span class="${colors[l.level] || 'text-slate-300'}">${l.message}</span></div>`
      )
      .join("");

    container.scrollTop = container.scrollHeight;
  } catch (e) {
    console.debug("Error fetching logs:", e);
  }
}

// Plein écran pour le flux vidéo
function toggleFullscreen() {
  const elem = document.getElementById("video-stream");
  if (!elem) return;

  if (!document.fullscreenElement) {
    if (elem.requestFullscreen) {
      elem.requestFullscreen();
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen();
    }
  }
}

// Modale d'aide Smartphone
function showHelpModal() {
  const modal = document.getElementById("help-modal");
  if (modal) modal.classList.remove("hidden");
  if (window.lucide) lucide.createIcons();
}

function hideHelpModal() {
  const modal = document.getElementById("help-modal");
  if (modal) modal.classList.add("hidden");
}
