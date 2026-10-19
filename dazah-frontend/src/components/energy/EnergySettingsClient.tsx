'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tabs, Tag } from 'antd'
import dayjs from 'dayjs'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { adjustLedgerUsage, rebuildLedgerReports, retryLedgerNotification, saveLedgerBot, saveLedgerLock, saveLedgerMeter, saveLedgerPlan, saveLedgerRule, trialLedgerRules } from '@/actions/energy-ledger'
import { CATEGORY_LABELS, resolveLedgerAction, ledgerRequest, type Bot, type BotWrite, type Lock, type Meter, type MeterWrite, type Notification, type Options, type Plan, type PlanWrite, type Rule, type RuleWrite, type AdjustmentWrite, type Trial } from '@/lib/api/energy-ledger'
import { EnergyImportClient } from './EnergyImportClient'
import styles from './EnergyWorkspace.module.css'

type MeterForm = MeterWrite['definition'] & { reason?: string }
type RuleForm = RuleWrite['definition'] & { reason?: string }
type PlanForm = PlanWrite['definition'] & { reason?: string }
const scopes = [{ value: 'source', label: '原始来源（不计入车间／全厂汇总）' }, { value: 'detail', label: '车间及公共区域明细' }, { value: 'plant', label: '全厂总表' }, { value: 'check', label: '核对与差值' }]
const categories = Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label }))
const required = [{ required: true, message: '请填写该项' }]
const quantityKinds = [{ value: 'volume', label: '体积' }, { value: 'mass', label: '质量' }, { value: 'heat', label: '热量' }, { value: 'electricity', label: '电量' }]

export function EnergySettingsClient({ options }: { options?: Options }) {
  const { message, modal } = App.useApp()
  const client = useQueryClient()
  const [meterForm] = Form.useForm<MeterForm>()
  const [ruleForm] = Form.useForm<RuleForm>()
  const [planForm] = Form.useForm<PlanForm>()
  const [botForm] = Form.useForm<BotWrite['definition'] & { app_secret?: string }>()
  const [adjustmentForm] = Form.useForm<AdjustmentWrite>()
  const [editing, setEditing] = useState<{ kind: 'meter' | 'rule' | 'plan'; id: string | null; version: number }>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [month, setMonth] = useState(dayjs().subtract(1, 'month').format('YYYY-MM'))
  const [reason, setReason] = useState('')
  const [trialDate, setTrialDate] = useState(dayjs().subtract(1, 'day').format('YYYY-MM-DD'))
  const [trial, setTrial] = useState<Trial>()
  const enabled = Boolean(options?.is_manager)
  const meters = useQuery({ queryKey: ['energy-ledger', 'meters'], queryFn: () => ledgerRequest<Meter[]>('/meter-points'), enabled })
  const rules = useQuery({ queryKey: ['energy-ledger', 'rules'], queryFn: () => ledgerRequest<Rule[]>('/calculation-rules'), enabled })
  const plans = useQuery({ queryKey: ['energy-ledger', 'plans'], queryFn: () => ledgerRequest<Plan[]>('/entry-plans'), enabled })
  const locks = useQuery({ queryKey: ['energy-ledger', 'locks'], queryFn: () => ledgerRequest<Lock[]>('/period-locks'), enabled })
  const bot = useQuery({ queryKey: ['energy-ledger', 'bot'], queryFn: () => ledgerRequest<Bot>('/bot-config'), enabled })
  const notifications = useQuery({ queryKey: ['energy-ledger', 'notifications'], queryFn: () => ledgerRequest<Notification[]>('/notification-runs'), enabled })
  const metricOptions = [...(meters.data?.map(item => ({ value: `point:${item.definition.code}`, label: `计量点 · ${item.definition.name}` })) ?? []), ...(rules.data?.map(item => ({ value: `rule:${item.definition.code}`, label: `计算指标 · ${item.definition.name}` })) ?? [])]
  const queryError = meters.error || rules.error || plans.error || locks.error || bot.error || notifications.error
  useEffect(() => { if (bot.data && !botForm.isFieldsTouched()) botForm.setFieldsValue(bot.data.definition) }, [bot.data, botForm])

  async function run(action: () => Promise<unknown>, text: string) {
    setBusy(true); setError('')
    try { await action(); await client.invalidateQueries({ queryKey: ['energy-ledger'] }); message.success(text); return true }
    catch (cause) { setError(cause instanceof Error ? cause.message : '操作未完成，请核对后重试'); return false }
    finally { setBusy(false) }
  }

  function editMeter(item?: Meter) {
    meterForm.resetFields()
    meterForm.setFieldsValue(item?.definition ?? { category: 'drinking_water', reading_type: 'counter', frequency: 'daily', multiplier: '1', precision: 3, report_scope: 'source', quantity_kind: 'volume', active_from: dayjs().format('YYYY-MM-DD'), enabled: false })
    setEditing({ kind: 'meter', id: item?.id ?? null, version: item?.version ?? 0 })
  }
  function editRule(item?: Rule) {
    ruleForm.resetFields()
    ruleForm.setFieldsValue(item?.definition ?? { category: 'drinking_water', operation: 'sum', report_scope: 'detail', quantity_kind: 'volume', active_from: dayjs().format('YYYY-MM-DD'), enabled: false, terms: [{ metric_key: '', coefficient: '1' }] })
    setEditing({ kind: 'rule', id: item?.id ?? null, version: item?.version ?? 0 })
  }
  function editPlan(item?: Plan) {
    planForm.resetFields()
    planForm.setFieldsValue(item?.definition ?? { publish_time: '08:00', deadline_time: '10:00', reminder_time: '10:30', enabled: true })
    setEditing({ kind: 'plan', id: item?.id ?? null, version: item?.version ?? 0 })
  }

  async function save() {
    if (!editing) return
    try {
      if (editing.kind === 'meter') {
        const { reason: changeReason, ...definition } = await meterForm.validateFields()
        if (await run(() => resolveLedgerAction(saveLedgerMeter(editing.id, { definition, reason: changeReason || '', version: editing.version })), '计量点已保存，相关未封账结果已重算')) setEditing(undefined)
      } else if (editing.kind === 'rule') {
        const { reason: changeReason, ...definition } = await ruleForm.validateFields()
        if (await run(() => resolveLedgerAction(saveLedgerRule(editing.id, { definition, reason: changeReason || '', version: editing.version })), '计算规则已保存')) setEditing(undefined)
      } else {
        const { reason: changeReason, ...definition } = await planForm.validateFields()
        if (await run(() => resolveLedgerAction(saveLedgerPlan(editing.id, { definition, reason: changeReason || '', version: editing.version })), '填报计划已保存')) setEditing(undefined)
      }
    } catch { /* Form displays field-specific validation and preserves values. */ }
  }

  if (options && !options.is_manager) return <PlatformNotice type="warning" title="需要能源配置管理操作权限" />
  return <>
    <PlatformNotice title="先确认计量口径，再启用计量点和计算关系" description="计量点编号稳定不变；新配置保留版本和生效日期。原始来源与汇总结果不能重复参与同一范围合计。月底抄表按月首边界读数计算上月期间用量，不平均摊入每日。" />
    {(error || queryError) && <PlatformNotice type="error" title={error || queryError?.message} description="配置输入已保留，请核对错误后重试。" />}
    <Tabs items={[
      { key: 'meters', label: '计量点', children: <><Button type="primary" onClick={() => editMeter()}>新增计量点</Button><Table<Meter> rowKey="id" loading={meters.isLoading} dataSource={meters.data} scroll={{ x: 900 }} columns={[{ title: '编号', render: (_, row) => row.definition.code }, { title: '计量点', render: (_, row) => row.definition.name }, { title: '能源', render: (_, row) => CATEGORY_LABELS[row.definition.category] }, { title: '区域', render: (_, row) => row.definition.area }, { title: '单位／倍率', render: (_, row) => `${row.definition.unit} × ${row.definition.multiplier}` }, { title: '状态', render: (_, row) => <Tag>{row.definition.enabled ? '启用' : '草案／停用'}</Tag> }, { title: '操作', render: (_, row) => <Button type="link" onClick={() => editMeter(row)}>配置</Button> }]} /></> },
      { key: 'rules', label: '计算关系', children: <><Space wrap><Button type="primary" onClick={() => editRule()}>新增计算指标</Button><Input type="date" aria-label="试算日期" value={trialDate} onChange={event => setTrialDate(event.target.value)} /><Button loading={busy} onClick={() => void run(async () => setTrial(await resolveLedgerAction(trialLedgerRules(trialDate))), '试算完成，未写入报表')}>试算该日</Button><Button loading={busy} onClick={() => modal.confirm({ title: '重算该月未封账报表', content: `将按生效规则重算 ${dayjs(trialDate).format('YYYY-MM')} 的结果。原始读数不变。`, onOk: () => run(() => resolveLedgerAction(rebuildLedgerReports(dayjs(trialDate).startOf('month').format('YYYY-MM-DD'), dayjs(trialDate).endOf('month').format('YYYY-MM-DD'))), '报表已重算') })}>重算该月</Button></Space><Table<Rule> rowKey="id" loading={rules.isLoading} dataSource={rules.data} columns={[{ title: '指标', render: (_, row) => row.definition.name }, { title: '车间', render: (_, row) => row.definition.workshop || '公共区域／全厂' }, { title: '单位', render: (_, row) => row.definition.unit }, { title: '生效日期', render: (_, row) => row.definition.active_from }, { title: '状态', render: (_, row) => row.definition.enabled ? '启用' : '草案／停用' }, { title: '操作', render: (_, row) => <Button type="link" onClick={() => editRule(row)}>配置</Button> }]} />{trial && <Table rowKey="metric_key" dataSource={trial.values} columns={[{ title: '指标', dataIndex: 'name' }, { title: '试算值', dataIndex: 'value' }, { title: '状态', dataIndex: 'status' }]} />}</> },
      { key: 'plans', label: '责任分组', children: <><Button type="primary" onClick={() => editPlan()}>新增填报分组</Button><Table<Plan> rowKey="id" loading={plans.isLoading} dataSource={plans.data} columns={[{ title: '分组', render: (_, row) => row.definition.name }, { title: '计量点数', render: (_, row) => row.definition.point_ids.length }, { title: '责任人', render: (_, row) => row.definition.owner_ids.map(id => options?.people.find(person => person.id === id)?.name || id).join('、') }, { title: '发布／截止／提醒', render: (_, row) => `${row.definition.publish_time} / ${row.definition.deadline_time} / ${row.definition.reminder_time}` }, { title: '状态', render: (_, row) => row.definition.enabled ? '启用' : '停用' }, { title: '操作', render: (_, row) => <Button type="link" onClick={() => editPlan(row)}>配置</Button> }]} /></> },
      { key: 'bot', label: '飞书机器人', children: <>
        <PlatformNotice title="机器人发布清单，员工在飞书内打开填报页" description="机器人应用使用能源模块独立凭据。员工身份复用平台飞书登录，个人消息使用企业人员标识。请先确认应用发消息权限、人员可达及 HTTPS 地址；密钥不会回传。" />
        <Form form={botForm} layout="vertical" onFinish={({ app_secret, ...definition }) => void run(() => resolveLedgerAction(saveLedgerBot({ definition, app_secret: app_secret || undefined, version: bot.data?.version || 0 })), '机器人配置已保存')}>
          <Button onClick={() => botForm.setFieldsValue(bot.data?.definition || { enabled: false })}>载入已保存配置</Button>
          <Form.Item name="app_id" label="能源应用 App ID"><Input autoComplete="off" /></Form.Item><Form.Item name="app_secret" label={bot.data?.secret_configured ? '应用密钥（已配置，留空保留）' : '应用密钥'}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item name="base_url" label="平台 HTTPS 访问地址"><Input placeholder="https://平台域名" /></Form.Item><Form.Item name="enabled" label="启用机器人" valuePropName="checked"><Switch /></Form.Item><Button htmlType="submit" type="primary" loading={busy}>保存机器人配置</Button>
        </Form>
        <Table<Notification> rowKey="id" dataSource={notifications.data} columns={[{ title: '状态', dataIndex: 'status' }, { title: '尝试次数', dataIndex: 'attempts' }, { title: '处理提示', dataIndex: 'error' }, { title: '操作', render: (_, row) => <Button disabled={!['failed', 'retry'].includes(row.status)} onClick={() => void run(() => resolveLedgerAction(retryLedgerNotification(row.id)), '消息已加入重试队列')}>重试</Button> }]} />
      </> },
      { key: 'periods', label: '封账与调整', children: <>
        <div className={styles.toolbar}><Input type="month" aria-label="封账月份" value={month} onChange={event => setMonth(event.target.value)} style={{ width: 170 }} /><Input aria-label="封账或解锁原因" value={reason} onChange={event => setReason(event.target.value)} placeholder="填写封账或解锁原因" style={{ width: 300 }} /><Button disabled={!reason} loading={busy} onClick={() => modal.confirm({ title: locks.data?.find(item => item.month === month)?.locked ? '解锁月份' : '确认封账', content: `${month}：${reason}。封账保存本次报表版本并阻止后续更正；解锁后更正将重算相关结果。`, onOk: () => run(() => resolveLedgerAction(saveLedgerLock(month, { locked: !locks.data?.find(item => item.month === month)?.locked, version: locks.data?.find(item => item.month === month)?.version || 0, reason })), '月份状态已更新') })}>{locks.data?.find(item => item.month === month)?.locked ? '解锁该月' : '封账该月'}</Button></div>
        <Table<Lock> rowKey="month" dataSource={locks.data} columns={[{ title: '月份', dataIndex: 'month' }, { title: '状态', render: (_, row) => row.locked ? '已封账' : '未封账' }, { title: '版本', dataIndex: 'version' }]} />
        <Form form={adjustmentForm} layout="vertical" onFinish={payload => modal.confirm({ title: '确认人工调整', content: `${payload.usage_date} 的用量将${payload.mode === 'override' ? '覆盖为' : '增减'} ${payload.value}。保留原计算值和调整原因，并重算关联结果。`, onOk: () => run(() => resolveLedgerAction(adjustLedgerUsage(payload)), '调整已生效') })}>
          <div className={styles.forms}><Form.Item name="metric_key" label="调整指标" rules={required}><Select showSearch optionFilterProp="label" options={metricOptions} /></Form.Item><Form.Item name="usage_date" label="用量日期" rules={required}><Input type="date" /></Form.Item><Form.Item name="mode" label="调整方式" rules={required}><Select options={[{ value: 'override', label: '覆盖有效值' }, { value: 'delta', label: '增减量' }]} /></Form.Item><Form.Item name="value" label="调整数值" rules={required}><InputNumber stringMode /></Form.Item><Form.Item name="reason" label="依据与原因" rules={required} className={styles.full}><Input.TextArea maxLength={1000} /></Form.Item></div><Button htmlType="submit" loading={busy}>应用人工调整</Button>
        </Form>
      </> },
      { key: 'imports', label: '历史导入', children: <EnergyImportClient meters={meters.data ?? []} rules={rules.data ?? []} onChanged={() => client.invalidateQueries({ queryKey: ['energy-ledger'] })} /> },
      { key: 'history', label: '历史来源', children: <Space wrap><Link href="/energy/sources">历史来源与映射</Link><Link href="/energy/data">历史快照</Link><Link href="/energy/sync-runs">历史同步记录</Link></Space> },
    ]} />
    <Modal title={editing?.kind === 'meter' ? '配置计量点' : editing?.kind === 'rule' ? '配置计算关系' : '配置填报分组'} open={Boolean(editing)} onCancel={() => setEditing(undefined)} width={820} confirmLoading={busy} onOk={() => void save()} okText="保存配置" destroyOnHidden>
      {error && <PlatformNotice type="error" title={error} />}
      {editing?.kind === 'meter' && <Form form={meterForm} layout="vertical" preserve>
        <Form.Item name="source_sheet" hidden><Input /></Form.Item><Form.Item name="source_column" hidden><InputNumber /></Form.Item>
        <div className={styles.forms}>
          <Form.Item name="code" label="稳定编号" rules={required}><Input disabled={Boolean(editing.id)} /></Form.Item><Form.Item name="name" label="计量点名称" rules={required}><Input /></Form.Item>
          <Form.Item name="category" label="能源类别" rules={required}><Select options={categories} onChange={value => { if (value === 'electricity') meterForm.setFieldsValue({ reading_type: 'direct', quantity_kind: 'electricity' }) }} /></Form.Item><Form.Item name="area" label="抄表区域" rules={required}><Input /></Form.Item>
          <Form.Item name="department" label="归属部门" rules={required}><Input /></Form.Item><Form.Item name="workshop" label="车间／共享区域"><Input /></Form.Item><Form.Item name="unit" label="计量单位" rules={required}><Input placeholder="如 m³、t、kWh" /></Form.Item><Form.Item name="quantity_kind" label="指标类型" rules={required}><Select options={quantityKinds} /></Form.Item>
          <Form.Item name="reading_type" label="填写口径" rules={required}><Select options={[{ value: 'counter', label: '累计表底' }, { value: 'direct', label: '直接用量' }]} /></Form.Item><Form.Item name="frequency" label="抄表频率" rules={required}><Select options={[{ value: 'daily', label: '每日' }, { value: 'monthly', label: '月首抄取上月期末表底' }]} /></Form.Item>
          <Form.Item name="multiplier" label="倍率" rules={required}><InputNumber stringMode min="0.00000001" /></Form.Item><Form.Item name="precision" label="允许小数位数" rules={required}><InputNumber min={0} max={8} /></Form.Item><Form.Item name="temperature" label="温度／工况"><Input placeholder="如 7℃、-5℃" /></Form.Item><Form.Item name="report_scope" label="参与统计范围" rules={required}><Select options={scopes} /></Form.Item>
          <Form.Item name="active_from" label="生效日期" rules={required}><Input type="date" /></Form.Item><Form.Item name="active_to" normalize={value => value || null} label="结束日期"><Input type="date" onChange={event => { if (!event.target.value) meterForm.setFieldValue('active_to', null) }} /></Form.Item><Form.Item name="warning_limit" label="用量提醒阈值"><InputNumber stringMode min="0" /></Form.Item><Form.Item name="enabled" label="确认并启用" valuePropName="checked"><Switch /></Form.Item><Form.Item name="notes" label="计量说明" className={styles.full}><Input.TextArea /></Form.Item><Form.Item name="reason" label="配置变更原因" rules={editing.id ? required : []} className={styles.full}><Input.TextArea /></Form.Item>
        </div>
      </Form>}
      {editing?.kind === 'rule' && <Form form={ruleForm} layout="vertical" preserve><div className={styles.forms}>
        <Form.Item name="code" label="稳定编号" rules={required}><Input disabled={Boolean(editing.id)} /></Form.Item><Form.Item name="name" label="指标名称" rules={required}><Input /></Form.Item><Form.Item name="category" label="能源类别" rules={required}><Select options={categories} /></Form.Item><Form.Item name="unit" label="结果单位" rules={required}><Input /></Form.Item><Form.Item name="department" label="归属部门" rules={required}><Input /></Form.Item><Form.Item name="workshop" label="车间／区域"><Input /></Form.Item><Form.Item name="temperature" label="温度／工况"><Input /></Form.Item><Form.Item name="quantity_kind" label="指标类型" rules={required}><Select options={[...quantityKinds, { value: 'ratio', label: '占比' }]} /></Form.Item><Form.Item name="operation" label="计算方式" rules={required}><Select options={[{ value: 'sum', label: '按系数加减来源' }, { value: 'ratio', label: '第一来源除以第二来源' }]} /></Form.Item><Form.Item name="report_scope" label="统计范围" rules={required}><Select options={scopes} /></Form.Item>
        <Form.Item name="frequency" initialValue="daily" label="计量周期"><Select options={[{ value: 'daily', label: '每日用量' }, { value: 'monthly', label: '月度期间用量' }]} /></Form.Item><Form.List name="terms">{(fields, { add, remove }) => <div className={styles.full}>{fields.map(field => <Space key={field.key} align="baseline" wrap><Form.Item name={[field.name, 'metric_key']} label="来源" rules={required}><Select showSearch optionFilterProp="label" style={{ width: 380 }} options={metricOptions.filter(item => item.value !== `rule:${ruleForm.getFieldValue('code')}`)} /></Form.Item><Form.Item name={[field.name, 'coefficient']} label="系数（减项填 -1）" rules={required}><InputNumber stringMode /></Form.Item><Button onClick={() => remove(field.name)}>移除</Button></Space>)}<Button onClick={() => add({ metric_key: '', coefficient: '1' })}>增加来源</Button></div>}</Form.List>
        <Form.Item name="active_from" label="生效日期" rules={required}><Input type="date" /></Form.Item><Form.Item name="active_to" normalize={value => value || null} label="结束日期"><Input type="date" /></Form.Item><Form.Item name="enabled" label="确认并启用" valuePropName="checked"><Switch /></Form.Item><Form.Item name="notes" label="计算说明" className={styles.full}><Input.TextArea /></Form.Item><Form.Item name="reason" label="配置变更原因" rules={editing.id ? required : []} className={styles.full}><Input.TextArea /></Form.Item>
      </div></Form>}
      {editing?.kind === 'plan' && <Form form={planForm} layout="vertical" preserve><Form.Item name="name" label="能源＋抄表区域分组名称" rules={required}><Input /></Form.Item><Form.Item name="point_ids" label="负责的计量点" rules={required}><Select mode="multiple" showSearch optionFilterProp="label" options={meters.data?.map(item => ({ value: item.id, label: item.definition.name }))} /></Form.Item><Form.Item name="owner_ids" label="责任人" rules={required}><Select mode="multiple" showSearch optionFilterProp="label" options={options?.people.map(person => ({ value: person.id, label: `${person.name}（${person.department}）` }))} /></Form.Item><div className={styles.forms}><Form.Item name="publish_time" label="每日发布时间" rules={required}><Input type="time" /></Form.Item><Form.Item name="deadline_time" label="每日截止时间" rules={required}><Input type="time" /></Form.Item><Form.Item name="reminder_time" label="未完成提醒时间" rules={required}><Input type="time" /></Form.Item><Form.Item name="group_chat_id" label="汇总群标识（可选）"><Input /></Form.Item><Form.Item name="enabled" label="启用计划" valuePropName="checked"><Switch /></Form.Item><Form.Item name="reason" label="变更原因"><Input /></Form.Item></div></Form>}
    </Modal>
  </>
}
