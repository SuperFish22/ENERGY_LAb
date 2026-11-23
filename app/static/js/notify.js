/* Колокольчик кабинета (spec 003): раз в 30 секунд спрашивает сайт о новых уведомлениях,
   обновляет счётчик и заголовок вкладки, показывает всплывающее сообщение. Без JS работает обычная ссылка. */
(() => {
  const bell = document.querySelector("[data-bell]");
  if (!bell) return;
  const count = bell.querySelector("[data-bell-count]");
  const toasts = document.querySelector("[data-toasts]");
  const baseTitle = document.title.replace(/^\(\d+\+?\)\s*/, "");
  let last = null;            // id последнего известного уведомления; первый опрос только запоминает его
  let timer = null;

  function show(n) {
    count.hidden = n === 0;
    count.textContent = n > 99 ? "99+" : String(n);
    bell.classList.toggle("has-unread", n > 0);
    bell.setAttribute("aria-label", n ? `Уведомления: непрочитанных ${n}` : "Уведомления");
    document.title = n ? `(${n}) ${baseTitle}` : baseTitle;
  }

  function toast(item) {
    if (!toasts) return;
    const a = document.createElement("a");
    a.className = "toast";
    a.href = item.url;
    a.textContent = item.text;
    toasts.append(a);
    setTimeout(() => a.classList.add("is-gone"), 7000);
    setTimeout(() => a.remove(), 7600);
  }

  async function poll() {
    try {
      const r = await fetch(`/cabinet/notifications/feed?after=${last ?? 0}`, { headers: { Accept: "application/json" } });
      if (!r.ok) return;
      const data = await r.json();
      if (last !== null) data.items.forEach(toast);
      last = data.last;
      show(data.unread);
    } catch (e) { /* нет сети — попробуем позже */ }
  }

  function start() { if (!timer) { poll(); timer = setInterval(poll, 30000); } }
  function stop() { clearInterval(timer); timer = null; }
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
  start();
})();
