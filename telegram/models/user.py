import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .admin import Admin

USERNAME_REGEXP = re.compile(r"^(?=\w{3,32}\b)[a-zA-Z0-9-_@.]+(?:_[a-zA-Z0-9-_@.]+)*$")


class ReminderType(str, Enum):
    expiration_date = "expiration_date"
    data_usage = "data_usage"


class UserStatus(str, Enum):
    active = "active"
    disabled = "disabled"
    limited = "limited"
    expired = "expired"
    on_hold = "on_hold"


class UserStatusModify(str, Enum):
    active = "active"
    disabled = "disabled"
    on_hold = "on_hold"


class UserStatusCreate(str, Enum):
    active = "active"
    on_hold = "on_hold"


class UserDataLimitResetStrategy(str, Enum):
    no_reset = "no_reset"
    day = "day"
    week = "week"
    month = "month"
    year = "year"


class NextPlanModel(BaseModel):
    data_limit: Optional[int] = None
    expire: Optional[int] = None
    add_remaining_traffic: bool = False
    fire_on_either: bool = True
    model_config = ConfigDict(from_attributes=True)


class User(BaseModel):
    """
    Base user fields shared between create/modify/response models.

    This version is adapted for the **remote Marzban HTTP API** and does not
    depend on local Xray config or server internals.
    """

    proxies: Dict[str, Dict[str, Any]] = {}
    expire: Optional[int] = Field(None, nullable=True)
    data_limit: Optional[int] = Field(
        ge=0, default=None, description="data_limit can be 0 or greater"
    )
    data_limit_reset_strategy: UserDataLimitResetStrategy = (
        UserDataLimitResetStrategy.no_reset
    )
    inbounds: Dict[str, List[str]] = {}
    note: Optional[str] = Field(None, nullable=True)
    sub_updated_at: Optional[datetime] = Field(None, nullable=True)
    sub_last_user_agent: Optional[str] = Field(None, nullable=True)
    online_at: Optional[datetime] = Field(None, nullable=True)
    on_hold_expire_duration: Optional[int] = Field(None, nullable=True)
    on_hold_timeout: Optional[Union[datetime, None]] = Field(None, nullable=True)

    auto_delete_in_days: Optional[int] = Field(None, nullable=True)

    next_plan: Optional[NextPlanModel] = Field(None, nullable=True)

    @field_validator("data_limit", mode="before")
    @classmethod
    def cast_data_limit(cls, v):
        if v is None:
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, int):
            return v
        raise ValueError("data_limit must be an integer or a float")

    @field_validator("username", check_fields=False)
    @classmethod
    def validate_username(cls, v: str):
        if not USERNAME_REGEXP.match(v):
            raise ValueError(
                "Username must be 3–32 chars and contain a-z, 0-9 and underscores."
            )
        return v

    @field_validator("note", check_fields=False)
    @classmethod
    def validate_note(cls, v: Optional[str]):
        if v and len(v) > 500:
            raise ValueError("User note can be at most 500 characters")
        return v

    @field_validator("on_hold_expire_duration", "on_hold_timeout", mode="before")
    @classmethod
    def validate_timeout(cls, v, values):
        if v in (0, None):
            return None
        return v


class UserCreate(User):
    """Request body for creating user via Marzban API."""

    username: str
    status: Optional[UserStatusCreate] = None
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "username": "user1234",
            "proxies": {
                "vmess": {"id": "35e4e39c-7d5c-4f4b-8b71-558e4f37ff53"},
                "vless": {},
            },
            "inbounds": {
                "vmess": ["VMess TCP", "VMess Websocket"],
                "vless": ["VLESS TCP REALITY", "VLESS GRPC REALITY"],
            },
            "next_plan": {
                "data_limit": 0,
                "expire": 0,
                "add_remaining_traffic": False,
                "fire_on_either": True,
            },
            "expire": 0,
            "data_limit": 0,
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
            "note": "",
            "on_hold_timeout": "2023-11-03T20:30:00",
            "on_hold_expire_duration": 0,
        }
    })

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, status, values):
        on_hold_expire = values.data.get("on_hold_expire_duration")
        expire = values.data.get("expire")
        if status == UserStatusCreate.on_hold:
            if on_hold_expire in (0, None):
                raise ValueError(
                    "User cannot be on hold without a valid on_hold_expire_duration."
                )
            if expire:
                raise ValueError("User cannot be on hold with specified expire.")
        return status


class UserModify(User):
    """Request body for modifying user via Marzban API."""

    status: Optional[UserStatusModify] = None
    data_limit_reset_strategy: Optional[UserDataLimitResetStrategy] = None
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "proxies": {
                "vmess": {"id": "35e4e39c-7d5c-4f4b-8b71-558e4f37ff53"},
                "vless": {},
            },
            "inbounds": {
                "vmess": ["VMess TCP", "VMess Websocket"],
                "vless": ["VLESS TCP REALITY", "VLESS GRPC REALITY"],
            },
            "next_plan": {
                "data_limit": 0,
                "expire": 0,
                "add_remaining_traffic": False,
                "fire_on_either": True,
            },
            "expire": 0,
            "data_limit": 0,
            "data_limit_reset_strategy": "no_reset",
            "status": "active",
            "note": "",
            "on_hold_timeout": "2023-11-03T20:30:00",
            "on_hold_expire_duration": 0,
        }
    })

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, status, values):
        on_hold_expire = values.data.get("on_hold_expire_duration")
        expire = values.data.get("expire")
        if status == UserStatusCreate.on_hold:
            if on_hold_expire in (0, None):
                raise ValueError(
                    "User cannot be on hold without a valid on_hold_expire_duration."
                )
            if expire:
                raise ValueError("User cannot be on hold with specified expire.")
        return status


class UserResponse(User):
    """Full user representation returned by Marzban API."""

    username: str
    status: UserStatus
    used_traffic: int
    lifetime_used_traffic: int = 0
    created_at: datetime
    links: List[str] = []
    subscription_url: str = ""
    excluded_inbounds: Dict[str, List[str]] = {}

    admin: Optional[Admin] = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("used_traffic", "lifetime_used_traffic", mode="before")
    @classmethod
    def cast_to_int(cls, v):
        if v is None:
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, int):
            return v
        raise ValueError("must be an integer or a float")


class SubscriptionUserResponse(UserResponse):
    """
    Lightweight user representation used in subscription endpoints.
    Fields excluded here correspond to how Marzban exposes subscription data.
    """

    admin: Admin | None = Field(default=None, exclude=True)
    excluded_inbounds: Dict[str, List[str]] | None = Field(None, exclude=True)
    note: str | None = Field(None, exclude=True)
    inbounds: Dict[str, List[str]] | None = Field(None, exclude=True)
    auto_delete_in_days: int | None = Field(None, exclude=True)
    model_config = ConfigDict(from_attributes=True)


class UsersResponse(BaseModel):
    users: List[UserResponse]
    total: int


class UserUsageResponse(BaseModel):
    node_id: Union[int, None] = None
    node_name: str
    used_traffic: int

    @field_validator("used_traffic", mode="before")
    @classmethod
    def cast_to_int(cls, v):
        if v is None:
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, int):
            return v
        raise ValueError("must be an integer or a float")


class UserUsagesResponse(BaseModel):
    username: str
    usages: List[UserUsageResponse]


class UsersUsagesResponse(BaseModel):
    usages: List[UserUsageResponse]
