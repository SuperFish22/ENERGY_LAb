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
TASK_STATUSES = {"todo": "К выполнению", "in_progress": "В работе", "done": "Готово"}
ROLE_NAMES = {
    "member": "Участник Lab",
    "expert": "Эксперт",
    "head": "Руководитель",
    "listener": "Слушатель",
    "master": "Мастер школы",
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
    def cover(self) -> "EventPhoto | None":
        return self.photos[0] if self.photos else None

    @property
    def status_name(self) -> str:
        return EVENT_STATUSES.get(self.status, (self.status, self.status))[0]

    @property
    def stage_name(self) -> str:
        return EVENT_STATUSES.get(self.status, (self.status, self.status))[1]


class Station(Base):
    __tablename__ = "stations"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"))
    order_no: Mapped[int] = mapped_column(SmallInteger, default=1)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    duration_min: Mapped[int] = mapped_column(SmallInteger, default=15)
    cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
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
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_score"),
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
        CheckConstraint("probability BETWEEN 1 AND 5 AND impact BETWEEN 1 AND 5", name="ck_risk"),
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
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_fb_rating"),)
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
    event: Mapped[Event | None] = relationship(lazy="selectin")
    department: Mapped[Department | None] = relationship(lazy="selectin")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], lazy="selectin")

    @property
    def status_name(self) -> str:
        return TASK_STATUSES.get(self.status, self.status)


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
    """Вопросы для публичной доски и SOS (перенос прототипа ENERGY_board)."""
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="Другое")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/approved/answered/rejected/sos
    author_name: Mapped[str | None] = mapped_column(String(150))
    channel: Mapped[str] = mapped_column(String(10), default="web")
    channel_user_id: Mapped[str | None] = mapped_column(String(40))
    answer: Mapped[str | None] = mapped_column(Text)
    moderated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)


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
    contact: Mapped[str] = mapped_column(String(150))               # телефон, e-mail или ник в мессенджере
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


REQUEST_STATUSES = {"new": "Новая", "in_work": "В работе", "done": "Договорились", "rejected": "Отказ"}


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
