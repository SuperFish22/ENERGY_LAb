/* Доска задач Energy Lab (ЧТЗ М06-13): перетаскивание карточек и смена колонки списком на карточке.
   Без JavaScript всё работает формой «Перенести»; скрипт только убирает перезагрузку страницы. */
(() => {
  const board = document.querySelector("[data-board]");
  if (!board) return;
  const csrf = board.dataset.csrf;
  const live = document.querySelector("[data-board-status]");
  const dialog = document.querySelector("[data-return-dialog]");
  const narrow = matchMedia("(max-width: 900px)");
  board.classList.add("is-js");

  const say = (text) => { live.textContent = ""; setTimeout(() => { live.textContent = text; }, 30); };
  const col = (status) => board.querySelector(`[data-col="${status}"]`);
  const titleOf = (card) => card.querySelector(".tcard-title").textContent.replace("Срочно", "").trim();

  function refreshCounts() {
    board.querySelectorAll("[data-col]").forEach((c) => {
      const n = c.querySelectorAll(".tcard").length;
      c.querySelector("[data-count]").textContent = n;
      c.querySelector("[data-empty]").hidden = n > 0;
    });
  }

  function setDraggable() {
    board.querySelectorAll(".tcard").forEach((card) => {
      if (card.querySelector(".tcard-move")) card.draggable = !narrow.matches;
    });
  }
  narrow.addEventListener("change", setDraggable);
  setDraggable();

  function askComment() {
    return new Promise((resolve) => {
      if (!dialog || !dialog.showModal) { resolve(prompt("Что исправить?") || ""); return; }
      const text = dialog.querySelector("textarea");
      text.value = "";
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok" ? text.value.trim() : ""), { once: true });
      dialog.showModal();
      text.focus();
    });
  }

  function placeCard(card, status, beforeId) {
    const list = col(status).querySelector("[data-list]");
    const before = beforeId && list.querySelector(`.tcard[data-id="${beforeId}"]`);
    list.insertBefore(card, before || list.querySelector("[data-empty]"));
  }

  async function move(card, to, beforeId) {
    const from = card.dataset.status;
    const home = { parent: card.parentNode, next: card.nextSibling };
    const select = card.querySelector("select[name=status]");
    let comment = "";
    if (from === "review" && (to === "in_progress" || to === "todo") && card.dataset.judge === "1") {
      comment = await askComment();
      if (!comment) { select.value = from; home.parent.insertBefore(card, home.next); say("Возврат отменён"); return; }
    }
    placeCard(card, to, beforeId);              // сразу показываем результат, при отказе вернём
    refreshCounts();
    const body = new FormData();
    body.append("csrf_token", csrf);
    body.append("status", to);
    body.append("expected", from);
    if (beforeId) body.append("before_id", beforeId);
    if (comment) body.append("comment", comment);
    let res, data = {};
    try {
      res = await fetch(`/cabinet/tasks/${card.dataset.id}/move`, { method: "POST", body, headers: { Accept: "application/json" } });
      data = await res.json();
    } catch (e) { res = { ok: false }; data = { error: "Нет связи с сервером, попробуйте ещё раз" }; }
    if (!res.ok) {
      home.parent.insertBefore(card, home.next);
      select.value = from;
      refreshCounts();
      say(data.error || "Не получилось перенести задачу");
      card.classList.add("is-refused");
      setTimeout(() => card.classList.remove("is-refused"), 1200);
      if (res.status === 409) setTimeout(() => location.reload(), 1500);
      return;
    }
    if (data.status !== to) placeCard(card, data.status, null);   // например, «Выполнено» → «На проверке»
    card.dataset.status = data.status;
    select.value = data.status;
    const expected = card.querySelector("input[name=expected]");
    if (expected) expected.value = data.status;
    const note = card.querySelector("input[name=comment]");
    if (note && data.status !== "review") note.remove();
    refreshCounts();
    say(`«${titleOf(card)}» — ${data.status_name}${data.note ? ". " + data.note : ""}`);
  }

  // смена колонки списком на карточке (клавиатура, телефон)
  board.addEventListener("change", (e) => {
    if (e.target.name !== "status") return;
    const card = e.target.closest(".tcard");
    move(card, e.target.value, null);
  });
  board.addEventListener("submit", (e) => {           // Enter в форме карточки
    e.preventDefault();
    const card = e.target.closest(".tcard");
    move(card, e.target.querySelector("select[name=status]").value, null);
  });

  // перетаскивание
  let dragged = null;
  board.addEventListener("dragstart", (e) => {
    const card = e.target.closest(".tcard");
    if (!card || !card.draggable) return;
    dragged = card;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", card.dataset.id);
    requestAnimationFrame(() => card.classList.add("is-dragging"));
  });
  board.addEventListener("dragend", () => {
    if (dragged) dragged.classList.remove("is-dragging");
    board.querySelectorAll(".is-over").forEach((c) => c.classList.remove("is-over"));
    dragged = null;
  });
  const cardAfter = (list, y) => [...list.querySelectorAll(".tcard:not(.is-dragging)")]
    .find((c) => { const r = c.getBoundingClientRect(); return y < r.top + r.height / 2; });
  board.addEventListener("dragover", (e) => {
    const c = e.target.closest("[data-col]");
    if (!dragged || !c) return;
    e.preventDefault();
    board.querySelectorAll(".is-over").forEach((x) => x !== c && x.classList.remove("is-over"));
    c.classList.add("is-over");
  });
  board.addEventListener("drop", (e) => {
    const c = e.target.closest("[data-col]");
    if (!dragged || !c) return;
    e.preventDefault();
    const before = cardAfter(c.querySelector("[data-list]"), e.clientY);
    const to = c.dataset.col;
    if (to === dragged.dataset.status && (before === dragged.nextElementSibling || before === dragged)) return;
    move(dragged, to, before ? before.dataset.id : null);
  });
})();
