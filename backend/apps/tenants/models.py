import hashlib
import secrets
import uuid
from django.contrib.auth.hashers import make_password, check_password as django_check_password
from django.db import models
from django.contrib.auth.models import AbstractUser


class Operator(AbstractUser):
    class Meta:
        db_table = "operators"


class TenantManager(models.Manager):
    def create_with_key(self, name: str, raw_key: str) -> "Tenant":
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        tenant = self.create(name=name, tenant_key_hash=key_hash)
        TenantConfig.objects.create(tenant=tenant)
        return tenant


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    # 공개 챗봇 URL(/chatbot/{slug}/)용 고유·URL-safe 식별자. 표시명(name)과 분리.
    # null 허용: 기존/미설정 Tenant는 slug 없이 존재(Postgres에서 NULL은 unique 충돌 안 함).
    slug = models.CharField(max_length=63, unique=True, null=True, blank=True)
    tenant_key_hash = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = "tenants"

    @classmethod
    def verify_key(cls, raw_key: str) -> "Tenant | None":
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        return cls.objects.filter(tenant_key_hash=key_hash, is_active=True).first()

    @classmethod
    def resolve_slug(cls, slug: str) -> "Tenant | None":
        """공개 챗봇 URL의 slug로 활성 Tenant를 조회한다. 미존재·정지 시 None."""
        if not slug:
            return None
        return cls.objects.filter(slug=slug, is_active=True).first()

    def reset_key(self) -> str:
        new_key = secrets.token_urlsafe(32)
        self.tenant_key_hash = hashlib.sha256(new_key.encode()).hexdigest()
        self.save(update_fields=["tenant_key_hash"])
        return new_key

class TenantAgent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="agents")
    username = models.CharField(max_length=150)
    password_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant_agents"
        unique_together = [("tenant", "username")]

    def set_password(self, raw_password: str) -> None:
        self.password_hash = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return django_check_password(raw_password, self.password_hash)


class TenantConfig(models.Model):
    WEBHOOK_SLACK = "slack"
    WEBHOOK_DISCORD = "discord"
    WEBHOOK_GENERIC = "generic"
    WEBHOOK_TYPE_CHOICES = [
        (WEBHOOK_SLACK, "Slack"),
        (WEBHOOK_DISCORD, "Discord"),
        (WEBHOOK_GENERIC, "Generic"),
    ]

    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name="config")
    model_id = models.CharField(max_length=255, default="openrouter/owl-alpha")
    # LLM Provider(챗+추출) 설정 — Tenant가 자기 키로 비용 부담(ADR-0012). type이 비면
    # 플랫폼 기본(OpenRouter)으로 폴백. api_key는 암호화 저장(write-only).
    llm_provider_type = models.CharField(max_length=20, blank=True, default="")
    llm_base_url = models.CharField(max_length=500, blank=True, default="")
    llm_api_key = models.TextField(blank=True, default="")
    extraction_model = models.CharField(max_length=255, blank=True, default="")
    # Embedding Provider — LLM Provider와 독립(Anthropic 임베딩 부재). type이 비면
    # 플랫폼 기본(dev=ollama). 변경 시 재임베딩 재구축 트리거(issue 95).
    embed_provider_type = models.CharField(max_length=20, blank=True, default="")
    embed_base_url = models.CharField(max_length=500, blank=True, default="")
    embed_api_key = models.TextField(blank=True, default="")
    embed_model = models.CharField(max_length=255, blank=True, default="")
    embed_dim = models.IntegerField(default=1024)
    system_prompt = models.TextField(
        default="You are a helpful assistant. Answer questions clearly and concisely."
    )
    agent_display_name = models.CharField(max_length=100, default="상담원")
    webhook_url = models.URLField(blank=True, default="")
    webhook_type = models.CharField(max_length=10, choices=WEBHOOK_TYPE_CHOICES, blank=True, default="")
    welcome_message = models.TextField(blank=True, default="")
    # 위젯 헤더 상단에 표시되는 Tenant 브랜드 텍스트(이미지 로고 아님). 비면 상태 텍스트만.
    brand_name = models.CharField(max_length=100, blank=True, default="")
    # 식별 Visitor의 visitor_id 위조를 막는 HMAC 신원검증 요구(opt-in). 기본 꺼짐.
    require_identity_verification = models.BooleanField(default=False)
    # HITL(사람 상담원 전환) 사용 여부. 꺼지면 에이전트 그래프가 escalation 분기 없이 로드된다.
    hitl_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_configs"
