'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Drawer, Input, InputNumber, Modal, Select, Space, Table, Typography } from 'antd'
import dayjs from 'dayjs'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { saveDirectReadings } from '@/actions/energy-ledger'
import { resolveLedgerAction, formatAmount, ledgerRequest, reportQuery, type DirectReading, type Revision } from '@/lib/api/energy-ledger'
import { useAuthStore } from '@/stores/auth'
import styles from './EnergyWorkspace.module.css'
import { EnergyDatePicker } from './EnergyDatePicker'

const SOURCES = ['饮用水码', '冰水码', '蒸汽码', '循环水码', '空气码', '电量']
type Item = DirectReading['items'][number]

function fieldName(name: string) {
  return name.replace(/^开发验证\s*[·•:：-]\s*/, '')
}

export function EnergyEntryClient() {
  const { message, modal } = App.useApp()
  const allowNavigation = useRef(false)
  const params = useSearchParams()
  const client = useQueryClient()
  const canOperate = useAuthStore(state => state.hasPagePermission('energy:entry', 'operate'))
  const [date, setDate] = useState(() => /^\d{4}-\d{2}-\d{2}$/.test(params.get('date') || '') && dayjs(params.get('date')).isValid() ? params.get('date')! : dayjs().format('YYYY-MM-DD'))
  const [dataset, setDataset] = useState(() => SOURCES.includes(params.get('dataset') || '') ? params.get('dataset')! : SOURCES[0])
  const [values, setValues] = useState<Record<string, string | undefined>>({})
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [historyId, setHistoryId] = useState<string>()
  const query = reportQuery({ reading_date: date, dataset })
  const readings = useQuery({ queryKey: ['energy-ledger', 'input-readings', query], queryFn: () => ledgerRequest<DirectReading>(`/input-readings?${query}`), enabled: Boolean(date) })
  const history = useQuery({ queryKey: ['energy-ledger', 'history', historyId], queryFn: () => ledgerRequest<Revision[]>(`/ledger-history/reading/${historyId}`), enabled: Boolean(historyId) })
  const items = readings.data?.items ?? []
  const pending = items.flatMap(row => {
    const value = values[row.point_id] ?? row.draft_value
    return value !== undefined && value !== null && value !== '' && (value !== row.value || row.draft_value !== null) ? [{ point_id: row.point_id, version: row.version, value }] : []
  })
  const dirty = Object.keys(values).length > 0
  useEffect(() => {
    if (!dirty) return
    function unload(event: BeforeUnloadEvent) { if (!allowNavigation.current) event.preventDefault() }
    function leaving(event: MouseEvent) {
      const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null
      if (!(anchor instanceof HTMLAnchorElement) || anchor.href === window.location.href || allowNavigation.current) return
      event.preventDefault(); event.stopImmediatePropagation()
      modal.confirm({
        title: '离开能源填写', content: '有未保存的能源填写，离开将放弃这些输入。', okText: '放弃并离开', cancelText: '继续填写',
        onOk: () => { allowNavigation.current = true; setValues({}); setReason(''); setError(''); anchor.click() },
      })
    }
    window.addEventListener('beforeunload', unload); document.addEventListener('click', leaving, true)
    return () => { window.removeEventListener('beforeunload', unload); document.removeEventListener('click', leaving, true) }
  }, [dirty, modal])

  function changeSelection(change: () => void) {
    const apply = () => { setValues({}); setReason(''); setError(''); change() }
    if (dirty) {
      modal.confirm({ title: '切换数据范围', content: '有未保存的输入，切换将放弃这些输入。', okText: '放弃并切换', cancelText: '继续填写', onOk: apply })
    } else apply()
  }
  async function save(draft: boolean) {
    if (!pending.length) { setError('请填写至少一个原始字段'); return }
    setBusy(true); setError('')
    try {
      await resolveLedgerAction(saveDirectReadings({ reading_date: date, dataset, values: pending, draft, reason }))
      setValues({}); setReason(''); setConfirmOpen(false)
      await client.invalidateQueries({ queryKey: ['energy-ledger'] })
      message.success(draft ? '草稿已保存' : '原始数据已保存，关联台账已更新')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存未完成，输入已保留') }
    finally { setBusy(false) }
  }
  return <>
    <div className={styles.filters}>
      <div className={styles.filterField}><label htmlFor="energy-entry-date">数据日期</label><EnergyDatePicker id="energy-entry-date" label="数据日期" disabled={busy} allowClear={false} value={date} onChange={value => changeSelection(() => setDate(value))} /></div>
      <div className={styles.filterField}><label htmlFor="energy-entry-dataset">原始数据表</label><Select id="energy-entry-dataset" aria-label="原始数据表" disabled={busy} value={dataset} onChange={value => changeSelection(() => setDataset(value))} options={SOURCES.map(value => ({ value, label: value }))} /></div>
      <Typography.Text className={styles.entryDateHint} type="secondary">{dataset === '电量' ? '日期为电量归属日；只填写原始电量字段' : '日期为表码抄表日'}</Typography.Text>
    </div>
    {(error || readings.error) && <PlatformNotice type="error" title={error || readings.error?.message} description="输入已保留，请核对字段数值或数据版本后重试。" action={<Button onClick={() => void readings.refetch()}>重试</Button>} />}
    {!readings.isPending && !readings.error && !items.length && <PlatformNotice title="该原始表暂无当前权限内的字段" description="能源管理员可通过历史导入识别原表字段与公式，无需配置责任分组或生成清单。" />}
    <Table<Item> className={styles.entryTable} tableLayout="fixed" rowKey="point_id" dataSource={items} loading={readings.isFetching} pagination={false} scroll={{ x: 900 }} columns={[
      { title: '原始字段', dataIndex: 'name', ellipsis: true, render: (name: string) => fieldName(name) },
      { title: '单位', dataIndex: 'unit', width: 90 },
      { title: '已保存数值', width: 200, align: 'right', render: (_, row) => formatAmount(row.value) },
      { title: '本次填写', width: 240, render: (_, row) => <InputNumber<string> className={styles.entryValue} stringMode min="0" precision={row.precision} disabled={!canOperate || busy} aria-label={`${fieldName(row.name)}本次填写`} value={values[row.point_id] ?? row.draft_value ?? undefined} onChange={value => { allowNavigation.current = false; setValues(current => ({ ...current, [row.point_id]: value ?? '' })) }} /> },
      { title: '修改记录', width: 140, align: 'center', render: (_, row) => row.reading_id ? <Button type="link" onClick={() => setHistoryId(row.reading_id!)}>查看记录</Button> : '—' },
    ]} />
    {items.length > 0 && <Space orientation="vertical" style={{ width: '100%' }}>
      <Input.TextArea aria-label="更正原因" placeholder="更正已保存数值时填写原因" maxLength={1000} disabled={busy || !canOperate} value={reason} onChange={event => setReason(event.target.value)} />
      <Space><Button disabled={!canOperate || busy} onClick={() => void save(true)}>保存草稿</Button><Button type="primary" disabled={!canOperate || busy || !date} loading={busy} onClick={() => pending.length ? setConfirmOpen(true) : setError('请填写至少一个原始字段')}>提交生效</Button></Space>
    </Space>}
    <Modal title="确认保存原始数据" open={confirmOpen} onCancel={() => setConfirmOpen(false)} onOk={() => void save(false)} confirmLoading={busy}>
      <p>{dataset} · {date}：本次保存 {pending.length} 项，相关台账将自动重新计算。</p>
      {error && <Typography.Text type="danger">{error}</Typography.Text>}
    </Modal>
    <Drawer title="原始数据修改记录" open={Boolean(historyId)} onClose={() => setHistoryId(undefined)} size={560}>
      {history.error && <PlatformNotice type="error" title={history.error.message} />}
      <Table<Revision> rowKey="id" dataSource={history.data} loading={history.isFetching} pagination={false} columns={[{ title: '版本', dataIndex: 'version' }, { title: '时间', dataIndex: 'created_at' }, { title: '数值', render: (_, row) => String(row.payload.value ?? '—') }, { title: '原因', dataIndex: 'reason' }]} />
    </Drawer>
  </>
}
