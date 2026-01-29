import random
import string

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(64), nullable=False)
    last_name = Column(String(64), nullable=True)
    reg_time = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    status_user = Column(String(64), default="user")
    language = Column(String(2), default="ru")
    trial = Column(String(5), default="true")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    payload = Column(String(255), nullable=False)
    telegram_payment_charge_id = Column(String(255), nullable=False)
    provider_payment_charge_id = Column(String(255), nullable=True)
    payment_date = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    status = Column(String(20), default="completed")


class DeepLink(Base):
    __tablename__ = "deep_links"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    deep_link = Column(String(32), unique=True, nullable=False)
    duration_days = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    activated_at = Column(DateTime, nullable=True)
    activated_by_user_id = Column(BigInteger, nullable=True)


class PasarguardNotificationEvent(Base):
    """
    События, полученные по webhook'у от панели (для дедупликации).
    """

    __tablename__ = "pasarguard_notification_events"
    __table_args__ = (
        UniqueConstraint(
            "source", "event_id", name="uq_pasarguard_event_source_event_id"
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(64), nullable=False, default="pasarguard")
    event_id = Column(String(128), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    days_left = Column(Integer, nullable=False)
    received_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))


class DB_M:
    def __init__(self, db_uri):
        if not db_uri:
            raise ValueError(
                "SQLALCHEMY_DATABASE_URL_TG не установлен в переменных окружения"
            )

        self.engine = create_async_engine(
            db_uri, echo=False, pool_pre_ping=True, pool_size=10, max_overflow=20
        )
        self.async_session = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def add_new_user(
        self, user_id, username, first_name, last_name, language="ru", trial="true"
    ):
        async with self.async_session() as session:
            # Проверяем, существует ли пользователь
            result = await session.execute(select(User).where(User.user_id == user_id))
            existing_user = result.scalar_one_or_none()

            if existing_user is None:
                # Пользователь не существует, создаем нового
                new_user = User(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    language=language,
                    trial="true",
                )
                session.add(new_user)
                await session.commit()

    async def get_user_by_id(self, user_id):
        async with self.async_session() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalar_one_or_none()

            if user is None:
                return None

            # Возвращаем в формате кортежа для совместимости: (user_id, username, first_name, last_name, reg_time, status_user, language, trial)
            return (
                user.user_id,
                user.username,
                user.first_name,
                user.last_name,
                user.reg_time,
                user.status_user,
                user.language,
                user.trial,
            )

    async def get_status_user(self, user_id):
        async with self.async_session() as session:
            result = await session.execute(
                select(User.status_user).where(User.user_id == user_id)
            )
            status_user = result.scalar_one_or_none()

            # Если пользователь не найден, возвращаем дефолтный статус 'user'
            if status_user is None:
                status_user = "user"

            # Возвращаем в формате кортежа для совместимости: (status_user,)
            return (status_user,)

    async def get_admins(self):
        async with self.async_session() as session:
            result = await session.execute(
                select(User).where(
                    (User.status_user == "main_admin") | (User.status_user == "admin")
                )
            )
            admins = result.scalars().all()

            # Возвращаем список кортежей для совместимости
            return [
                (
                    admin.user_id,
                    admin.username,
                    admin.first_name,
                    admin.last_name,
                    admin.reg_time,
                    admin.status_user,
                    admin.language,
                    admin.trial,
                )
                for admin in admins
            ]

    async def create_deep_link(self, duration_days: int) -> str:
        """
        Генерирует уникальный deep_link и сохраняет запись в БД.
        Возвращает строку deep_link (payload).
        """
        while True:
            # Генерируем случайную строку длиной 8 символов
            deep_link = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=8)
            )
            # Проверяем уникальность
            async with self.async_session() as session:
                result = await session.execute(
                    select(DeepLink).where(DeepLink.deep_link == deep_link)
                )
                existing = result.scalar_one_or_none()
                if existing is None:
                    break

        async with self.async_session() as session:
            new_deep_link = DeepLink(
                deep_link=deep_link, duration_days=duration_days, is_active=True
            )
            session.add(new_deep_link)
            await session.commit()

        return deep_link

    async def get_deep_link(self, deep_link: str):
        """
        Возвращает диплинк подписки.
        Если диплинк не найден или не активен, возвращает None.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(DeepLink).where(DeepLink.deep_link == deep_link)
            )
            record = result.scalar_one_or_none()
            if record is None or not record.is_active:
                return None
            return record

    async def activate_deep_link(self, deep_link: str, user_id: int) -> bool:
        """
        Активирует диплинк, помечая его использованным и записывая user_id.
        Возвращает True в случае успеха, False если диплинк не найден или уже использован.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(DeepLink).where(DeepLink.deep_link == deep_link)
            )
            record = result.scalar_one_or_none()
            if record is None or not record.is_active:
                return False

            # Обновляем запись
            stmt = (
                update(DeepLink)
                .where(DeepLink.id == record.id)
                .values(
                    is_active=False,
                    activated_at=func.now(),
                    activated_by_user_id=user_id,
                )
            )
            await session.execute(stmt)
            await session.commit()
            return True

    async def list_deep_links(self):
        """
        Возвращает список всех диплинков.
        """
        async with self.async_session() as session:
            result = await session.execute(
                select(DeepLink).order_by(DeepLink.created_at.desc())
            )
            records = result.scalars().all()
            return records

    async def update_user(
        self,
        user_id,
        username=None,
        first_name=None,
        last_name=None,
        status_user=None,
        language=None,
        trial=None,
    ) -> None:
        old_user = await self.get_user_by_id(user_id)

        if old_user is None:
            return

        if username is None:
            username = old_user[1]

        if first_name is None:
            first_name = old_user[2]

        if last_name is None:
            last_name = old_user[3]

        if status_user is None:
            status_user = old_user[5]

        if language is None:
            language = old_user[6]

        if trial is None:
            trial = old_user[7]

        async with self.async_session() as session:
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    status_user=status_user,
                    language=language,
                    trial=trial,
                )
            )
            await session.execute(stmt)
            await session.commit()

    async def count_users(self) -> int:
        async with self.async_session() as session:
            result = await session.execute(select(func.count(User.user_id)))
            count = result.scalar()

            return count

    async def get_users_id(self) -> list:
        async with self.async_session() as session:
            result = await session.execute(select(User.user_id))
            users_id = result.scalars().all()

            # Возвращаем список кортежей для совместимости: [(user_id,), ...]
            return [(user_id,) for user_id in users_id]

    async def add_payment(
        self,
        user_id,
        amount,
        currency,
        payload,
        telegram_payment_charge_id,
        provider_payment_charge_id=None,
        status="completed",
    ):
        async with self.async_session() as session:
            new_payment = Payment(
                user_id=user_id,
                amount=amount,
                currency=currency,
                payload=payload,
                telegram_payment_charge_id=telegram_payment_charge_id,
                provider_payment_charge_id=provider_payment_charge_id,
                status=status,
            )
            session.add(new_payment)
            await session.commit()

    async def get_payments_by_user(self, user_id):
        async with self.async_session() as session:
            result = await session.execute(
                select(Payment)
                .where(Payment.user_id == user_id)
                .order_by(Payment.payment_date.desc())
            )
            payments = result.scalars().all()

            # Возвращаем список словарей
            return [
                {
                    "id": p.id,
                    "user_id": p.user_id,
                    "amount": p.amount,
                    "currency": p.currency,
                    "payload": p.payload,
                    "telegram_payment_charge_id": p.telegram_payment_charge_id,
                    "provider_payment_charge_id": p.provider_payment_charge_id,
                    "payment_date": p.payment_date,
                    "status": p.status,
                }
                for p in payments
            ]

    async def register_pasarguard_notification_event(
        self,
        *,
        event_id: str,
        user_id: int,
        days_left: int,
        source: str = "pasarguard",
    ) -> bool:
        """
        Регистрирует событие уведомления.
        Возвращает True если событие новое (будем слать сообщение),
        False если уже было (дубль — игнорируем).
        """
        async with self.async_session() as session:
            exists = await session.execute(
                select(PasarguardNotificationEvent.id).where(
                    (PasarguardNotificationEvent.source == source)
                    & (PasarguardNotificationEvent.event_id == event_id)
                )
            )
            if exists.scalar_one_or_none() is not None:
                return False

            session.add(
                PasarguardNotificationEvent(
                    source=source,
                    event_id=event_id,
                    user_id=user_id,
                    days_left=int(days_left),
                )
            )
            await session.commit()
            return True
