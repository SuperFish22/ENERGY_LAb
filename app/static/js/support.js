// Диалог поддержки: новые сообщения без перезагрузки, отправка по Ctrl+Enter, вставка ответа из FAQ.
(function () {
  var thread = document.querySelector("[data-sup-thread]");
  var form = document.querySelector("[data-sup-form]");
  if (!thread || !form) return;
  var area = form.querySelector("textarea");
  var badge = document.querySelector("[data-sup-status]");
  var last = parseInt(thread.dataset.last, 10) || 0;

  function bubble(m) {
    if (document.getElementById("m" + m.id)) return;
    var li = document.createElement("li");
    li.className = "bubble bubble-" + m.dir;
    li.id = "m" + m.id;
    var p = document.createElement("p");
    p.textContent = m.text;
    var meta = document.createElement("span");
    meta.className = "bubble-meta";
    meta.textContent = (m.dir === "out" ? (m.who || "Оператор") + (m.source && m.source !== "с сайта" ? ", " + m.source : "") + " · " : "") + m.at;
    li.appendChild(p);
    li.appendChild(meta);
    thread.appendChild(li);
    last = Math.max(last, m.id);
    li.scrollIntoView({ block: "nearest" });
  }

  function poll() {
    if (document.hidden) return;
    fetch(thread.dataset.feed + "?after=" + last, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d) return;
        d.messages.forEach(bubble);
        if (badge) badge.textContent = d.status_name;
      })
      .catch(function () {});
  }
  setInterval(poll, 10000);

  form.addEventListener("submit", function (e) {
    if (!window.fetch || !area.value.trim()) return;
    e.preventDefault();
    var btn = form.querySelector("button");
    btn.disabled = true;
    fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin",
                         headers: { Accept: "application/json" } })
      .then(function (r) { if (!r.ok) throw r; return r.json(); })
      .then(function (d) { bubble(d.message); area.value = ""; if (badge) badge.textContent = d.status_name; })
      .catch(function () { form.submit(); })
      .finally(function () { btn.disabled = false; area.focus(); });
  });
  area.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) form.requestSubmit();
  });
  document.querySelectorAll("[data-insert]").forEach(function (b) {
    b.addEventListener("click", function () {
      area.value = (area.value ? area.value.replace(/\s+$/, "") + "\n\n" : "") + b.dataset.insert;
      area.focus();
    });
  });
  var end = thread.lastElementChild;
  if (end && !location.hash) end.scrollIntoView({ block: "nearest" });
})();
