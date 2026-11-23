"""Доска задач (ЧТЗ М06-13 – М06-15): правила переходов между колонками, порядок карточек, история.

Колонки — это статусы задачи, набор фиксирован: К выполнению → В работе → На проверке → Выполнено.
Права (spec 001, data-model.md):
* исполнитель двигает свою задачу между «К выполнению» и «В работе» и сдаёт её «На проверку»;
  если он же автор — может сразу закрыть «Выполнено»;
* автор задачи и руководитель — любые переходы; вернуть с проверки в работу — только с комментарием;
* остальным менять статус нельзя.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.notify import notify
from app.security import audit

COLUMNS = tuple(m.TASK_STATUSES)          # порядок колонок на доске
STEP = 1000                               # шаг позиций внутри колонки
DONE_VISIBLE_DAYS = 14                    # сколько дней «Выполнено» видно на доске, остальное — «Архив»

NO_RIGHTS = "Менять статус может исполнитель, автор или руководитель"
NEED_COMMENT = "Напишите, что исправить: без комментария вернуть задачу в работу нельзя"


@dataclass
class MoveResult:
    ok: bool
    status: str
    error: str | None = None
    note: str | None = None      # пояснение, если статус поменялся не на тот, что просили
    conflict: bool = False


def roles_for(user: m.User, task: m.Task) -> tuple[bool, bool, bool]:
    """(исполнитель, автор, руководитель)."""
    return task.assignee_id == user.id, task.author_id == user.id, user.has_role("head")


def resolve_target(user: m.User, task: m.Task, to: str) -> tuple[str, str | None]:
    """Какой статус получится на самом деле. Исполнитель, сдающий чужую задачу, отправляет её на проверку."""
    is_assignee, is_author, is_head = roles_for(user, task)
    if to == "done" and is_assignee and not (is_author or is_head):
        return "review", "Отправлено на проверку автору"
    return to, None


def can_move(user: m.User, task: m.Task, to: str, comment: str | None = None) -> str | None:
    """Текст ошибки или None, если переход разрешён. `to` — уже итоговый статус (после resolve_target)."""
    if to not in m.TASK_STATUSES:
        return "Такой колонки нет"
    is_assignee, is_author, is_head = roles_for(user, task)
    if not (is_assignee or is_author or is_head):
        return NO_RIGHTS
    frm = task.status
    if is_author or is_head:
        if frm == "review" and to in ("in_progress", "todo") and not (comment or "").strip():
            return NEED_COMMENT
        return None
    # только исполнитель
    if frm == to:
        return None
    allowed = {("todo", "in_progress"), ("in_progress", "todo"), ("todo", "review"), ("in_progress", "review")}
    if (frm, to) in allowed:
        return None
    if frm == "review":
        return "Задача на проверке у автора — вернуть или принять её может автор или руководитель"
    if frm == "done":
        return "Задача уже принята — открыть её заново может автор или руководитель"
    return NO_RIGHTS


def _column(db: Session, status: str, exclude_id: int) -> list[m.Task]:
    return list(db.scalars(select(m.Task).where(m.Task.status == status, m.Task.id != exclude_id)
                           .order_by(m.Task.position, m.Task.id)))


def place(db: Session, task: m.Task, status: str, before_id: int | None) -> None:
    """Поставить карточку в колонку `status` перед карточкой `before_id` (или в конец)."""
    col = _column(db, status, task.id)
    idx = next((i for i, t in enumerate(col) if t.id == before_id), None) if before_id else None
    if idx is None:                                   # в конец колонки
        task.position = (col[-1].position if col else 0) + STEP
        return
    prev_pos = col[idx - 1].position if idx > 0 else col[idx].position - 2 * STEP
    nxt = col[idx].position
    if nxt - prev_pos > 1:
        task.position = (prev_pos + nxt) // 2
        return
    # соседние позиции слиплись — перенумеровать колонку с шагом STEP
    for i, t in enumerate(col[:idx] + [task] + col[idx:], 1):
        t.position = i * STEP


def log(db: Session, task: m.Task, user: m.User | None, field: str, old: str | None, new: str | None,
        comment: str | None = None, source: str = "cabinet") -> None:
    db.add(m.TaskEvent(task_id=task.id, user_id=user.id if user else None, field=field,
                       old_value=old, new_value=new, comment=(comment or "").strip() or None, source=source))


def move(db: Session, user: m.User, task: m.Task, to: str, *, before_id: int | None = None,
         comment: str | None = None, expected: str | None = None, source: str = "cabinet") -> MoveResult:
    """Перенести задачу. `expected` — статус, который видел пользователь (защита от одновременных изменений)."""
    if expected and expected != task.status:
        who = _last_mover(db, task)
        return MoveResult(False, task.status, f"Задачу уже переместил(а) {who} — доска обновлена".strip(),
                          conflict=True)
    target, note = resolve_target(user, task, to)
    err = can_move(user, task, target, comment)
    if err:
        return MoveResult(False, task.status, err)
    frm = task.status
    if frm != target or before_id is not None:
        place(db, task, target, before_id)
    if frm == target:
        db.flush()
        return MoveResult(True, target, note=note)
    task.status = target
    task.updated_at = datetime.now()
    task.done_at = datetime.now() if target == "done" else None
    log(db, task, user, "status", frm, target, comment, source)
    audit(db, user.id, "task_status", f"task:{task.id}", f"{frm} → {target}")
    _notify(db, user, task, frm, target, comment)
    db.flush()
    return MoveResult(True, target, note=note)


def _last_mover(db: Session, task: m.Task) -> str:
    ev = db.scalar(select(m.TaskEvent).where(m.TaskEvent.task_id == task.id, m.TaskEvent.field == "status")
                   .order_by(m.TaskEvent.id.desc()))
    return ev.user.full_name if ev and ev.user else ""


WORK_BUTTONS = "work"      # кнопки исполнителю: «В работу», «Сдать»
ACCEPT_BUTTONS = "accept"  # кнопки автору: «Принять»


def buttons(task: m.Task, which: str) -> list[tuple[str, str]]:
    """Кнопки под сообщением Telegram; нажатие обрабатывает бот (callback «task:id:статус»)."""
    if which == WORK_BUTTONS:
        return ([("▶ Взять в работу", f"task:{task.id}:in_progress")] if task.status == "todo" else []) + \
               [("✓ Сдать", f"task:{task.id}:done")]
    if which == ACCEPT_BUTTONS:
        return [("✓ Принять", f"task:{task.id}:done")]
    return []


def link(task: m.Task) -> str:
    return f"/cabinet/tasks/{task.id}"


def _notify(db: Session, actor: m.User, task: m.Task, frm: str, to: str, comment: str | None) -> None:
    author = task.author if task.author_id else None
    assignee = task.assignee if task.assignee_id else None
    kw = {"task": task, "actor": actor}
    who = actor.full_name
    if to == "in_progress" and frm == "review":
        notify(db, assignee, f"Задачу «{task.title}» вернули в работу: {comment.strip()}", link(task),
               buttons=buttons(task, WORK_BUTTONS), **kw)
    elif to == "in_progress":
        notify(db, author, f"{who} взял(а) в работу: «{task.title}»", link(task), **kw)
    elif to == "review":
        notify(db, author, f"Проверьте задачу «{task.title}» — {who} сдал(а) её", link(task),
               buttons=buttons(task, ACCEPT_BUTTONS), **kw)
    elif to == "done":
        notify(db, assignee, f"Задача «{task.title}» принята ✓", link(task), **kw)
    elif to == "todo":
        notify(db, assignee, f"Задачу «{task.title}» вернули в «К выполнению»"
               + (f": {comment.strip()}" if comment and comment.strip() else ""), link(task), **kw)


# ------------------------------------------------------------------ изменение задачи (spec 003)
HISTORY_NAMES = {"status": "колонка", "title": "название", "description": "описание", "due_date": "срок",
                 "priority": "приоритет", "event": "проект", "assignee": "исполнитель"}
TRACKED = {"title": "название", "description": "описание", "due_date": "срок", "priority": "приоритет",
           "event_id": "проект", "assignee_id": "исполнитель"}


def _fmt(field: str, value) -> str | None:
    if value is None or value == "":
        return None
    if field == "due_date":
        return value.strftime("%d.%m.%Y")
    if field == "priority":
        return m.TASK_PRIORITIES.get(value, value)
    return str(value)[:50]


def can_edit(user: m.User, task: m.Task) -> bool:
    """Править задачу (название, срок, исполнителя…) может автор или руководитель."""
    return task.author_id == user.id or user.has_role("head")


def update(db: Session, user: m.User, task: m.Task, changes: dict, source: str = "cabinet") -> list[str]:
    """Применить изменения задачи, записать историю и уведомить. Возвращает названия изменённых полей."""
    changed = []
    old_assignee = task.assignee
    for field, new in changes.items():
        if field not in TRACKED:
            continue
        old = getattr(task, field)
        if (old or None) == (new or None):
            continue
        setattr(task, field, new)
        changed.append(field)
        if field == "assignee_id":                     # в истории — имена, а не номера
            o, n = (db.get(m.User, x) if x else None for x in (old, new))
            log(db, task, user, "assignee", o.full_name if o else None, n.full_name if n else None, source=source)
        elif field == "event_id":
            o, n = (db.get(m.Event, x) if x else None for x in (old, new))
            log(db, task, user, "event", o.title[:50] if o else None, n.title[:50] if n else None, source=source)
        elif field == "description":
            log(db, task, user, "description", None, None, source=source)
        else:
            log(db, task, user, field, _fmt(field, old), _fmt(field, new), source=source)
    if not changed:
        return []
    task.updated_at = datetime.now()
    db.flush()
    db.refresh(task)
    audit(db, user.id, "task_update", f"task:{task.id}", ", ".join(changed))
    parts = []                                   # «срок → 28.11.2026; приоритет → высокий; описание»
    for f in changed:
        if f == "due_date":
            parts.append(f"срок → {_fmt('due_date', task.due_date) or 'без срока'}")
        elif f == "priority":
            parts.append(f"приоритет → {m.TASK_PRIORITIES[task.priority].lower()}")
        elif f == "event_id":
            parts.append(f"проект → {task.event.title if task.event else 'без проекта'}")
        elif f == "title":
            parts.append("новое название")
        elif f == "description":
            parts.append("описание")
    what = "; ".join(parts)
    names = parts
    kw = {"task": task, "actor": user}
    if "assignee_id" in changed:
        notify(db, task.assignee, f"{user.full_name} передал(а) вам задачу «{task.title}»"
               + (f", срок {_fmt('due_date', task.due_date)}" if task.due_date else ""), link(task),
               buttons=buttons(task, WORK_BUTTONS), **kw)
        notify(db, old_assignee, f"Задачу «{task.title}» передали: {task.assignee.full_name if task.assignee else '—'}",
               link(task), **kw)
    elif names:
        notify(db, task.assignee, f"{user.full_name} изменил(а) задачу «{task.title}»: {what}", link(task), **kw)
    if names and task.author and task.author_id != task.assignee_id:
        notify(db, task.author, f"{user.full_name} изменил(а) задачу «{task.title}»: {what}", link(task), **kw)
    return changed


def new_position(db: Session, status: str = "todo") -> int:
    """Позиция для новой задачи — в конец колонки."""
    return (db.scalar(select(func.max(m.Task.position)).where(m.Task.status == status)) or 0) + STEP
