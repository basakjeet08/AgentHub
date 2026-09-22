import net from "node:net"

const endpoint = process.env.AGENTHUB_ACTIVITY_ENDPOINT
const sessionID = process.env.AGENTHUB_SESSION_ID
const token = process.env.AGENTHUB_ACTIVITY_TOKEN
const configuredSessionID = process.env.AGENTHUB_OPENCODE_SESSION_ID

function address() {
  try {
    const parsed = new URL(endpoint ?? "")
    const port = Number(parsed.port)
    if (parsed.protocol !== "tcp:" || parsed.hostname !== "127.0.0.1" || parsed.pathname || parsed.search || parsed.hash || !Number.isInteger(port)) return
    return { host: "127.0.0.1", port }
  } catch { return }
}

function send(event) {
  const target = address()
  if (!target || !sessionID || !token) return Promise.resolve()
  return new Promise((resolve) => {
    const socket = net.createConnection(target)
    socket.unref()
    socket.setTimeout(250)
    socket.once("connect", () => socket.end(`${JSON.stringify({version: 1, provider: "opencode", session_id: sessionID, token, event})}\n`))
    socket.once("close", resolve)
    socket.once("error", resolve)
    socket.once("timeout", () => { socket.destroy(); resolve() })
  })
}

const requested = new Map([["permission.asked", "permission"], ["permission.v2.asked", "permission"], ["form.created", "form"], ["question.asked", "question"], ["question.v2.asked", "question"]])
const resolved = new Map([["permission.replied", "permission"], ["permission.v2.replied", "permission"], ["form.replied", "form"], ["form.cancelled", "form"], ["question.replied", "question"], ["question.rejected", "question"], ["question.v2.replied", "question"], ["question.v2.rejected", "question"]])

function observer() {
  let root = configuredSessionID
  const family = new Set(root ? [root] : [])
  const pending = new Set()
  let scope
  let sequence = 0
  let delivery = Promise.resolve()
  const enqueue = (event) => { delivery = delivery.then(() => send(event)).catch(() => {}) }
  const data = (event) => event?.data ?? event?.properties
  const session = (event) => { const value = data(event); return value?.sessionID ?? value?.session?.id ?? value?.info?.id }
  const info = (event) => { const value = data(event); return value?.info ?? value?.session ?? value }
  const requestID = (event, isResolution) => { const value = data(event); return isResolution ? value?.requestID ?? value?.permissionID ?? value?.id : value?.id ?? value?.requestID ?? value?.permissionID }
  const forward = (type, native) => enqueue({type, data: {sessionID: native}, activity_scope_id: scope})
  const start = (native) => { root ??= native; if (native !== root || scope) return; family.add(native); pending.clear(); scope = `${native}:${++sequence}`; forward("session.execution.started", native) }
  const observe = (event) => {
    if (!event || typeof event.type !== "string") return
    const native = session(event)
    if (event.type === "session.created") { const parent = info(event)?.parentID; if (parent && family.has(parent) && native) family.add(native); return }
    if (event.type === "session.execution.started") { if (native) start(native); return }
    if (event.type === "session.status") { const status = data(event)?.status; if (native && (status === "busy" || status?.type === "busy")) start(native); return }
    if (!native || !family.has(native) || !scope) return
    const requestFamily = requested.get(event.type)
    if (requestFamily) { const id = requestID(event, false); if (!id) return; const key = `${requestFamily}:${native}:${id}`; const wasEmpty = pending.size === 0; pending.add(key); if (wasEmpty) forward(event.type, native); return }
    const resolvedFamily = resolved.get(event.type)
    if (resolvedFamily) { const id = requestID(event, true); const key = id && `${resolvedFamily}:${native}:${id}`; if (!key || !pending.delete(key) || pending.size) return; forward(event.type, native); return }
    let terminal = event.type
    if (terminal === "session.idle") terminal = "session.execution.succeeded"
    if (terminal === "session.error") terminal = "session.execution.failed"
    if (!["session.execution.succeeded", "session.execution.failed", "session.execution.interrupted"].includes(terminal) || native !== root) return
    pending.clear(); forward(terminal, native); scope = undefined
  }
  return {observe, enqueue}
}

function setup(ctx) {
  const controller = new AbortController()
  const current = observer()
  current.enqueue({type: "agenthub.plugin.ready"})
  void (async () => { try { for await (const event of ctx.event.subscribe({signal: controller.signal})) current.observe(event) } catch {} })()
  return () => controller.abort()
}

async function server() {
  const current = observer()
  current.enqueue({type: "agenthub.plugin.ready"})
  return {event: async ({event}) => current.observe(event)}
}

export default {id: "agenthub.activity", setup, server}
