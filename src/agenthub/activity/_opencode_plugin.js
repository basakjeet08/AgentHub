import net from "node:net"

const provider = "opencode"
const sessionID = process.env.AGENTHUB_SESSION_ID
const token = process.env.AGENTHUB_ACTIVITY_TOKEN
const endpoint = process.env.AGENTHUB_ACTIVITY_ENDPOINT
const configuredSessionID = process.env.AGENTHUB_OPENCODE_SESSION_ID

function receiverAddress() {
  try {
    const parsed = new URL(endpoint ?? "")
    if (
      parsed.protocol !== "tcp:" ||
      parsed.hostname !== "127.0.0.1" ||
      parsed.pathname !== "" ||
      parsed.search !== "" ||
      parsed.hash !== ""
    ) return
    const port = Number(parsed.port)
    if (!Number.isInteger(port) || port < 1 || port > 65535) return
    return { host: "127.0.0.1", port }
  } catch {
    return
  }
}

function send(event) {
  const address = receiverAddress()
  if (!address || !sessionID || !token) return Promise.resolve()
  const message = `${JSON.stringify({
    version: 1,
    provider,
    session_id: sessionID,
    token,
    event,
  })}\n`

  return new Promise((resolve) => {
    const socket = net.createConnection(address)
    socket.unref()
    socket.setTimeout(250)
    socket.once("connect", () => socket.end(message))
    socket.once("close", resolve)
    socket.once("error", () => resolve())
    socket.once("timeout", () => {
      socket.destroy()
      resolve()
    })
  })
}

function eventData(event) {
  return event?.data ?? event?.properties
}

function eventSessionID(event) {
  const data = eventData(event)
  return data?.sessionID ?? data?.session?.id ?? data?.info?.id
}

function eventSessionInfo(event) {
  const data = eventData(event)
  return data?.info ?? data?.session ?? data
}

const inputRequests = new Map([
  ["permission.asked", "permission"],
  ["permission.v2.asked", "permission"],
  ["form.created", "form"],
  ["question.asked", "question"],
  ["question.v2.asked", "question"],
])

const inputResolutions = new Map([
  ["permission.replied", "permission"],
  ["permission.v2.replied", "permission"],
  ["form.replied", "form"],
  ["form.cancelled", "form"],
  ["question.replied", "question"],
  ["question.rejected", "question"],
  ["question.v2.replied", "question"],
  ["question.v2.rejected", "question"],
])

const terminalEvents = new Set([
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
])

function requestID(event, resolution = false) {
  const data = eventData(event)
  if (!data) return
  return resolution
    ? data.requestID ?? data.permissionID ?? data.id
    : data.id ?? data.requestID ?? data.permissionID
}

function createObserver() {
  let rootSessionID = configuredSessionID
  const familySessionIDs = new Set(rootSessionID ? [rootSessionID] : [])
  const pendingInputs = new Set()
  let activeScopeID
  let sequence = 0
  let delivery = Promise.resolve()

  const enqueue = (event) => {
    delivery = delivery.then(() => send(event)).catch(() => {})
  }

  const forward = (type, nativeSessionID) => {
    enqueue({
      type,
      data: { sessionID: nativeSessionID },
      activity_scope_id: activeScopeID,
    })
  }

  const startExecution = (nativeSessionID) => {
    rootSessionID ??= nativeSessionID
    if (nativeSessionID !== rootSessionID || activeScopeID) return
    familySessionIDs.add(nativeSessionID)
    pendingInputs.clear()
    activeScopeID = `${nativeSessionID}:${++sequence}`
    forward("session.execution.started", nativeSessionID)
  }

  const blockerKey = (event, family, resolution = false) => {
    const nativeSessionID = eventSessionID(event)
    const id = requestID(event, resolution)
    if (!nativeSessionID || !id) return
    return `${family}:${nativeSessionID}:${id}`
  }

  const observe = (event) => {
    if (!event || typeof event.type !== "string") return
    const nativeSessionID = eventSessionID(event)

    if (event.type === "session.created") {
      const info = eventSessionInfo(event)
      if (info?.parentID && familySessionIDs.has(info.parentID) && nativeSessionID) {
        familySessionIDs.add(nativeSessionID)
      }
      return
    }

    if (event.type === "session.execution.started") {
      if (nativeSessionID) startExecution(nativeSessionID)
      return
    }

    if (event.type === "session.status") {
      const status = eventData(event)?.status
      if (nativeSessionID && (status === "busy" || status?.type === "busy")) {
        startExecution(nativeSessionID)
      }
      return
    }

    if (
      !nativeSessionID ||
      !familySessionIDs.has(nativeSessionID) ||
      !activeScopeID
    ) return

    const requestedFamily = inputRequests.get(event.type)
    if (requestedFamily) {
      const key = blockerKey(event, requestedFamily)
      if (!key) return
      const wasEmpty = pendingInputs.size === 0
      pendingInputs.add(key)
      if (wasEmpty) forward(event.type, nativeSessionID)
      return
    }

    const resolvedFamily = inputResolutions.get(event.type)
    if (resolvedFamily) {
      const key = blockerKey(event, resolvedFamily, true)
      if (!key || !pendingInputs.delete(key) || pendingInputs.size !== 0) return
      forward(event.type, nativeSessionID)
      return
    }

    let terminalType = event.type
    if (event.type === "session.idle") terminalType = "session.execution.succeeded"
    if (event.type === "session.error") terminalType = "session.execution.failed"
    if (!terminalEvents.has(terminalType) || nativeSessionID !== rootSessionID) return

    pendingInputs.clear()
    forward(terminalType, nativeSessionID)
    activeScopeID = undefined
  }

  return { observe, enqueue }
}

function setup(ctx) {
  const controller = new AbortController()
  const observer = createObserver()
  observer.enqueue({ type: "agenthub.plugin.ready" })

  void (async () => {
    try {
      for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
        observer.observe(event)
      }
    } catch {
      // Activity reporting is observational and must never affect OpenCode.
    }
  })()

  return () => controller.abort()
}

async function server() {
  const observer = createObserver()
  observer.enqueue({ type: "agenthub.plugin.ready" })
  return {
    event: async ({ event }) => {
      observer.observe(event)
    },
  }
}

// OpenCode 1.18.29+ accepts one default object containing both interfaces.
// V1 calls server(); V2 reads id/setup and ignores server(). Keeping this file
// dependency-free also lets the normal V1 TUI load it as a local file plugin.
export default {
  id: "agenthub.activity",
  setup,
  server,
}
