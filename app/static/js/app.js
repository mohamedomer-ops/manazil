"use strict";

const apiStatus = document.getElementById("api-status");
const databaseStatus = document.getElementById("database-status");
const statusLabels = document.querySelector("[data-health-url]").dataset;

function setStatus(element, label, state) {
  element.textContent = label;
  element.dataset.state = state;
}

async function checkHealth() {
  try {
    const response = await fetch(document.querySelector("[data-health-url]").dataset.healthUrl, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    const health = await response.json();
    if (health.service !== "Manazil" || !["connected", "unavailable"].includes(health.database)) {
      throw new Error("Unexpected health response");
    }
    setStatus(apiStatus, statusLabels.connected, "ok");
    const connected = response.ok && health.database === "connected";
    setStatus(databaseStatus, connected ? statusLabels.connected : statusLabels.unavailable, connected ? "ok" : "error");
  } catch {
    setStatus(apiStatus, statusLabels.unavailable, "error");
    setStatus(databaseStatus, statusLabels.unknown, "error");
  }
}

checkHealth();
setInterval(checkHealth, 15000);
