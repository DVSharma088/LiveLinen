(function () {
  "use strict";

  // CSRF helpers
  function getCookie(name) {
    if (!document.cookie) return null;
    const cookies = document.cookie.split(";").map(c => c.trim());
    for (let cookie of cookies) {
      if (cookie.startsWith(name + "=")) {
        return decodeURIComponent(cookie.split("=")[1]);
      }
    }
    return null;
  }
  const csrftoken = getCookie("csrftoken");

  function setLoading(btn, isLoading) {
    if (!btn) return;
    if (isLoading) {
      btn.dataset.orig = btn.innerHTML;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Please wait';
      btn.disabled = true;
    } else {
      if (btn.dataset.orig) btn.innerHTML = btn.dataset.orig;
      btn.disabled = false;
    }
  }

  // Login/Logout button
  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest && ev.target.closest("#login-time-btn");
    if (!btn) return;
    ev.preventDefault();

    const form = document.querySelector("#login-time-form");
    const feedback = document.querySelector("#login-time-feedback");

    setLoading(btn, true);
    if (feedback) feedback.textContent = "Saving...";

    // always post to /dashboard/login-time/
    const action = form ? form.getAttribute("action") : "/dashboard/login-time/";

    const headers = {
      "X-CSRFToken": csrftoken,
      Accept: "application/json",
    };

    fetch(action, {
      method: "POST",
      credentials: "same-origin",
      headers,
    })
      .then(async (res) => {
        if (!res.ok) {
          const txt = await res.text().catch(() => "");
          throw new Error("Server error: " + (txt || res.statusText));
        }
        return res.json().catch(() => {
          throw new Error("Invalid JSON response");
        });
      })
      .then((data) => {
        if (data && data.ok && data.attendance) {
          const att = data.attendance;
          // update UI: change button label and show times
          if (att.logout_time && att.login_time) {
            btn.innerText = "Login";
            if (feedback) feedback.innerText = `Logged out at ${new Date(att.logout_time).toLocaleString()}`;
          } else if (att.login_time && !att.logout_time) {
            btn.innerText = "Logout";
            if (feedback) feedback.innerText = `Logged in at ${new Date(att.login_time).toLocaleString()}`;
          } else {
            if (feedback) feedback.innerText = "Attendance recorded";
          }
          // reload to update other widgets
          setTimeout(() => window.location.reload(), 900);
        } else {
          throw new Error((data && data.error) || "Unexpected server response");
        }
      })
      .catch((err) => {
        console.error("Attendance error", err);
        if (feedback) feedback.innerText = err.message || "Could not record attendance";
      })
      .finally(() => setLoading(btn, false));
  });

  // Generic AJAX form submit handler for forms with class "ajax-form"
  document.addEventListener("submit", function (ev) {
    const form = ev.target;
    if (!form.classList || !form.classList.contains("ajax-form")) return; // ignore non-ajax forms
    ev.preventDefault();

    const submitBtn = form.querySelector('button[type="submit"]') || form.querySelector('input[type="submit"]');
    setLoading(submitBtn, true);

    const url = form.getAttribute("action") || window.location.href;
    const method = (form.getAttribute("method") || "POST").toUpperCase();

    const fd = new FormData(form);

    const headers = {
      "X-CSRFToken": csrftoken,
      Accept: "text/html, application/json",
    };

    fetch(url, {
      method,
      credentials: "same-origin",
      headers,
      body: fd,
    })
      .then(async (res) => {
        if (res.redirected) {
          window.location.href = res.url;
          return;
        }
        if (!res.ok) {
          const text = await res.text().catch(() => "");
          throw new Error(text || res.statusText);
        }
        window.location.reload();
      })
      .catch((err) => {
        console.error("Form submit error", err);
        let errBox = form.querySelector(".form-submit-error");
        if (!errBox) {
          errBox = document.createElement("div");
          errBox.className = "form-submit-error alert alert-danger mt-3";
          form.prepend(errBox);
        }
        errBox.innerText = err.message || "Could not submit form";
      })
      .finally(() => setLoading(submitBtn, false));
  });
})();
