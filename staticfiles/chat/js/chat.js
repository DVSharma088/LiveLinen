/* static/chat/js/chat.js
   Robust WebSocket client for LiveLinen global chat
   - Auto reconnect with exponential backoff
   - Heartbeat (ping/pong) to keep connections alive
   - Sends messages as { message, username }
   - Handles ack/system/chat message shapes from server
   - Non-intrusive: safely checks for missing DOM elements
*/

(function () {
  // ----- Configuration -----
  const THREAD_DEFAULT = "global";
  const RECONNECT_BASE_MS = 1000;
  const RECONNECT_MAX_MS = 30000;
  const HEARTBEAT_INTERVAL_MS = 25000;
  const HEARTBEAT_TIMEOUT_MS = 10000;
  const MAX_PAYLOAD_LENGTH = 2000;

  // ----- DOM lookups -----
  const container =
    document.querySelector(".container[data-thread]") ||
    document.querySelector(".container") ||
    document.body;

  const threadSlug =
    (container &&
      container.getAttribute &&
      (container.getAttribute("data-thread") || THREAD_DEFAULT)) ||
    THREAD_DEFAULT;

  let msgList = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("msg-input");
  const sendBtn = document.getElementById("send-btn");
  const wsStatus = document.getElementById("ws-status");

  if (!msgList) msgList = createMessageList();

  // ----- Connection state -----
  let socket = null;
  let reconnectAttempts = 0;
  let reconnectTimer = null;
  let heartbeatTimer = null;
  let heartbeatTimeoutTimer = null;
  let manualClose = false;

  // ----- Build socket URL -----
  function buildSocketUrl() {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    return `${scheme}://${window.location.host}/ws/chat/${threadSlug}/`;
  }

  // ----- Connect / Reconnect logic -----
  function connect() {
    if (
      socket &&
      (socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING)
    ) {
      console.log("[chat] socket already open/connecting");
      return;
    }

    const url = buildSocketUrl();
    console.log("[chat] connecting to", url);
    socket = new WebSocket(url);
    updateStatus("connecting");

    socket.addEventListener("open", onOpen);
    socket.addEventListener("message", onMessage);
    socket.addEventListener("close", onClose);
    socket.addEventListener("error", onError);
  }

  function scheduleReconnect() {
    if (manualClose) return;
    reconnectAttempts += 1;
    const backoff = Math.min(
      RECONNECT_BASE_MS * 2 ** (reconnectAttempts - 1),
      RECONNECT_MAX_MS
    );
    const jitter = Math.floor(Math.random() * 500);
    const wait = backoff + jitter;
    console.warn(`[chat] reconnect attempt ${reconnectAttempts} in ${wait}ms`);
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(connect, wait);
  }

  // ----- Heartbeat -----
  function startHeartbeat() {
    stopHeartbeat();
    heartbeatTimer = setInterval(() => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      try {
        socket.send(JSON.stringify({ type: "ping" }));
        clearTimeout(heartbeatTimeoutTimer);
        heartbeatTimeoutTimer = setTimeout(() => {
          console.warn("[chat] heartbeat timeout - closing socket");
          try {
            socket.close();
          } catch {}
        }, HEARTBEAT_TIMEOUT_MS);
      } catch (err) {
        console.error("[chat] heartbeat send error", err);
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  function stopHeartbeat() {
    if (heartbeatTimer) clearInterval(heartbeatTimer);
    if (heartbeatTimeoutTimer) clearTimeout(heartbeatTimeoutTimer);
    heartbeatTimer = heartbeatTimeoutTimer = null;
  }

  // ----- WebSocket Handlers -----
  function onOpen() {
    console.log("[chat] websocket open");
    reconnectAttempts = 0;
    updateStatus("connected");
    clearTimeout(reconnectTimer);
    startHeartbeat();
  }

  function onMessage(ev) {
    try {
      const raw = ev.data;
      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        appendSystemLine(String(raw));
        return;
      }

      const t = data.type || null;

      if (t === "pong") {
        clearTimeout(heartbeatTimeoutTimer);
        heartbeatTimeoutTimer = null;
        return;
      }

      if (t === "system") {
        appendSystemLine(data.message || "system");
        return;
      }

      if (t === "ack") return;

      if (t === "chat") {
        const obj = {
          username: data.username || "anonymous",
          message: data.message || "",
          created_at: data.ts || new Date().toISOString(),
        };
        addMessageToList(obj);
        return;
      }

      if (data.message && data.username) {
        addMessageToList({
          username: data.username,
          message: data.message,
          created_at: data.ts || new Date().toISOString(),
        });
        return;
      }

      if (Array.isArray(data.messages)) {
        data.messages.forEach((m) => {
          addMessageToList({
            username: m.username || "anonymous",
            message: m.message || "",
            created_at: m.ts || new Date().toISOString(),
          });
        });
        return;
      }

      appendSystemLine(JSON.stringify(data));
    } catch (err) {
      console.error("[chat] onMessage error", err);
    } finally {
      scrollToBottom();
    }
  }

  function onClose(ev) {
    console.warn("[chat] websocket closed", ev.code, ev.reason);
    updateStatus("disconnected");
    appendSystemLine("Connection closed.");
    stopHeartbeat();
    if (!manualClose) scheduleReconnect();
  }

  function onError(err) {
    console.error("[chat] websocket error", err);
    updateStatus("error");
  }

  // ----- Send message -----
  function sendMessage() {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      appendSystemLine("Cannot send message: socket not connected.");
      return;
    }
    if (!input) return;
    const text = input.value ? input.value.trim() : "";
    if (!text) return;

    if (text.length > MAX_PAYLOAD_LENGTH) {
      appendSystemLine("Message too long.");
      return;
    }

    // ✅ Always fetch username fresh (ensures it’s correct)
    const payload = {
      message: text,
      username:
        (typeof window !== "undefined" && window.GLOBAL_CHAT_USERNAME) ||
        (container && container.dataset && container.dataset.username) ||
        "anonymous",
    };
    console.log("[chat] sending payload:", payload);

    try {
      socket.send(JSON.stringify(payload));
      input.value = "";
    } catch (err) {
      console.error("[chat] send error", err);
      appendSystemLine("Failed to send message.");
    }
  }

  // ----- DOM helpers -----
  function addMessageToList(obj) {
    const sender = obj.username || "anonymous";
    const body = obj.message || "";
    const created_at = obj.created_at || null;

    const wrapper = document.createElement("div");
    wrapper.className = "mb-2";

    const myName =
      (typeof window !== "undefined" && window.GLOBAL_CHAT_USERNAME) ||
      (container && container.dataset && container.dataset.username) ||
      "anonymous";

    const isMe = myName === sender;

    const header = document.createElement("div");
    header.style.fontSize = "0.9em";
    header.style.marginBottom = "3px";
    header.className = isMe ? "text-primary" : "text-dark";
    header.innerHTML =
      `<strong>@${escapeHtml(sender)}</strong>` +
      (created_at
        ? ` <small class="text-muted">· ${formatTime(created_at)}</small>`
        : "");

    const bodyEl = document.createElement("div");
    bodyEl.innerHTML = escapeHtml(body).replace(/\n/g, "<br/>");
    bodyEl.style.display = "inline-block";
    bodyEl.style.padding = "8px 10px";
    bodyEl.style.borderRadius = "8px";
    bodyEl.style.maxWidth = "80%";
    bodyEl.style.background = isMe ? "#e7f3ff" : "#f1f3f5";

    wrapper.appendChild(header);
    wrapper.appendChild(bodyEl);
    msgList.appendChild(wrapper);
  }

  function appendSystemLine(text) {
    const el = document.createElement("div");
    el.className = "text-muted small mb-2";
    el.innerText = text;
    msgList.appendChild(el);
    scrollToBottom();
  }

  function formatTime(iso) {
    try {
      const dt = new Date(iso);
      return dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  }

  function scrollToBottom() {
    try {
      msgList.scrollTop = msgList.scrollHeight;
    } catch {}
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str).replace(/[&<>"'`=\/]/g, function (s) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
        "/": "&#x2F;",
        "`": "&#x60;",
        "=": "&#x3D;",
      }[s];
    });
  }

  function createMessageList() {
    const el = document.createElement("div");
    el.id = "messages";
    el.style.height = "60vh";
    el.style.overflow = "auto";
    el.style.padding = "12px";
    el.style.border = "1px solid #ddd";
    el.style.background = "#fff";
    (container.appendChild || document.body.appendChild).call(container, el);
    return el;
  }

  function updateStatus(state) {
    if (!wsStatus) return;
    wsStatus.textContent = `Chat status: ${state}`;
    wsStatus.className = `ws-status ws-${state}`;
  }

  // ----- UI wiring -----
  if (form && input) {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      sendMessage();
    });

    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) {
        ev.preventDefault();
        sendMessage();
      }
    });
  } else {
    console.warn("[chat] form/input not found - cannot send messages.");
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", (ev) => {
      ev.preventDefault();
      sendMessage();
    });
  }

  // ----- Global API -----
  window.liveLinenChat = {
    connect: () => {
      manualClose = false;
      connect();
    },
    close: () => {
      manualClose = true;
      if (socket) socket.close();
    },
    socketRef: () => socket,
  };

  // ----- Lifecycle -----
  connect();

  window.addEventListener("beforeunload", () => {
    manualClose = true;
    try {
      socket && socket.close();
    } catch {}
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      stopHeartbeat();
    } else if (!socket || socket.readyState !== WebSocket.OPEN) {
      connect();
    }
  });
})();
