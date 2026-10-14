'use client'

import { useRef, useState } from 'react'
import { usePathname } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { App, Badge, Button, DatePicker, Drawer, Empty, Form, Image, Input, Modal, Pagination, Select, Spin, Tabs, Tag, Upload } from 'antd'
import type { UploadFile } from 'antd'
import { CommentOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { processFeedback, submitFeedback } from '@/actions/feedback'
import { feedbackPath, fetchFeedback, type Feedback, type FeedbackStatus } from '@/lib/api/feedback'
import { isSystemAdministrator } from '@/lib/administrator-role'
import type { User } from '@/types/user'
import PlatformNotice from '@/components/shared/PlatformNotice'

const statusNames: Record<FeedbackStatus, string> = { pending: '待处理', processing: '处理中', resolved: '已解决' }
const statusOptions = Object.entries(statusNames).map(([value, label]) => ({ value, label }))

function FeedbackForm({ pagePath, onSuccess }: { pagePath: string; onSuccess: () => void }) {
  const { message } = App.useApp()
  const [form] = Form.useForm<{ description: string; occurred_at: Dayjs }>()
  const [files, setFiles] = useState<UploadFile[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const feedbackId = useRef<string | null>(null)
  const submit = async (values: { description: string; occurred_at: Dayjs }) => {
    if (files.length === 0) { setError('请上传至少一张问题截图'); return }
    setSubmitting(true)
    setError('')
    const body = new FormData()
    feedbackId.current ||= crypto.randomUUID()
    body.set('feedback_id', feedbackId.current)
    body.set('description', values.description.trim())
    body.set('occurred_at', values.occurred_at.toISOString())
    body.set('page_path', pagePath)
    for (const file of files) {
      if (file.originFileObj) body.append('screenshots', file.originFileObj)
    }
    try {
      const result = await submitFeedback(body)
      if (!result.success) { setError(result.error); return }
      message.success('反馈已提交，系统管理员可在反馈收件箱查看')
      form.resetFields()
      setFiles([])
      feedbackId.current = null
      onSuccess()
    } catch {
      setError('提交未完成，填写内容已保留，请稍后重试')
    } finally { setSubmitting(false) }
  }
  return <div className="space-y-4">
    <PlatformNotice title="请填写问题描述、发生时间，并上传问题截图。"
      description="描述应包含操作步骤、预期结果和实际结果。截图支持 PNG、JPEG、WebP，最多 3 张，每张不超过 2MB；请先遮盖密码、密钥等敏感信息。反馈及截图仅本人和系统管理员可见。" />
    {error && <PlatformNotice type="error" title={error} description="填写内容尚未清空，请检查后重试；重复重试使用同一反馈编号。" />}
    <Form form={form} layout="vertical" onFinish={submit} disabled={submitting}>
      <Form.Item name="description" label="问题描述" rules={[{ required: true, whitespace: true, message: '请填写问题描述' }, { validator: (_, value: string) => value?.trim().length >= 10 && value.trim().length <= 5000 ? Promise.resolve() : Promise.reject(new Error('请填写 10–5000 字的问题描述')) }]}>
        <Input.TextArea rows={5} maxLength={5000} showCount placeholder="在哪个页面进行了什么操作？预期是什么，实际发生了什么？" />
      </Form.Item>
      <Form.Item name="occurred_at" label="发生时间" rules={[{ required: true, message: '请选择问题发生时间' }, { validator: (_, value: Dayjs | undefined) => !value || value.valueOf() <= Date.now() ? Promise.resolve() : Promise.reject(new Error('发生时间不能晚于当前时间')) }]}>
        <DatePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: '100%' }} placeholder="请选择问题发生时间" disabledDate={(date) => date.isAfter(dayjs(), 'day')} />
      </Form.Item>
      <Form.Item label="问题截图" required extra="1–3 张，PNG / JPEG / WebP，每张不超过 2MB。">
        <Upload accept="image/png,image/jpeg,image/webp" multiple maxCount={3} fileList={files}
          beforeUpload={(file) => {
            if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
              message.error('截图格式不支持或超过 2MB'); return Upload.LIST_IGNORE
            }
            return false
          }} onChange={({ fileList }) => setFiles(fileList)}>
          <Button icon={<UploadOutlined />}>选择截图</Button>
        </Upload>
      </Form.Item>
      <p className="text-xs text-[var(--color-steel)] mb-4">发生页面：{pagePath}</p>
      <Button type="primary" htmlType="submit" loading={submitting}>提交反馈</Button>
    </Form>
  </div>
}

function FeedbackInbox({ user, admin, active }: { user: User; admin: boolean; active: boolean }) {
  const client = useQueryClient()
  const { message } = App.useApp()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<FeedbackStatus>()
  const [selected, setSelected] = useState<Feedback | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const query = useQuery({
    queryKey: ['feedback', user.id, user.grant_version, admin, status, page],
    queryFn: ({ signal }) => fetchFeedback(admin, page, status, signal), retry: false,
    enabled: active, refetchInterval: active ? 60_000 : false,
  })
  const openDetail = (item: Feedback) => {
    setSelected(item); setError('')
  }
  const save = async (values: { status: FeedbackStatus; reply: string }) => {
    if (!selected) return
    setSaving(true); setError('')
    try {
      const result = await processFeedback(selected.id, { ...values, version: selected.version })
      if (!result.success) { setError(result.error); return }
      setSelected(result.data)
      message.success('反馈处理结果已保存，提交者可查看回复')
      await client.invalidateQueries({ queryKey: ['feedback'] })
    } catch { setError('处理结果未保存，请稍后重试') }
    finally { setSaving(false) }
  }
  return <div className="space-y-4">
    <div className="flex items-center gap-2 justify-between">
      <Select aria-label="反馈状态" allowClear placeholder="全部状态" value={status} options={statusOptions} style={{ width: 140 }}
        onChange={(value: FeedbackStatus | undefined) => { setStatus(value); setPage(1) }} />
      <Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => void query.refetch()}>刷新</Button>
    </div>
    {query.isPending ? <Spin aria-label="正在读取反馈" /> : query.isError ? <PlatformNotice type="error" title={query.error.message}
      action={<Button onClick={() => void query.refetch()}>重试</Button>} /> : <>
      {query.data.items.length === 0 && <Empty description="暂无反馈" />}
      <ul className="space-y-3">{query.data.items.map((item) => <li key={item.id}>
        <button type="button" className="w-full rounded-[var(--rounded-lg)] bg-[var(--color-surface)] p-4 text-left focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]" onClick={() => openDetail(item)}>
          <div className="flex justify-between gap-2"><span>{admin ? item.reporter_name : '我的反馈'}</span><Tag>{statusNames[item.status]}</Tag></div>
          <p className="line-clamp-2 my-2 text-sm whitespace-pre-wrap break-words">{item.description}</p>
          <span className="text-xs text-[var(--color-steel)]">发生时间：{dayjs(item.occurred_at).format('YYYY-MM-DD HH:mm')} · {item.screenshots.length} 张截图</span>
          {item.reply && <p className="text-sm mt-2 line-clamp-2">管理员回复：{item.reply}</p>}
        </button>
      </li>)}</ul>
      <Pagination current={page} total={query.data.total} pageSize={10} showSizeChanger={false} onChange={setPage} size="small" />
    </>}
    <Modal title="反馈详情" open={Boolean(selected)} onCancel={() => { if (!saving) setSelected(null) }} width={640} footer={null} destroyOnHidden>
      {selected && <div className="space-y-4 max-h-[70vh] overflow-y-auto">
        <p>提交者：{selected.reporter_name} · {statusNames[selected.status]}</p>
        <p>发生时间：{dayjs(selected.occurred_at).format('YYYY-MM-DD HH:mm')}</p>
        <p>提交时间：{dayjs(selected.created_at).format('YYYY-MM-DD HH:mm')}</p>
        <p className="break-all">发生页面：{selected.page_path || '未记录'}</p>
        <p className="whitespace-pre-wrap break-words">{selected.description}</p>
        <div className="flex flex-wrap gap-2"><Image.PreviewGroup>{selected.screenshots.map((image, index) => <Image key={image.id} width={140}
          alt={`问题截图 ${index + 1}`} src={`${feedbackPath(admin)}/${selected.id}/screenshots/${image.id}`} />)}</Image.PreviewGroup></div>
        {error && <PlatformNotice type="error" title={error} action={<Button onClick={() => { setSelected(null); void query.refetch() }}>刷新列表</Button>} />}
        {admin ? <Form key={selected.id} initialValues={{ status: selected.status, reply: selected.reply }} layout="vertical" onFinish={save} disabled={saving}>
          <Form.Item name="status" label="处理状态" rules={[{ required: true }]}><Select options={statusOptions} /></Form.Item>
          <Form.Item name="reply" label="管理员回复／处理结果" dependencies={['status']} rules={[{ max: 2000 }, ({ getFieldValue }) => ({ validator: (_, value: string) => getFieldValue('status') !== 'resolved' || value?.trim() ? Promise.resolve() : Promise.reject(new Error('处理完成时请填写处理结果')) })]}>
            <Input.TextArea rows={3} maxLength={2000} placeholder="说明处理进展或解决办法，提交者可以看到回复" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saving}>保存处理结果</Button>
        </Form> : <p className="whitespace-pre-wrap">管理员回复：{selected.reply || '暂未回复'}</p>}
      </div>}
    </Modal>
  </div>
}

export function FeedbackEntry({ user, ready = true }: { user: User; ready?: boolean }) {
  const pathname = usePathname()
  const [pagePath, setPagePath] = useState(pathname)
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState('submit')
  const admin = isSystemAdministrator(user)
  const activeTab = admin ? 'admin' : tab === 'mine' ? 'mine' : 'submit'
  const client = useQueryClient()
  const inbox = useQuery({
    queryKey: ['feedback', user.id, user.grant_version, 'pending-count'],
    queryFn: ({ signal }) => fetchFeedback(true, 1, 'pending', signal),
    enabled: admin, staleTime: 30_000, refetchInterval: admin ? 60_000 : false, retry: false,
  })
  return <>
    <Badge count={admin && !inbox.isError ? inbox.data?.pending_count : undefined} size="small" overflowCount={99}>
      <Button type="text" disabled={!ready} icon={<CommentOutlined />} onClick={() => { if (!open) setPagePath(pathname); setOpen(true) }} aria-label="问题反馈">反馈</Button>
    </Badge>
    <Drawer title="问题反馈" open={open} onClose={() => setOpen(false)} size={560} styles={{ wrapper: { maxWidth: '100vw' } }}>
      <Tabs activeKey={activeTab} onChange={setTab} items={admin ? [
        { key: 'admin', label: '收件箱', children: <FeedbackInbox key={`admin-${user.id}`} user={user} admin active={open} /> },
      ] : [
        { key: 'submit', label: '提交反馈', children: <FeedbackForm pagePath={pagePath} onSuccess={() => { setTab('mine'); void client.invalidateQueries({ queryKey: ['feedback'] }) }} /> },
        { key: 'mine', label: '我的反馈', children: <FeedbackInbox key={`mine-${user.id}`} user={user} admin={false} active={open && activeTab === 'mine'} /> },
      ]} />
    </Drawer>
  </>
}
