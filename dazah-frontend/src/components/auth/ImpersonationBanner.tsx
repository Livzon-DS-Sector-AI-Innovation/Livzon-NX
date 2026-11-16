'use client'

import { useEffect, useRef, useState } from 'react'
import { Button, Tooltip } from 'antd'
import { ExclamationCircleOutlined, SwapOutlined } from '@ant-design/icons'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { exitImpersonation } from '@/lib/api/client/impersonation'
import { IMPERSONATION_RECOVERY_PATH, IMPERSONATION_SETTINGS_PATH } from '@/lib/impersonation'
import { finishImpersonationListReturn } from '@/lib/impersonationListState'
import { switchWorkspaceIdentity } from './WorkspaceIdentitySync'
import styles from './ImpersonationBanner.module.css'

export function ImpersonationBanner({ name, expiresAt, inToolbar = false }: {
  name?: string
  expiresAt?: string
  inToolbar?: boolean
}) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const banner = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!expiresAt) return
    const deadline = Date.parse(expiresAt)
    if (!Number.isFinite(deadline)) return
    const timeout = window.setTimeout(
      () => window.location.replace(IMPERSONATION_RECOVERY_PATH),
      Math.max(0, deadline - Date.now()),
    )
    return () => window.clearTimeout(timeout)
  }, [expiresAt])

  async function restore() {
    if (pending) return
    const bounds = inToolbar ? banner.current?.getBoundingClientRect() : undefined
    const origin = bounds && {
      x: (bounds.left + bounds.width / 2) / window.innerWidth,
      y: bounds.bottom / window.innerHeight,
    }
    setPending(true)
    setError('')
    try {
      await switchWorkspaceIdentity('restored', async () => {
        const restored = await exitImpersonation()
        finishImpersonationListReturn(restored)
        return restored ? IMPERSONATION_SETTINGS_PATH : '/login'
      }, origin)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '暂时无法退出模拟')
      setPending(false)
    }
  }

  const title = <span className={styles.summary}>
    {name ? <>
      <span>当前处于</span>{' '}
      <strong className={styles.name}>{name}</strong>{' '}
      <span>用户的模拟视角</span>
    </> : '模拟登录暂不可用或已结束'}
  </span>
  const button = <Button
    size="small"
    className={styles.restore}
    icon={inToolbar && error ? <ExclamationCircleOutlined aria-hidden="true" /> : <SwapOutlined aria-hidden="true" />}
    aria-label="返回管理员身份"
    loading={pending}
    onClick={restore}
  >
    <span>{inToolbar && error ? '重试返回' : '返回管理员身份'}</span>
  </Button>

  return <div ref={banner} className={inToolbar ? styles.toolbar : styles.container}>
    <PlatformNotice
      type="warning"
      showRulesLink={false}
      surface="custom"
      className={styles.notice}
      title={title}
      action={inToolbar ? <Tooltip trigger={['hover', 'focus']} title={error || (name ? `返回管理员身份 · 当前模拟 ${name}` : '返回管理员身份')}>
        {button}
      </Tooltip> : button}
    />
    <p className={inToolbar ? 'sr-only' : styles.error} aria-live="assertive">{error}</p>
  </div>
}
