/* VeriVault front-end behaviour - vanilla JavaScript, no dependencies. */
(function () {
  "use strict";
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var csrf = function () { var m = document.cookie.match(/csrftoken=([^;]+)/); return m ? decodeURIComponent(m[1]) : ($("input[name=csrfmiddlewaretoken]") || {}).value; };

  /* ---- theme ---- */
  $$("[data-theme-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("verivault-theme", next); } catch (e) {}
    });
  });

  /* ---- navigation ---- */
  var menu = $("[data-menu-toggle]");
  if (menu) {
    menu.addEventListener("click", function () { document.body.classList.toggle("sidebar-open"); });
    var scrim = $(".scrim");
    if (scrim) scrim.addEventListener("click", function () { document.body.classList.remove("sidebar-open"); });
  }
  var navToggle = $("[data-nav-toggle]");
  if (navToggle) navToggle.addEventListener("click", function () { $(".site-nav").classList.toggle("open"); });

  $$(".dropdown").forEach(function (dd) {
    var trigger = $("[data-dropdown]", dd);
    if (!trigger) return;
    trigger.addEventListener("click", function (e) { e.stopPropagation(); dd.classList.toggle("open"); trigger.setAttribute("aria-expanded", dd.classList.contains("open")); });
  });
  document.addEventListener("click", function () { $$(".dropdown.open").forEach(function (d) { d.classList.remove("open"); }); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { $$(".dropdown.open").forEach(function (d) { d.classList.remove("open"); }); document.body.classList.remove("sidebar-open"); } });

  /* ---- flash messages ---- */
  $$(".message").forEach(function (m) {
    var close = $(".close", m);
    if (close) close.addEventListener("click", function () { m.remove(); });
    if (m.classList.contains("success") || m.classList.contains("info")) setTimeout(function () { m.remove(); }, 7000);
  });

  /* ---- confirmations, copy, dialogs ---- */
  document.addEventListener("submit", function (e) {
    var msg = e.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) e.preventDefault();
  });
  document.addEventListener("click", function (e) {
    var copy = e.target.closest("[data-copy]");
    if (copy) {
      var text = copy.getAttribute("data-copy");
      var done = function () { var old = copy.getAttribute("data-label") || copy.textContent; copy.setAttribute("data-label", old); copy.textContent = "Copied"; setTimeout(function () { copy.textContent = old; }, 1400); };
      if (navigator.clipboard && window.isSecureContext !== false) { navigator.clipboard.writeText(text).then(done, done); }
      else { var ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (err) {} ta.remove(); done(); }
      return;
    }
    var open = e.target.closest("[data-dialog-open]");
    if (open) { var d = document.getElementById(open.getAttribute("data-dialog-open")); if (d && d.showModal) d.showModal(); return; }
    var close = e.target.closest("[data-dialog-close]");
    if (close) { var dd = close.closest("dialog"); if (dd) dd.close(); return; }
    if (e.target.tagName === "DIALOG") e.target.close();
  });

  /* ---- progress bars & rings (values come from data-* to stay CSP friendly) ---- */
  requestAnimationFrame(function () {
    $$("[data-width]").forEach(function (el) { el.style.width = el.getAttribute("data-width") + "%"; });
    $$("[data-ring]").forEach(function (el) { el.style.setProperty("--v", el.getAttribute("data-ring")); });
    $$("[data-bg]").forEach(function (el) { el.style.background = el.getAttribute("data-bg"); });
    $$("[data-color]").forEach(function (el) { el.style.background = el.getAttribute("data-color"); });
  });

  /* ---- category donut ---- */
  var donutData = $("#category-data");
  var donut = $("[data-donut]");
  if (donutData && donut) {
    try {
      var rows = JSON.parse(donutData.textContent), total = rows.reduce(function (s, r) { return s + r.count; }, 0);
      var palette = ["#1d7f6e", "#14233a", "#a8802c", "#c2536a", "#7256b8", "#3a76c4", "#6b7a8c", "#4aa88f", "#8b6b1f", "#9aa7b5"];
      var acc = 0, stops = [];
      rows.forEach(function (r, i) { var start = acc / total * 100; acc += r.count; stops.push(palette[i % palette.length] + " " + start + "% " + (acc / total * 100) + "%"); });
      if (total) donut.style.background = "conic-gradient(" + stops.join(",") + ")";
      $$("[data-legend-dot]").forEach(function (el, i) { el.style.background = palette[i % palette.length]; });
    } catch (err) {}
  }

  /* ---- auto submit selects ---- */
  $$("[data-autosubmit]").forEach(function (el) { el.addEventListener("change", function () { el.form.submit(); }); });

  /* ---- password helpers ---- */
  $$("[data-pw-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = btn.parentElement.querySelector("input");
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
    });
  });
  $$("[data-strength]").forEach(function (input) {
    var bar = input.parentElement.parentElement.querySelector(".strength > span");
    if (!bar) return;
    input.addEventListener("input", function () {
      var v = input.value, score = 0;
      if (v.length >= 8) score++; if (v.length >= 12) score++;
      if (/[a-z]/.test(v) && /[A-Z]/.test(v)) score++;
      if (/\d/.test(v)) score++; if (/[^A-Za-z0-9]/.test(v)) score++;
      bar.style.width = (score * 20) + "%";
      bar.style.background = score <= 2 ? "#b3372b" : score <= 3 ? "#b26a12" : "#1d7f6e";
    });
  });

  /* ---- SHA-256 in the browser ---- */
  function sha256(file) {
    if (!(window.crypto && window.crypto.subtle) || !file.arrayBuffer) return Promise.reject(new Error("unsupported"));
    if (file.size > 60 * 1024 * 1024) return Promise.reject(new Error("too-large"));
    return file.arrayBuffer().then(function (buf) { return crypto.subtle.digest("SHA-256", buf); }).then(function (digest) {
      return Array.prototype.map.call(new Uint8Array(digest), function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
    });
  }
  function groups(hex) { return hex.match(/.{1,8}/g).map(function (g) { return "<span>" + g + "</span>"; }).join(""); }
  function humanSize(n) { var u = ["B", "KB", "MB", "GB"], i = 0; while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; } return (i ? n.toFixed(1) : n) + " " + u[i]; }
  function wireDrop(zone, input, onFile) {
    if (!zone || !input) return;
    ["dragenter", "dragover"].forEach(function (ev) { zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.add("drop-active"); }); });
    ["dragleave", "drop"].forEach(function (ev) { zone.addEventListener(ev, function (e) { e.preventDefault(); zone.classList.remove("drop-active"); }); });
    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files.length) { try { input.files = e.dataTransfer.files; } catch (err) {} onFile(e.dataTransfer.files[0]); }
    });
    zone.addEventListener("click", function (e) { if (e.target !== input && !e.target.closest("label")) input.click(); });
    input.addEventListener("change", function () { if (input.files.length) onFile(input.files[0]); });
  }

  /* home page demo */
  var demo = $("[data-fingerprint-demo]");
  if (demo) {
    var out = $(".demo-result", demo), dinput = $("input[type=file]", demo);
    wireDrop($(".demo-drop", demo), dinput, function (file) {
      out.classList.remove("hidden");
      $("[data-demo-name]", demo).textContent = file.name + " · " + humanSize(file.size);
      var hash = $("[data-demo-hash]", demo); hash.textContent = "Computing…";
      sha256(file).then(function (hex) { hash.innerHTML = groups(hex); hash.classList.add("hash-groups"); $("[data-demo-copy]", demo).setAttribute("data-copy", hex); })
        .catch(function () { hash.textContent = "Your browser could not fingerprint this file (too large or unsupported)."; });
    });
  }

  /* public verify page */
  var vform = $("[data-verify-form]");
  if (vform) {
    var vfile = $("input[type=file]", vform), vhash = $("#id_sha256"), note = $("[data-verify-local]", vform);
    vfile.addEventListener("change", function () {
      if (!vfile.files.length) return;
      var f = vfile.files[0];
      note.textContent = "Fingerprinting " + f.name + " in your browser…";
      sha256(f).then(function (hex) {
        vhash.value = hex; note.textContent = "Fingerprint computed locally - the file itself never leaves your device.";
        vfile.value = ""; vfile.setAttribute("data-cleared", "1");
      }).catch(function () { note.textContent = "Local fingerprinting unavailable - the file will be checked on the server and not stored."; });
    });
  }

  /* upload page: local hash + rule-based suggestions */
  var upload = $("[data-upload-form]");
  if (upload) {
    var ufile = $("input[type=file]", upload), zone = $("[data-dropzone]", upload), label = $("[data-file-label]", upload);
    var suggestBox = $("[data-suggestion]", upload), titleInput = $("#id_title"), catSel = $("#id_category"), tagsInput = $("#id_tags_text"), expiry = $("#id_expiry_date");
    var timer;
    wireDrop(zone, ufile, function (file) {
      label.innerHTML = "<strong>" + file.name.replace(/[<>&]/g, "") + "</strong> · " + humanSize(file.size);
      var hashEl = $("[data-local-hash]", upload);
      if (hashEl) { hashEl.textContent = "SHA-256: computing…"; sha256(file).then(function (hex) { hashEl.textContent = "SHA-256: " + hex; }).catch(function () { hashEl.textContent = ""; }); }
      clearTimeout(timer);
      timer = setTimeout(function () {
        fetch(upload.getAttribute("data-suggest-url") + "?filename=" + encodeURIComponent(file.name), { credentials: "same-origin" })
          .then(function (r) { return r.json(); }).then(function (s) {
            if (titleInput && !titleInput.value) titleInput.value = s.title || "";
            if (s.category && s.category !== "other") {
              suggestBox.classList.remove("hidden");
              suggestBox.innerHTML = "Looks like <strong>" + s.category_label + "</strong> (" + Math.round(s.confidence * 100) + "% match)" + (s.tags.length ? " · suggested tags: " + s.tags.join(", ") : "") + (s.expiry_hint ? "<br>" + s.expiry_hint : "");
              if (catSel && catSel.value === "auto") catSel.value = s.category;
              if (tagsInput && !tagsInput.value) tagsInput.value = s.tags.join(", ");
            } else { suggestBox.classList.add("hidden"); }
            if (expiry && !expiry.value && s.expiry_date) expiry.value = s.expiry_date;
          }).catch(function () {});
      }, 150);
    });
  }

  /* ---- live search suggestions ---- */
  var search = $("[data-search]");
  if (search) {
    var box = $(".suggest", search.parentElement), url = search.getAttribute("data-suggest-url"), t;
    search.addEventListener("input", function () {
      clearTimeout(t);
      var q = search.value.trim();
      if (q.length < 2) { box.classList.add("hidden"); return; }
      t = setTimeout(function () {
        fetch(url + "?q=" + encodeURIComponent(q), { credentials: "same-origin" }).then(function (r) { return r.json(); }).then(function (d) {
          box.innerHTML = "";
          d.results.forEach(function (r) { var a = document.createElement("a"); a.href = r.url; var s1 = document.createElement("span"); s1.textContent = r.title; var s2 = document.createElement("span"); s2.className = "muted small"; s2.textContent = r.category; a.appendChild(s1); a.appendChild(s2); box.appendChild(a); });
          box.classList.toggle("hidden", !d.results.length);
        }).catch(function () {});
      }, 200);
    });
    document.addEventListener("click", function (e) { if (!search.parentElement.contains(e.target)) box.classList.add("hidden"); });
  }

  /* ---- bulk selection ---- */
  var bulk = $("[data-bulk]");
  if (bulk) {
    var boxes = $$("input[name=ids]", bulk), bar = $(".bulkbar", bulk), count = $("[data-bulk-count]", bulk), all = $("[data-select-all]", bulk);
    var refresh = function () {
      var n = boxes.filter(function (b) { return b.checked; }).length;
      bar.classList.toggle("show", n > 0); count.textContent = n + " selected";
      if (all) all.checked = n === boxes.length && n > 0;
    };
    boxes.forEach(function (b) { b.addEventListener("change", refresh); });
    if (all) all.addEventListener("change", function () { boxes.forEach(function (b) { b.checked = all.checked; }); refresh(); });
    var actionSel = $("[data-bulk-action]", bulk);
    if (actionSel) actionSel.addEventListener("change", function () {
      $("[data-bulk-folder]", bulk).classList.toggle("hidden", actionSel.value !== "move");
      $("[data-bulk-tag]", bulk).classList.toggle("hidden", actionSel.value !== "tag");
    });
    bulk.addEventListener("submit", function (e) {
      if (e.target.id !== "bulk-form") return;
      var sel = actionSel && actionSel.value;
      if (!sel) { e.preventDefault(); actionSel.focus(); }
      else if (sel === "trash" && !window.confirm("Move the selected documents to the trash? Their share links will be revoked.")) e.preventDefault();
    });
  }

  /* ---- favourite stars (progressive enhancement) ---- */
  $$("form[data-favorite]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      fetch(form.action, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.json(); }).then(function (d) { $(".star", form).classList.toggle("on", d.favorite); })
        .catch(function () { form.submit(); });
    });
  });
})();
