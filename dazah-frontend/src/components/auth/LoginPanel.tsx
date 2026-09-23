'use client'

import { useEffect, useRef, useState } from 'react'
import { ArrowRightOutlined, SafetyCertificateOutlined } from '@ant-design/icons'

import type { LocalLoginMode } from '@/lib/local-auth'

import { AuthLayout } from './AuthLayout'
import styles from './AuthLayout.module.css'

const errorMessages: Record<string, string> = {
  feishu_not_configured: '飞书应用凭证未配置，请联系系统管理员。',
  redirect_uri_missing: '飞书回调地址未配置，请联系系统管理员。',
  invalid_state: '登录状态已失效，请重新发起授权。',
  missing_code: '飞书未返回授权码，请重新登录。',
  access_denied: '你已取消飞书授权。',
  account_disabled: '账号已停用，请联系系统管理员。',
  callback_failed: '飞书授权登录失败，请稍后重试。',
  local_login_failed: '账号或密码不正确，请重新输入。',
  local_login_forbidden: '本地登录当前不可用，或该账号不具备应急管理员权限。',
  missing_credentials: '请输入账号和密码。',
  missing_token: '登录响应无效，请重新登录。',
}

interface LoginPanelProps {
  error?: string
  nextPath: string
  localLoginMode: LocalLoginMode
}

export function LoginPanel({
  error,
  nextPath,
  localLoginMode,
}: LoginPanelProps) {
  const redirectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const recoveryTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pending = useRef(false)
  const localError = Boolean(
    error?.startsWith('local_') || error === 'missing_credentials',
  )
  const [showLocalLogin, setShowLocalLogin] = useState(localError)
  const [isRedirecting, setIsRedirecting] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [navigationError, setNavigationError] = useState<string | null>(null)
  const isBusy = isRedirecting || isSubmitting

  const message = getLoginErrorMessage(error)
  const feishuHref = buildFeishuLoginHref(nextPath)
  const localLoginAvailable = localLoginMode !== 'disabled'
  const emergencyOnly = localLoginMode === 'admin_only'

  useEffect(() => {
    function resetNavigation() {
      pending.current = false
      setIsRedirecting(false)
      setIsSubmitting(false)
      if (redirectTimer.current) clearTimeout(redirectTimer.current)
      if (recoveryTimer.current) clearTimeout(recoveryTimer.current)
    }
    window.addEventListener('pageshow', resetNavigation)
    return () => {
      window.removeEventListener('pageshow', resetNavigation)
      if (redirectTimer.current) clearTimeout(redirectTimer.current)
      if (recoveryTimer.current) clearTimeout(recoveryTimer.current)
    }
  }, [])

  function beginNavigation() {
    if (pending.current) return false
    pending.current = true
    setNavigationError(null)
    recoveryTimer.current = setTimeout(() => {
      pending.current = false
      setIsRedirecting(false)
      setIsSubmitting(false)
      setNavigationError('页面跳转耗时较长，请检查网络后重试。')
    }, 12000)
    return true
  }

  function startFeishuLogin() {
    if (!beginNavigation()) return
    setIsRedirecting(true)
    redirectTimer.current = setTimeout(() => {
      window.location.assign(feishuHref)
    }, 240)
  }

  return (
    <AuthLayout>
      <div className={styles.loginPanel}>
        <div className={styles.panelHeader}>
          <p className={styles.panelEyebrow}>企业身份认证</p>
          <h2>欢迎登录</h2>
          <p>使用丽珠企业账号，安全进入工厂管理平台。</p>
        </div>

        {(navigationError || (message && !isBusy)) && (
          <div role="alert" className={styles.errorNotice}>
            {navigationError || message}
          </div>
        )}

        <div className={styles.loginMethod}>
          <div className={styles.methodHeader}>
            <span className={styles.methodIcon} aria-hidden="true"><SafetyCertificateOutlined /></span>
            <div><strong>飞书企业账号</strong><p>使用企业身份完成授权</p></div>
            <span className={styles.methodBadge}>推荐</span>
          </div>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={startFeishuLogin}
            disabled={isBusy}
            aria-busy={isRedirecting}
            aria-describedby="login-status"
          >
            {isRedirecting && (
              <span className={styles.buttonSpinner} aria-hidden="true" />
            )}
            {isRedirecting ? '正在打开飞书认证…' : '使用飞书企业账号登录'}
            {!isRedirecting && <ArrowRightOutlined className={styles.buttonArrow} aria-hidden="true" />}
          </button>
          <p id="login-status" className={styles.loginStatus} role="status" aria-live="polite">
            {isRedirecting ? '正在前往飞书，请在授权页面确认身份。' : isSubmitting ? '正在验证账号，请稍候…' : '授权完成后，将自动进入已获授权的业务页面。'}
          </p>
        </div>
        <ol className={styles.loginSteps} aria-label="登录流程">
          <li data-active={isRedirecting || undefined}><span>1</span>飞书授权</li>
          <li><span>2</span>验证身份</li>
          <li><span>3</span>进入平台</li>
        </ol>

        {localLoginAvailable && (
          <div className={styles.emergencyArea}>
            <button
              type="button"
              className={styles.emergencyToggle}
              aria-expanded={showLocalLogin}
              aria-controls="local-login-form"
              disabled={isBusy}
              onClick={() => setShowLocalLogin((value) => !value)}
            >
              <span className={styles.toggleChevron} aria-hidden="true">
                ▶
              </span>
              {emergencyOnly ? '管理员应急登录' : '本地账号登录'}
            </button>

            {showLocalLogin && (
              <form
                id="local-login-form"
                action="/auth/local-login"
                method="post"
                className={styles.localForm}
                onSubmit={(event) => {
                  if (!beginNavigation()) {
                    event.preventDefault()
                    return
                  }
                  setIsSubmitting(true)
                }}
              >
                <input type="hidden" name="next" value={nextPath} />
                {emergencyOnly && (
                  <p className={styles.localHint}>
                    仅用于飞书认证故障期间的系统恢复，普通本地账号无法登录。
                  </p>
                )}
                <label className={styles.field}>
                  <span>账号</span>
                  <input name="username" autoComplete="username" required />
                </label>
                <label className={styles.field}>
                  <span>密码</span>
                  <input
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                  />
                </label>
                <button type="submit" className={styles.localSubmit} disabled={isBusy} aria-busy={isSubmitting}>
                  {isSubmitting ? '正在验证账号…' : '验证并进入系统'}
                </button>
              </form>
            )}
          </div>
        )}
        <p className={styles.loginHelp}>如无法登录，请联系企业管理员确认账号与访问权限。</p>
      </div>
    </AuthLayout>
  )
}

export function buildFeishuLoginHref(nextPath: string): string {
  const completionPath = `/login/complete?next=${encodeURIComponent(nextPath)}`
  return `/auth/login?next=${encodeURIComponent(completionPath)}`
}

export function getLoginErrorMessage(error?: string): string | null {
  return error
    ? errorMessages[error] || '登录失败，请重新尝试。'
    : null
}
