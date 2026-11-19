/* Dani Action Queue — dashboard app.js */

// ---------------------------------------------------------------------------
// Error banner
// ---------------------------------------------------------------------------

function showError(msg) {
  document.getElementById('error-message').textContent = msg;
  document.getElementById('error-banner').classList.remove('hidden');
}

function dismissError() {
  document.getElementById('error-banner').classList.add('hidden');
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiFetch(path, options = {}) {
  const defaults = {
    headers: { 'Content-Type': 'application/json' },
  };
  const res = await fetch(path, { ...defaults, ...options });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function showQueue() {
  document.getElementById('queue-view').classList.remove('hidden');
  document.getElementById('audit-view').classList.add('hidden');
  document.getElementById('nav-queue').classList.add('active');
  document.getElementById('nav-audit').classList.remove('active');
  loadQueue();
}

function showAudit() {
  document.getElementById('audit-view').classList.remove('hidden');
  document.getElementById('queue-view').classList.add('hidden');
  document.getElementById('nav-audit').classList.add('active');
  document.getElementById('nav-queue').classList.remove('active');
  loadAudit();
}

// ---------------------------------------------------------------------------
// Queue view
// ---------------------------------------------------------------------------

function stateBadge(state) {
  return `<span class="badge badge-${state}">${state}</span>`;
}

function actionButtons(action) {
  const btns = [];
  if (action.state === 'draft') {
    btns.push(`<button class="btn btn-approve" onclick="approveAction('${action.id}')">Approve</button>`);
    btns.push(`<button class="btn btn-reject"  onclick="rejectAction('${action.id}')">Reject</button>`);
  }
  if (action.state === 'approved') {
    btns.push(`<button class="btn btn-execute" onclick="executeAction('${action.id}')">Execute</button>`);
    btns.push(`<button class="btn btn-reject"  onclick="rejectAction('${action.id}')">Reject</button>`);
  }
  if (action.receipt_id) {
    btns.push(`<button class="btn btn-receipt" onclick="toggleReceipt('${action.id}', '${action.receipt_id}', this)">Receipt</button>`);
  }
  return btns.join('');
}

function formatDate(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

async function loadQueue() {
  dismissError();
  const state = document.getElementById('state-filter').value;
  const url = '/api/v1/actions?limit=100' + (state ? `&state=${state}` : '');
  try {
    const actions = await apiFetch(url);
    renderQueue(actions);
  } catch (err) {
    showError('Failed to load queue: ' + err.message);
  }
}

function renderQueue(actions) {
  const tbody = document.getElementById('queue-tbody');
  tbody.innerHTML = '';
  if (actions.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#888;">No actions found.</td></tr>';
    return;
  }
  for (const action of actions) {
    const tr = document.createElement('tr');
    tr.id = `row-${action.id}`;
    tr.innerHTML = `
      <td><strong>${escHtml(action.title)}</strong><br><small style="color:#888">${action.id}</small></td>
      <td>${escHtml(action.executor)}</td>
      <td>${stateBadge(action.state)}</td>
      <td>${formatDate(action.created_at)}</td>
      <td>${actionButtons(action)}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function approveAction(id) {
  try {
    await apiFetch(`/api/v1/actions/${id}/approve`, { method: 'POST' });
    loadQueue();
  } catch (err) {
    showError('Approve failed: ' + err.message);
  }
}

async function rejectAction(id) {
  const reason = prompt('Rejection reason:');
  if (reason === null) return; // cancelled
  try {
    await apiFetch(`/api/v1/actions/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason: reason || 'No reason given.' }),
    });
    loadQueue();
  } catch (err) {
    showError('Reject failed: ' + err.message);
  }
}

async function executeAction(id) {
  try {
    await apiFetch(`/api/v1/actions/${id}/execute`, { method: 'POST' });
    loadQueue();
  } catch (err) {
    showError('Execute failed: ' + err.message);
  }
}

async function toggleReceipt(actionId, receiptId, btn) {
  const existingRow = document.getElementById(`receipt-row-${actionId}`);
  if (existingRow) {
    existingRow.remove();
    btn.textContent = 'Receipt';
    return;
  }
  try {
    const r = await apiFetch(`/api/v1/receipts/${receiptId}`);
    const v = await apiFetch(`/api/v1/receipts/${receiptId}/verify`);
    const row = document.getElementById(`row-${actionId}`);
    const tr = document.createElement('tr');
    tr.id = `receipt-row-${actionId}`;
    tr.className = 'receipt-row';
    tr.innerHTML = `
      <td colspan="5">
        <div class="receipt-panel">
          <h4>Receipt — ${stateBadge(r.status)}</h4>
          <p><strong>Summary:</strong> ${escHtml(r.result_summary)}</p>
          <p><strong>Started:</strong> ${formatDate(r.started_at)} &nbsp; <strong>Finished:</strong> ${formatDate(r.finished_at)}</p>
          <p><strong>Integrity (SHA-256):</strong> <code>${escHtml(r.integrity_hash)}</code>
            &nbsp; ${v.valid ? '<span class="badge badge-done">verified</span>' : '<span class="badge badge-failed">TAMPERED</span>'}</p>
          <pre>${escHtml(r.log_excerpt)}</pre>
        </div>
      </td>
    `;
    row.after(tr);
    btn.textContent = 'Hide Receipt';
  } catch (err) {
    showError('Could not load receipt: ' + err.message);
  }
}

// ---------------------------------------------------------------------------
// Audit view
// ---------------------------------------------------------------------------

async function loadAudit() {
  dismissError();
  try {
    const entries = await apiFetch('/api/v1/audit?limit=200');
    renderAudit(entries);
  } catch (err) {
    showError('Failed to load audit log: ' + err.message);
  }
}

function renderAudit(entries) {
  const tbody = document.getElementById('audit-tbody');
  tbody.innerHTML = '';
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;">No audit entries.</td></tr>';
    return;
  }
  for (const e of entries) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${formatDate(e.timestamp)}</td>
      <td><small>${e.action_id}</small></td>
      <td>${stateBadge(e.from_state)}</td>
      <td>${stateBadge(e.to_state)}</td>
      <td>${escHtml(e.actor)}</td>
      <td>${escHtml(e.note || '')}</td>
    `;
    tbody.appendChild(tr);
  }
}

// ---------------------------------------------------------------------------
// Utils
// ---------------------------------------------------------------------------

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  loadQueue();
});
