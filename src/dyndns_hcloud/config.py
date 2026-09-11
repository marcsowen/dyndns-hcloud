"""Strict TOML configuration, validated before accepting requests."""

import re
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .addressing import interface_id


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def dns_name(value: str) -> str:
    value = value.lower().rstrip(".")
    if len(value) > 253 or not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in value.split(".")
    ):
        raise ValueError("invalid DNS name (use ASCII/punycode)")
    return value


class Server(Model):
    host: str = "*"
    port: int = Field(default=8080, ge=1, le=65535)
    username: str = Field(min_length=1)
    password: SecretStr

    @field_validator("password")
    @classmethod
    def nonempty_password(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("password must not be empty")
        return value


class Hetzner(Model):
    token: SecretStr
    zone: str
    ttl: int = Field(default=300, ge=60, le=2147483647)

    _zone = field_validator("zone")(dns_name)

    @field_validator("token")
    @classmethod
    def nonempty_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("token must not be empty")
        return value


class Apex(Model):
    ipv4: bool = True
    ipv6: bool = True


class Record(Model):
    name: str
    mac: str
    ipv4: bool = False
    subnet_id: int = Field(default=0, ge=0, le=2**63 - 1)

    @field_validator("name")
    @classmethod
    def relative_name(cls, value: str) -> str:
        return "@" if value == "@" else dns_name(value)

    @field_validator("mac")
    @classmethod
    def valid_mac(cls, value: str) -> str:
        interface_id(value)
        return value.lower().replace("-", ":")


class Config(Model):
    server: Server
    hetzner: Hetzner
    apex: Apex = Field(default_factory=Apex)
    records: list[Record] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_names(self):
        names = [r.name for r in self.records]
        if len(set(names)) != len(names):
            raise ValueError("record names must be unique")
        if "@" in names and (self.apex.ipv4 or self.apex.ipv6):
            raise ValueError("disable both apex options before configuring a client record named @")
        for name in names:
            if name != "@":
                dns_name(f"{name}.{self.hetzner.zone}")
        return self

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        with open(path, "rb") as stream:
            return cls.model_validate(tomllib.load(stream))
