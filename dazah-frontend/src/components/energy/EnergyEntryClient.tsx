'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Drawer, Form, Input, InputNumber, Modal, Pagination, Progress, Select, Space, Table, Tag, Typography } from 'antd'
import dayjs from 'dayjs'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { generateLedgerTasks, submitLedgerTask } from '@/actions/energy-ledger'
import { CATEGORY_LABELS, resolveLedgerAction, estimateUsage, formatAmount, ledgerRequest, reportQuery, taskChanges, type EntryItem, type EntrySubmission, type Revision, type Task, type TaskList } from '@/lib/api/energy-ledger'
import { useAuthStore } from '@/stores/auth'
import styles from './EnergyWorkspace.module.css'

type MeterEvent = NonNullable<EntrySubmission['values'][number]['exception']>

export function EnergyEntryClient({ manager }: { manager: boolean }) {
  const { message } = App.useApp()
  const canOperate = useAuthStore(state => state.hasPagePermission('energy:entry', 'operate'))
  const router = useRouter()
  const params = useSearchParams()
  const queryClient = useQueryClient()
  const [taskPage, setTaskPage] = useState(1)
  const [view, setView] = useState('mine')
  const [taskDay, setTaskDay] = useState(dayjs().format('YYYY-MM-DD'))
  const [values, setValues] = useState<Record<string, string | undefined>>({})
  const [reason, setReason] = useState('')
  const [category, setCategory] = useState<string>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [historyId, setHistoryId] = useState<string>()
  const [events, setEvents] = useState<Record<string, MeterEvent>>({})
  const [eventRow, setEventRow] = useState<EntryItem>()
  const [eventForm] = Form.useForm<MeterEvent & { current_value: string }>()
  const taskId = params.get('task')
  const list = useQuery({ queryKey: ['energy-ledger', 'tasks', taskDay, taskPage, view], queryFn: () => ledgerRequest<TaskList>(`/entry-tasks?${reportQuery({ start_date: taskDay, end_date: taskDay, page_size: 30, page: taskPage, mine: view === 'mine' ? 'true' : 'false' })}`) })
  const task = useQuery({ queryKey: ['energy-ledger', 'task', taskId], queryFn: () => ledgerRequest<Task>(`/entry-tasks/${taskId}`), enabled: Boolean(taskId) })
  const history = useQuery({ queryKey: ['energy-ledger', 'history', historyId], queryFn: () => ledgerRequest<Revision[]>(`/ledger-history/reading/${historyId}`), enabled: Boolean(historyId) })
  const items = task.data?.items.filter(item => !category || item.category === category) ?? []
  const pendingEntries = task.data ? taskChanges(task.data, values) : []
  function previewUsage(row: EntryItem) {
    const previousDate = dayjs(row.reading_date).subtract(1, row.frequency === 'monthly' ? 'month' : 'day').format('YYYY-MM-DD')
    return estimateUsage(values[row.id] ?? row.draft_value ?? undefined, row.previous_date === previousDate ? row.previous_value : null, row.multiplier || '1', row.reading_type === 'direct')
  }
  function openEvent(row: EntryItem) {
    eventForm.resetFields()
    eventForm.setFieldsValue({ ...row.exception, ...events[row.id], kind: events[row.id]?.kind || row.exception?.kind || 'replacement', current_value: values[row.id] ?? row.draft_value ?? row.value ?? undefined })
    setEventRow(row)
  }
  const dirty = Object.keys(values).length > 0
  useEffect(() => {
    if (!dirty) return
    function unload(event: BeforeUnloadEvent) { event.preventDefault() }
    function leaving(event: MouseEvent) {
      const anchor = event.target instanceof Element ? event.target.closest('a[href]') : null
      if (anchor instanceof HTMLAnchorElement && anchor.href !== window.location.href && !window.confirm('有未保存的能源填写，确认离开？')) { event.preventDefault(); event.stopImmediatePropagation() }
    }
    window.addEventListener('beforeunload', unload)
    document.addEventListener('click', leaving, true)
    return () => { window.removeEventListener('beforeunload', unload); document.removeEventListener('click', leaving, true) }
  }, [dirty])

  function selectTask(id: string) {
    if (Object.keys(values).length && !window.confirm('有未保存的输入，切换清单将放弃这些输入。确认切换？')) return
    setValues({}); setEvents({}); setError(''); setReason('')
    const next = new URLSearchParams(params)
    next.set('task', id)
    router.replace(`/energy/entry?${next}`)
  }

  async function submit(draft: boolean) {
    if (!task.data) return
    const entries = pendingEntries.map(value => ({ ...value, exception: events[value.reading_id] }))
    if (!entries.length) { setError('请填写至少一个计量点的本次值'); return }
    setBusy(true); setError('')
    try {
      await resolveLedgerAction(submitLedgerTask(task.data.id, { values: entries, draft, reason, source: params.get('source') === 'feishu' ? 'feishu' : 'platform' }))
      setValues({}); setEvents({}); setReason(''); setConfirmOpen(false)
      await queryClient.invalidateQueries({ queryKey: ['energy-ledger'] })
      message.success(draft ? '草稿已保存，正式报表未变更' : '填写已生效，相关报表已更新')
    } catch (cause) { setError(cause instanceof Error ? cause.message : '提交未完成，输入已保留') }
    finally { setBusy(false) }
  }

  async function generate() {
    setBusy(true)
    try { await resolveLedgerAction(generateLedgerTasks(taskDay)); await list.refetch(); message.success('清单已生成，重复操作不会重复创建') }
    catch (cause) { setError(cause instanceof Error ? cause.message : '生成清单失败') }
    finally { setBusy(false) }
  }

  function paste(event: React.ClipboardEvent<HTMLInputElement>, row: EntryItem) {
    const pasted = event.clipboardData.getData('text').trim().split(/\r?\n|\t/)
    if (pasted.length <= 1) return
    event.preventDefault()
    const start = items.findIndex(item => item.id === row.id)
    if (pasted.some(value => !/^\d+(\.\d+)?$/.test(value))) { setError('粘贴内容须为一列非负数值'); return }
    setValues(current => ({ ...current, ...Object.fromEntries(items.slice(start, start + pasted.length).map((item, index) => [item.id, pasted[index]])) }))
  }

  return <>
    <PlatformNotice title="填写当天累计表码与昨日电量；提交即生效" description="可按计量点分批提交。上次读数仅供参考，不自动复制。月末封账后须由能源管理员解锁才能更正；换表等特殊情况联系能源管理员登记。" />
    <div className={styles.toolbar}>
      <label>清单日期 <Input type="date" aria-label="清单日期" value={taskDay} onChange={event => setTaskDay(event.target.value)} /></label>
      <Select aria-label="选择填报清单" style={{ minWidth: 250 }} loading={list.isLoading} value={list.data?.items.some(item => item.id === taskId) ? taskId : undefined} placeholder="选择我的填报清单" onChange={selectTask} options={list.data?.items.map(item => ({ value: item.id, label: `${item.name}（${item.completed_count}/${item.total_count}）` }))} />
      {manager && <Select aria-label="清单范围" value={view} onChange={value => { setView(value); setTaskPage(1) }} options={[{ value: 'mine', label: '我的待填清单' }, { value: 'all', label: '全部任务' }]} />}
      {Boolean(list.data && list.data.total > 30) && <Pagination size="small" current={taskPage} total={list.data?.total} pageSize={30} showSizeChanger={false} onChange={setTaskPage} />}
      {manager && <Button disabled={!canOperate} onClick={generate} loading={busy}>生成该日清单</Button>}
    </div>
    {(error || list.error || task.error) && <PlatformNotice type="error" title={error || list.error?.message || task.error?.message} description="输入仍保留。请按错误提示核对权限、数值、并发版本或封账状态后重试。" action={<Button onClick={() => { void list.refetch(); void task.refetch() }}>重试</Button>} />}
    {!taskId && !list.isLoading && !list.data?.items.length && <PlatformNotice title="该日没有分配给您的填报清单" description="请检查日期；能源管理员可配置责任人和计量点，并生成清单。" />}
    {task.data && <section className={styles.surface}>
      <Typography.Title level={4}>{task.data.name} · {task.data.task_date}</Typography.Title>
      <Progress percent={task.data.total_count ? Math.round(task.data.completed_count / task.data.total_count * 100) : 0} format={() => `${task.data?.completed_count}/${task.data?.total_count}`} />
      <div className={styles.toolbar}><Select aria-label="能源类别" allowClear placeholder="全部能源" value={category} onChange={setCategory} style={{ width: 160 }} options={Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label }))} /><Typography.Text type="secondary">截止 {task.data.deadline_time}；累计表码按抄表日记录，电量按归属日记录</Typography.Text></div>
      <Table<EntryItem> className={styles.desktopTable} rowKey="id" loading={task.isLoading} dataSource={items} pagination={false} scroll={{ x: 1180 }} columns={[
        { title: '计量点', dataIndex: 'name', fixed: 'left', width: 180 },
        { title: '归属／抄表日期', dataIndex: 'reading_date', width: 130 },
        { title: '单位', dataIndex: 'unit', width: 70 },
        { title: '上次值', width: 145, render: (_, row) => <><div>{formatAmount(row.previous_value)}</div><Typography.Text type="secondary">{row.previous_date}</Typography.Text></> },
        { title: '已生效值', render: (_, row) => formatAmount(row.value), width: 130 },
        { title: '本次填写', width: 190, render: (_, row) => <InputNumber<string> disabled={!canOperate} stringMode min="0" precision={row.precision} className={styles.input} aria-label={`${row.name}本次填写`} value={values[row.id] ?? row.draft_value ?? undefined} placeholder={row.draft_value ? '已保存草稿' : '请输入本次值'} onPaste={event => paste(event, row)} onChange={value => setValues(current => ({ ...current, [row.id]: value ?? '' }))} onKeyDown={event => { if (event.key === 'Enter') { const next = event.currentTarget.closest('tr')?.nextElementSibling?.querySelector('input'); if (next instanceof HTMLInputElement) next.focus() } }} /> },
        { title: '预计用量', width: 130, render: (_, row) => events[row.id] || row.exception ? '按特殊事件计算' : formatAmount(previewUsage(row)) },
        { title: '状态', width: 100, render: (_, row) => <Tag>{row.value !== null ? '已生效' : row.draft_value !== null ? '草稿' : '待填写'}</Tag> },
        { title: '记录', width: 140, render: (_, row) => <Space wrap><Button type="link" onClick={() => setHistoryId(row.id)}>历史</Button>{manager && canOperate && row.reading_type === 'counter' && <Button type="link" onClick={() => openEvent(row)}>换表／复位</Button>}</Space> },
      ]} />
      <div className={styles.mobileCards}>{items.map(row => <section key={row.id} className={styles.mobileEntry}>
        <Space wrap><Typography.Text strong>{row.name}</Typography.Text><Tag>{row.value !== null ? '已生效' : row.draft_value !== null ? '草稿' : '待填写'}</Tag></Space>
        <p>{row.reading_type === 'counter' ? '抄表日期' : '用量归属'}：{row.reading_date}；单位 {row.unit}</p>
        <p>上次值 {formatAmount(row.previous_value)}（{row.previous_date || '尚无读数'}）；已生效 {formatAmount(row.value)}</p>
        <InputNumber<string> disabled={!canOperate} stringMode min="0" precision={row.precision} aria-label={`${row.name}本次填写`} placeholder="请输入本次值" value={values[row.id] ?? row.draft_value ?? undefined} onChange={value => setValues(current => ({ ...current, [row.id]: value ?? '' }))} style={{ width: '100%' }} />
        <p>预计用量：{events[row.id] || row.exception ? '按特殊事件计算' : `${formatAmount(previewUsage(row))} ${row.unit}`}</p>
        <Space wrap><Button onClick={() => setHistoryId(row.id)}>填写历史</Button>{manager && canOperate && row.reading_type === 'counter' && <Button onClick={() => openEvent(row)}>换表／复位</Button>}</Space>
      </section>)}</div>
      <Space orientation="vertical" style={{ width: '100%', marginTop: 16 }}>
        <Input.TextArea aria-label="更正原因" placeholder="更正已生效数据时填写原因" value={reason} onChange={event => setReason(event.target.value)} maxLength={1000} />
        <Space><Button disabled={!canOperate} onClick={() => void submit(true)} loading={busy}>保存草稿</Button><Button disabled={!canOperate} type="primary" onClick={() => setConfirmOpen(true)} loading={busy}>提交生效</Button></Space>
      </Space>
    </section>}
    <Modal title="确认能源数据生效" open={confirmOpen} onCancel={() => setConfirmOpen(false)} onOk={() => void submit(false)} confirmLoading={busy}>
      <p>{task.data?.name}：本次填写 {pendingEntries.length} 项，提交后将更新相关日报、月报。</p>
      {pendingEntries.map(entry => {
        const item = task.data?.items.find(item => item.id === entry.reading_id)
        return item && <p key={item.id}>{item.name}（{item.reading_date}）：{formatAmount(item.value)} → {entry.value} {item.unit}</p>
      })}
      {error && <Typography.Text type="danger">{error}</Typography.Text>}
    </Modal>
    <Drawer title="填写与更正历史" open={Boolean(historyId)} onClose={() => setHistoryId(undefined)} size={560}>
      {history.error && <PlatformNotice type="error" title={history.error.message} />}
      <Table<Revision> rowKey="id" loading={history.isLoading} dataSource={history.data} pagination={false} columns={[{ title: '版本', dataIndex: 'version' }, { title: '时间', dataIndex: 'created_at' }, { title: '填写值', render: (_, row) => String(row.payload.value ?? '—') }, { title: '类型', render: (_, row) => row.payload.draft ? '草稿' : '生效' }, { title: '原因', dataIndex: 'reason' }]} />
    </Drawer>
    <Modal title={`${eventRow?.name || ''}：登记换表、复位或回绕`} open={Boolean(eventRow)} onCancel={() => setEventRow(undefined)} onOk={async () => { if (!eventRow) return; try { const { current_value, ...event } = await eventForm.validateFields(); setEvents(current => ({ ...current, [eventRow.id]: event })); setValues(current => ({ ...current, [eventRow.id]: current_value })); if (!reason) setReason(event.reason); setEventRow(undefined) } catch { /* Field errors remain visible. */ } }}>
      <Form form={eventForm} layout="vertical"><Form.Item name="kind" label="事件类型" rules={[{ required: true }]}><Select options={[{ value: 'replacement', label: '更换计量表' }, { value: 'reset', label: '表码复位' }, { value: 'rollover', label: '表码回绕' }]} /></Form.Item><Form.Item name="previous_final" label="旧表最终值／回绕上限" rules={[{ required: true }]}><InputNumber stringMode min="0" /></Form.Item><Form.Item name="new_initial" label="新表初始值／回绕起点" rules={[{ required: true }]}><InputNumber stringMode min="0" /></Form.Item><Form.Item name="current_value" label="本次读数" rules={[{ required: true }]}><InputNumber stringMode min="0" /></Form.Item><Form.Item name="reason" label="事件依据" rules={[{ required: true }]}><Input.TextArea /></Form.Item></Form>
    </Modal>
  </>
}
