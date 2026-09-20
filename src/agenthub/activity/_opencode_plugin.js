import net from "node:net"
import { Plugin } from "@opencode/plugin"

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

function eventSessionID(event) {
  const data = event?.data
  return data?.sessionID ?? data?.session?.id ?? data?.info?.id
}

const observedEvents = new Set([
  "permission.asked",
  "permission.replied",
  "form.created",
  "form.replied",
  "form.cancelled",
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
])

const terminalEvents = new Set([
  "session.execution.succeeded",
  "session.execution.failed",
  "session.execution.interrupted",
])

export default Plugin.define({
  id: "agenthub.activity",
  setup(ctx) {
    const controller = new AbortController()
    let rootSessionID = configuredSessionID
    const familySessionIDs = new Set(rootSessionID ? [rootSessionID] : [])
    let activeScopeID
    let sequence = 0
    let delivery = Promise.resolve()

    const enqueue = (event) => {
      delivery = delivery.then(() => send(event)).catch(() => {})
    }

    const observe = (event) => {
      const nativeSessionID = eventSessionID(event)
      if (!nativeSessionID) return

      if (event.type === "session.created") {
        const info = event.data?.info ?? event.data?.session ?? event.data
        if (info?.parentID && familySessionIDs.has(info.parentID)) {
          familySessionIDs.add(nativeSessionID)
        }
        return
      }

      if (event.type === "session.execution.started") {
        rootSessionID ??= nativeSessionID
        if (nativeSessionID !== rootSessionID) return
        familySessionIDs.add(nativeSessionID)
        activeScopeID = `${nativeSessionID}:${++sequence}`
        enqueue({
          type: event.type,
          data: { sessionID: nativeSessionID },
          activity_scope_id: activeScopeID,
        })
        return
      }

      if (
        !familySessionIDs.has(nativeSessionID) ||
        !activeScopeID ||
        !observedEvents.has(event.type)
      ) return
      if (terminalEvents.has(event.type) && nativeSessionID !== rootSessionID) return
      enqueue({
        type: event.type,
        data: { sessionID: nativeSessionID },
        activity_scope_id: activeScopeID,
      })
      if (terminalEvents.has(event.type)) activeScopeID = undefined
    }

    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          observe(event)
        }
      } catch {
        // Activity reporting is observational and must never affect OpenCode.
      }
    })()

    return () => controller.abort()
  },
})
