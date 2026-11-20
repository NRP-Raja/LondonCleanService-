"""CleanLondon Authentication Schemas — Pydantic request/response models for auth endpoints."""

from pydantic import BaseModel, EmailStr, Field


class UserRegisterSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    phone: str
    role: str = "customer"


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginSchema(BaseModel):
    id_token: str
    email: str | None = None
    name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    message: str | None = None
    is_mock: bool | None = None
