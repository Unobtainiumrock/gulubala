// ── State ──────────────────────────────────────────────────────────────────
const state = {
  sessions: new Map(),          // session_id → { intent, validatedFields, missingFields, currentFields, escalated, resolved }
  activeSessionId: null,
  globalWs: null,
  sessionWs: null,
  reconnectTimer: null,
  reconnectDelay: 1000,
  calltreeNetwork: null,
  workflowNetwork: null,
  workflowNodes: null,          // vis.DataSet
  workflowEdges: null,          // vis.DataSet
  fieldOrder: [],               // ordered field names for current session
};

const COLORS = {
  pending:   { background: '#6c757d', border: '#5a6268', font: '#fff' },
  active:    { background: '#0d6efd', border: '#0a58ca', font: '#fff' },
  completed: { background: '#198754', border: '#146c43', font: '#fff' },
  escalated: { background: '#dc3545', border: '#b02a37', font: '#fff' },
};

// ── DOM refs ──────────────────────────────────────────────────────────────
const $select      = document.getElementById('session-select');
const $connDot     = document.getElementById('conn-dot');
const $connLabel   = document.getElementById('conn-label');
const $transcript  = document.getElementById('transcript');
const $escalation  = document.getElementById('banner-escalation');
const $escalText   = document.getElementById('escalation-text');
const $completion  = document.getElementById('banner-completion');
const $complText   = document.getElementById('completion-text');
const $complLink   = document.getElementById('completion-transcript-link');

// ── Utilities ─────────────────────────────────────────────────────────────
function wsUrl(path) {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}${path}`;
}

function setConnStatus(status) {
  $connDot.className = 'conn-dot ' + status;
  $connLabel.textContent = status === 'connected' ? 'Connected'
    : status === 'error' ? 'Reconnecting...' : 'Disconnected';
}

// ── IVR Call Tree ─────────────────────────────────────────────────────────
async function loadCallTree() {
  try {
    const res = await fetch('/calltree/acme_corp');
    if (!res.ok) throw new Error(res.statusText);
    const tree = await res.json();
    renderCallTree(tree);
  } catch (err) {
    console.error('Failed to load call tree:', err);
    document.querySelector('#calltree-graph .empty-state').textContent =
      'Failed to load call tree';
  }
}

function renderCallTree(tree) {
  const container = document.getElementById('calltree-graph');
  container.innerHTML = '';

  const nodes = tree.nodes.map(n => ({
    id: n.id,
    label: n.label,
    shape: n.input_type === 'dtmf' ? 'box' : 'ellipse',
    color: {
      background: n.input_type === 'dtmf' ? '#21262d' : '#1a3a5c',
      border: n.input_type === 'dtmf' ? '#30363d' : '#2a5a8c',
      highlight: { background: '#0d6efd', border: '#0a58ca' },
    },
    font: { color: '#e1e4e8', size: 13 },
    borderWidth: 1,
  }));

  const edges = [];
  for (const node of tree.nodes) {
    for (const t of (node.transitions || [])) {
      edges.push({
        from: node.id,
        to: t.next_node_id,
        label: t.label || t.input,
        font: { color: '#8b949e', size: 11, strokeWidth: 0 },
        color: { color: '#30363d', highlight: '#58a6ff' },
        arrows: 'to',
      });
    }
  }

  const data = { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) };
  const options = {
    layout: {
      hierarchical: {
        direction: 'UD',
        sortMethod: 'directed',
        levelSeparation: 80,
        nodeSpacing: 140,
      },
    },
    physics: false,
    interaction: { dragNodes: false, zoomView: true, dragView: true },
    edges: { smooth: { type: 'cubicBezier' } },
  };

  state.calltreeNetwork = new vis.Network(container, data, options);
}

// ── Workflow Progress Graph ───────────────────────────────────────────────
function buildWorkflowGraph(fields) {
  const container = document.getElementById('workflow-graph');
  container.innerHTML = '';

  state.fieldOrder = fields;
  const nodes = fields.map((f, i) => ({
    id: f,
    label: f.replace(/_/g, ' '),
    shape: 'box',
    color: COLORS.pending,
    font: { color: '#fff', size: 13 },
    borderWidth: 2,
    margin: 10,
  }));

  const edges = [];
  for (let i = 0; i < fields.length - 1; i++) {
    edges.push({
      from: fields[i],
      to: fields[i + 1],
      arrows: 'to',
      color: { color: '#30363d' },
      smooth: { type: 'cubicBezier' },
    });
  }

  state.workflowNodes = new vis.DataSet(nodes);
  state.workflowEdges = new vis.DataSet(edges);

  const options = {
    layout: {
      hierarchical: {
        direction: 'LR',
        sortMethod: 'directed',
        levelSeparation: 160,
        nodeSpacing: 60,
      },
    },
    physics: false,
    interaction: { dragNodes: false, zoomView: true, dragView: true },
  };

  state.workflowNetwork = new vis.Network(
    container, { nodes: state.workflowNodes, edges: state.workflowEdges }, options,
  );
}

function updateWorkflowColors(validatedFields, missingFields, currentFields, escalated) {
  if (!state.workflowNodes) return;

  const validated = new Set(Object.keys(validatedFields || {}));
  const active = new Set(currentFields || []);

  for (const fieldId of state.fieldOrder) {
    let color;
    if (validated.has(fieldId)) {
      color = COLORS.completed;
    } else if (escalated) {
      color = COLORS.escalated;
    } else if (active.has(fieldId)) {
      color = COLORS.active;
    } else {
      color = COLORS.pending;
    }
    state.workflowNodes.update({ id: fieldId, color });
  }
}

function markAllWorkflowCompleted() {
  if (!state.workflowNodes) return;
  for (const fieldId of state.fieldOrder) {
    state.workflowNodes.update({ id: fieldId, color: COLORS.completed });
  }
}

// ── Transcript ────────────────────────────────────────────────────────────
function clearTranscript() {
  $transcript.innerHTML = '';
}

function appendTranscriptMessage(role, content, turnCount) {
  // Remove empty state if present
  const empty = $transcript.querySelector('.empty-state');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = `msg msg-${role}`;
  div.innerHTML =
    `<div class="msg-role">${role}</div>` +
    `<div>${escapeHtml(content)}</div>` +
    `<div class="msg-turn">Turn ${turnCount}</div>`;
  $transcript.appendChild(div);
  $transcript.scrollTop = $transcript.scrollHeight;
}

function appendNodeIndicator(fields, questions) {
  const empty = $transcript.querySelector('.empty-state');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = 'node-indicator';
  div.innerHTML =
    `<div class="fields">Now asking: ${fields.map(escapeHtml).join(', ')}</div>` +
    (questions && questions.length
      ? `<div class="questions">${questions.map(escapeHtml).join(' | ')}</div>`
      : '');
  $transcript.appendChild(div);
  $transcript.scrollTop = $transcript.scrollHeight;
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ── Banners ───────────────────────────────────────────────────────────────
function showEscalation(reason, intent, validatedFields) {
  const fields = Object.entries(validatedFields || {})
    .map(([k, v]) => `${k}: ${v}`).join(', ');
  $escalText.textContent = `ESCALATED \u2014 ${reason}` +
    (intent ? ` (${intent})` : '') +
    (fields ? ` | Collected: ${fields}` : '');
  $escalation.classList.add('visible');
}

async function showCompletion(sessionId, event) {
  let summary = event.action_result || 'Call completed successfully.';
  try {
    const res = await fetch('/escalation-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (res.ok) {
      const data = await res.json();
      summary = data.summary || summary;
    }
  } catch (_) { /* fallback to action_result */ }

  $complText.textContent = `COMPLETED \u2014 ${summary}`;
  $complLink.onclick = (e) => {
    e.preventDefault();
    $transcript.scrollIntoView({ behavior: 'smooth' });
  };
  $completion.classList.add('visible');
}

function hideBanners() {
  $escalation.classList.remove('visible');
  $completion.classList.remove('visible');
}

// ── WebSocket ─────────────────────────────────────────────────────────────
function connectGlobal() {
  if (state.globalWs) {
    state.globalWs.onclose = null;
    state.globalWs.close();
  }

  const ws = new WebSocket(wsUrl('/ws'));
  state.globalWs = ws;

  ws.onopen = () => {
    setConnStatus('connected');
    state.reconnectDelay = 1000;
  };

  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    trackSession(event.session_id);

    // If we're viewing this session, handle the event
    if (event.session_id === state.activeSessionId) {
      handleEvent(event);
    }
  };

  ws.onclose = () => {
    setConnStatus('error');
    scheduleReconnect(() => connectGlobal());
  };

  ws.onerror = () => ws.close();
}

function connectSession(sessionId) {
  // Close existing session WS
  if (state.sessionWs) {
    state.sessionWs.onclose = null;
    state.sessionWs.close();
    state.sessionWs = null;
  }

  if (!sessionId) return;

  const ws = new WebSocket(wsUrl(`/ws/${sessionId}`));
  state.sessionWs = ws;

  ws.onopen = () => {
    setConnStatus('connected');
    state.reconnectDelay = 1000;
  };

  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleEvent(event);
  };

  ws.onclose = () => {
    setConnStatus('error');
    scheduleReconnect(() => connectSession(sessionId));
  };

  ws.onerror = () => ws.close();
}

function scheduleReconnect(fn) {
  clearTimeout(state.reconnectTimer);
  state.reconnectTimer = setTimeout(() => {
    fn();
    state.reconnectDelay = Math.min(state.reconnectDelay * 2, 30000);
  }, state.reconnectDelay);
}

// ── Session tracking ──────────────────────────────────────────────────────
function trackSession(sessionId) {
  if (!sessionId || state.sessions.has(sessionId)) return;
  state.sessions.set(sessionId, {
    intent: null,
    validatedFields: {},
    missingFields: [],
    currentFields: [],
    escalated: false,
    resolved: false,
  });
  addSessionOption(sessionId);
}

function addSessionOption(sessionId) {
  if ($select.querySelector(`option[value="${sessionId}"]`)) return;
  const opt = document.createElement('option');
  opt.value = sessionId;
  opt.textContent = sessionId.slice(0, 12) + '...';
  $select.appendChild(opt);
}

$select.addEventListener('change', () => {
  const sessionId = $select.value;
  state.activeSessionId = sessionId || null;

  hideBanners();
  clearTranscript();

  // Reset workflow graph
  state.workflowNodes = null;
  state.workflowEdges = null;
  state.workflowNetwork = null;
  state.fieldOrder = [];
  const wfContainer = document.getElementById('workflow-graph');
  wfContainer.innerHTML = sessionId
    ? '<div class="empty-state">Waiting for workflow events...</div>'
    : '<div class="empty-state">Select a session to view workflow progress</div>';

  if (!sessionId) {
    $transcript.innerHTML = '<div class="empty-state">Select a session to view the transcript</div>';
  }

  // Connect to per-session WS for targeted events
  connectSession(sessionId);
});

// ── Event dispatch ────────────────────────────────────────────────────────
function handleEvent(event) {
  const sid = event.session_id;
  const sess = state.sessions.get(sid);
  if (!sess) return;

  switch (event.event_type) {
    case 'node_entered':
      handleNodeEntered(sid, sess, event);
      break;
    case 'transcript':
      handleTranscript(sid, sess, event);
      break;
    case 'escalation':
      handleEscalation(sid, sess, event);
      break;
    case 'completed':
      handleCompleted(sid, sess, event);
      break;
  }
}

function handleNodeEntered(sid, sess, event) {
  sess.intent = event.intent || sess.intent;
  sess.validatedFields = event.validated_fields || {};
  sess.missingFields = event.missing_required_fields || [];
  sess.currentFields = event.node_fields || [];

  // Derive full field list on first event (or if new fields appear)
  const allFields = [
    ...Object.keys(sess.validatedFields),
    ...sess.missingFields,
  ];
  // Deduplicate while preserving order
  const seen = new Set();
  const ordered = [];
  for (const f of allFields) {
    if (!seen.has(f)) { seen.add(f); ordered.push(f); }
  }

  if (state.fieldOrder.length === 0 || ordered.length > state.fieldOrder.length) {
    buildWorkflowGraph(ordered);
  }

  updateWorkflowColors(sess.validatedFields, sess.missingFields, sess.currentFields, sess.escalated);

  if (sid === state.activeSessionId) {
    appendNodeIndicator(sess.currentFields, event.last_questions);
  }
}

function handleTranscript(sid, sess, event) {
  if (sid === state.activeSessionId) {
    appendTranscriptMessage(event.role, event.content, event.turn_count);
  }
}

function handleEscalation(sid, sess, event) {
  sess.escalated = true;
  updateWorkflowColors(sess.validatedFields, sess.missingFields, sess.currentFields, true);

  if (sid === state.activeSessionId) {
    showEscalation(event.reason, event.intent, event.validated_fields);
  }
}

function handleCompleted(sid, sess, event) {
  sess.resolved = true;
  markAllWorkflowCompleted();

  if (sid === state.activeSessionId) {
    showCompletion(sid, event);
  }
}

// ── Init ──────────────────────────────────────────────────────────────────
loadCallTree();
connectGlobal();
