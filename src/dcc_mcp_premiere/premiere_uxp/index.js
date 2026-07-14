const app = require("premierepro");
const baseUrl = "http://127.0.0.1:47393";
const token = "dev-token"; // Set the same value as DCC_MCP_PREMIERE_BRIDGE_TOKEN before production use.

async function reply(id, result, error) {
  await fetch(`${baseUrl}/result`, {method: "POST", headers: {"Content-Type": "application/json", "X-DCC-MCP-Token": token}, body: JSON.stringify({id, result, error})});
}

function project() { return app.project; }
function dispatch(job) {
  const current = project();
  if (job.action === "inspect_project") return {project_name: current.name || null, active_sequence: current.activeSequence ? current.activeSequence.name : null};
  if (job.action === "list_sequences") return {sequences: Array.from(current.sequences || []).map(sequence => ({name: sequence.name})), sequence_count: (current.sequences || []).length || 0};
  if (job.action === "save_project") { current.save(); return {saved: true}; }
  throw new Error(`Unsupported action: ${job.action}`);
}

async function poll() {
  try {
    const response = await fetch(`${baseUrl}/next`, {headers: {"X-DCC-MCP-Token": token}});
    const job = await response.json();
    if (job.id) { try { await reply(job.id, dispatch(job), null); } catch (error) { await reply(job.id, null, String(error)); } }
  } finally { setTimeout(poll, 50); }
}
poll();
