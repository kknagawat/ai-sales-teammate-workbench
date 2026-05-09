from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import UserRole

SignupMode = Literal["CREATE_ORG_ADMIN", "JOIN_ORG_REVIEWER"]
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
COMMON_WEAK_PASSWORDS = {
    "adminpassword1",
    "company123",
    "letmein123",
    "password123",
    "password123!",
    "qwerty1234",
    "qwerty1234!",
    "sales12345",
    "welcome123",
}


def _validate_password_strength(value: str) -> str:
    if len(value) < 10:
        raise ValueError("Password must be at least 10 characters.")
    if not any(character.islower() for character in value):
        raise ValueError("Password must include a lowercase letter.")
    if not any(character.isupper() for character in value):
        raise ValueError("Password must include an uppercase letter.")
    if not any(character.isdigit() for character in value):
        raise ValueError("Password must include a number.")
    if value.lower().strip() in COMMON_WEAK_PASSWORDS:
        raise ValueError("Password is too common.")
    return value


class LoginRequest(BaseModel):
    # Unknown auth fields are rejected so clients cannot smuggle role/admin flags.
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)
    organization_slug: str | None = Field(default=None, max_length=120)

    @field_validator("organization_slug")
    @classmethod
    def normalize_organization_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower().strip()
        return normalized or None


class SignupRequest(BaseModel):
    # Unknown auth fields are rejected so clients cannot smuggle role/admin flags.
    model_config = ConfigDict(extra="forbid")

    mode: SignupMode
    organization_name: str | None = Field(default=None, min_length=2, max_length=255)
    organization_slug: str = Field(min_length=2, max_length=120, pattern=SLUG_PATTERN)
    invite_code: str | None = Field(default=None, min_length=1, max_length=200)
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=10, max_length=1024)

    @field_validator("organization_slug", mode="before")
    @classmethod
    def normalize_organization_slug(cls, value: str) -> str:
        return str(value).lower().strip()

    @field_validator("organization_name", "name", "invite_code", mode="before")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = str(value).strip()
        return stripped or None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)

    @model_validator(mode="after")
    def validate_mode_fields(self) -> "SignupRequest":
        if self.mode == "CREATE_ORG_ADMIN":
            if not self.organization_name:
                raise ValueError("organization_name is required when creating an organization.")
            if self.invite_code:
                raise ValueError("invite_code is not used when creating an organization.")
        if self.mode == "JOIN_ORG_REVIEWER":
            if self.organization_name:
                raise ValueError("organization_name is not used when joining an organization.")
            if not self.invite_code:
                raise ValueError("invite_code is required when joining an organization.")
        return self


class UserResponse(BaseModel):
    id: UUID
    organization_id: UUID
    email: str
    name: str
    role: UserRole


class AuthResponse(BaseModel):
    user: UserResponse


def user_response_from_model(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        name=user.name,
        role=user.role,
    )
