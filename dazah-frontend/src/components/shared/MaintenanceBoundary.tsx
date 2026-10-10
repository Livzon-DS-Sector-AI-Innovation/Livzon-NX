'use client'

import { useEffect, useRef, useState } from 'react'
import { Button, Modal, Typography } from 'antd'
import styles from './MaintenanceBoundary.module.css'
import PlatformNotice from './PlatformNotice'
import { isMaintenanceActive, protectFetch, readMaintenance } from '@/lib/maintenance-client'
import type { MaintenanceState } from '@/lib/maintenance-client'

export default function MaintenanceBoundary({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<MaintenanceState>({ phase: 'normal' })
  const stateRef = useRef(state)
  const [now, setNow] = useState(() => Date.now())
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dismissedPhase, setDismissedPhase] = useState('')
  const dirty = useRef(false)

  useEffect(() => {
    const original = window.fetch.bind(window)
    let controller = new AbortController()
    const wrapped = protectFetch(original, () => stateRef.current, () => controller.signal)
    window.fetch = wrapped
    let mounted = true
    const apply = (next: MaintenanceState) => {
      if (!mounted) return
      if (isMaintenanceActive(next)) {
        next = { phase: 'maintenance' }
        controller.abort()
      } else if (controller.signal.aborted) controller = new AbortController()
      if (next.phase === 'maintenance' && stateRef.current.phase !== 'maintenance') setDialogOpen(true)
      if (next.phase === 'normal') { setDialogOpen(false); setDismissedPhase('') }
      setNow(Date.now())
      stateRef.current = next
      setState(next)
    }
    let polling = false
    const check = async () => {
      if (polling || document.hidden) return
      polling = true
      try { const next = await readMaintenance(original); if (next) apply(next) }
      catch { /* A network failure does not reopen maintenance traffic. */ }
      finally { polling = false }
    }
    const changed = () => { dirty.current = true }
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (dirty.current || isMaintenanceActive(stateRef.current)) {
        event.preventDefault(); event.returnValue = ''
      }
    }
    const preventAction = (event: Event) => {
      if (!isMaintenanceActive(stateRef.current) || !(event.target instanceof Element)) return
      if (event.target.closest('[data-maintenance-control],.dazah-maintenance-dialog')) return
      if (event.type === 'submit' || event.target.closest('a,button,[role="button"]')) {
        event.preventDefault(); event.stopImmediatePropagation(); setDialogOpen(true)
      }
    }
    const timer = setInterval(() => {
      setNow(Date.now())
      if (stateRef.current.phase === 'announced' && isMaintenanceActive(stateRef.current)) apply({ phase: 'maintenance' })
      void check()
    }, 1000)
    document.addEventListener('visibilitychange', check)
    document.addEventListener('input', changed, true)
    document.addEventListener('change', changed, true)
    document.addEventListener('click', preventAction, true)
    document.addEventListener('submit', preventAction, true)
    window.addEventListener('beforeunload', beforeUnload)
    void check()
    return () => {
      mounted = false; clearInterval(timer)
      if (window.fetch === wrapped) window.fetch = original
      document.removeEventListener('visibilitychange', check)
      document.removeEventListener('input', changed, true)
      document.removeEventListener('change', changed, true)
      document.removeEventListener('click', preventAction, true)
      document.removeEventListener('submit', preventAction, true)
      window.removeEventListener('beforeunload', beforeUnload)
    }
  }, [])

  const remaining = Math.max(0, Math.ceil((state.starts_at || 0) - now / 1000))
  const title = state.phase === 'announced' ?
    `系统将在 ${Math.floor(remaining / 60)} 分 ${remaining % 60} 秒后更新，请完成当前工作并停止操作` :
    '系统正在更新发布，请停止操作，等待维护结束'
  const description = '发布前提前 3 分钟提醒，请在倒计时内完成并保存当前工作，然后停止操作。维护开始后停止页面请求；维护结束后可继续使用。页面不会自动刷新，未保存输入仅保留在当前标签页。'
  const dismiss = () => { setDialogOpen(false); setDismissedPhase(state.phase) }
  return <>
    {state.phase !== 'normal' && <div data-maintenance-control className={styles.floating}>
      {dismissedPhase !== state.phase ? <PlatformNotice type="warning" title={title} description={description}
        onLearnRules={() => setDialogOpen(true)} action={<Button onClick={dismiss}>我知道了</Button>} /> :
        <Button onClick={() => setDialogOpen(true)}>查看维护说明</Button>}
    </div>}
    <div data-dazah-maintenance-boundary>{children}</div>
    <Modal className="dazah-maintenance-dialog" open={dialogOpen} title="系统更新维护" onCancel={dismiss}
      centered width={640} footer={<Button type="primary" onClick={dismiss}>我知道了，保留当前页面</Button>}>
      <Typography.Paragraph strong>{title}</Typography.Paragraph>
      <Typography.Paragraph>{description}</Typography.Paragraph>
    </Modal>
  </>
}
