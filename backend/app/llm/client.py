"""Shared Azure AI Foundry / Azure OpenAI client used by the explainer.

The model is called in JSON mode only. Callers validate every answer; nothing the model
returns is trusted without a check (CLAUDE.md principles 1 and 2).
"""

import logging
from typing import Any, Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class LlmCallError(Exception):
    """The LLM service could not answer (network, auth, quota or a rejected request)."""


class LlmClient(Protocol):
    def complete_json(self, system: str, user: str) -> str: ...


class AzureLlmClient:
    """Azure AI Foundry / Azure OpenAI chat completion in JSON mode."""

    def __init__(self, settings: Settings) -> None:
        from openai import AzureOpenAI

        self.client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint.rstrip("/"),
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        self.deployment = settings.azure_openai_deployment
        self.send_temperature = True  # reasoning models accept only the default temperature

    def create(self, system: str, user: str) -> Any:
        """One chat completion call; temperature 0 only while the model accepts it."""
        options: dict[str, Any] = {"temperature": 0} if self.send_temperature else {}
        return self.client.chat.completions.create(
            model=self.deployment,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            **options,
        )

    def complete_json(self, system: str, user: str) -> str:
        """JSON text from the model; raises LlmCallError when the service fails."""
        from openai import APIError, BadRequestError

        try:
            try:
                response = self.create(system, user)
            except BadRequestError as error:
                if not self.send_temperature or getattr(error, "param", None) != "temperature":
                    raise
                logger.info("Deployment %s rejects temperature=0; using the model default", self.deployment)
                self.send_temperature = False
                response = self.create(system, user)
        except APIError as error:
            raise LlmCallError(f"{type(error).__name__}: {getattr(error, 'message', error)}") from error
        return response.choices[0].message.content or "{}"


def client_from_settings(settings: Settings) -> LlmClient | None:
    """An Azure client when all four settings are present, else None (LLM step skipped)."""
    required = (settings.azure_openai_endpoint, settings.azure_openai_api_key, settings.azure_openai_deployment, settings.azure_openai_api_version)
    if not all(required):
        return None
    return AzureLlmClient(settings)
