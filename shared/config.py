"""Shared configuration — reads from .env, no module-level side effects."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings. All values can be overridden via environment variables."""

    # DashScope / LLM
    dashscope_api_key: str = ""
    llm_model: str = "qwen3-max"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Agent
    agent_max_iterations: int = 10

    # Data sources
    mining_api_base: str = "https://www.mining.com/wp-json/wp/v2"
    mining_rss_url: str = "https://www.mining.com/feed"

    # Demo / fallback mode
    demo_mode: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}
