import asyncio
import logging
import time

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

FAST_MODEL = "gpt-4o-mini"
SMART_MODEL = "gpt-4o"
FAST_FALLBACK = "gpt-4o-mini-2024-07-18"
SMART_FALLBACK = "gpt-4o-mini"


class LLMRouter:
    def __init__(self):
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI()
        return self._client

    async def complete_fast(
        self,
        prompt: str,
        system: str = None,
        max_tokens: int = 1000,
        cached_prefix: str = None,
    ) -> str:
        start = time.monotonic()
        # OpenAI auto-caches long system prompts (>1024 tokens).
        # Prepend stable filing text to system so subsequent calls hit the cache.
        sys_content = system or ""
        if cached_prefix:
            sys_content = f"{sys_content}\n\n{cached_prefix}" if sys_content else cached_prefix

        messages = []
        if sys_content:
            messages.append({"role": "system", "content": sys_content})
        messages.append({"role": "user", "content": prompt})

        resp = None
        last_err = None
        for model in (FAST_MODEL, FAST_FALLBACK):
            try:
                resp = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
                break
            except Exception as e:
                last_err = e
                logger.warning(f"[fast] {model} failed: {e}")

        if resp is None:
            raise RuntimeError(f"All fast models failed: {last_err}")

        elapsed = time.monotonic() - start
        usage = resp.usage
        logger.info(
            f"[fast] model={model} {elapsed:.2f}s | "
            f"in={usage.prompt_tokens} out={usage.completion_tokens}"
        )
        return resp.choices[0].message.content

    async def complete_smart(
        self,
        messages: list,
        system: str,
        max_tokens: int = 4000,
        cached_prefix: str = None,
    ) -> str:
        start = time.monotonic()
        full_system = f"{system}\n\n{cached_prefix}" if cached_prefix else system
        full_messages = [{"role": "system", "content": full_system}] + messages

        resp = None
        last_err = None
        for model in (SMART_MODEL, SMART_FALLBACK):
            try:
                resp = await self.client.chat.completions.create(
                    model=model,
                    messages=full_messages,
                    max_tokens=max_tokens,
                )
                break
            except Exception as e:
                last_err = e
                logger.warning(f"[smart] {model} failed: {e}")

        if resp is None:
            raise RuntimeError(f"All smart models failed: {last_err}")

        elapsed = time.monotonic() - start
        usage = resp.usage
        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
        logger.info(
            f"[smart] model={model} {elapsed:.2f}s | "
            f"in={usage.prompt_tokens} cached={cached} out={usage.completion_tokens}"
        )
        return resp.choices[0].message.content

    async def complete_parallel(self, prompts: list[dict]) -> list[str]:
        async def _one(p: dict) -> str:
            try:
                return await self.complete_fast(
                    prompt=p["prompt"],
                    system=p.get("system"),
                    max_tokens=p.get("max_tokens", 1000),
                )
            except Exception as e:
                logger.error(f"Parallel subagent error: {e}")
                return f"Error: {str(e)}"

        start = time.monotonic()
        results = await asyncio.gather(*[_one(p) for p in prompts], return_exceptions=True)
        results = [str(r) if isinstance(r, Exception) else r for r in results]

        completed = sum(1 for r in results if not str(r).startswith("Error:"))
        logger.info(
            f"[parallel] {len(prompts)} tasks in {time.monotonic()-start:.2f}s | "
            f"{completed}/{len(prompts)} ok"
        )
        return results


llm_router = LLMRouter()
