const state = {
  socket: null,
};

const refs = {
  portSelect: document.getElementById("portSelect"),
  refreshPortsBtn: document.getElementById("refreshPortsBtn"),
  connectBtn: document.getElementById("connectBtn"),
  disconnectBtn: document.getElementById("disconnectBtn"),
  portMessage: document.getElementById("portMessage"),
  socketStatus: document.getElementById("socketStatus"),
  liveCard: document.getElementById("liveScanCard"),
  liveUid: document.getElementById("liveUid"),
  liveName: document.getElementById("liveName"),
  liveCategory: document.getElementById("liveCategory"),
  liveStatus: document.getElementById("liveStatus"),
  liveAction: document.getElementById("liveAction"),
  liveSeen: document.getElementById("liveSeen"),
  statRegistered: document.getElementById("statRegistered"),
  statGauzeUsed: document.getElementById("statGauzeUsed"),
  statToolsMissing: document.getElementById("statToolsMissing"),
  categoryGrid: document.getElementById("categoryGrid"),
};

function setSocketStatus(label, className) {
  refs.socketStatus.textContent = label;
  refs.socketStatus.className = `badge ${className}`;
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "in use") return "in-use";
  if (normalized === "sterilized") return "sterilized";
  if (normalized === "missing") return "missing";
  if (normalized === "unknown") return "unknown";
  return "neutral";
}

function updateLiveScan(payload) {
  refs.liveUid.textContent = payload.uid || "-";
  refs.liveName.textContent = payload.name || "-";
  refs.liveCategory.textContent = payload.category || "-";
  refs.liveStatus.textContent = payload.status || "Unknown";
  refs.liveStatus.className = `badge ${statusClass(payload.status)}`;
  refs.liveAction.textContent = `Action: ${payload.action || "-"}`;
  refs.liveSeen.textContent = `Device time: ${payload.timestamp || "--"}`;

  refs.liveCard.classList.remove("scan-pulse");
  void refs.liveCard.offsetWidth;
  refs.liveCard.classList.add("scan-pulse");
}

function updateStats(stats) {
  if (!stats) return;
  refs.statRegistered.textContent = stats.total_registered ?? 0;
  refs.statGauzeUsed.textContent = stats.gauze_used ?? 0;
  refs.statToolsMissing.textContent = stats.tools_missing ?? 0;
}

function updateCategoryText(items) {
  if (!Array.isArray(items)) return;
  refs.categoryGrid.innerHTML = "";

  const excludedUids = new Set(["RFID-2001", "RFID-2003", "RFID-2004", "RFID-2006", "3CA54A06"]);
  const filteredItems = items.filter((item) => !excludedUids.has(item.uid));

  if (!filteredItems.length) {
    const cell = document.createElement("div");
    cell.className = "category-cell";
    cell.innerHTML = `<p class="name">No items yet</p>`;
    refs.categoryGrid.appendChild(cell);
    return;
  }

  const preferredRows = [
    { uid: "EEF73206", name: "Curved Artery Forceps" },
    { uid: "426F3406", name: "Kidney Tray" },
    { uid: "ACA54A06", name: "Scalpel" },
  ];

  const byUid = new Map(filteredItems.map((item) => [item.uid, item]));
  const ordered = [];
  for (const row of preferredRows) {
    const match = byUid.get(row.uid);
    ordered.push({
      uid: row.uid,
      name: match?.name || row.name,
    });
    if (match) byUid.delete(row.uid);
  }
  ordered.push(...Array.from(byUid.values()).sort((a, b) => a.uid.localeCompare(b.uid)));

  for (const entry of ordered) {
    const cell = document.createElement("div");
    cell.className = "category-cell category-text-row";
    cell.innerHTML = `
      <p class="name">${entry.uid}</p>
      <p>${entry.name}</p>
      <p class="muted">-</p>
    `;
    refs.categoryGrid.appendChild(cell);
  }
}

async function fetchPorts() {
  const response = await fetch("/api/ports");
  const data = await response.json();
  refs.portSelect.innerHTML = "";

  for (const port of data.ports || []) {
    const option = document.createElement("option");
    option.value = port.device;
    option.textContent = `${port.device} - ${port.description || "Serial Device"}`;
    refs.portSelect.appendChild(option);
  }

  if (!refs.portSelect.options.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No ports detected";
    refs.portSelect.appendChild(option);
  }
}

async function fetchInitialDashboardData() {
  const [statsRes, itemsRes, statusRes] = await Promise.all([
    fetch("/api/stats"),
    fetch("/api/items"),
    fetch("/api/status"),
  ]);

  const stats = await statsRes.json();
  const items = await itemsRes.json();
  const status = await statusRes.json();

  updateStats(stats);
  updateCategoryText(items.items || []);
  refs.portMessage.textContent = status.connected
    ? `Connected to ${status.port}`
    : "Choose a port to begin listening.";
  setSocketStatus(status.connected ? "Socket: Live" : "Socket: Idle", status.connected ? "in-use" : "unknown");
}

function connectSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  setSocketStatus("Socket: Connecting", "neutral");
  const socket = new WebSocket(`${protocol}://${location.host}/ws/rfid`);

  socket.addEventListener("open", () => {
    // WebSocket is open, but listener may still be disconnected.
    setSocketStatus("Socket: Connected", "neutral");
  });

  socket.addEventListener("message", async (event) => {
    const payload = JSON.parse(event.data);

    if (payload.event === "scan") {
      updateLiveScan(payload);
      updateStats(payload.quick_stats);
      await fetchInitialDashboardData();
      refs.portMessage.textContent = `${payload.action} event from ${payload.uid}`;
      return;
    }

    if (payload.event === "error") {
      refs.portMessage.textContent = payload.message;
      return;
    }

    if (payload.event === "listener_status") {
      refs.portMessage.textContent = payload.connected
        ? `Connected to ${payload.port}`
        : "Listener is disconnected.";
      setSocketStatus(payload.connected ? "Socket: Live" : "Socket: Idle", payload.connected ? "in-use" : "unknown");
    }
  });

  socket.addEventListener("close", async () => {
    setSocketStatus("Socket: Reconnecting", "unknown");
    setTimeout(connectSocket, 1500);
    await fetchInitialDashboardData();
  });

  state.socket = socket;
}

async function connectPort() {
  const selectedPort = refs.portSelect.value;
  if (!selectedPort) {
    refs.portMessage.textContent = "Select a valid port.";
    return;
  }

  const response = await fetch("/api/connect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ port: selectedPort }),
  });

  const data = await response.json();
  if (!response.ok) {
    refs.portMessage.textContent = data.detail || "Failed to connect.";
    setSocketStatus("Socket: Idle", "unknown");
    return;
  }

  refs.portMessage.textContent = `Connected to ${data.port}`;
  setSocketStatus("Socket: Live", "in-use");
}

async function disconnectPort() {
  await fetch("/api/disconnect", { method: "POST" });
  refs.portMessage.textContent = "Disconnected from serial port.";
  setSocketStatus("Socket: Idle", "unknown");
}

refs.refreshPortsBtn.addEventListener("click", fetchPorts);
refs.connectBtn.addEventListener("click", connectPort);
refs.disconnectBtn.addEventListener("click", disconnectPort);

(async function bootstrap() {
  await Promise.all([fetchPorts(), fetchInitialDashboardData()]);
  connectSocket();
})();
