import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Input, InputNumber, Space, Typography } from 'antd'
import { saveDirectReadings } from '@/actions/energy-ledger'
import { ledgerRequest, reportQuery, resolveLedgerAction, type DirectReading } from '@/lib/api/energy-ledger'

export function EnergyWorkbookCellEditor({ date, dataset, pointId, onClose }: { date: string; dataset: string; pointId: string; onClose: () => void }) {
  const { message } = App.useApp()
  const client = useQueryClient()
  const [value, setValue] = useState<string>()
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const locked = useRef(false)
  const pending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const messageKey = `energy-edit:${dataset}:${date}:${pointId}`
  const query = useQuery({ queryKey: ['energy-ledger', 'input-readings', date, dataset], queryFn: () => ledgerRequest<DirectReading>(`/input-readings?${reportQuery({ reading_date: date, dataset })}`, { headers: { 'X-Dazah-Page-Path': '/energy/entry' } }), staleTime: 0 })
  const item = query.data?.items.find(row => row.point_id === pointId)
  const current = value ?? item?.draft_value ?? item?.value ?? undefined

  useEffect(() => {
    return () => {
      if (pending.current) {
        clearTimeout(pending.current)
        message.destroy(messageKey)
        void message.info('已取消尚未保存的单元格修改')
      }
    }
  }, [message, messageKey])
  useEffect(() => {
    function unload(event: BeforeUnloadEvent) { event.preventDefault() }
    if (value !== undefined || busy) window.addEventListener('beforeunload', unload)
    return () => window.removeEventListener('beforeunload', unload)
  }, [value, busy])

  function submit() {
    if (!item || locked.current) return
    if (!current || !/^\d+(?:\.\d+)?$/.test(current) || !Number.isFinite(Number(current)) || (current.split('.')[1]?.length ?? 0) > item.precision) {
      setError(`请输入非负数，最多 ${item.precision} 位小数`); return
    }
    if (current === item.value && !item.draft_value) { onClose(); return }
    if (item.value !== null && item.value !== undefined && !reason.trim()) { setError('请填写更正原因'); return }
    locked.current = true; setBusy(true); setError('')
    const cancel = () => {
      clearTimeout(pending.current); pending.current = undefined
      locked.current = false; setBusy(false); message.destroy(messageKey)
      void message.info('已撤销修改'); onClose()
    }
    void message.open({ key: messageKey, type: 'info', duration: 0, content: <Space wrap><span>{date} 的修改将在 5 秒后保存</span><Button size="small" type="link" onClick={cancel}>撤销</Button></Space> })
    pending.current = setTimeout(async () => {
      pending.current = undefined
      message.destroy(messageKey)
      try {
        await resolveLedgerAction(saveDirectReadings({ reading_date: date, dataset, values: [{ point_id: pointId, version: item.version, value: current }], draft: false, reason: reason.trim() }))
        await client.invalidateQueries({ queryKey: ['energy-ledger'] })
        void message.success('数据已保存，关联报表已更新'); onClose()
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : '保存失败，输入已保留')
      } finally { locked.current = false; setBusy(false) }
    }, 5000)
  }
  return <Space orientation="vertical" size={4} onKeyDown={event => {
    event.stopPropagation()
    if (event.key === 'Escape' && !busy) { event.preventDefault(); onClose() }
    if (event.key === 'Enter') { event.preventDefault(); submit() }
  }}>
    <InputNumber<string> autoFocus stringMode min="0" aria-label="单元格数值" value={current} disabled={busy || !item || query.isFetching} onFocus={event => event.target.select()} onChange={next => setValue(next ?? '')} />
    {item?.value !== null && item?.value !== undefined && <Input aria-label="更正原因" placeholder="更正原因" value={reason} maxLength={1000} disabled={busy} onChange={event => setReason(event.target.value)} />}
    <Space><Button size="small" type="primary" loading={busy} disabled={!item || query.isFetching} onClick={submit}>保存</Button><Button size="small" disabled={busy} onClick={onClose}>取消</Button></Space>
    {(error || query.error) && <Typography.Text role="alert" type="danger">{error || query.error?.message}</Typography.Text>}
    {query.error && <Button size="small" onClick={() => void query.refetch()}>重试</Button>}
    {!query.isPending && !query.error && !item && <Typography.Text>该字段不可填写</Typography.Text>}
  </Space>
}
