'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import type { User } from '@/types/user'

import { AuthLayout } from './AuthLayout'
import styles from './AuthLayout.module.css'

interface AuthCompletionProps {
  nextPath: string
}

interface CurrentUserResponse {
  data?: User | null
}

const READY_DURATION_MS = 850
const ENTER_DURATION_MS = 900

export type AuthCompletionState =
  | 'checking'
  | 'ready'
  | 'entering'
  | 'error'

interface AuthCompletionPresentation {
  title: string
  description: string
  tone: 'primary' | 'success' | 'error'
  symbol?: string
}

export function getAuthCompletionPresentation(
  state: AuthCompletionState,
): AuthCompletionPresentation {
  switch (state) {
    case 'ready':
      return {
        title: '身份验证成功',
        description: '企业身份和访问权限已确认。',
        tone: 'success',
        symbol: '✓',
      }
    case 'entering':
      return {
        title: '正在进入系统',
        description: '工作台准备完成，即将为你打开。',
        tone: 'primary',
      }
    case 'error':
      return {
        title: '身份验证未完成',
        description: '请检查认证状态后重新登录。',
        tone: 'error',
        symbol: '!',
      }
    default:
      return {
        title: '正在验证身份',
        description: '正在读取企业身份和访问权限，请稍候。',
        tone: 'primary',
      }
  }
}

export function AuthCompletion({ nextPath }: AuthCompletionProps) {
  const router = useRouter()
  const abortController = useRef<AbortController | null>(null)
  const readyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const enterTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [state, setState] = useState<AuthCompletionState>('checking')
  const [user, setUser] = useState<User | null>(null)
  const [failureMessage, setFailureMessage] = useState<string | null>(null)

  const clearPendingWork = useCallback(() => {
    abortController.current?.abort()
    if (readyTimer.current) clearTimeout(readyTimer.current)
    if (enterTimer.current) clearTimeout(enterTimer.current)
  }, [])

  const verifyIdentity = useCallback(async () => {
    clearPendingWork()
    const controller = new AbortController()
    abortController.current = controller
    setFailureMessage(null)
    setState('checking')

    try {
      const response = await fetch('/api/v1/identity/me', {
        cache: 'no-store',
        credentials: 'same-origin',
        signal: controller.signal,
      })
      const payload = (await response.json().catch(() => null)) as
        | CurrentUserResponse
        | null

      if (!response.ok || !payload?.data) {
        throw new Error(
          response.status === 401 || response.status === 403
            ? '登录状态未生效，请重新发起飞书认证。'
            : '暂时无法确认登录状态，请重新验证。',
        )
      }

      setUser(payload.data)
      setState('ready')
      readyTimer.current = setTimeout(() => {
        setState('entering')
        enterTimer.current = setTimeout(() => {
          const documentWithTransition = document as Document & {
            startViewTransition?: (callback: () => void) => void
          }
          if (documentWithTransition.startViewTransition) {
            documentWithTransition.startViewTransition(() => {
              router.replace(nextPath)
            })
          } else {
            router.replace(nextPath)
          }
        }, ENTER_DURATION_MS)
      }, READY_DURATION_MS)
    } catch (error) {
      if (controller.signal.aborted) return
      setFailureMessage(
        error instanceof Error
          ? error.message
          : '暂时无法确认登录状态，请重新验证。',
      )
      setState('error')
    }
  }, [clearPendingWork, nextPath, router])

  useEffect(() => {
    const startTimer = window.setTimeout(() => {
      void verifyIdentity()
    }, 0)
    return () => {
      window.clearTimeout(startTimer)
      clearPendingWork()
    }
  }, [clearPendingWork, verifyIdentity])

  function restartLogin() {
    const loginUrl = `/login?next=${encodeURIComponent(nextPath)}`
    window.location.assign(loginUrl)
  }

  const presentation = getAuthCompletionPresentation(state)

  return (
    <AuthLayout footerText="企业身份认证 · 安全访问">
      <div
        className={styles.completionCard}
        aria-live="polite"
        aria-atomic="true"
      >
        <div
          className={styles.completionVisual}
          data-tone={presentation.tone}
          aria-hidden="true"
        >
          {presentation.symbol ? (
            <span className={styles.statusSymbol}>{presentation.symbol}</span>
          ) : (
            <span className={styles.statusSpinner} />
          )}
        </div>

        <h2>{presentation.title}</h2>
        <p className={styles.completionDescription}>
          {presentation.description}
        </p>

        {(state === 'ready' || state === 'entering') &&
          (user?.name || user?.username) && (
            <span className={styles.identityName}>
              {user.name || user.username}
            </span>
          )}

        {failureMessage && (
          <div
            role="alert"
            className={`${styles.errorNotice} ${styles.completionError}`}
          >
            {failureMessage}
          </div>
        )}

        {state === 'error' && (
          <div className={styles.completionActions}>
            <button
              type="button"
              className={styles.primaryButton}
              onClick={restartLogin}
            >
              返回登录
            </button>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => void verifyIdentity()}
            >
              重新验证
            </button>
          </div>
        )}
      </div>
    </AuthLayout>
  )
}
