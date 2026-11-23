"""Модель данных ИС Energy Lab (физическая модель — раздел 2.4 ВКР + таблицы ЧТЗ)."""
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# ---------------------------------------------------------------- статусы мероприятия
# Код статуса -> (название, название этапа запуска для интерфейса Lab)
EVENT_STATUSES = {
    "draft": ("Черновик", "Сборка"),
    "review": ("На экспертизе", "Предстартовые проверки"),
    "rework": ("Доработка", "Возврат на доработку"),
    "evaluated": ("Оценён", "Проверки пройдены"),
    "approved": ("Утверждён", "Готов к старту"),
    "rejected": ("Отклонён", "Старт отменён"),
    "on_sale": ("Продажа билетов", "Обратный отсчёт"),
    "held": ("Проведён", "Полёт завершён"),
    "analyzed": ("Проанализирован", "Разбор полёта"),
}
# Разрешённые переходы (диаграмма состояний, рис. 8 ВКР): статус -> {новый статус: кто может}
TRANSITIONS = {
    "draft": {"review": "author"},
    "rework": {"review": "author"},
    "review": {"rework": "head", "evaluated": "head"},
    "evaluated": {"approved": "head", "rework": "head", "rejected": "head"},
    "approved": {"on_sale": "head"},
    "on_sale": {"held": "head"},
    "held": {"analyzed": "head"},
}
TASK_STATUSES = {"todo": "К выполнению", "in_progress": "В работе", "review": "На проверке", "done": "Выполнено"}
TASK_PRIORITIES = {"normal": "Обычный", "high": "Высокий"}
ROLE_NAMES = {
    "member": "Участник Lab",
    "expert": "Эксперт",
    "head": "Руководитель",
    "listener": "Слушатель",
    "master": "Мастер школы",
    "support": "Поддержка",
}


def _now() -> datetime:
    return datetime.now()


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    telegram_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    vk_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    notify_channel: Mapped[str] = mapped_column(String(10), default="telegram")  # telegram / vk / email
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", lazy="selectin")
    expert: Mapped["Expert | None"] = relationship(back_populates="user", uselist=False, lazy="selectin")

    def has_role(self, *codes: str) -> bool:
        return any(r.code in codes for r in self.roles)

    @property
    def role_codes(self) -> list[str]:
        return [r.code for r in self.roles]


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    weight: Mapped[float] = mapped_column(Float, default=0.2)  # вес отдела α
    criteria: Mapped[list["Criterion"]] = relationship(back_populates="department", order_by="Criterion.code",
                                                       lazy="selectin")


class Expert(Base):
    __tablename__ = "experts"
    __table_args__ = (CheckConstraint("competence >= 0.5 AND competence <= 1.0", name="ck_competence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    competence: Mapped[float] = mapped_column(Float, default=0.7)
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    organization: Mapped[str | None] = mapped_column(String(150))
    user: Mapped[User] = relationship(back_populates="expert", lazy="selectin")
    department: Mapped[Department] = relationship(lazy="selectin")


class CompetenceHistory(Base):
    __tablename__ = "competence_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    expert_id: Mapped[int] = mapped_column(ForeignKey("experts.id", ondelete="CASCADE"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    old_value: Mapped[float] = mapped_column(Float)
    new_value: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EventFormat(Base):
    """Классификатор форматов: иерархический код (первая цифра — группа), раздел 2.3 ВКР."""
    __tablename__ = "event_formats"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    group_name: Mapped[str] = mapped_column(String(100))

    @property
    def group_code(self) -> str:
        return self.code[0]


class Venue(Base):
    __tablename__ = "venues"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    address: Mapped[str | None] = mapped_column(String(255))
    capacity: Mapped[int | None] = mapped_column(Integer)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    format_id: Mapped[int] = mapped_column(ForeignKey("event_formats.id"))
    venue_id: Mapped[int | None] = mapped_column(ForeignKey("venues.id"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    planned_date: Mapped[date | None] = mapped_column(Date)
    start_time: Mapped[str | None] = mapped_column(String(5))
    slot_min: Mapped[int | None] = mapped_column(SmallInteger)   # сколько минут есть на площадке (план тайминга)
    album_url: Mapped[str | None] = mapped_column(String(500))    # полный фотоальбом на Яндекс/Google Диске
    age_rating: Mapped[str] = mapped_column(String(4), default="16+")
    ticket_price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    planned_budget: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    capacity: Mapped[int | None] = mapped_column(Integer)
    target_audience: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    timepad_event_id: Mapped[str | None] = mapped_column(String(40))
    timepad_url: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    format: Mapped[EventFormat] = relationship(lazy="selectin")
    venue: Mapped[Venue | None] = relationship(lazy="selectin")
    author: Mapped[User | None] = relationship(lazy="selectin")
    stations: Mapped[list["Station"]] = relationship(back_populates="event", order_by="Station.order_no",
                                                     cascade="all, delete-orphan", lazy="selectin")
    result: Mapped["EventResult | None"] = relationship(back_populates="event", uselist=False,
                                                        cascade="all, delete-orphan", lazy="selectin")
    photos: Mapped[list["EventPhoto"]] = relationship(
        order_by=lambda: (EventPhoto.is_cover.desc(), EventPhoto.order_no, EventPhoto.id),
        cascade="all, delete-orphan", lazy="selectin")

    @property
    def documents(self) -> list["Attachment"]:
        from sqlalchemy import select
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        if not sess:
            return []
        return list(sess.scalars(select(Attachment).where(Attachment.event_id == self.id, Attachment.task_id.is_(None))
                                 .order_by(Attachment.category, Attachment.id.desc())))

    @property
    def scenario(self):
        """(строки сценария, общая длительность в минутах) — app/scenario.py."""
        from app import scenario
        return scenario.timeline(list(self.stations))

    @property
    def scenario_min(self) -> int:
        return self.scenario[1]

    @property
    def rated_stations(self) -> list["Station"]:
        """Блоки и станции, которые оценивают эксперты и гости (методы А–В, анкета, «эксперты vs гости»)."""
        from app import scenario
        return scenario.rated(list(self.stations))

    @property
    def cover(self) -> "EventPhoto | None":
        return self.photos[0] if self.photos else None

    @property
    def status_name(self) -> str:
        return EVENT_STATUSES.get(self.status, (self.status, self.status))[0]

    @property
    def stage_name(self) -> str:
        return EVENT_STATUSES.get(self.status, (self.status, self.status))[1]


class Station(Base):
    """Блок сценария (spec 002). Историческое имя таблицы — «stations»: раньше сценарий состоял только из станций.
    Виды: block — блок программы, service — служебный, carousel — карусель станций, station — станция в карусели."""
    __tablename__ = "stations"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    order_no: Mapped[int] = mapped_column(SmallInteger, default=1)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(SmallInteger, default=15)
    cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(10), default="block")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"))  # карусель
    rated: Mapped[bool] = mapped_column(Boolean, default=True)          # оценивают эксперты и гости
    fact_min: Mapped[int | None] = mapped_column(SmallInteger)          # фактическая длительность
    groups: Mapped[int | None] = mapped_column(SmallInteger)            # карусель: сколько групп
    transition_min: Mapped[int | None] = mapped_column(SmallInteger)    # карусель: переход между станциями
    event: Mapped[Event] = relationship(back_populates="stations")
    responsible: Mapped[User | None] = relationship(lazy="selectin")


class Criterion(Base):
    __tablename__ = "criteria"
    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    code: Mapped[str] = mapped_column(String(20), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    weight: Mapped[float] = mapped_column(Float, default=0.33)
    department: Mapped[Department] = relationship(back_populates="criteria")


class EventExpert(Base):
    __tablename__ = "event_experts"
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), primary_key=True)
    expert_id: Mapped[int] = mapped_column(ForeignKey("experts.id", ondelete="CASCADE"), primary_key=True)


class ExpertiseRound(Base):
    __tablename__ = "expertise_rounds"
    __table_args__ = (UniqueConstraint("event_id", "round_no"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    round_no: Mapped[int] = mapped_column(SmallInteger, default=1)
    deadline: Mapped[date | None] = mapped_column(Date)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    kendall_w: Mapped[float | None] = mapped_column(Float)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("round_id", "expert_id", "criterion_id", "station_id", name="uq_evaluation"),
        CheckConstraint("score BETWEEN 1 AND 10", name="ck_score"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("expertise_rounds.id", ondelete="CASCADE"))
    expert_id: Mapped[int] = mapped_column(ForeignKey("experts.id", ondelete="RESTRICT"))
    criterion_id: Mapped[int] = mapped_column(ForeignKey("criteria.id"))
    station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"))
    score: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        UniqueConstraint("round_id", "station_id", "expert_id", name="uq_risk"),
        CheckConstraint("probability BETWEEN 1 AND 10 AND impact BETWEEN 1 AND 10", name="ck_risk"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("expertise_rounds.id", ondelete="CASCADE"))
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"))
    expert_id: Mapped[int] = mapped_column(ForeignKey("experts.id", ondelete="RESTRICT"))
    probability: Mapped[int] = mapped_column(SmallInteger)
    impact: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)


class Forecast(Base):
    __tablename__ = "forecasts"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expert_score: Mapped[float | None] = mapped_column(Float)
    kendall_w: Mapped[float | None] = mapped_column(Float)
    variation: Mapped[float | None] = mapped_column(Float)          # коэффициент вариации оценок экспертов, %
    attendance: Mapped[int | None] = mapped_column(Integer)
    attendance_low: Mapped[int | None] = mapped_column(Integer)
    attendance_high: Mapped[int | None] = mapped_column(Integer)
    tickets_sold: Mapped[int | None] = mapped_column(Integer)
    revenue: Mapped[float | None] = mapped_column(Float)
    budget: Mapped[float | None] = mapped_column(Float)
    avg_rating: Mapped[float | None] = mapped_column(Float)
    failure_risk: Mapped[float | None] = mapped_column(Float)
    recommendation: Mapped[str | None] = mapped_column(String(40))
    reasons: Mapped[list | None] = mapped_column(JSON)
    analogs: Mapped[list | None] = mapped_column(JSON)
    params: Mapped[dict | None] = mapped_column(JSON)


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    decision: Mapped[str] = mapped_column(String(20))  # approved / rework / rejected
    comment: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class EventResult(Base):
    __tablename__ = "event_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True)
    guests_count: Mapped[int] = mapped_column(Integer, default=0)
    tickets_sold: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    actual_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    avg_rating: Mapped[float | None] = mapped_column(Float)
    lessons: Mapped[str | None] = mapped_column(Text)                # выводы для следующих проектов
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)   # когда завершена итоговая оценка
    event: Mapped[Event] = relationship(back_populates="result")


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    external_order_id: Mapped[str] = mapped_column(String(60), unique=True)
    buyer_name: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(120))
    price: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    status: Mapped[str] = mapped_column(String(20), default="paid")  # paid / refunded / used
    purchased_at: Mapped[datetime | None] = mapped_column(DateTime)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 10", name="ck_fb_rating"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id", ondelete="SET NULL"), unique=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    nps: Mapped[int | None] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    client_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FeedbackStation(Base):
    __tablename__ = "feedback_stations"
    feedback_id: Mapped[int] = mapped_column(ForeignKey("feedback.id", ondelete="CASCADE"), primary_key=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True)
    rating: Mapped[int] = mapped_column(SmallInteger)


class Task(Base):
    """Задачи подготовки мероприятия — видны в кабинете и в боте (/tasks)."""
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="todo")
    due_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    position: Mapped[int] = mapped_column(Integer, default=0)            # порядок в колонке доски, шаг 1000
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # normal / high
    done_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    event: Mapped[Event | None] = relationship(lazy="selectin")
    department: Mapped[Department | None] = relationship(lazy="selectin")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="selectin")

    author: Mapped[User | None] = relationship(foreign_keys=[author_id], lazy="selectin")
    attachments: Mapped[list["Attachment"]] = relationship(lazy="selectin", order_by="Attachment.id",
                                                          cascade="all, delete-orphan", passive_deletes=True)

    @property
    def status_name(self) -> str:
        return TASK_STATUSES.get(self.status, self.status)

    @property
    def days_overdue(self) -> int:
        """Сколько дней просрочена (0 — не просрочена или выполнена)."""
        if not self.due_date or self.status == "done":
            return 0
        return max(0, (date.today() - self.due_date).days)


class TaskEvent(Base):
    """История задачи: смена статуса, срока, исполнителя (ЧТЗ М06-19)."""
    __tablename__ = "task_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    field: Mapped[str] = mapped_column(String(20))
    old_value: Mapped[str | None] = mapped_column(String(50))
    new_value: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="cabinet")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    user: Mapped[User | None] = relationship(lazy="selectin")


class CalendarFeed(Base):
    """Личная ссылка-подписка на календарь задач для Google и Яндекс Календаря (ЧТЗ М06-21)."""
    __tablename__ = "calendar_feeds"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Discussion(Base):
    """Вопрос на обсуждение внутри отдела (из кабинета или из бота)."""
    __tablename__ = "discussions"
    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(10), default="open")  # open / closed
    source: Mapped[str] = mapped_column(String(10), default="web")   # web / telegram / vk
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    department: Mapped[Department] = relationship(lazy="selectin")
    author: Mapped[User | None] = relationship(lazy="selectin")
    event: Mapped[Event | None] = relationship(lazy="selectin")
    messages: Mapped[list["Message"]] = relationship(order_by="Message.created_at", cascade="all, delete-orphan",
                                                     lazy="selectin")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    discussion_id: Mapped[int] = mapped_column(ForeignKey("discussions.id", ondelete="CASCADE"))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    author: Mapped[User | None] = relationship(lazy="selectin")


class Question(Base):
    """Вопросы для публичной доски (перенос прототипа ENERGY_board)."""
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="Другое")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/answered/rejected
    author_name: Mapped[str | None] = mapped_column(String(150))
    channel: Mapped[str] = mapped_column(String(10), default="web")
    channel_user_id: Mapped[str | None] = mapped_column(String(40))
    answer: Mapped[str | None] = mapped_column(Text)
    moderated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FaqItem(Base):
    """Вопрос и ответ для раздела «Вопросы и ответы» на сайте и команды /faq в боте (spec 005)."""
    __tablename__ = "faq"
    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(40), default="Общие вопросы")
    order_no: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)
    question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id", ondelete="SET NULL"))  # из доски
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


SUPPORT_STATUSES = {"open": "Ждёт ответа", "answered": "Отвечено", "closed": "Закрыт"}


class SupportChat(Base):
    """Переписка поддержки с внешним человеком (покупатель, гость), который пишет боту без привязки аккаунта."""
    __tablename__ = "support_chats"
    __table_args__ = (Index("ix_support_chats_peer", "channel", "chat_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(10))                # telegram / vk
    chat_id: Mapped[str] = mapped_column(String(40))
    name: Mapped[str | None] = mapped_column(String(150))
    status: Mapped[str] = mapped_column(String(10), default="open")
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    operator: Mapped[User | None] = relationship(lazy="selectin")
    messages: Mapped[list["SupportMessage"]] = relationship(back_populates="chat", cascade="all, delete-orphan",
                                                            order_by="SupportMessage.id", lazy="selectin")

    @property
    def status_name(self) -> str:
        return SUPPORT_STATUSES.get(self.status, self.status)

    @property
    def last(self) -> "SupportMessage | None":
        return self.messages[-1] if self.messages else None


class SupportMessage(Base):
    __tablename__ = "support_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("support_chats.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(3))                 # in — от человека, out — от оператора
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(10), default="web")    # откуда ответил оператор: web/telegram/vk
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    chat: Mapped[SupportChat] = relationship(back_populates="messages")
    author: Mapped[User | None] = relationship(lazy="selectin")


class LinkCode(Base):
    __tablename__ = "link_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(12), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Notification(Base):
    """Очередь исходящих уведомлений: n8n забирает её по API и отправляет в Telegram/VK."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(10))
    chat_id: Mapped[str] = mapped_column(String(40))
    text: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255))
    reply_markup: Mapped[str | None] = mapped_column(Text)        # кнопки под сообщением Telegram (JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


INBOX_KINDS = {"task": "Задачи", "project": "Проекты", "discussion": "Обсуждения", "request": "Заявки",
               "support": "Поддержка", "system": "Система"}


class InboxItem(Base):
    """Уведомление на сайте (колокольчик в кабинете). Создаётся всегда, независимо от мессенджера."""
    __tablename__ = "inbox"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="system")
    text: Mapped[str] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255))           # путь на сайте, например /cabinet/tasks/5
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id], lazy="selectin")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60))
    object: Mapped[str | None] = mapped_column(String(60))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class PartyRequest(Base):
    """Заявка покупателя на создание тусовки «под ключ» (день рождения, выпускной, корпоратив)."""
    __tablename__ = "party_requests"
    __table_args__ = (CheckConstraint("guests BETWEEN 1 AND 1000", name="ck_pr_guests"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    contact: Mapped[str] = mapped_column(String(150), default="")   # телефон или e-mail
    telegram: Mapped[str | None] = mapped_column(String(32))        # ник в Telegram без «@» (ссылка https://t.me/ник)
    occasion: Mapped[str] = mapped_column(String(60))               # повод
    format_id: Mapped[int | None] = mapped_column(ForeignKey("event_formats.id", ondelete="SET NULL"))
    wish_date: Mapped[date | None] = mapped_column(Date)
    guests: Mapped[int] = mapped_column(Integer, default=20)
    age_group: Mapped[str | None] = mapped_column(String(20))
    budget: Mapped[float | None] = mapped_column(Numeric(12, 2))
    estimate: Mapped[float | None] = mapped_column(Numeric(12, 2))  # оценка калькулятора на момент заявки
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)  # new / in_work / done / rejected
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    format: Mapped[EventFormat | None] = relationship(lazy="selectin")
    manager: Mapped[User | None] = relationship(lazy="selectin")

    @property
    def telegram_url(self) -> str | None:
        return f"https://t.me/{self.telegram}" if self.telegram else None


REQUEST_STATUSES = {"new": "Новая", "in_work": "В работе", "done": "Договорились", "rejected": "Отказ"}


DOC_CATEGORIES = {"estimate": "Смета", "contract": "Договор", "scenario": "Сценарий", "rider": "Райдер",
                  "presentation": "Презентация", "other": "Прочее"}
LINK_PROVIDERS = {"yandex": "Яндекс Диск", "gdrive": "Google Диск", "gdocs": "Google Документ",
                  "gsheets": "Google Таблица", "gslides": "Google Презентация", "gforms": "Google Форма"}


class Attachment(Base):
    """Документ проекта или вложение задачи: загруженный файл (FILES_DIR) или ссылка на Яндекс/Google Диск."""
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(5))                    # file / link
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(15), default="other")
    file: Mapped[str | None] = mapped_column(String(255))           # путь относительно FILES_DIR
    original_name: Mapped[str | None] = mapped_column(String(200))
    size: Mapped[int | None] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(500))
    provider: Mapped[str | None] = mapped_column(String(10))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    uploader: Mapped[User | None] = relationship(lazy="selectin")

    @property
    def ext(self) -> str:
        return (self.original_name or "").rsplit(".", 1)[-1].upper() if self.original_name and "." in \
            self.original_name else ""

    @property
    def provider_name(self) -> str:
        return LINK_PROVIDERS.get(self.provider or "", "Ссылка")


class EventPhoto(Base):
    """Фотоальбом проведённого мероприятия."""
    __tablename__ = "event_photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    file: Mapped[str] = mapped_column(String(255))                 # путь относительно MEDIA_DIR
    caption: Mapped[str | None] = mapped_column(String(200))
    order_no: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TeamMember(Base):
    """Карточка человека из команды для слайдера «Кто создаёт тусовки» на главной."""
    __tablename__ = "team_members"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(120))                 # «Руководитель Energy Lab», «Сценарист»
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    bio: Mapped[str | None] = mapped_column(String(400))
    photo: Mapped[str | None] = mapped_column(String(255))         # путь относительно MEDIA_DIR
    order_no: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    consent: Mapped[bool] = mapped_column(Boolean, default=False)  # согласие на публикацию фото и имени
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    department: Mapped[Department | None] = relationship(lazy="selectin")


class SiteSetting(Base):
    """Настройки главной, которые руководитель меняет в кабинете (тексты, калькулятор стоимости)."""
    __tablename__ = "site_settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict | list | str | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
