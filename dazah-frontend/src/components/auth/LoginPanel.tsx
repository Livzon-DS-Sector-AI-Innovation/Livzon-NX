'use client'

import { useEffect, useRef, useState } from 'react'

import type { LocalLoginMode } from '@/lib/local-auth'

import {
  IdentityBubble,
  type IdentityBubbleState,
} from './IdentityBubble'
import styles from './IdentityBubble.module.css'
import { LivzonCircuitField } from './LivzonCircuitField'
import { LoginAtmosphere } from './LoginAtmosphere'

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

function BrandMark() {
  return <span aria-hidden="true" className={styles.brandMark} />
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
  const [bubbleState, setBubbleState] = useState<IdentityBubbleState>(
    error && !localError ? 'error' : 'idle',
  )

  const message = error ? errorMessages[error] || '登录失败，请重新尝试。' : null
  const completionPath = `/login/complete?next=${encodeURIComponent(nextPath)}`
  const feishuHref = `/auth/login?next=${encodeURIComponent(completionPath)}`
  const localLoginAvailable = localLoginMode !== 'disabled'
  const emergencyOnly = localLoginMode === 'admin_only'

  useEffect(
    () => () => {
      if (redirectTimer.current) clearTimeout(redirectTimer.current)
    },
    [],
  )

  function startFeishuLogin() {
    if (bubbleState === 'launching') return
    setBubbleState('launching')
    redirectTimer.current = setTimeout(() => {
      window.location.assign(feishuHref)
    }, 240)
  }

  const statusText =
    bubbleState === 'launching'
      ? 'CONNECTING TO FEISHU IDENTITY'
      : bubbleState === 'error'
        ? 'RETRY IDENTITY CHECKPOINT'
        : 'FEISHU IDENTITY CHECKPOINT'

  return (
    <main className={styles.loginExperience}>
      <LoginAtmosphere />
      <header className={styles.loginHeader}>
        <div className={styles.brand}>
          <BrandMark />
          <div>
            <p className={styles.brandName}>LIVZON</p>
            <p className={styles.companyName}>
              ACTIVE PHARMACEUTICAL INGREDIENT
              <br />
              FACTORY MANAGEMENT PLATFORM
            </p>
          </div>
        </div>
        <span className={styles.internalFlag}>
          <strong>INTERNAL SYSTEM</strong>
          <small>STATUS — OPERATIONAL</small>
        </span>
      </header>

      <section className={styles.loginStage} aria-label="身份认证">
        <LivzonCircuitField />
        <div className={styles.stageContent}>
          <IdentityBubble
            state={bubbleState}
            statusText={statusText}
            detailText={
              bubbleState === 'launching'
                ? 'OPENING LIVZON ENTERPRISE AUTHORIZATION'
                : 'CLICK ANYWHERE ON LIVZON TO AUTHENTICATE'
            }
            onActivate={startFeishuLogin}
            disabled={bubbleState === 'launching'}
          />

          {message && (
            <div role="alert" className={styles.errorNotice}>
              {message}
            </div>
          )}

          {localLoginAvailable && (
            <div className={styles.emergencyArea}>
              <button
                type="button"
                className={styles.emergencyToggle}
                aria-expanded={showLocalLogin}
                aria-controls="local-login-form"
                onClick={() => setShowLocalLogin((value) => !value)}
              >
                {showLocalLogin
                  ? 'CLOSE RECOVERY ACCESS'
                  : emergencyOnly
                    ? 'ADMIN RECOVERY ACCESS'
                    : 'LOCAL RECOVERY ACCESS'}
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
        </div>
      </section>

      <footer className={styles.loginFooter}>
        <span>LOG STREAM　——　ONLINE</span>
        <span>TIME SYNC　——　UTC+08:00</span>
      </footer>
    </main>
  )
}
