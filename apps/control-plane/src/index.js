function json(body, status = 200) {
    return new Response(JSON.stringify(body, null, 2), {
        status,
        headers: { "content-type": "application/json; charset=utf-8" },
    });
}
async function sha256Hex(secret, body) {
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    const signature = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
    const bytes = Array.from(new Uint8Array(signature));
    return bytes.map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
async function verifyIngestRequest(request, env, rawBody) {
    const auth = request.headers.get("authorization");
    if (env.WATCHDOG_INGEST_TOKEN && auth === `Bearer ${env.WATCHDOG_INGEST_TOKEN}`) {
        return true;
    }
    if (env.WATCHDOG_HMAC_SECRET) {
        const received = request.headers.get("x-loop-watchdog-signature");
        if (!received) {
            return false;
        }
        const expected = await sha256Hex(env.WATCHDOG_HMAC_SECRET, rawBody);
        return received === expected;
    }
    return !env.WATCHDOG_INGEST_TOKEN && !env.WATCHDOG_HMAC_SECRET;
}
function validateIncidentEnvelope(value) {
    if (!value || typeof value !== "object") {
        throw new Error("Payload must be an object.");
    }
    const envelope = value;
    if (!envelope.incident || typeof envelope.incident.incident_id !== "string") {
        throw new Error("Missing incident payload.");
    }
    if (!Array.isArray(envelope.incident.reasons) || envelope.incident.reasons.length === 0) {
        throw new Error("Incident reasons are required.");
    }
    if (!Array.isArray(envelope.recent_events)) {
        throw new Error("recent_events must be an array.");
    }
    return envelope;
}
async function storeIncident(env, envelope) {
    const incident = envelope.incident;
    await env.DB.prepare(`INSERT OR REPLACE INTO incidents (
      incident_id,
      session_id,
      created_at,
      score,
      reasons_json,
      repeated_files_json,
      repeated_errors_json,
      triggering_event_ids_json,
      request_count,
      recommendation,
      raw_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
        .bind(incident.incident_id, incident.session_id, incident.created_at, incident.score, JSON.stringify(incident.reasons), JSON.stringify(incident.repeated_files), JSON.stringify(incident.repeated_errors), JSON.stringify(incident.triggering_event_ids), incident.request_count, incident.recommendation, JSON.stringify(envelope))
        .run();
}
async function sendSlackAlert(env, envelope) {
    if (!env.SLACK_WEBHOOK_URL) {
        return;
    }
    const incident = envelope.incident;
    const facts = [
        `Session: ${incident.session_id}`,
        `Score: ${incident.score}`,
        `Requests: ${incident.request_count}`,
        `Files: ${incident.repeated_files.join(", ") || "n/a"}`,
    ].join("\n");
    const text = `${incident.reasons.join("\n")}\n\n${facts}\n\nRecommendation: ${incident.recommendation}`;
    const response = await fetch(env.SLACK_WEBHOOK_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
            text: "Loop Watchdog paused a coding session.",
            blocks: [
                {
                    type: "header",
                    text: {
                        type: "plain_text",
                        text: "Loop Watchdog Incident",
                    },
                },
                {
                    type: "section",
                    text: {
                        type: "mrkdwn",
                        text,
                    },
                },
            ],
        }),
    });
    if (!response.ok) {
        throw new Error(`Slack webhook failed with status ${response.status}.`);
    }
}
async function sendEmailAlert(env, envelope) {
    if (!env.RESEND_API_KEY || !env.ALERT_EMAIL_TO || !env.ALERT_EMAIL_FROM) {
        return;
    }
    const incident = envelope.incident;
    const html = `
    <h1>Loop Watchdog Incident</h1>
    <p><strong>Session:</strong> ${incident.session_id}</p>
    <p><strong>Score:</strong> ${incident.score}</p>
    <p><strong>Reasons:</strong></p>
    <ul>${incident.reasons.map((reason) => `<li>${reason}</li>`).join("")}</ul>
    <p><strong>Files:</strong> ${incident.repeated_files.join(", ") || "n/a"}</p>
    <p><strong>Recommendation:</strong> ${incident.recommendation}</p>
  `;
    const response = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
            authorization: `Bearer ${env.RESEND_API_KEY}`,
            "content-type": "application/json",
        },
        body: JSON.stringify({
            from: env.ALERT_EMAIL_FROM,
            to: [env.ALERT_EMAIL_TO],
            subject: `Loop Watchdog paused ${incident.session_id}`,
            html,
        }),
    });
    if (!response.ok) {
        throw new Error(`Resend failed with status ${response.status}.`);
    }
}
async function listIncidents(request, env) {
    const auth = request.headers.get("authorization");
    if (env.WATCHDOG_DASHBOARD_TOKEN && auth !== `Bearer ${env.WATCHDOG_DASHBOARD_TOKEN}`) {
        return json({ error: "Unauthorized" }, 401);
    }
    const url = new URL(request.url);
    const parsedLimit = Number(url.searchParams.get("limit") ?? "20");
    const limit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 100) : 20;
    const result = await env.DB.prepare("SELECT incident_id, session_id, created_at, score, reasons_json, repeated_files_json, repeated_errors_json, request_count, recommendation FROM incidents ORDER BY created_at DESC LIMIT ?")
        .bind(limit)
        .all();
    const incidents = result.results.map((row) => ({
        incident_id: row.incident_id,
        session_id: row.session_id,
        created_at: row.created_at,
        score: row.score,
        reasons: JSON.parse(String(row.reasons_json)),
        repeated_files: JSON.parse(String(row.repeated_files_json)),
        repeated_errors: JSON.parse(String(row.repeated_errors_json)),
        request_count: row.request_count,
        recommendation: row.recommendation,
    }));
    return json({ incidents });
}
export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        if (request.method === "GET" && url.pathname === "/health") {
            return json({ status: "ok" });
        }
        if (request.method === "GET" && url.pathname === "/api/incidents") {
            return listIncidents(request, env);
        }
        if (request.method === "POST" && url.pathname === "/api/incidents") {
            const rawBody = await request.text();
            if (!(await verifyIngestRequest(request, env, rawBody))) {
                return json({ error: "Unauthorized" }, 401);
            }
            try {
                const envelope = validateIncidentEnvelope(JSON.parse(rawBody));
                await storeIncident(env, envelope);
                await Promise.allSettled([sendSlackAlert(env, envelope), sendEmailAlert(env, envelope)]);
                return json({ accepted: true }, 202);
            }
            catch (error) {
                const message = error instanceof Error ? error.message : "Unknown error";
                return json({ error: message }, 400);
            }
        }
        return json({ error: "Not found" }, 404);
    },
};
