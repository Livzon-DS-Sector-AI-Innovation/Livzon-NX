'use client'

import { useEffect, useRef, useState } from 'react'

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
  const localError = Boolean(
    error?.startsWith('local_') || error === 'missing_credentials',
  )
  const [showLocalLogin, setShowLocalLogin] = useState(localError)
  const [isRedirecting, setIsRedirecting] = useState(false)

  const message = getLoginErrorMessage(error)
  const feishuHref = buildFeishuLoginHref(nextPath)
  const localLoginAvailable = localLoginMode !== 'disabled'
  const emergencyOnly = localLoginMode === 'admin_only'

  useEffect(
    () => () => {
      if (redirectTimer.current) clearTimeout(redirectTimer.current)
    },
    [],
  )

  function startFeishuLogin() {
    if (isRedirecting) return
    setIsRedirecting(true)
    redirectTimer.current = setTimeout(() => {
      window.location.assign(feishuHref)
    }, 240)
  }

  return (
    <AuthLayout>
      <div className={styles.panelHeader}>
        <p className={styles.panelEyebrow}>企业身份认证</p>
        <h2>欢迎登录</h2>
        <p>使用丽珠企业飞书账号验证身份并进入管理平台。</p>
      </div>

      {message && (
        <div role="alert" className={styles.errorNotice}>
          {message}
        </div>
      )}

      <button
        type="button"
        className={styles.primaryButton}
        onClick={startFeishuLogin}
        disabled={isRedirecting}
        aria-busy={isRedirecting}
      >
        {isRedirecting && (
          <span className={styles.buttonSpinner} aria-hidden="true" />
        )}
        {isRedirecting ? '正在打开飞书认证…' : '使用飞书企业账号登录'}
      </button>
      <p className={styles.securityHint}>企业身份认证通道运行正常</p>

      {localLoginAvailable && (
        <div className={styles.emergencyArea}>
          <button
            type="button"
            className={styles.emergencyToggle}
            aria-expanded={showLocalLogin}
            aria-controls="local-login-form"
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
              <button type="submit" className={styles.localSubmit}>
                验证并进入系统
              </button>
            </form>
          )}
        </div>
      )}
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
