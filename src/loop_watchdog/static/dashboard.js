const REFRESH_MS = Number(document.body.dataset.refreshMs || "3000");
const URL_SESSION = new URLSearchParams(window.location.search).get("session");

const state = {
  snapshot: null,
  selectedSessionId: URL_SESSION,
  loading: false,
};

const elements = {
  overviewStats: document.getElementById("overview-stats"),
  heroStats: document.getElementById("hero-stats"),
  sessionList: document.getElementById("session-list"),
  selectedStage: document.getElementById("selected-stage"),
  selectedSession: document.getElementById("selected-session"),
  selectedSummary: document.getElementById("selected-summary"),
  selectedBadges: document.getElementById("selected-badges"),
  incidentPanel: document.getElementById("incident-panel"),
  timeline: document.getElementById("timeline"),
  operatorNote: document.getElementById("operator-note"),
  actionFeedback: document.getElementById("action-feedback"),
  lastRefresh: document.getElementById("last-refresh"),
  clearHistoryButton: document.getElementById("clear-history-button"),
  resumeButton: document.getElementById("resume-button"),
  resumeResetButton: document.getElementById("resume-reset-button"),
  acknowledgeButton: document.getElementById("acknowledge-button"),
  archiveButton: document.getElementById("archive-button"),
  killButton: document.getElementById("kill-button"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDate(value) {
  if (!value) {
    return "No activity";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatRelative(value) {
  if (!value) {
    return "No activity yet";
  }
  const deltaSeconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const steps = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
    ["second", 1],
  ];
  for (const [unit, size] of steps) {
    if (Math.abs(deltaSeconds) >= size || unit === "second") {
      return rtf.format(Math.round(deltaSeconds / size), unit);
    }
  }
  return "just now";
}

function sessionById(sessionId) {
  return state.snapshot?.sessions?.find((session) => session.session_id === sessionId) ?? null;
}

function chooseSelectedSession() {
  const sessions = state.snapshot?.sessions ?? [];
  if (sessions.length === 0) {
    state.selectedSessionId = null;
    return null;
  }

  const existing = sessionById(state.selectedSessionId);
  if (existing) {
    return existing;
  }

  const paused = sessions.find((session) => session.paused);
  state.selectedSessionId = (paused ?? sessions[0]).session_id;
  return sessionById(state.selectedSessionId);
}

function renderOverview(snapshot) {
  const stats = [
    { label: "Sessions", value: snapshot.total_sessions, tone: "sessions" },
    { label: "Paused", value: snapshot.paused_sessions, tone: "paused" },
    { label: "Events", value: snapshot.total_events, tone: "events" },
    { label: "Incidents", value: snapshot.active_incidents, tone: "incidents" },
  ];
  elements.overviewStats.innerHTML = stats
    .map(
      (stat) => `
        <article class="stat-tile stat-tile-stat-${escapeHtml(stat.tone)}">
          <div class="stat-tile-label">${escapeHtml(stat.label)}</div>
          <div class="stat-tile-value">${escapeHtml(stat.value)}</div>
        </article>
      `,
    )
    .join("");

  const heroStats = [
    {
      label: "Sessions under watch",
      value: snapshot.total_sessions,
      note: snapshot.total_sessions === 1 ? "1 active thread" : `${snapshot.total_sessions} active threads`,
    },
    {
      label: "Paused by watchdog",
      value: snapshot.paused_sessions,
      note: snapshot.paused_sessions > 0 ? "Intervention required" : "No intervention needed",
    },
    {
      label: "Recent signal volume",
      value: snapshot.total_events,
      note: "Events captured in memory",
    },
    {
      label: "Acknowledged sessions",
      value: snapshot.acknowledged_sessions,
      note: snapshot.archived_sessions > 0 ? `${snapshot.archived_sessions} archived` : "No archived sessions",
    },
  ];
  elements.heroStats.innerHTML = heroStats
    .map(
      (stat) => `
        <article class="hero-stat">
          <div class="hero-stat-label">${escapeHtml(stat.label)}</div>
          <div class="hero-stat-value">${escapeHtml(stat.value)}</div>
          <div class="hero-stat-note">${escapeHtml(stat.note)}</div>
        </article>
      `,
    )
    .join("");
}

function renderSessionList(snapshot, selectedSessionId) {
  if (snapshot.sessions.length === 0) {
    elements.sessionList.innerHTML = `
      <div class="empty-panel">
        No sessions have reported yet. Start posting events or route a model call through the proxy.
      </div>
    `;
    return;
  }

  elements.sessionList.innerHTML = snapshot.sessions
    .map((session) => {
      const pausedBadge = session.paused
        ? `<span class="badge badge-paused">Paused</span>`
        : `<span class="badge badge-live">Watching</span>`;
      const stage = session.current_stage || "idle";
      const isSelected = session.session_id === selectedSessionId;
      return `
        <article
          class="session-card ${session.paused ? "is-paused" : ""} ${isSelected ? "is-selected" : ""}"
          data-session-id="${escapeHtml(session.session_id)}"
        >
          <div class="session-header">
            <div class="session-title mono">${escapeHtml(session.session_id)}</div>
            ${pausedBadge}
          </div>

          <div class="session-summary">${escapeHtml(session.last_summary || "No summary yet.")}</div>

          <div class="session-meta">
            <span class="badge badge-stage">${escapeHtml(stage)}</span>
            <span class="badge badge-neutral">${escapeHtml(formatRelative(session.last_event_at))}</span>
          </div>

          <div class="metrics-row">
            <span class="metric-pill">Req ${escapeHtml(session.metrics.request_count)}</span>
            <span class="metric-pill">Edits ${escapeHtml(session.metrics.edit_count)}</span>
            <span class="metric-pill">Failures ${escapeHtml(session.metrics.test_failure_count)}</span>
          </div>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll("[data-session-id]").forEach((card) => {
    card.addEventListener("click", () => {
      state.selectedSessionId = card.dataset.sessionId;
      renderAll();
    });
  });
}

function renderHero(session) {
  if (!session) {
    elements.selectedStage.textContent = "No session selected";
    elements.selectedSession.textContent = "Choose a session to inspect";
    elements.selectedSummary.textContent =
      "Once events start flowing, the Watchdog will explain where the session is stuck and let you intervene from here.";
    elements.selectedBadges.innerHTML = "";
    return;
  }

  elements.selectedStage.textContent = session.current_stage || "idle";
  elements.selectedSession.textContent = session.session_id;
  elements.selectedSummary.textContent = session.last_summary || "No summary yet.";
  const badges = [
    session.paused
      ? `<span class="badge badge-paused">Paused</span>`
      : `<span class="badge badge-live">Live monitoring</span>`,
    `<span class="badge badge-stage">Last event ${escapeHtml(formatDate(session.last_event_at))}</span>`,
    `<span class="badge badge-neutral">Created ${escapeHtml(formatDate(session.created_at))}</span>`,
  ];
  if (session.requires_changed_plan) {
    badges.push(`<span class="badge badge-paused">Changed plan required</span>`);
  }
  if (session.cooldown_until) {
    badges.push(`<span class="badge badge-neutral">Cooldown until ${escapeHtml(formatDate(session.cooldown_until))}</span>`);
  }
  if (session.acknowledged_at) {
    badges.push(`<span class="badge badge-live">Acknowledged</span>`);
  }
  elements.selectedBadges.innerHTML = badges.join("");
}

function renderIncident(session) {
  if (!session?.incident) {
    elements.incidentPanel.className = "incident-panel empty-panel";
    elements.incidentPanel.textContent = "No active incident for this session.";
    return;
  }

  const incident = session.incident;
  const repeatedFiles = incident.repeated_files.length
    ? incident.repeated_files.map((file) => `<div class="list-chip mono">${escapeHtml(file)}</div>`).join("")
    : `<div class="empty-panel">No repeated file cluster recorded.</div>`;
  const repeatedErrors = incident.repeated_errors.length
    ? incident.repeated_errors
        .map((error) => `<div class="list-chip mono">${escapeHtml(error)}</div>`)
        .join("")
    : `<div class="empty-panel">No repeated error signature recorded.</div>`;

  elements.incidentPanel.className = "incident-panel";
  elements.incidentPanel.innerHTML = `
    <div class="incident-reasons">
      ${incident.reasons
        .map((reason) => `<div class="reason-chip severity-high">${escapeHtml(reason)}</div>`)
        .join("")}
    </div>

    <div class="incident-meta-grid">
      <div class="meta-card">
        <div class="meta-label">Score</div>
        <div class="meta-value">${escapeHtml(incident.score)}</div>
      </div>
      <div class="meta-card">
        <div class="meta-label">Request Count</div>
        <div class="meta-value">${escapeHtml(incident.request_count)}</div>
      </div>
    </div>

    ${
      session.acknowledged_at
        ? `
      <div class="meta-card subsection-heading">
        <div class="meta-label">Acknowledged</div>
        <div class="meta-value meta-value-copy">${escapeHtml(formatDate(session.acknowledged_at))}</div>
        <div class="timeline-summary">${escapeHtml(session.acknowledged_note || "Acknowledged by an operator.")}</div>
      </div>
    `
        : ""
    }

    <div class="section-heading subsection-heading">
      <span class="eyebrow">Repeated Files</span>
    </div>
    <div class="list-block">${repeatedFiles}</div>

    <div class="section-heading subsection-heading">
      <span class="eyebrow">Repeated Errors</span>
    </div>
    <div class="list-block">${repeatedErrors}</div>

    <div class="meta-card subsection-heading">
      <div class="meta-label">Recommendation</div>
      <div class="meta-value meta-value-copy">${escapeHtml(incident.recommendation)}</div>
    </div>
  `;
}

function renderTimeline(session) {
  const events = session?.recent_events ?? [];
  if (events.length === 0) {
    elements.timeline.innerHTML = `
      <div class="empty-timeline">
        No events yet for this session. Once model calls or manual events arrive, they will stack up here.
      </div>
    `;
    return;
  }

  elements.timeline.innerHTML = [...events]
    .reverse()
    .map((event) => {
      const files = event.files?.length
        ? `<div class="timeline-files">${event.files
            .map((file) => `<span class="file-chip">${escapeHtml(file)}</span>`)
            .join("")}</div>`
        : "";
      return `
        <article class="timeline-item">
          <div class="timeline-time">${escapeHtml(formatRelative(event.created_at))}</div>
          <div class="timeline-content">
            <div class="timeline-head">
              <span class="timeline-kind">${escapeHtml(event.kind.replaceAll("_", " "))}</span>
              <span class="badge badge-neutral">${escapeHtml(formatDate(event.created_at))}</span>
            </div>
            <div class="timeline-summary">${escapeHtml(event.summary || "No summary.")}</div>
            ${files}
          </div>
        </article>
      `;
    })
    .join("");
}

function renderControls(session) {
  const disabled = !session;
  elements.resumeButton.disabled = disabled;
  elements.resumeResetButton.disabled = disabled;
  if (elements.acknowledgeButton) {
    elements.acknowledgeButton.disabled = disabled;
  }
  if (elements.archiveButton) {
    elements.archiveButton.disabled = disabled;
  }
  elements.killButton.disabled = disabled;
}

function renderAll() {
  const snapshot = state.snapshot;
  if (!snapshot) {
    return;
  }

  const selected = chooseSelectedSession();
  renderOverview(snapshot);
  renderSessionList(snapshot, state.selectedSessionId);
  renderHero(selected);
  renderIncident(selected);
  renderTimeline(selected);
  renderControls(selected);
}

async function fetchDashboard() {
  if (state.loading) {
    return;
  }
  state.loading = true;
  try {
    const response = await fetch("/v1/watchdog/dashboard", { headers: { accept: "application/json" } });
    if (!response.ok) {
      throw new Error(`Dashboard fetch failed with status ${response.status}`);
    }
    state.snapshot = await response.json();
    elements.lastRefresh.textContent = `Updated ${formatRelative(state.snapshot.generated_at)}`;
    renderAll();
  } catch (error) {
    elements.actionFeedback.textContent =
      error instanceof Error ? error.message : "Failed to refresh the dashboard.";
  } finally {
    state.loading = false;
  }
}

async function clearHistory() {
  const confirmed = window.confirm(
    "Clear all local Loop Watchdog session history from memory and disk?",
  );
  if (!confirmed) {
    return;
  }

  elements.actionFeedback.textContent = "Clearing local session history...";
  try {
    const response = await fetch("/v1/watchdog/history/clear", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
      },
      body: JSON.stringify({
        note: "Operator cleared the local watchdog history.",
      }),
    });
    if (!response.ok) {
      throw new Error(`Clear history failed with status ${response.status}`);
    }
    state.selectedSessionId = null;
    elements.operatorNote.value = "";
    elements.actionFeedback.textContent = "Local session history cleared.";
    await fetchDashboard();
  } catch (error) {
    elements.actionFeedback.textContent =
      error instanceof Error ? error.message : "Failed to clear local history.";
  }
}

async function performAction(action, options = {}) {
  const session = sessionById(state.selectedSessionId);
  if (!session) {
    return;
  }

  const note = elements.operatorNote.value.trim();
  const payload = { note };
  if (action === "resume") {
    payload.note =
      note || "Operator reviewed the session and approved the next move.";
    payload.clear_recent_events = Boolean(options.clearRecentEvents);
    payload.cooldown_seconds = options.cooldownSeconds ?? 0;
    payload.changed_plan = options.changedPlan ?? "";
  } else if (action === "kill") {
    payload.note = note || "Operator terminated the session from the dashboard.";
  } else if (action === "acknowledge") {
    payload.note = note || "Operator acknowledged the incident and is reviewing it.";
  } else if (action === "archive") {
    payload.note = note || "Operator archived the session from the dashboard.";
  }

  elements.actionFeedback.textContent = "Sending operator command...";
  try {
    const response = await fetch(
      `/v1/watchdog/sessions/${encodeURIComponent(session.session_id)}/${action}`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          accept: "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
    if (!response.ok) {
      throw new Error(`Action failed with status ${response.status}`);
    }
    elements.actionFeedback.textContent =
      action === "kill"
        ? `Session ${session.session_id} was terminated.`
        : action === "acknowledge"
          ? `Session ${session.session_id} was acknowledged.`
          : action === "archive"
            ? `Session ${session.session_id} was archived.`
        : options.clearRecentEvents
          ? `Session ${session.session_id} resumed with a cleared recent window.`
          : `Session ${session.session_id} resumed.`;
    await fetchDashboard();
  } catch (error) {
    elements.actionFeedback.textContent =
      error instanceof Error ? error.message : "Action failed.";
  }
}

elements.resumeButton.addEventListener("click", () =>
  performAction("resume", {
    clearRecentEvents: false,
    cooldownSeconds: 0,
    changedPlan: "",
  }),
);
elements.resumeResetButton.addEventListener("click", () =>
  performAction("resume", {
    clearRecentEvents: true,
    cooldownSeconds: 90,
    changedPlan: "Reset the window, start from a new diagnosis, and avoid retrying the same patch.",
  }),
);
if (elements.acknowledgeButton) {
  elements.acknowledgeButton.addEventListener("click", () => performAction("acknowledge"));
}
if (elements.archiveButton) {
  elements.archiveButton.addEventListener("click", () => performAction("archive"));
}
elements.killButton.addEventListener("click", () => performAction("kill"));
if (elements.clearHistoryButton) {
  elements.clearHistoryButton.addEventListener("click", clearHistory);
}

fetchDashboard();
window.setInterval(fetchDashboard, REFRESH_MS);
