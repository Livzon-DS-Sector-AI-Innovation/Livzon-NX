'use client'

import { useEffect, useState } from 'react'
import { App, Card, Input, Switch, Button, Select, Space, Tag, InputNumber, Typography, Upload } from 'antd'
import { SaveOutlined, ArrowLeftOutlined, PlusOutlined, CloseOutlined, UploadOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import { fetchReminderConfigs, fetchHrMembers, type ReminderConfigVM as ReminderConfig, type HrMemberVM } from '@/lib/api/client/hr'
import { updateReminderConfig, uploadOffboardingTemplateAction, fetchOffboardingTemplateInfoAction } from '@/actions/hr'
import DeptRecipientDrawer from './DeptRecipientDrawer'

export default function ReminderDetailClient({ params }: { params: Promise<{ entityCode: string }> }) {
  const { message } = App.useApp()
  const router = useRouter()
  const [configs, setConfigs] = useState<ReminderConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [hrMembers, setHrMembers] = useState<HrMemberVM[]>([])
  const [deptDrawerOpen, setDeptDrawerOpen] = useState(false)
  const [deptDrawerConfigId, setDeptDrawerConfigId] = useState('')
  const [deptDrawerMode, setDeptDrawerMode] = useState<'recipient' | 'clerk'>('recipient')

  const [entityCode, setEntityCode] = useState<string>('')
  const [templateInfo, setTemplateInfo] = useState<{ exists: boolean; filename: string | null; updated_at: string | null } | null>(null)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    (async () => {
      const { entityCode: ec } = await params
      setEntityCode(ec)
      setLoading(true)
      try {
        const [all, members] = await Promise.all([
          fetchReminderConfigs(),
          fetchHrMembers(),
        ])
        setConfigs(all.filter(c => c.entity_code === ec))
        setHrMembers(members)
        if (ec === 'offboarding') {
          const res = await fetchOffboardingTemplateInfoAction()
          setTemplateInfo(res.data)
        }
      } catch { message.error('加载失败') }
      finally { setLoading(false) }
    })()
  }, [params, message])

  const handleSave = async (config: ReminderConfig) => {
    setSaving(true)
    try {
      await updateReminderConfig(config.id, {
        reminder_days: config.reminder_days,
        recipient_open_ids: config.recipient_open_ids,
        dept_notify_enabled: config.dept_notify_enabled,
        trigger_frequency: config.trigger_frequency,
        trigger_day: config.trigger_day,
        trigger_hour: config.trigger_hour,
        notify_hours: config.notify_hours,
        message_template: config.message_template,
        sign_clerk_open_ids: config.sign_clerk_open_ids,
        sign_clerk_names: config.sign_clerk_names,
        sign_reminder_days: config.sign_reminder_days,
        is_enabled: config.is_enabled,
      })
      message.success(`${config.reminder_label} 保存成功`)
    } catch { message.error('保存失败') }
    finally { setSaving(false) }
  }

  const handleTemplateUpload = async (file: File) => {
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await uploadOffboardingTemplateAction(formData)
      message.success(res.message || '模板上传成功')
      setTemplateInfo({ exists: true, filename: file.name, updated_at: new Date().toISOString() })
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '上传失败')
    }
    finally { setUploading(false) }
    return false // 阻止 antd Upload 自动上传
  }

  const updateConfig = (id: string, field: keyof ReminderConfig, value: any) => {
    setConfigs(configs.map(c => c.id === id ? { ...c, [field]: value } : c))
  }

  const handleRecipientChange = (id: string, openIds: string[]) => {
    const names = hrMembers.filter(m => openIds.includes(m.open_id)).map(m => m.name)
    setConfigs(configs.map(c => c.id === id ? { ...c, recipient_open_ids: openIds, recipient_names: names } : c))
  }

  const handleClerkChange = (id: string, openIds: string[]) => {
    const names = hrMembers.filter(m => openIds.includes(m.open_id)).map(m => m.name)
    setConfigs(configs.map(c => c.id === id ? { ...c, sign_clerk_open_ids: openIds, sign_clerk_names: names } : c))
  }

  const hrMemberOptions = hrMembers.map(m => ({
    value: m.open_id,
    label: `${m.name}（${m.department}）`,
  }))

  return (
    <div className="space-y-4">
      <Space>
        <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/hr/settings/reminder')}>返回</Button>
        <h1 className="text-[22px] font-semibold">{configs[0]?.entity_label || '提醒配置'}</h1>
      </Space>

      {loading && <Card loading />}

      {/* 离职管理：模板上传区域 */}
      {entityCode === 'offboarding' && (
        <Card title="离职证明模板" size="small">
          <div className="space-y-3">
            <Typography.Text type="secondary">
              上传 .docx 格式的 Word 模板文件，使用 {'{{姓名}}'}、{'{{身份证号}}'}、{'{{入职日期}}'}、{'{{部门}}'}、{'{{岗位}}'}、{'{{离职日期}}'} 作为占位符
            </Typography.Text>
            <div>
              <Upload
                accept=".docx"
                maxCount={1}
                beforeUpload={handleTemplateUpload}
                showUploadList={false}
              >
                <Button icon={<UploadOutlined />} loading={uploading}>
                  {templateInfo?.exists ? '更新模板' : '上传模板'}
                </Button>
              </Upload>
            </div>
            {templateInfo?.exists && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                当前模板：{templateInfo.filename}（{templateInfo.updated_at ? new Date(templateInfo.updated_at).toLocaleString() : ''}）
              </Typography.Text>
            )}
          </div>
        </Card>
      )}

      {configs.map(config => (
        <Card key={config.id} title={
          <Space>
            <Typography.Text strong>{config.reminder_label}</Typography.Text>
            <Tag color={config.is_enabled ? 'green' : 'default'}>{config.is_enabled ? '已启用' : '未启用'}</Tag>
          </Space>
        }>
          <div className="space-y-4">
            {/* 通用设置 - 离职提醒不显示 */}
            {entityCode !== 'offboarding' && (
              <Card type="inner" title="通用设置" size="small">
                <div className="space-y-4">
                  <div>
                    <Typography.Text type="secondary">提醒天数</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Space wrap>
                        {config.reminder_days.map((day: number, idx: number) => (
                          <Space key={idx}>
                            <Space.Compact>
                              <InputNumber value={day} onChange={(v) => {
                                const next = [...config.reminder_days]
                                next[idx] = v ?? 30
                                updateConfig(config.id, 'reminder_days', next)
                              }} min={1} max={365} style={{ width: 90 }} />
                              <Button disabled style={{ cursor: 'default' }}>天</Button>
                            </Space.Compact>
                            {config.reminder_days.length > 1 && (
                              <Button icon={<CloseOutlined />} onClick={() => updateConfig(config.id, 'reminder_days', config.reminder_days.filter((_, i) => i !== idx))} size="small" />
                            )}
                          </Space>
                        ))}
                        <Button icon={<PlusOutlined />} onClick={() => updateConfig(config.id, 'reminder_days', [...config.reminder_days, 30])} size="small">添加</Button>
                      </Space>
                    </div>
                  </div>

                  {/* 自动触发频率配置 */}
                  <div>
                    <Typography.Text type="secondary">自动触发频率</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Space wrap>
                        <Select
                          value={config.trigger_frequency || 'monthly'}
                          onChange={(v) => updateConfig(config.id, 'trigger_frequency', v)}
                          options={[
                            { value: 'daily', label: '每天' },
                            { value: 'monthly', label: '每月' },
                            { value: 'quarterly', label: '每季度' },
                          ]}
                          style={{ width: 120 }}
                        />
                        {(config.trigger_frequency || 'monthly') !== 'daily' && (
                          <>
                            <span>每月第</span>
                            <Select
                              value={config.trigger_day || 1}
                              onChange={(v) => updateConfig(config.id, 'trigger_day', v)}
                              options={Array.from({ length: 28 }, (_, i) => ({ value: i + 1, label: `${i + 1}` }))}
                              style={{ width: 70 }}
                            />
                            <span>日</span>
                          </>
                        )}
                        <span>在</span>
                        <Select
                          value={config.trigger_hour ?? 9}
                          onChange={(v) => updateConfig(config.id, 'trigger_hour', v)}
                          options={Array.from({ length: 24 }, (_, i) => ({ value: i, label: `${String(i).padStart(2, '0')}:00` }))}
                          style={{ width: 90 }}
                        />
                        <span>触发</span>
                      </Space>
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* 离职管理专属：小时设置和消息模板 */}
            {entityCode === 'offboarding' && (
              <Card type="inner" title="离职提醒设置" size="small">
                <div className="space-y-4">
                  <div>
                    <Typography.Text type="secondary">提醒时间（离职记录创建后多少小时）</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Space>
                        <InputNumber
                          value={config.notify_hours ?? 24}
                          onChange={(v) => updateConfig(config.id, 'notify_hours', v ?? 24)}
                          min={1}
                          max={72}
                          style={{ width: 120 }}
                        />
                        <span>小时（最大 72 小时）</span>
                      </Space>
                    </div>
                  </div>

                  <div>
                    <Typography.Text type="secondary">每天几点检查提醒</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Space>
                        <Select
                          value={config.trigger_hour ?? 9}
                          onChange={(v) => updateConfig(config.id, 'trigger_hour', v)}
                          options={Array.from({ length: 24 }, (_, i) => ({ value: i, label: `${String(i).padStart(2, '0')}:00` }))}
                          style={{ width: 120 }}
                        />
                        <span>检查并发送提醒</span>
                      </Space>
                    </div>
                  </div>

                  <div>
                    <Typography.Text type="secondary">消息模板（支持变量：{'{姓名}'}、{'{工号}'}、{'{部门}'}、{'{离职日期}'}、{'{离职类型}'}）</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Input.TextArea
                        value={config.message_template || ''}
                        onChange={(e) => updateConfig(config.id, 'message_template', e.target.value)}
                        rows={6}
                        placeholder={`示例：
离职手续未办结提醒

员工：{姓名}
工号：{工号}
部门：{部门}
离职日期：{离职日期}
离职类型：{离职类型}

该员工离职手续尚未办结，请及时跟进。`}
                        style={{ fontFamily: 'monospace' }}
                      />
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* 合同续签专属：签署设置 */}
            {entityCode === 'contract_renewal' && (
              <Card type="inner" title="合同签署设置" size="small">
                <div className="space-y-4">
                  <div>
                    <Typography.Text type="secondary">签署催签间隔（审批通过后未签署，每隔多少天提醒办事员）</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Space>
                        <InputNumber
                          value={config.sign_reminder_days ?? 7}
                          onChange={(v) => updateConfig(config.id, 'sign_reminder_days', v ?? 7)}
                          min={1}
                          max={365}
                          style={{ width: 120 }}
                        />
                        <span>天（默认 7 天）</span>
                      </Space>
                    </div>
                  </div>
                  <div>
                    <Typography.Text type="secondary">签署办事员（审批通过后通知其安排员工到人事签署合同；未按部门配置时使用此处全局办事员，仍为空则回退 HR 通知人员）</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Select
                        mode="multiple"
                        showSearch
                        optionFilterProp="label"
                        placeholder="选择签署办事员（全局）"
                        value={config.sign_clerk_open_ids || []}
                        onChange={(v) => handleClerkChange(config.id, v)}
                        options={hrMemberOptions}
                        style={{ width: '100%' }}
                      />
                    </div>
                  </div>
                  <div>
                    <Typography.Text type="secondary">按部门配置办事员（每个部门可指定不同办事员，优先于全局办事员）</Typography.Text>
                    <div style={{ marginTop: 8 }}>
                      <Button
                        size="small"
                        onClick={() => { setDeptDrawerConfigId(config.id); setDeptDrawerMode('clerk'); setDeptDrawerOpen(true) }}
                      >
                        按部门配置办事员
                      </Button>
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* 区域 2 - 接收人设置 */}
            <Card type="inner" title="接收人设置" size="small">
              <div className="space-y-4">
                <div>
                  <Typography.Text type="secondary">HR 通知人员</Typography.Text>
                  <div style={{ marginTop: 8 }}>
                    <Select
                      mode="multiple"
                      showSearch
                      optionFilterProp="label"
                      placeholder="选择需要通知的 HR 人员"
                      value={config.recipient_open_ids}
                      onChange={(v) => handleRecipientChange(config.id, v)}
                      options={hrMemberOptions}
                      style={{ width: '100%' }}
                    />
                  </div>
                </div>

                {entityCode === 'contract_renewal' ? (
                  <div>
                    <Typography.Text type="secondary">
                      审批卡片自动按「审批流程设置」中配置的部门经理/部门总监发送（飞书内直接审批），此处无需单独设置。
                    </Typography.Text>
                  </div>
                ) : (
                  <div>
                    <Space>
                      <Switch checked={config.dept_notify_enabled} onChange={(v) => updateConfig(config.id, 'dept_notify_enabled', v)} />
                      <Typography.Text>通知部门负责人</Typography.Text>
                      <Button
                        size="small"
                        onClick={() => { setDeptDrawerConfigId(config.id); setDeptDrawerMode('recipient'); setDeptDrawerOpen(true) }}
                      >
                        配置部门接收人
                      </Button>
                    </Space>
                  </div>
                )}


              </div>
            </Card>

            <div>
              <Space><Switch checked={config.is_enabled} onChange={(v) => updateConfig(config.id, 'is_enabled', v)} /><Typography.Text>启用此提醒</Typography.Text></Space>
            </div>

            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => handleSave(config)}>保存</Button>
          </div>
        </Card>
      ))}

      <DeptRecipientDrawer
        open={deptDrawerOpen}
        onClose={() => setDeptDrawerOpen(false)}
        reminderConfigId={deptDrawerConfigId}
        hrMembers={hrMembers}
        mode={deptDrawerMode}
      />
    </div>
  )
}
