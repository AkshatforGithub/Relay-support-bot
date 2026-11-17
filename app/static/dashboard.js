// Relay Dashboard - Dashboard JavaScript
// Auth box management, API calls, and panel updates

const ADMIN_API_KEY = sessionStorage.getItem('admin-api-key');
const API_BASE = '/api';

// Elements
const authBox = document.getElementById('auth-box');
const dashboard = document.getElementById('dashboard');
const apiKeyInput = document.getElementById('api-key');
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const apiError = document.getElementById('api-error');

// Panel content elements
const statsContent = document.getElementById('stats-content');
const ticketsContent = document.getElementById('tickets-content');
const convContent = document.getElementById('conv-content');
const convTextbox = document.getElementById('conv-textbox');
const convLoadBtn = document.getElementById('conv-load-btn');

// Ticket table element (created dynamically)
let ticketTable = null;

// Initialize: show auth box if no key, otherwise try to proceed
function init() {
  // If we have a key in sessionStorage, try to use it
  if (ADMIN_API_KEY) {
    apiKeyInput.value = ADMIN_API_KEY;
    // Don't auto-sign in - let user explicitly sign in
    // Actually, per the spec: "On load, show a small box asking for the admin key"
    // So we always show the auth box on load
  }

  // Show auth box
  authBox.classList.remove('hidden');
  dashboard.style.display = 'none';

  // Set up event listeners
  signInBtn.addEventListener('click', handleSignIn);
  signOutBtn.addEventListener('click', handleSignOut);
  apiKeyInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleSignIn();
  });
}

// Handle sign in
async function handleSignIn() {
  const key = apiKeyInput.value.trim();
  if (!key) {
    showApiError('Please enter an API key');
    return;
  }

  // Store in sessionStorage
  sessionStorage.setItem('admin-api-key', key);

  // Try to verify the key by making a test API call
  try {
    await fetch(`${API_BASE}/system-stats`, {
      method: 'GET',
      headers: {
        'X-API-Key': key
      }
    });
    // If we get here, the key is valid
    hideAuthBox();
    await loadSystemStats();
    await loadTickets();
  } catch (error) {
    // Key is invalid, clear sessionStorage and show error
    sessionStorage.removeItem('admin-api-key');
    showApiError('Invalid API key. Please try again.');
  }
}

// Handle sign out
function handleSignOut() {
  sessionStorage.removeItem('admin-api-key');
  showAuthBox();
  hideAllPanels();
  showApiError('Signed out. Please sign in again to access the dashboard.');
}

// Hide auth box and show dashboard
function hideAuthBox() {
  authBox.classList.add('hidden');
  dashboard.style.display = 'block';
}

// Show auth box
function showAuthBox() {
  authBox.classList.remove('hidden');
  dashboard.style.display = 'none';
  hideAllPanels();
}

// Show API error banner
function showApiError(message) {
  apiError.textContent = message;
  apiError.classList.add('visible');
}

// Hide API error banner
function hideApiError() {
  apiError.classList.remove('visible');
}

// Hide all panels
function hideAllPanels() {
  statsContent.innerHTML = '';
  ticketsContent.innerHTML = '';
  convContent.innerHTML = '';
}

// API fetch with auth header
async function apiFetch(endpoint, options = {}) {
  const key = sessionStorage.getItem('admin-api-key');
  if (!key) {
    showAuthBox();
    throw new Error('No API key');
  }

  const headers = {
    'X-API-Key': key,
    'Content-Type': 'application/json',
    ...options.headers
  };

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers
  });

  // Handle 401/403 - send back to auth box
  if (response.status === 401 || response.status === 403) {
    sessionStorage.removeItem('admin-api-key');
    hideAuthBox();
    showAllPanelsEmpty();
    showApiError(`Authentication failed (${response.status}: ${response.statusText}). Please sign in again.`);
    throw new Error(`Auth failed: ${response.statusText}`);
  }

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`);
  }

  return response.json();
}

// Show all panels empty
function showAllPanelsEmpty() {
  statsContent.innerHTML = '<div class="empty">No data yet</div>';
  ticketsContent.innerHTML = '<div class="empty">No data yet</div>';
  convContent.innerHTML = '<div class="empty">No data yet</div>';
}

// Load system stats
async function loadSystemStats() {
  try {
    const data = await apiFetch('/system-stats');
    displaySystemStats(data);
  } catch (error) {
    console.error('Failed to load system stats:', error);
    statsContent.innerHTML = '<div class="empty">Failed to load stats</div>';
  }
}

// Display system stats
function displaySystemStats(data) {
  const { total_tickets, pending_tickets, resolved_tickets,
           escalation_rate, active_conversations_30d, test_bench } = data;

  statsContent.innerHTML = `
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
      <div class="card">
        <strong>Total Tickets</strong>
        <p>${total_tickets}</p>
      </div>
      <div class="card">
        <strong>Pending Tickets</strong>
        <p>${pending_tickets}</p>
      </div>
      <div class="card">
        <strong>Resolved Tickets</strong>
        <p>${resolved_tickets}</p>
      </div>
      <div class="card">
        <strong>Escalation Rate</strong>
        <p>${escalation_rate}%</p>
      </div>
      <div class="card">
        <strong>Active Conversations (30d)</strong>
        <p>${active_conversations_30d}</p>
      </div>
    </div>

    <div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border);">
      <h4>Test-Bench Results (not live data)</h4>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem;">
        <div class="card">
          <strong>Dupes Suppressed</strong>
          <p>${test_bench.dupesSuppressed}</p>
        </div>
        <div class="card">
          <strong>Rate Limit False Positives</strong>
          <p>${test_bench.rateLimitFalsePositives}</p>
        </div>
        <div class="card">
          <strong>Silent Failures</strong>
          <p>${test_bench.silentFailures}</p>
        </div>
        <div class="card">
          <strong>Median Response Time</strong>
          <p>${test_bench.medianResponseTime}s</p>
        </div>
        <div class="card">
          <strong>P95 Response Time</strong>
          <p>${test_bench.p95ResponseTime}s</p>
        </div>
        <div class="card">
          <strong>Critic First Pass Approval</strong>
          <p>${test_bench.criticFirstPassApproval}%</p>
        </div>
        <div class="card">
          <strong>Auto Resolution Rate</strong>
          <p>${test_bench.autoResolutionRate}%</p>
        </div>
        <div class="card">
          <strong>Escalation Rate</strong>
          <p>${test_bench.escalationRate}%</p>
        </div>
      </div>
    </div>
  `;
}

// Load tickets with filters
async function loadTickets(statusFilter, categoryFilter) {
  try {
    const params = new URLSearchParams({
      page: '1',
      perPage: '20'
    });
    if (statusFilter) params.append('status', statusFilter);
    if (categoryFilter) params.append('category', categoryFilter);

    const data = await apiFetch(`/tickets?${params.toString()}`);
    displayTickets(data);
  } catch (error) {
    console.error('Failed to load tickets:', error);
    ticketsContent.innerHTML = '<div class="empty">Failed to load tickets</div>';
  }
}

// Display tickets
function displayTickets(tickets) {
  const { tickets: allTickets, total, page, perPage } = tickets;

  if (!allTickets || allTickets.length === 0) {
    ticketsContent.innerHTML = '<div class="empty">No tickets yet</div>';
    return;
  }

  // Build ticket rows
  const rows = allTickets.map(ticket => {
    const statusClass = ticket.status === 'resolved' ? 'resolved' : 'pending';
    const statusText = ticket.status === 'resolved' ? 'Resolved' : 'Pending';
    const resolvedBy = ticket.resolved_by || '';

    return `
      <div class="ticket-row ${statusClass}" data-ticket-id="${ticket.id}" data-chat-id="${ticket.parent_chat_id}">
        <span>${ticket.summary || 'No summary'}</span>
        <span class="ticket-status ${statusClass}">${statusText}</span>
        ${resolvedBy ? `<span>by: ${resolvedBy}</span>` : ''}
      </div>
    `;
  }).join('');

  ticketsContent.innerHTML = `
    <div style="max-height: 400px; overflow-y: auto;">
      ${rows}
    </div>
    <div style="margin-top: 0.5rem; font-size: 0.85rem;">
      Showing page ${page} of ${Math.ceil(total / perPage)} (total: ${total} tickets)
    </div>
  `;

  // Add click handlers to ticket rows
  document.querySelectorAll('.ticket-row').forEach(row => {
    row.addEventListener('click', () => {
      const ticketId = row.dataset.ticketId;
      const chatId = row.dataset.chatId;
      // Open conversation panel with this chat ID
      convTextbox.value = chatId;
      loadConversation(chatId);
    });
  });

  // Add resolve button handlers
  document.querySelectorAll('.resolve-ticket').forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.stopPropagation();
      const ticketId = this.dataset.ticketId;
      resolveTicket(ticketId);
    });
  });
}

// Resolve a ticket
async function resolveTicket(ticketId) {
  const resolvedBy = prompt('Enter the name or ID of who is resolving this ticket:');
  if (!resolvedBy || resolvedBy.trim() === '') {
    // Button is disabled while empty per phase2.md, but we handle this gracefully
    return;
  }

  try {
    const data = await apiFetch('/resolve-ticket', {
      method: 'POST',
      body: JSON.stringify({
        ticketId: parseInt(ticketId),
        resolvedBy: resolvedBy.trim()
      })
    });

    showApiError('Ticket resolved successfully!');

    // Reload tickets
    await loadTickets();

    // Reload conversation if same chat is open
    const openChatId = document.querySelector('.ticket-row.selected');
    if (openChatId) {
      loadConversation(openChatId.dataset.chatId);
    }
  } catch (error) {
    console.error('Failed to resolve ticket:', error);
    showApiError('Failed to resolve ticket');
  }
}

// Load conversation
async function loadConversation(chatId) {
  try {
    const data = await apiFetch(`/conversations/${chatId}`);
    displayConversation(data);

    // Set up interval to refresh conversation every 30s
    const convRefresh = setInterval(() => {
      loadConversation(chatId);
    }, 30000);

    // Store the interval ID to clear it later if needed
    // We'll clear it when a new chat is loaded or on sign out

  } catch (error) {
    console.error('Failed to load conversation:', error);
    convContent.innerHTML = '<div class="empty">Failed to load conversation</div>';
  }
}

// Display conversation
function displayConversation(conv) {
  const { chatId, query, username, correlationId, chatHistory,
          lastAssistantAnswer, assistantCategory, needsEscalation,
          escalationAlreadyOpen, status, usedOrderId, usedEmail } = conv;

  // Build conversation messages
  const messages = chatHistory || [];
  const messageElements = messages.map(msg => {
    const role = msg.role || 'unknown';
    const content = msg.content || '';
    return `<div style="margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border);">
      <strong>${role.charAt(0).toUpperCase() + role.slice(1)}:</strong> ${content}
    </div>`;
  }).join('') || '<p>No messages yet</p>';

  convContent.innerHTML = `
    <div style="margin-bottom: 1rem;">
      <p><strong>Chat ID:</strong> ${chatId}</p>
      <p><strong>Query:</strong> ${query || 'N/A'}</p>
      <p><strong>Status:</strong> ${status || 'N/A'}</p>
      <p><strong>Escalation:</strong> ${escalationAlreadyOpen ? 'Already open (pending)' : needsEscalation ? 'Needed' : 'None'}</p>
      ${usedOrderId ? `<p><strong>Order ID:</strong> ${usedOrderId}</p>` : ''}
      ${usedEmail ? `<p><strong>Email:</strong> ${usedEmail}</p>` : ''}
    </div>

    <h4>Conversation (last 10 messages)</h4>
    <div style="max-height: 300px; overflow-y: auto;">
      ${messageElements}
    </div>

    ${lastAssistantAnswer ? `<div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border);">
      <strong>Last Assistant Answer:</strong> ${lastAssistantAnswer}
    </div>` : ''}
  `;

  // Set up refresh interval for conversation every 30s
  // (already handled in loadConversation)
}

// Sign in button click handler
signInBtn.addEventListener('click', handleSignIn);

// Sign out button click handler
signOutBtn.addEventListener('click', handleSignOut);

// Initialization
init();

// Export functions for use in HTML
window.loadSystemStats = loadSystemStats;
window.loadTickets = loadTickets;
window.loadConversation = loadConversation;
window.resolveTicket = resolveTicket;