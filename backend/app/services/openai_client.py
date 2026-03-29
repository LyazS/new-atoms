from openai import AsyncOpenAI

from app.config.settings import settings


def create_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.openai_timeout,
    )


openai_client = create_openai_client()
