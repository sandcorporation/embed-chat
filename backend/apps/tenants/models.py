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
    system_prompt = models.TextField(
        default="You are a helpful assistant. Answer questions clearly and concisely."
    )
    agent_display_name = models.CharField(max_length=100, default="상담원")
    webhook_url = models.URLField(blank=True, default="")
    webhook_type = models.CharField(max_length=10, choices=WEBHOOK_TYPE_CHOICES, blank=True, default="")
    welcome_message = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_configs"
