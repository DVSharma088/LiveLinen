/**
 * stage_actions.js
 *
 * Handles AJAX-driven stage actions:
 *  - in_progress
 *  - complete (with optional file upload)
 *  - confirm_received
 *
 * Expects each form to:
 *  - have class "stage-action-form"
 *  - have data-action (one of: in_progress, complete, confirm_received)
 *  - have data-stage-id
 *  - have a proper `action` attribute (URL to POST to)
 *
 * The template used earlier already meets these requirements.
 */

(function () {
  'use strict';

  // --- Utilities ----------------------------------------------------------
  function getCookie(name) {
    if (!document.cookie) return null;
    const cookies = document.cookie.split(';').map(c => c.trim()).filter(c => c.startsWith(name + '='));
    if (cookies.length === 0) return null;
    return decodeURIComponent(cookies[0].split('=')[1]);
  }
  const csrftoken = getCookie('csrftoken');

  function isJsonResponse(headers) {
    const accept = headers.get('accept') || '';
    return accept.indexOf('application/json') !== -1;
  }

  function showAlert(message, type = 'success', timeout = 4000) {
    const container = document.getElementById('workorder-alerts') || document.body;
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.role = 'alert';
    alert.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    // prefer alert container if present
    container.prepend(alert);
    if (timeout) setTimeout(() => {
      try { alert.remove(); } catch (e) { /* ignore */ }
    }, timeout);
  }

  // --- Main handler -------------------------------------------------------
  function initStageActionForms() {
    document.querySelectorAll('.stage-action-form').forEach(form => {
      // avoid double-binding
      if (form.__stageActionsBound) return;
      form.__stageActionsBound = true;

      form.addEventListener('submit', function (ev) {
        ev.preventDefault();

        const action = form.dataset.action;
        const stageId = form.dataset.stageId;
        const url = form.action;

        // find a button inside form to disable while request runs
        const submitBtn = form.querySelector('.js-action-btn') || form.querySelector('button[type="submit"]');

        if (submitBtn) submitBtn.disabled = true;

        // Build fetch options
        let options = {
          method: 'POST',
          headers: {
            'X-CSRFToken': csrftoken,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        };

        // If there's a file input with a selected file, use FormData
        const fileInput = form.querySelector('input[type="file"]');
        if (fileInput && fileInput.files && fileInput.files.length > 0) {
          const fd = new FormData();
          // Include hidden action input or dataset action for safety
          fd.append('action', form.querySelector('input[name="action"]') ? form.querySelector('input[name="action"]').value : action);
          fd.append('image', fileInput.files[0]);
          options.body = fd;
          // Don't set Content-Type — browser will set multipart boundary
        } else {
          // send urlencoded body
          const body = new URLSearchParams();
          body.append('action', form.querySelector('input[name="action"]') ? form.querySelector('input[name="action"]').value : action);
          options.body = body;
          options.headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8';
        }

        fetch(url, options)
          .then(response => response.json().catch(() => { throw new Error('Invalid JSON response'); }))
          .then(data => {
            if (!data || !data.ok) {
              const msg = (data && data.message) ? data.message : 'Action failed';
              showAlert(msg, 'danger');
              return;
            }

            // Success
            const msg = data.message || 'Success';
            showAlert(msg, 'success');

            // Update DOM depending on action
            if (action === 'in_progress') {
              const statusEl = document.getElementById('stage-status-' + stageId);
              if (statusEl) statusEl.textContent = 'In Progress';
            } else if (action === 'complete') {
              const statusEl = document.getElementById('stage-status-' + stageId);
              if (statusEl) statusEl.textContent = 'Completed';

              // If backend returned next_stage info, enable its Confirm Received button
              if (data.next_stage && data.next_stage.id) {
                const nextRow = document.getElementById('stage-row-' + data.next_stage.id);
                if (nextRow) {
                  const confirmBtn = nextRow.querySelector('.js-confirm-btn');
                  if (confirmBtn) {
                    confirmBtn.disabled = false;
                    // Add small hint text if not already present
                    if (!nextRow.querySelector('.handoff-hint')) {
                      const hint = document.createElement('div');
                      hint.className = 'small text-success mt-1 handoff-hint';
                      hint.textContent = 'Task received — please Confirm Received';
                      nextRow.querySelector('td:last-child').appendChild(hint);
                    }
                  }
                }
              }
            } else if (action === 'confirm_received') {
              const row = document.getElementById('stage-row-' + stageId);
              if (row) {
                const confirmBtn = row.querySelector('.js-confirm-btn');
                if (confirmBtn) confirmBtn.disabled = true;
                // append ack text
                if (!row.querySelector('.handoff-ack')) {
                  const ack = document.createElement('div');
                  ack.className = 'small text-muted mt-1 handoff-ack';
                  ack.textContent = 'Handoff confirmed';
                  row.querySelector('td:last-child').appendChild(ack);
                }
              }
            }
          })
          .catch(err => {
            console.error('Stage action error', err);
            showAlert('An error occurred while performing the action.', 'danger');
          })
          .finally(() => {
            if (submitBtn) submitBtn.disabled = false;
          });
      });
    });
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initStageActionForms);
  } else {
    initStageActionForms();
  }

})();
