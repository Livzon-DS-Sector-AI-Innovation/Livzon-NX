import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # dazah-backend/


def _get_env_file() -> str:
    """根据 APP_ENV 选择 .env 文件；缺省环境文件不存在时回退到 .env。"""
    app_env = os.getenv("APP_ENV", "development")
    env_path = _PROJECT_ROOT / f".env.{app_env}"
    if not env_path.exists():
        env_path = _PROJECT_ROOT / ".env"
    env_file = str(env_path)
    print(f"Loading environment variables from: {env_file}")
    return env_file


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "dazah-backend"
    APP_ENV: str = "development"
    DEBUG: bool = False
    DEV_BYPASS_AUTH: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def coerce_debug_bool(cls, v: object) -> bool:
        """兼容 VS Code 等注入的非布尔值（如 DEBUG=release）。"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes"):
                return True
            return False
        return bool(v)

    SECRET_KEY: str = "change-me-in-production"
    ENCRYPTION_KEY: str | None = None

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/dazah"
    TEST_DATABASE_URL: str | None = None

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Audit
    AUDIT_RETENTION_DAYS: int = 7

    # Feishu / Lark — platform app shared by SSO, org sync, IM and common Bitable.
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_REDIRECT_URI: str = ""
    FEISHU_SCOPES: str = (
        "contact:contact.base:readonly contact:user.base:readonly offline_access"
    )
    FRONTEND_URL: str = ""
    BACKEND_PUBLIC_URL: str = ""
    FEISHU_WS_ENABLED: bool = True

    # Feishu 设备部
    FEISHU_EQUIPMENT_DEPT_ID: str = ""
    FEISHU_EQUIPMENT_CHAT_ID: str = "oc_ba1a54a70a0d611315f29581621c50b5"
    FEISHU_SAFETY_CHAT_ID: str = ""

    # Feishu 组织架构同步
    FEISHU_SYNC_ROOT_DEPT_ID: str = ""  # 部门同步的根部门 ID（API 触发）
    FEISHU_SYNC_MEMBER_DEPT_ID: str = ""  # 成员同步的目标部门 ID（每日 00:00）

    # Feishu 安全模块机器人（独立应用凭证）
    SAFETY_FEISHU_APP_ID: str = ""
    SAFETY_FEISHU_APP_SECRET: str = ""
    SAFETY_FEISHU_BITABLE_APP_TOKEN: str = ""
    SAFETY_FEISHU_BITABLE_HAZARD_TABLE_ID: str = ""

    # Feishu 设备模块交互机器人（独立应用凭证）
    EQUIPMENT_FEISHU_APP_ID: str = ""
    EQUIPMENT_FEISHU_APP_SECRET: str = ""
    EQUIPMENT_FEISHU_WS_ENABLED: bool = True

    # Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # MinIO / S3-compatible object storage
    MINIO_ENABLED: bool = False
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET_PREFIX: str = "dazah"
    MINIO_SECURE: bool = False

    # Energy
    ENERGY_AUTO_COLLECT_ENABLED: bool = False

    # Maintenance Plan — 自动生成工单
    MAINTENANCE_PLAN_AUTO_ENABLED: bool = True

    # JWT
    JWT_EXPIRE_SECONDS: int = 86400  # 24 hours

    # Local auth. When unset, development enables it and production disables it.
    # Use admin_only only for a time-boxed production recovery window.
    LOCAL_LOGIN_MODE: Literal["disabled", "admin_only", "enabled"] | None = None

    # All authenticated users can access business modules in the current
    # development and production deployment. Set this to ``roles`` only when
    # grant-based module access is explicitly required.
    MODULE_ACCESS_MODE: Literal["roles", "all"] | None = None

    # Local auth bootstrap (development or emergency administrator accounts)
    BOOTSTRAP_ADMIN_USERNAME: str = ""
    BOOTSTRAP_ADMIN_PASSWORD: str = ""
    BOOTSTRAP_ADMIN_NAME: str = "系统管理员"
    BOOTSTRAP_ADMIN_EMAIL: str = ""
    BOOTSTRAP_USER_USERNAME: str = ""
    BOOTSTRAP_USER_PASSWORD: str = ""
    BOOTSTRAP_USER_NAME: str = "普通用户"
    BOOTSTRAP_USER_EMAIL: str = ""
    SSO_ADMIN_IDENTIFIERS: str = ""

    # Feishu Bitable — HR 模块多维表格同步
    FEISHU_BOT_NAME: str = ""
    FEISHU_BITABLE_APP_TOKEN: str = ""
    FEISHU_BITABLE_EMPLOYEE_TABLE_ID: str = ""
    FEISHU_BITABLE_DEPARTMENT_TABLE_ID: str = ""
    FEISHU_BITABLE_OFFBOARDING_TABLE_ID: str = ""
    FEISHU_BITABLE_ONBOARDING_TABLE_ID: str = ""
    FEISHU_BITABLE_DEPARTURE_TABLE_ID: str = ""
    FEISHU_BITABLE_APPROVAL_TABLE_ID: str = ""
    FEISHU_BITABLE_CONTRACT_MANAGEMENT_TABLE_ID: str = ""
    FEISHU_BITABLE_POSITION_TRANSFER_TABLE_ID: str = ""

    # HR Feishu member synchronization. These are optional and intentionally
    # empty by default; deployments opt in through their environment.
    HR_FEISHU_MEMBER_ROOT_DEPT_ID: str = ""
    HR_FEISHU_MEMBER_EXTRA_ROOT_DEPT_IDS: str = ""
    HR_FEISHU_MEMBER_EMPLOYEE_NO_PREFIX: str = "112"
    HR_FEISHU_MEMBER_SYNC_INTERVAL_HOURS: int = 12
    HR_OFFBOARDING_REMINDER_OPEN_ID: str = ""

    # Feishu Bitable — 产品模块
    FEISHU_BITABLE_PRODUCT_APP_TOKEN: str = ""
    FEISHU_BITABLE_PRODUCT_TABLE_ID: str = ""

    # Feishu Bitable — 质量模块环境兜底。质量模块仍以模块内配置表为主；
    # 这些字段仅用于兼容既有部署和初始化预填。
    QUALITY_FEISHU_APP_TOKEN: str = ""
    QUALITY_SOLID_BASE_TOKEN: str = ""
    QUALITY_LIQUID_BASE_TOKEN: str = ""
    QUALITY_FEISHU_DEVIATION_REPORT_TABLE_ID: str = ""
    QUALITY_FEISHU_DEVIATION_INVESTIGATION_PUSH_TABLE_ID: str = ""
    QUALITY_FEISHU_DEVIATION_TABLE_ID: str = ""
    QUALITY_FEISHU_CAPA_TABLE_ID: str = ""
    QUALITY_FEISHU_CAPA_PLAN_TABLE_ID: str = ""
    QUALITY_DEPARTMENT_CONTACT_FEISHU_APP_TOKEN: str = ""
    QUALITY_DEPARTMENT_CONTACT_FEISHU_TABLE_ID: str = ""
    QUALITY_CHANGE_LEDGER_FEISHU_APP_TOKEN: str = ""
    QUALITY_CHANGE_LEDGER_FEISHU_TABLE_ID: str = ""
    QUALITY_CHANGE_ACTION_PLAN_FEISHU_APP_TOKEN: str = ""
    QUALITY_CHANGE_ACTION_PLAN_FEISHU_TABLE_ID: str = ""
    QUALITY_VALIDATION_FEISHU_APP_TOKEN: str = ""
    QUALITY_VALIDATION_FEISHU_TABLE_ID: str = ""

    # Training Notification Bitable
    FEISHU_BITABLE_TRAINING_NOTIFICATION_APP_TOKEN: str = ""
    FEISHU_BITABLE_TRAINING_NOTIFICATION_TABLE_ID: str = ""

    # AI — HR 离职分析提示词；模型连接统一使用 core.llm_configs。
    AI_SYSTEM_PROMPT: str = (
        "你是「小H」，原料药工厂人事管理助手。"
        "只基于查询结果回答人事问题，禁止编造。"
        "回答极其简洁，只陈述事实，不分析、不解释、不推理。"
        "禁止出现'根据规则'、'依据以上信息'等元话语。"
    )

    # Regulatory Tracker — 定时同步
    DAILY_SYNC_CRON: str = "0 2 * * *"
    CRAWLER_HEADLESS: bool = True
    CRAWLER_BROWSERS_PATH: str = ""  # 空字符串 = Playwright 默认路径
    CDE_GUIDELINE_URL: str = (
        "https://www.cde.org.cn/zdyz/listpage/9cd8db3b7530c6fa0c86485e563f93c7"
    )

    # Storage
    STORAGE_ROOT: str = "./storage"

    # Registration local workbooks/templates. Business attachments remain in
    # the deployment storage and are never copied from the migration source.
    REGISTRATION_AUTHORIZATION_SOURCE_DIR: str = "./data/registration/授权书"
    REGISTRATION_WORKBOOK_DIR: str = "./data/registration"
    REGISTRATION_PROJECT_LEDGER_WORKBOOK_NAME: str = "1. 注册台账.xlsx"
    REGISTRATION_DECLARATION_PROGRESS_WORKBOOK_NAME: str = (
        "宁夏-注册项目信息统计表-2026.06.25.xlsx"
    )
    REGISTRATION_CERTIFICATE_WORKBOOK_NAME: str = "2. 药政证书台账.xlsx"

    # Feishu event verification is optional for local deployments.
    FEISHU_EVENT_ENCRYPT_KEY: str = ""
    FEISHU_EVENT_VERIFICATION_TOKEN: str = ""

    # LLM (AI 解析配置)
    LLM_API_KEY: str | None = None
    LLM_BASE_URL: str | None = "https://api.deepseek.com"
    LLM_MODEL: str | None = "deepseek-chat"

    # MCP — AI Agent 认证
    MCP_AGENT_API_KEYS: str = ""

    # Hermes 中枢 Agent
    HERMES_AGENT_V2_URL: str = ""
    HERMES_AGENT_TOKEN: str = ""
    HERMES_INTERNAL_URL: str = ""
    HERMES_INTERNAL_TOKEN: str = ""
    AGENT_USER_MEMORY_MODE: Literal["auto", "explicit_only", "disabled"] = "auto"
    AGENT_USER_MEMORY_NOTICE_VERSION: int = 1
    LIVZON_FEISHU_ALLOWED_GROUPS: str = ""
    AGENT_TOOL_TOKEN: str = ""
    AGENT_LLM_PROXY_TOKEN: str = ""
    AGENT_INTERNAL_API_BASE_URL: str = "http://127.0.0.1:8000/api/v1"
    AGENT_INTERNAL_API_TOKEN: str = ""
    AGENT_WRITE_CONFIRM_TTL_SECONDS: int = 300
    AGENT_HERMES_TIMEOUT_SECONDS: int = 210
    AGENT_INTERNAL_API_TIMEOUT_SECONDS: int = 120

    @field_validator("HERMES_AGENT_V2_URL")
    @classmethod
    def require_agent_backend_v2_url(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if normalized and not normalized.endswith("/v2/agent/runs"):
            raise ValueError(
                "HERMES_AGENT_V2_URL must target AgentBackend V2 (/v2/agent/runs)"
            )
        return normalized

    # API
    API_V1_PREFIX: str = "/api/v1"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def effective_local_login_mode(
        self,
    ) -> Literal["disabled", "admin_only", "enabled"]:
        if self.LOCAL_LOGIN_MODE is not None:
            return self.LOCAL_LOGIN_MODE
        return "disabled" if self.is_production else "enabled"

    @property
    def effective_module_access_mode(self) -> Literal["roles", "all"]:
        if self.MODULE_ACCESS_MODE is not None:
            return self.MODULE_ACCESS_MODE
        return "roles"

    def check(self) -> None:
        """启动时校验关键配置，避免漏配导致运行时异常。"""
        missing: list[str] = []
        if not self.SECRET_KEY:
            missing.append("SECRET_KEY")
        if self.is_production and not self.ENCRYPTION_KEY:
            missing.append("ENCRYPTION_KEY")
        if not self.FRONTEND_URL:
            missing.append("FRONTEND_URL")
        if self.is_production:
            has_sso_admin = bool(self.SSO_ADMIN_IDENTIFIERS.strip())
            has_emergency_admin = (
                self.effective_local_login_mode in {"admin_only", "enabled"}
                and bool(self.BOOTSTRAP_ADMIN_USERNAME.strip())
                and bool(self.BOOTSTRAP_ADMIN_PASSWORD)
            )
            if not has_sso_admin and not has_emergency_admin:
                missing.append(
                    "SSO_ADMIN_IDENTIFIERS（或启用本地登录并配置 BOOTSTRAP_ADMIN_*）"
                )
        if missing:
            raise RuntimeError(
                "以下 .env 配置项缺失或无效，请检查:\n  " + "\n  ".join(missing),
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.check()
    return settings
