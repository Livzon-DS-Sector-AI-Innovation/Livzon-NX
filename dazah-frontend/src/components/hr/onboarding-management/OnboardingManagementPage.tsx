'use client'

import { useState, useMemo, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useForm, Controller } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { App, Card, Tag, Progress, Input, Button, Select, AutoComplete, Modal, Table, Space, DatePicker } from 'antd'
import { SearchOutlined, SaveOutlined, FileTextOutlined, EditOutlined, SyncOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  fetchOnboardingList,
  fetchOnboardingDashboard,
  fetchDepartments,
  fetchJobPostings,
} from '@/lib/api/client/hr'
import { updateOnboardingAction, syncOnboardingToEmployeeAction, syncOnboardingToContractAction } from '@/actions/hr'

interface OnboardingRecord {
  id: string
  name: string
  onboard_date?: string
  department?: string
  level?: string
  status?: string
  health_status?: string
  resignation_cert?: string
  id_card?: string
  education_cert?: string
  created_at?: string
  updated_at?: string
}

const STAGES = [
  { key: '待入职', label: '待入职', color: '#1677ff' },
  { key: '信息录入', label: '信息录入', color: '#722ed1' },
  { key: '体检', label: '体检', color: '#fa8c16' },
  { key: '材料登记', label: '材料登记', color: '#13c2c2' },
  { key: '完成', label: '完成', color: '#52c41a' },
  { key: '已放弃', label: '已放弃', color: '#d9d9d9' },
]

const MATERIALS = [
  { key: 'resignation_cert', label: '离职证明' },
  { key: 'id_card', label: '身份证信息' },
  { key: 'education_cert', label: '学历证明' },
]

const HEALTH_STATUS_OPTIONS = [
  { value: '未进行', label: '未进行' },
  { value: '合格', label: '合格' },
  { value: '不合格', label: '不合格' },
]

const MATERIAL_STATUS_OPTIONS = [
  { value: '已提供', label: '已提供' },
  { value: '未提供', label: '未提供' },
]

const ONBOARDING_STATUS_OPTIONS = [
  { value: '进行中', label: '进行中' },
  { value: '已完成', label: '已完成' },
  { value: '已放弃', label: '已放弃' },
]

function getStage(record: OnboardingRecord | null): string {
  if (!record) return '待入职'
  if (record.status === '已完成') return '完成'
  if (record.status === '已放弃') return '已放弃'
  if (record.status === '进行中' || !record.status) {
    if (!record.onboard_date) return '待入职'
    const h = record.health_status || '未进行'
    const mats = [record.resignation_cert, record.id_card, record.education_cert]
    if (h === '未进行') return '信息录入'
    if (h === '合格' && mats.every((m) => m === '已提供')) return '材料登记'
    return '体检'
  }
  return '待入职'
}

const stageColor: Record<string, string> = { 待入职: 'blue', 信息录入: 'purple', 体检: 'orange', 材料登记: 'cyan', 完成: 'green', 已放弃: 'default' }

function getProgress(stage: string): number {
  if (stage === '完成') return 100
  if (stage === '材料登记') return 75
  if (stage === '体检') return 50
  if (stage === '信息录入') return 25
  return 0
}

const onboardingFormSchema = z.object({
  onboard_date: z.string().optional(),
  department: z.string().optional(),
  level: z.string().optional(),
  status: z.string().optional(),
  health_status: z.string().optional(),
  resignation_cert: z.string().optional(),
  id_card: z.string().optional(),
  education_cert: z.string().optional(),
})

type OnboardingFormData = z.infer<typeof onboardingFormSchema>

export default function OnboardingManagementPage() {
  const { message } = App.useApp()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [stageModalOpen, setStageModalOpen] = useState(false)
  const [currentStage, setCurrentStage] = useState<string | null>(null)
  const [filterStage, setFilterStage] = useState<string | null>(null) // 阶段筛选
  const [syncing, setSyncing] = useState(false)
  const [syncLoading, setSyncLoading] = useState(false)

  const form = useForm<OnboardingFormData>({
    resolver: zodResolver(onboardingFormSchema),
  })

  const { data: listData, isLoading, refetch } = useQuery({
    queryKey: ['onboarding-list', page, pageSize, keyword],
    queryFn: () => fetchOnboardingList({ keyword: keyword || undefined, page, page_size: pageSize }),
    refetchInterval: 15000,
  })

  useQuery({
    queryKey: ['onboarding-dashboard'],
    queryFn: fetchOnboardingDashboard,
    refetchInterval: 30000,
  })

  // 动态加载部门列表（来自部门管理）
  const { data: deptData } = useQuery({
    queryKey: ['hr-departments'],
    queryFn: () => fetchDepartments({ page_size: 200 }),
  })
  const departmentOptions = useMemo(() => {
    const list = deptData?.data || []
    return list.map((d: any) => ({ value: d.name, label: d.name }))
  }, [deptData])

  // 动态加载招聘职位列表（来自招聘管理）
  const { data: jobData } = useQuery({
    queryKey: ['hr-job-postings'],
    queryFn: () => fetchJobPostings({ page_size: 200 }),
  })
  const positionOptions = useMemo(() => {
    const list = jobData?.data || []
    return list.map((j: any) => ({ value: j.title, label: j.title }))
  }, [jobData])

  const records = useMemo<OnboardingRecord[]>(() => listData?.data || [], [listData?.data])
  const total = listData?.meta?.total ?? 0

  // 根据阶段筛选记录
  const filteredRecords = useMemo(() => {
    if (!filterStage) {
      // 默认只显示进行中的记录
      return records.filter(r => {
        const stage = getStage(r)
        return stage !== '完成' && stage !== '已放弃'
      })
    }
    return records.filter(r => getStage(r) === filterStage)
  }, [records, filterStage])

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = { 待入职: 0, 信息录入: 0, 体检: 0, 材料登记: 0, 完成: 0, 已放弃: 0 }
    records.forEach((r) => {
      const s = getStage(r)
      if (counts[s] !== undefined) counts[s]++
    })
    return counts
  }, [records])

  // 当前阶段弹窗中的记录
  const stageRecords = useMemo(() => {
    if (!currentStage) return []
    return records.filter(r => getStage(r) === currentStage)
  }, [records, currentStage])

  const selectedRecord = useMemo(() => records.find(r => r.id === selectedId) || null, [records, selectedId])

  const handleSelect = useCallback((record: OnboardingRecord) => {
    setSelectedId(record.id)
    form.reset({
      onboard_date: record.onboard_date || '',
      department: record.department || '',
      level: record.level || '',
      status: record.status || '进行中',
      health_status: record.health_status || '未进行',
      resignation_cert: record.resignation_cert || '未提供',
      id_card: record.id_card || '未提供',
      education_cert: record.education_cert || '未提供',
    })
  }, [form])

  // 点击阶段卡片，筛选下面的列表
  const handleStageClick = useCallback((stageKey: string) => {
    setCurrentStage(stageKey)
    setStageModalOpen(true)
    setFilterStage(stageKey)
  }, [])

  // 清除阶段筛选
  const handleClearFilter = useCallback(() => {
    setFilterStage(null)
  }, [])

  // 手动同步（已移除 PG 同步，数据直接来自飞书）
  const handleSync = useCallback(async () => {
    try {
      setSyncing(true)
      // 飞书数据直接通过 fetchOnboardingList 获取，无需额外同步
      await refetch()
      message.success('数据已刷新')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '刷新失败')
    } finally {
      setSyncing(false)
    }
  }, [message, refetch])

  const handleSaveBasic = form.handleSubmit(async (data) => {
    if (!selectedId) return
    setSaving(true)
    try {
      await updateOnboardingAction(selectedId, {
        onboard_date: data.onboard_date,
        department: data.department,
        level: data.level,
        status: data.status,
        health_status: data.health_status,
        resignation_cert: data.resignation_cert,
        id_card: data.id_card,
        education_cert: data.education_cert,
      })
      message.success('保存成功')
      refetch()
    } catch (err) { message.error((err instanceof Error ? err.message : '') || '保存失败') }
    finally { setSaving(false) }
  })

  // 同步到员工档案
  const handleSyncToEmployee = useCallback(async () => {
    if (!selectedRecord) return
    if (!confirm(`确认将 ${selectedRecord.name} 同步到员工档案和合同管理？`)) return
    setSyncLoading(true)
    try {
      const result = await syncOnboardingToEmployeeAction(selectedRecord.id)
      message.success(result.message || '同步成功')
      refetch()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '同步失败')
    } finally {
      setSyncLoading(false)
    }
  }, [selectedRecord, message, refetch])

  // 同步到合同管理
  const handleSyncToContract = useCallback(async () => {
    if (!selectedRecord) return
    if (!confirm(`确认将 ${selectedRecord.name} 同步到合同管理？`)) return
    setSyncLoading(true)
    try {
      const result = await syncOnboardingToContractAction(
        selectedRecord.name,
        selectedRecord.department,
        selectedRecord.level,
      )
      message.success(result.message || '同步成功')
      refetch()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '同步失败')
    } finally {
      setSyncLoading(false)
    }
  }, [selectedRecord, message, refetch])

  // 阶段弹窗中的表格列
  const stageTableColumns = [
    { title: '姓名', dataIndex: 'name', key: 'name', width: 100 },
    { title: '岗位', dataIndex: 'level', key: 'level', width: 150 },
    { title: '部门', dataIndex: 'department', key: 'department', width: 100 },
    { title: '入职日期', dataIndex: 'onboard_date', key: 'onboard_date', width: 120 },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: OnboardingRecord) => (
        <Button
          size="small"
          icon={<EditOutlined />}
          onClick={() => {
            handleSelect(record)
            setStageModalOpen(false)
          }}
        >
          编辑
        </Button>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">入职管理</h1>
        <Space>
          <span className="text-sm text-gray-400">面试状态为「通过」的候选人可流转至入职</span>
          <Button
            icon={<SyncOutlined />}
            loading={syncing}
            onClick={handleSync}
          >
            刷新数据
          </Button>
        </Space>
      </div>

      {/* Stage Count Kanban - 一行6个 */}
      <div className="grid grid-cols-6 gap-3">
        {STAGES.map((stage) => (
          <Card
            key={stage.key}
            size="small"
            styles={{ body: { padding: '16px', textAlign: 'center' } }}
            className={`cursor-pointer hover:shadow-md transition-shadow ${filterStage === stage.key ? 'ring-2 ring-[#2f6bff]' : ''}`}
            onClick={() => handleStageClick(stage.key)}
          >
            <div className="text-sm text-gray-500 mb-2">{stage.label}</div>
            <div className="text-3xl font-bold" style={{ color: stage.color }}>{stageCounts[stage.key] ?? 0}</div>
          </Card>
        ))}
      </div>

      {/* 阶段详情弹窗 */}
      <Modal
        title={`${currentStage || ''} - 入职记录列表`}
        open={stageModalOpen}
        onCancel={() => setStageModalOpen(false)}
        width={800}
        footer={null}
      >
        <Table
          rowKey="id"
          columns={stageTableColumns}
          dataSource={stageRecords}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无记录' }}
        />
      </Modal>

      <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 460px' }}>
        {/* ─── Left: Card Kanban ─── */}
        <div>
          <div className="flex items-center gap-3 mb-3">
            <Input
              placeholder="搜索姓名"
              value={keyword}
              onChange={(e) => { setKeyword(e.target.value); setPage(1) }}
              prefix={<SearchOutlined />}
              className="w-48"
              allowClear
            />
            {filterStage && (
              <Tag
                color="blue"
                closable
                onClose={handleClearFilter}
                className="cursor-pointer"
              >
                筛选：{filterStage}
              </Tag>
            )}
            <span className="text-xs text-gray-400">
              共 {total} 人，显示 {filteredRecords.length} 条
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2" style={{ maxHeight: '65vh', overflow: 'auto' }}>
            {filteredRecords.map((record) => {
              const stage = getStage(record)
              const pct = getProgress(stage)
              const mats = [record.resignation_cert, record.id_card, record.education_cert]
              const matDone = mats.filter((m) => m === '已提供').length
              const sel = record.id === selectedId
              return (
                <Card
                  key={record.id}
                  size="small"
                  hoverable
                  onClick={() => handleSelect(record)}
                  className={`cursor-pointer transition-all ${sel ? 'ring-2 ring-[#2f6bff] bg-[#eaf1ff]' : ''}`}
                  styles={{ body: { padding: '10px' } }}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-semibold text-xs">{record.name || '-'}</span>
                    <Tag color={stageColor[stage] || 'default'} style={{ fontSize: 10, margin: 0, lineHeight: '18px' }}>{stage}</Tag>
                  </div>
                  <div className="text-[10px] text-gray-400 mb-1 truncate">
                    {record.level || '-'} · {record.department || '-'}
                  </div>
                  <Progress
                    percent={pct}
                    size="small"
                    strokeColor={STAGES.find(s => s.key === stage)?.color}
                  />
                  <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
                    <span>{record.onboard_date || '待定'}</span>
                    <span>材料 {matDone}/3</span>
                  </div>
                </Card>
              )
            })}
            {filteredRecords.length === 0 && !isLoading && (
              <div className="col-span-2 text-center text-gray-400 py-12">
                {filterStage ? `暂无${filterStage}的记录` : '暂无进行中的入职记录'}
              </div>
            )}
          </div>
        </div>

        {/* ─── Right: Detail Panel ─── */}
        <Card size="small" title="入职进度详情" styles={{ body: { padding: '16px' } }}>
          {selectedRecord ? (
            <div className="space-y-4">
              {/* Basic Info Form */}
              <div>
                <div className="text-sm font-semibold mb-2">基本信息</div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-gray-400">姓名</label>
                    <Input size="small" value={selectedRecord.name || ''} disabled className="text-sm" />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">入职日期</label>
                    <Controller name="onboard_date" control={form.control} render={({ field }) => (
                      <DatePicker
                        size="small"
                        style={{ width: '100%' }}
                        value={field.value ? dayjs(field.value) : null}
                        onChange={(d) => field.onChange(d ? d.format('YYYY-MM-DD') : '')}
                      />
                    )} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">入职部门</label>
                    <Controller name="department" control={form.control} render={({ field }) => (
                      <Select
                        size="small"
                        {...field}
                        style={{ width: '100%' }}
                        showSearch
                        allowClear
                        placeholder="选择或输入部门"
                        options={departmentOptions}
                        filterOption={(input, option) =>
                          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                        }
                      />
                    )} />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400">岗位</label>
                    <Controller name="level" control={form.control} render={({ field }) => (
                      <AutoComplete
                        size="small"
                        {...field}
                        style={{ width: '100%' }}
                        allowClear
                        placeholder="选择或输入岗位"
                        options={positionOptions}
                        filterOption={(input, option) =>
                          (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                        }
                      />
                    )} />
                  </div>
                </div>
              </div>

              {/* Onboarding Status & Health Status - 两项一行 */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-sm font-semibold mb-2">入职状态</div>
                  <Controller name="status" control={form.control} render={({ field }) => (
                    <Select
                      size="small"
                      value={field.value || '进行中'}
                      style={{ width: '100%' }}
                      onChange={(v) => field.onChange(v)}
                      options={ONBOARDING_STATUS_OPTIONS}
                    />
                  )} />
                </div>
                <div>
                  <div className="text-sm font-semibold mb-2">体检状态</div>
                  <Controller name="health_status" control={form.control} render={({ field }) => (
                    <Select
                      size="small"
                      value={field.value || '未进行'}
                      style={{ width: '100%' }}
                      onChange={(v) => field.onChange(v)}
                      options={HEALTH_STATUS_OPTIONS}
                    />
                  )} />
                </div>
              </div>

              {/* Materials - 三项一行 */}
              <div>
                <div className="text-sm font-semibold mb-2">材料登记</div>
                <div className="grid grid-cols-3 gap-2">
                  {MATERIALS.map((mt) => (
                    <div key={mt.key}>
                      <label className="text-xs text-gray-400 block mb-1">{mt.label}</label>
                      <Controller name={mt.key as keyof OnboardingFormData} control={form.control} render={({ field }) => (
                        <Select
                          size="small"
                          value={field.value || '未提供'}
                          style={{ width: '100%' }}
                          onChange={(v) => field.onChange(v)}
                          options={MATERIAL_STATUS_OPTIONS}
                        />
                      )} />
                    </div>
                  ))}
                </div>
              </div>

              {/* Overall Progress */}
              <div>
                <div className="text-sm text-gray-500 mb-1">总体进度</div>
                <Progress percent={getProgress(getStage(selectedRecord))} strokeColor={STAGES.find(s => s.key === getStage(selectedRecord))?.color} />
              </div>

              <Button type="primary" size="small" icon={<SaveOutlined />} loading={saving} onClick={handleSaveBasic} block>保存</Button>
              {getStage(selectedRecord) === '完成' && (
                <div className="space-y-2" style={{ marginTop: 8 }}>
                  <Button size="small" icon={<FileTextOutlined />} onClick={handleSyncToContract} loading={syncLoading} block>同步到合同管理</Button>
                  <Button size="small" icon={<FileTextOutlined />} onClick={handleSyncToEmployee} loading={syncLoading} block>同步到员工档案</Button>
                </div>
              )}
            </div>
          ) : (
            <div className="text-sm text-gray-400 py-12 text-center">
              点击左侧卡片查看入职进度
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
