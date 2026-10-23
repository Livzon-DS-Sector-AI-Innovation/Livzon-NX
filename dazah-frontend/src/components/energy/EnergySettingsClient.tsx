'use client'

import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Button, Form, Input, Skeleton, Switch, Table, Tabs } from 'antd'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { retryLedgerNotification, saveLedgerBot } from '@/actions/energy-ledger'
import { resolveLedgerAction, ledgerRequest, type Bot, type BotWrite, type Meter, type Notification, type Options } from '@/lib/api/energy-ledger'
import { EnergyImportClient } from './EnergyImportClient'
import { EnergyReviewClient } from './EnergyReviewClient'

export function EnergySettingsClient({ options }: { options?: Options }) {
  const { message } = App.useApp()
  const client = useQueryClient()
  const [botForm] = Form.useForm<BotWrite['definition'] & { app_secret?: string }>()
  const [activeTab, setActiveTab] = useState('bot')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const enabled = Boolean(options?.is_manager)
  // Import mappings still read existing definitions; there are no editing tabs.
  const meters = useQuery({ queryKey: ['energy-ledger', 'meters'], queryFn: () => ledgerRequest<Meter[]>('/input-fields'), enabled: enabled && activeTab === 'imports' })
  const bot = useQuery({ queryKey: ['energy-ledger', 'bot'], queryFn: () => ledgerRequest<Bot>('/bot-config'), enabled: enabled && activeTab === 'bot' })
  const notifications = useQuery({ queryKey: ['energy-ledger', 'notifications'], queryFn: () => ledgerRequest<Notification[]>('/notification-runs'), enabled: enabled && activeTab === 'bot' })
  const queryError = activeTab === 'bot' ? bot.error || notifications.error : meters.error
  useEffect(() => { if (bot.data && !botForm.isFieldsTouched()) botForm.setFieldsValue(bot.data.definition) }, [bot.data, botForm])

  async function run(action: () => Promise<unknown>, text: string) {
    setBusy(true); setError('')
    try { await action(); await client.invalidateQueries({ queryKey: ['energy-ledger'] }); message.success(text) }
    catch (cause) { setError(cause instanceof Error ? cause.message : '操作未完成，请核对后重试') }
    finally { setBusy(false) }
  }

  if (!options) return <Skeleton active />
  if (!options.is_manager) return <PlatformNotice type="warning" title="需要能源配置管理操作权限" />
  return <>
    {(error || queryError) && <PlatformNotice type="error" title={error || queryError?.message} description="输入已保留，请核对错误后重试。" action={queryError ? <Button onClick={() => { if (activeTab === 'bot') { void bot.refetch(); void notifications.refetch() } else { void meters.refetch() } }}>重试</Button> : undefined} />}
    <Tabs activeKey={activeTab} onChange={key => { setActiveTab(key); setError('') }} items={[
      { key: 'bot', label: '飞书机器人', children: <>
        <PlatformNotice title="原始数据提交后，通过飞书通知提交人" description="通知附带对应日期和原表的填写入口。机器人应用使用能源模块独立凭据，个人消息使用企业人员标识。请先确认应用发消息权限、人员可达及 HTTPS 地址；密钥不会回传。" />
        <Form form={botForm} layout="vertical" onFinish={({ app_secret, ...definition }) => void run(() => resolveLedgerAction(saveLedgerBot({ definition, app_secret: app_secret || undefined, version: bot.data?.version || 0 })), '机器人配置已保存')}>
          <Button onClick={() => botForm.setFieldsValue(bot.data?.definition || { enabled: false })}>载入已保存配置</Button>
          <Form.Item name="app_id" label="能源应用 App ID"><Input autoComplete="off" /></Form.Item><Form.Item name="app_secret" label={bot.data?.secret_configured ? '应用密钥（已配置，留空保留）' : '应用密钥'}><Input.Password autoComplete="new-password" /></Form.Item><Form.Item name="base_url" label="平台 HTTPS 访问地址"><Input placeholder="https://平台域名" /></Form.Item><Form.Item name="enabled" label="启用机器人" valuePropName="checked"><Switch /></Form.Item><Button htmlType="submit" type="primary" loading={busy}>保存机器人配置</Button>
        </Form>
        <Table<Notification> rowKey="id" dataSource={notifications.data} columns={[{ title: '状态', dataIndex: 'status' }, { title: '尝试次数', dataIndex: 'attempts' }, { title: '处理提示', dataIndex: 'error' }, { title: '操作', render: (_, row) => <Button disabled={!['failed', 'retry'].includes(row.status)} onClick={() => void run(() => resolveLedgerAction(retryLedgerNotification(row.id)), '消息已加入重试队列')}>重试</Button> }]} />
      </> },
      { key: 'imports', label: 'Excel 导入', children: meters.isPending ? <Skeleton active /> : queryError ? null : <EnergyImportClient meters={meters.data ?? []} onChanged={() => client.invalidateQueries({ queryKey: ['energy-ledger'] })} /> },
      { key: 'reviews', label: '待确认复核', children: <EnergyReviewClient /> },
    ]} />
  </>
}
