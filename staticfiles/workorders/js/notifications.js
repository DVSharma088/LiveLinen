/**
 * notifications.js
 *
 * Handles "Mark read" clicks on the Notifications list.
 *
 * Expects each notification item to have:
 *  - a hidden form with id "notif-form-<pk>" and a valid `action` attribute (URL)
 *  - a visible button with class "js-mark-read-btn" and data-notif-id="<pk>"
 *
 * The notifications_list.html template you created already includes that structure.
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

  function showTempMessage(msg, cls = 'success', timeout = 4000) {
    const container = document.querySelector('main') || document.body;
    const el = document.createElement('div');
    el.className = `alert alert-${cls} alert-dismissible`;
    el.role = 'alert';
    el.innerHTML = `
      ${msg}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    container.prepend(el);
    if (timeout) setTimeout(() => el.remove(), timeout);
  }

  // --- Main ---------------------------------------------------------------
  function initMarkReadButtons() {
    document.querySelectorAll('.js-mark-read-btn').forEach(btn => {
      if (btn.__notifBound) return;
      btn.__notifBound = true;

      btn.addEventListener('click', function (ev) {
        ev.preventDefault();
        const nid = btn.dataset.notifId;
        if (!nid) return;

        // Hidden form exists in template with id notif-form-<pk>
        const form = document.getElementById('notif-form-' + nid);
        if (!form) {
          console.warn('Hidden form for notification not found:', nid);
          return;
        }
        const url = form.action;

        btn.disabled = true;
        btn.textContent = 'Marking...';

        fetch(url, {
          method: 'POST',
          headers: {
            'X-CSRFToken': csrftoken,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json',
          },
        })
          .then(response => response.json().catch(() => ({ ok: false, message: 'Invalid response' })))
          .then(data => {
            if (data && data.ok) {
              // Update UI
              const row = document.getElementById('notif-' + nid);
              if (row) {
                row.classList.remove('bg-light');
                const wrap = btn.parentElement;
                if (wrap) {
                  wrap.innerHTML = '';
                  const badge = document.createElement('span');
                  badge.className = 'badge bg-success';
                  badge.textContent = 'Read';
                  wrap.appendChild(badge);
                }
              }
              showTempMessage(data.message || 'Marked as read', 'success');
            } else {
              // Fallback to submit hidden form (non-AJAX)
              form.submit();
            }
          })
          .catch(err => {
            console.error('Error marking notification read', err);
            // fallback to non-AJAX
            form.submit();
          });
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMarkReadButtons);
  } else {
    initMarkReadButtons();
  }

})();
