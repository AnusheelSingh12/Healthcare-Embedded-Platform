const refs = {
  toolsInTableBody: document.getElementById("toolsInTableBody"),
  toolsOutTableBody: document.getElementById("toolsOutTableBody"),
  allHistoryTableBody: document.getElementById("allHistoryTableBody"),
  allHistoryPanel: document.getElementById("allHistoryPanel"),
  showAllHistoryBtn: document.getElementById("showAllHistoryBtn"),
  hideAllHistoryBtn: document.getElementById("hideAllHistoryBtn"),
  clearHistoryBtn: document.getElementById("clearHistoryBtn"),
  editUidSelect: document.getElementById("editUidSelect"),
  newUidInput: document.getElementById("newUidInput"),
  nameInput: document.getElementById("nameInput"),
  refreshItemsBtn: document.getElementById("refreshItemsBtn"),
  saveItemBtn: document.getElementById("saveItemBtn"),
  editMessage: document.getElementById("editMessage"),
};

const excludedEditUids = new Set(["RFID-2001", "RFID-2003", "RFID-2004", "RFID-2006", "3CA54A06"]);

let itemsCache = [];
let socket = null;
let allHistoryVisible = false;

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function renderTable(tableBody, rows, emptyText) {
  tableBody.innerHTML = "";
  if (!rows.length) {
    const row = document.createElement("tr");
    row.innerHTML = `<td colspan="3" class="muted">${emptyText}</td>`;
    tableBody.appendChild(row);
    return;
  }

  for (const tool of rows) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${tool.uid}</td>
      <td>${tool.name}</td>
      <td>${formatTime(tool.time)}</td>
    `;
    tableBody.appendChild(row);
  }
}

function renderAllHistory(events) {
  refs.allHistoryTableBody.innerHTML = "";
  if (!events.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="6" class="muted">No movement history found.</td>';
    refs.allHistoryTableBody.appendChild(row);
    return;
  }

  for (const eventRow of events) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${eventRow.uid}</td>
      <td>${eventRow.name}</td>
      <td>${eventRow.action}</td>
      <td>${formatTime(eventRow.timestamp)}</td>
      <td>${eventRow.gauze_count}</td>
      <td>${eventRow.tools_missing}</td>
    `;
    refs.allHistoryTableBody.appendChild(row);
  }
}

function getSelectedItem() {
  const uid = refs.editUidSelect.value;
  return itemsCache.find((item) => item.uid === uid) || null;
}

function fillFormFromSelectedItem() {
  const item = getSelectedItem();
  if (!item) {
    refs.nameInput.value = "";
    refs.editMessage.textContent = "No item selected.";
    return;
  }

  refs.newUidInput.value = "";
  refs.nameInput.value = item.name;
  refs.editMessage.textContent = `Editing ${item.uid}`;
}

async function fetchItems() {
  const response = await fetch("/api/items");
  const data = await response.json();
  itemsCache = (data.items || []).filter((item) => !excludedEditUids.has(item.uid));

  refs.editUidSelect.innerHTML = "";
  if (!itemsCache.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No editable items";
    refs.editUidSelect.appendChild(option);
    fillFormFromSelectedItem();
    return;
  }

  for (const item of itemsCache) {
    const option = document.createElement("option");
    option.value = item.uid;
    option.textContent = `${item.uid} - ${item.name}`;
    refs.editUidSelect.appendChild(option);
  }

  fillFormFromSelectedItem();
}

async function fetchPresence() {
  const response = await fetch("/api/tools/presence");
  const data = await response.json();
  renderTable(refs.toolsInTableBody, data.in_tools || [], "No tools currently IN.");
  renderTable(refs.toolsOutTableBody, data.out_tools || [], "No tools currently OUT.");
}

async function fetchAllHistory() {
  const response = await fetch("/api/events?limit=1000");
  const data = await response.json();
  renderAllHistory(data.events || []);
}

async function showAllHistory() {
  allHistoryVisible = true;
  refs.allHistoryPanel.hidden = false;
  refs.showAllHistoryBtn.hidden = true;
  refs.hideAllHistoryBtn.hidden = false;
  await fetchAllHistory();
}

function hideAllHistory() {
  allHistoryVisible = false;
  refs.allHistoryPanel.hidden = true;
  refs.showAllHistoryBtn.hidden = false;
  refs.hideAllHistoryBtn.hidden = true;
}

async function clearHistoryTable() {
  const response = await fetch("/api/events/clear", { method: "POST" });
  const data = await response.json();
  if (!response.ok || !data.cleared) {
    refs.editMessage.textContent = "Failed to clear table data.";
    return;
  }

  refs.editMessage.textContent = "Table data cleared successfully.";
  await Promise.all([fetchPresence(), fetchAllHistory()]);
}

async function saveItemChanges() {
  const selected = getSelectedItem();
  if (!selected) {
    refs.editMessage.textContent = "Select an item to edit.";
    return;
  }

  const payload = {
    new_uid: refs.newUidInput.value.trim() || null,
    name: refs.nameInput.value.trim(),
    category: null,
    status: null,
  };

  const response = await fetch(`/api/items/${encodeURIComponent(selected.uid)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const data = await response.json();
  if (!response.ok) {
    refs.editMessage.textContent = data.detail || "Update failed.";
    return;
  }

  refs.editMessage.textContent = `Updated ${data.item.uid} successfully.`;
  await fetchItems();
}

function connectSocket() {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${location.host}/ws/rfid`);

  socket.addEventListener("message", async (event) => {
    const payload = JSON.parse(event.data);
    if (payload.event === "scan") {
      if (allHistoryVisible) {
        await Promise.all([fetchPresence(), fetchAllHistory()]);
      } else {
        await fetchPresence();
      }
    }
  });

  socket.addEventListener("close", () => {
    setTimeout(connectSocket, 1500);
  });
}

refs.refreshItemsBtn.addEventListener("click", fetchItems);
refs.saveItemBtn.addEventListener("click", saveItemChanges);
refs.editUidSelect.addEventListener("change", fillFormFromSelectedItem);
refs.showAllHistoryBtn.addEventListener("click", showAllHistory);
refs.hideAllHistoryBtn.addEventListener("click", hideAllHistory);
refs.clearHistoryBtn.addEventListener("click", clearHistoryTable);

(async function bootstrap() {
  await Promise.all([fetchItems(), fetchPresence()]);
  connectSocket();
})();
