"""Model Catalog editor validation and persistence for the Admin Console.

Enforces the Unified Model Catalog vocabulary from CONTEXT.md and ADR-0129:
the Active Text Model and Image Model for one run belong to the same
Model Provider. Canonical Model Identities are ``provider/model`` keys that
must exist in the catalog; providers are never inferred by string prefix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: str
    model: str
    capabilities: list[str] = Field(default_factory=list)
    protocol: str | None = None


class ModelCatalogDocument(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    active_text_model: str
    capability_models: dict[str, str] = Field(default_factory=dict)
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    models: dict[str, CatalogModel] = Field(default_factory=dict)
    retry: dict[str, Any] = Field(default_factory=dict)

    @field_validator("active_text_model")
    @classmethod
    def identity_shape(cls, value: str) -> str:
        if "/" not in value or value.startswith("/") or value.endswith("/"):
            raise ValueError(
                "Canonical Model Identity must look like 'provider/model', "
                f"got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def check_bindings(self) -> "ModelCatalogDocument":
        if self.active_text_model not in self.models:
            raise ValueError(
                f"active_text_model {self.active_text_model!r} is not declared in models"
            )
        for role, identity in self.capability_models.items():
            if identity not in self.models:
                raise ValueError(
                    f"capability_models.{role} {identity!r} is not declared in models"
                )
        for identity, model in self.models.items():
            if identity != f"{model.provider}/{model.model}" and not identity.startswith(
                f"{model.provider}/"
            ):
                # Allow local/BAAI-bge when model field is BAAI/bge-... (slash in model id).
                if not identity.startswith(f"{model.provider}/"):
                    raise ValueError(
                        f"model key {identity!r} must start with provider "
                        f"{model.provider!r}/"
                    )
            if model.provider not in self.providers:
                raise ValueError(
                    f"model {identity!r} references unknown provider {model.provider!r}"
                )

        text_provider = self.models[self.active_text_model].provider
        image_identity = self.capability_models.get("image_generation")
        if image_identity is not None:
            image_provider = self.models[image_identity].provider
            if image_provider != text_provider:
                raise ValueError(
                    "Active Text Model and Image Model must share one Model Provider "
                    f"(ADR-0129); text uses {text_provider!r}, image uses {image_provider!r}"
                )
        return self


def load_catalog(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def validate_catalog(values: dict) -> ModelCatalogDocument:
    return ModelCatalogDocument.model_validate(values)


def save_catalog(path: Path, document: ModelCatalogDocument) -> None:
    payload = document.model_dump(exclude_none=True)
    path.write_text(
        "# Managed by the Admin Console Model Catalog editor.\n"
        + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    )
