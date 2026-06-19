from .base import *

DEBUG = True
ALLOWED_HOSTS = ["*"]

# dev에서만 플랫폼 기본 Provider(OpenRouter LLM + ollama 임베딩) 폴백을 허용한다.
PLATFORM_DEFAULT_PROVIDERS_ENABLED = True
