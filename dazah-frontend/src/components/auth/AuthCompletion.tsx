'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'

import type { User } from '@/types/user'

import {
  IdentityBubble,
  type IdentityBubbleState,
} from './IdentityBubble'
import styles from './IdentityBubble.module.css'
import { LivzonCircuitField } from './LivzonCircuitField'
import { LoginAtmosphere } from './LoginAtmosphere'

interface AuthCompletionProps {
  nextPath: string
}

interface CurrentUserResponse {
  data?: User | null
}

const READY_DURATION_MS = 850
const ENTER_DURATION_MS = 900

export function AuthCompletion({ nextPath }: AuthCompletionProps) {
  const router = useRouter()
  const abortController = useRef<AbortController | null>(null)
  const readyTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const enterTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [state, setState] = useState<IdentityBubbleState>('checking')
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

  const statusText =
    state === 'checking'
      ? 'VERIFYING FEISHU IDENTITY'
      : state === 'ready'
        ? 'IDENTITY VERIFIED'
        : state === 'entering'
          ? 'OPENING CONTROLLED WORKSPACE'
          : 'RESTART IDENTITY CHECKPOINT'
  const channelStatus =
    state === 'checking'
      ? 'AUTHORIZING'
      : state === 'ready'
        ? 'VERIFIED'
        : state === 'entering'
          ? 'OPENING'
          : 'INTERRUPTED'

  return (
    <main
      className={`${styles.loginExperience} ${styles.authCompletion}`}
      data-state={state}
    >
      <LoginAtmosphere />
      <header className={styles.loginHeader}>
        <div className={styles.brand}>
          <span aria-hidden="true" className={styles.brandMark} />
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
          <strong>SECURE IDENTITY CHANNEL</strong>
          <small>STATUS — {channelStatus}</small>
        </span>
      </header>

      <section className={styles.loginStage} aria-label="完成身份认证">
        <LivzonCircuitField />
        <div className={styles.stageContent}>
          <IdentityBubble
            state={state}
            statusText={statusText}
            detailText={
              state === 'checking'
                ? 'READING ENTERPRISE IDENTITY AND ACCESS POLICY'
                : state === 'ready'
                  ? 'ENTERPRISE IDENTITY AND ACCESS POLICY CONFIRMED'
                  : state === 'entering'
                    ? 'ESTABLISHING LIVZON SECURE WORKSPACE'
                    : 'CLICK TO RETURN AND RESTART AUTHENTICATION'
            }
            identityText={
              state === 'ready' || state === 'entering'
                ? user?.name || user?.username || undefined
                : undefined
            }
            onActivate={state === 'error' ? restartLogin : undefined}
          />

          {failureMessage && (
            <div role="alert" className={styles.errorNotice}>
              {failureMessage}
            </div>
          )}
        </div>
      </section>

      <footer className={styles.loginFooter}>
        <span>IDENTITY STREAM　——　ENCRYPTED</span>
        <span>SESSION GATE　——　CONTROLLED</span>
      </footer>

      <div className={styles.transitionGate} aria-hidden="true">
        <span className={styles.transitionGateCore} />
        <span className={styles.transitionGateLabel}>
          LIVZON SECURE CHANNEL
        </span>
      </div>
    </main>
  )
}
