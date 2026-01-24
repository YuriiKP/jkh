from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class Token(BaseModel):
    """Response model for /api/admin/token."""

    access_token: str
    token_type: str = "bearer"


class Admin(BaseModel):
    """
    Admin representation as used by Marzban HTTP API.

    This is a **pure data model** (no FastAPI / DB / JWT dependencies) so it
    can be safely used on the Telegram bot side.
    """

    username: str
    is_sudo: bool
    telegram_id: Optional[int] = None
    discord_webhook: Optional[str] = None
    users_usage: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("users_usage", mode="before")
    @classmethod
    def cast_to_int(cls, v):
        if v is None:
            return v
        if isinstance(v, float):
            return int(v)
        if isinstance(v, int):
            return v
        raise ValueError("users_usage must be an int or float")


class AdminCreate(Admin):
    """
    Request body for creating an admin via Marzban API.

    The password is sent as plain text to the Marzban backend – hashing is
    handled server‑side.
    """

    password: str

    @field_validator("discord_webhook")
    @classmethod
    def validate_discord_webhook(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.startswith("https://discord.com"):
            raise ValueError("Discord webhook must start with 'https://discord.com'")
        return value


class AdminModify(BaseModel):
    """Request body for modifying an admin via Marzban API."""

    password: Optional[str] = None
    is_sudo: Optional[bool] = None
    telegram_id: Optional[int] = None
    discord_webhook: Optional[str] = None

    @field_validator("discord_webhook")
    @classmethod
    def validate_discord_webhook(cls, value: Optional[str]) -> Optional[str]:
        if value and not value.startswith("https://discord.com"):
            raise ValueError("Discord webhook must start with 'https://discord.com'")
        return value
