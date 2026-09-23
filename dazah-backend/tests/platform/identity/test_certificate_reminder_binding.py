"""药政证书到期提醒配置接口的页面契约回归测试。

生产曾因 GET /certificate-management/reminder-settings 仅登记注册设置页，
药政证书台账页首屏经服务端取数携带证书管理页 page key 调用时被拒
（403「当前页面不能调用此业务接口」，整页渲染失败）。回归锁定：
只读提醒配置对注册设置页与全部证书管理页开放，写操作仍限注册设置页。
"""

from app.platform.identity.page_policy import api_binding_for_route

_CERTIFICATE_PAGE_KEYS = (
    "registration:certificate-management:international-registration",
    "registration:certificate-management:domestic-registration",
    "registration:certificate-management:domestic-gmp",
    "registration:certificate-management:international-gmp",
)
_SETTINGS_PAGE_KEY = "registration:registration-settings"


def _binding_pages(method: str, path: str) -> tuple[str, ...]:
    binding = api_binding_for_route(method, path)
    assert binding is not None, f"{method} {path} 绑定缺失或契约校验未通过"
    return binding.page_keys


_REMINDER_SETTINGS = "/api/v1/registration/certificate-management/reminder-settings"
_REMINDER_TEST = "/api/v1/registration/certificate-management/reminder-settings/test"
_REMINDER_RECIPIENTS = "/api/v1/registration/certificate-management/reminder-recipients"


def test_reminder_settings_get_covers_certificate_pages():
    pages = _binding_pages("GET", _REMINDER_SETTINGS)
    assert _SETTINGS_PAGE_KEY in pages
    for key in _CERTIFICATE_PAGE_KEYS:
        assert key in pages, f"只读提醒配置缺少证书管理页登记：{key}"


def test_reminder_settings_mutations_stay_settings_only():
    for method, path in (
        ("PUT", _REMINDER_SETTINGS),
        ("POST", _REMINDER_TEST),
    ):
        assert _binding_pages(method, path) == (_SETTINGS_PAGE_KEY,)


def test_reminder_recipients_get_stays_settings_only():
    assert _binding_pages("GET", _REMINDER_RECIPIENTS) == (_SETTINGS_PAGE_KEY,)
