'use client'

import { useEffect, useRef, useState } from 'react'
import { Button, Modal, Space, Typography } from 'antd'
import PlatformNotice from './PlatformNotice'
import { protectFetch, readMaintenance } from '@/lib/maintenance-client'
import type { MaintenanceState, ProtectedOperation } from '@/lib/maintenance-client'
import type { components } from '@/types/generated/schema'

type OperationResult = components['schemas']['OperationResult']

export default function MaintenanceBoundary({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<MaintenanceState>({ phase: 'normal' })
  const stateRef = useRef(state)
  const [now, setNow] = useState(() => Date.now())
  const [dialogOpen, setDialogOpen] = useState(false)
  const [operationCount, setOperationCount] = useState(0)
  const operations = useRef(new Map<string, ProtectedOperation>())
  const originalFetch = useRef<typeof fetch | null>(null)
  const dirty = useRef(false)
  const [results, setResults] = useState<string[]>([])
  const [canReconcile, setCanReconcile] = useState(false)
  const verifiedOperations = useRef(new Map<string, ProtectedOperation>())
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    const original = window.fetch.bind(window)
    originalFetch.current = original
    let mounted = true
    const update = () => { if (mounted) { verifiedOperations.current.clear(); setOperationCount(operations.current.size); setCanReconcile(false) } }
    const wrapped = protectFetch(original, () => stateRef.current, operations.current, update)
    window.fetch = wrapped
    const apply = (next: MaintenanceState) => {
      if (!mounted) return
      if (next.phase === 'maintenance' && stateRef.current.phase !== 'maintenance') setDialogOpen(true)
      stateRef.current = next
      setState(next)
    }
    let polling = false
    const check = async () => {
      if (polling || document.hidden) return
      polling = true
      try { const next = await readMaintenance(original); if (next) apply(next) } catch { /* Keep the last verified state during a network outage. */ }
      finally { polling = false }
    }
    const changed = () => { dirty.current = true }
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (dirty.current || operations.current.size > 0 || stateRef.current.phase === 'maintenance') {
        event.preventDefault(); event.returnValue = ''
      }
    }
    const preventAction = (event: Event) => {
      if (stateRef.current.phase !== 'maintenance' || !(event.target instanceof Element)) return
      if (event.target.closest('[data-maintenance-control],.dazah-maintenance-dialog')) return
      if (event.type === 'submit' || event.target.closest('a,button,[role="button"]')) {
        event.preventDefault(); event.stopImmediatePropagation(); setDialogOpen(true)
      }
    }
    const timer = setInterval(() => { setNow(Date.now()); void check() }, 1000)
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

  const queryResults = async () => {
    if (!originalFetch.current) return
    setChecking(true)
    setCanReconcile(false)
    verifiedOperations.current.clear()
    const snapshot = new Map(operations.current)
    const messages: string[] = []
    let confirmed = true
    try {
      for (const operation of snapshot.values()) {
        const response = await originalFetch.current(`/api/v1/system/operations/${operation.id}`, { cache: 'no-store' })
        if (!response.ok) { confirmed = false; messages.push(`${operation.id}：结果暂不可确认，请勿重复提交`); continue }
        const result: OperationResult = await response.json()
        const uncertain = result.operation_id !== operation.id || !Array.isArray(result.receipts) || !result.receipts.length ||
          result.receipts.some(receipt => !['completed', 'rejected'].includes(receipt.state))
        confirmed &&= !uncertain
        messages.push(`${operation.id}：${uncertain ? '结果待确认，请勿重复提交' : '请求已处理，请核对业务记录和后台任务结果'}`)
      }
      const unchanged = operations.current.size === snapshot.size && [...snapshot].every(([key, operation]) =>
        operations.current.get(key) === operation && operation.settled)
      if (confirmed && unchanged) verifiedOperations.current = snapshot
      setResults(messages); setCanReconcile(confirmed && unchanged && messages.length > 0)
    } catch { setResults(['操作结果暂不可查询，请保留当前页面，不要重复提交']); setCanReconcile(false) }
    finally { setChecking(false) }
  }

  const remaining = Math.max(0, Math.ceil((state.starts_at || 0) - now / 1000))
  const title = state.phase === 'announced' ? `系统将在约 ${remaining} 秒后维护，请及时保存当前工作` :
    '系统维护中，当前页面和输入已保留，请勿刷新或重复提交'
  return <>
    <div data-maintenance-control style={{ position: 'sticky', top: 0, zIndex: 1050 }}>
      {state.phase !== 'normal' && <PlatformNotice type="warning" title={title}
        onLearnRules={() => setDialogOpen(true)}
        description="维护时暂停新操作，已经发出的请求会等待完成。页面不会自动跳转或刷新；未提交内容仅保留在当前页面。恢复后请先查询待确认操作，核对业务记录再继续。"
        action={<Button onClick={() => setDialogOpen(true)}>查看维护说明</Button>} />}
      {operationCount > 0 && <PlatformNotice title={`${operationCount} 项操作保留了处理记录编号`}
        onLearnRules={() => setDialogOpen(true)}
        description="编号仅保存在当前页面，不保存表单、密码或响应正文。维护或网络异常后先查询操作结果；结果缺失或不确定不能当作未执行。"
        action={<Button loading={checking} disabled={state.phase === 'maintenance'} onClick={() => { setDialogOpen(true); void queryResults() }}>查询操作结果</Button>} />}
    </div>
    <div data-dazah-maintenance-boundary>{children}</div>
    <Modal className="dazah-maintenance-dialog" open={dialogOpen} title={state.phase === 'normal' ? '维护已结束，请核对操作结果' : '系统维护与操作保护'}
      onCancel={() => setDialogOpen(false)} centered footer={<Space data-maintenance-control>
        {operationCount > 0 && <Button loading={checking} disabled={state.phase === 'maintenance'} onClick={() => void queryResults()}>查询操作结果</Button>}
        {canReconcile && <Button onClick={() => {
          for (const [key, operation] of verifiedOperations.current) {
            if (operations.current.get(key) === operation && operation.settled) operations.current.delete(key)
          }
          verifiedOperations.current.clear(); setOperationCount(operations.current.size); setCanReconcile(false); setResults([])
        }}>已核对业务结果，允许新的提交</Button>}
        <Button type="primary" onClick={() => setDialogOpen(false)}>保留页面，查看输入</Button>
      </Space>}>
      <Typography.Paragraph>{state.phase === 'normal' ? '服务已恢复。当前输入仍在原页面，写操作不会自动重放。' : title}</Typography.Paragraph>
      <Typography.Paragraph>已经点击保存的操作可能已经完成。恢复后先查询结果，再核对业务记录；未保存内容仅保留在当前标签页，请勿刷新或关闭。</Typography.Paragraph>
      {results.map(result => <Typography.Paragraph key={result}>{result}</Typography.Paragraph>)}
    </Modal>
  </>
}
