'use client'

import { useEffect, useState, useCallback, useMemo } from 'react'
import {
  App, Card, Button, Space, Table, Tabs, Tag, Typography, Select, Input,
  Popconfirm, Result, Modal, Tooltip,
} from 'antd'
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { usePermission } from '@/hooks/usePermission'
import {
  fetchFeishuMemberDepartments,
  fetchTrainingDepartments,
  type DeptMappingItem,
} from '@/lib/api/client/hr'
import {
  createTrainingDeptMappingAction,
  updateTrainingDeptMappingAction,
  deleteTrainingDeptMappingAction,
  type TrainingDeptMappingCreateInput,
  type TrainingDeptMappingUpdateInput,
} from '@/actions/hr'
import PersonDeptMappingClient from './PersonDeptMappingClient'
import {
  refreshDeptMappings,
  ensureDeptMappings,
  resolveTrainingDept,
  unifyDept,
  getModalRules,
  useDeptMappings,
} from './trainingDept'

/** 数据列（各培训页面），签到表列显示打印统一名，其余显示解析名 */
const PAGE_COLS = [
  { key: 'signin', title: '培训资料/签到表' },
  { key: 'ledger', title: '培训台账' },
  { key: 'annual', title: '年度培训计划' },
  { key: 'trainer', title: '培训师管理' },
  { key: 'position', title: '岗位培训清单' },
  { key: 'tracking', title: '培训计划跟踪' },
  { key: 'newemp', title: '新员工培训' },
  { key: 'emplist', title: '员工培训清单' },
] as const

/** 人员配置弹窗列下拉选项（3.A） */
const MODAL_OPTIONS = [
  { value: 'normal', label: '正常' },
  { value: 'drop', label: '不参与' },
  { value: 'no_expand', label: '不展开' },
  { value: 'extra', label: '额外补行' },
]

interface RowVM {
  source: string
  resolved: string
  printName: string
  modalStatus: 'normal' | 'drop' | 'no_expand' | 'extra'
  color: string
  hasRule: boolean
}

interface FormValues {
  source_name: string
  target_name?: string
  match_level: 'first' | 'second' | 'both'
  mapping_type: string
  priority: number
  enabled: boolean
  remark?: string
}

/**
 * 培训部门映射对照表（HR 设置，主界面）。
 *
 * 行 = 源部门（飞书联系人 + 映射源），列 = 各培训页面显示名 + 人员配置弹窗。
 * 点击数据格编辑该行统一目标（2.A 改一格=改整行）；弹窗列用下拉（3.A）。
 * 底层仍写入 training_dept_mappings 配置表，前后端解析共用。
 */
export default function DeptMappingSettingsClient() {
  const { has } = usePermission()
  const { message } = App.useApp()
  const { version } = useDeptMappings()

  const [mappings, setMappings] = useState<DeptMappingItem[]>([])
  const [feishuDepts, setFeishuDepts] = useState<string[]>([])
  const [trainingDepts, setTrainingDepts] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingSource, setEditingSource] = useState<string | null>(null)
  const [newSource, setNewSource] = useState('')
  const [dataTarget, setDataTarget] = useState('')
  const [signinTarget, setSigninTarget] = useState('')

  const forbidden = !has('hr:write')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [m, fd, td] = await Promise.all([
        ensureDeptMappings(),
        fetchFeishuMemberDepartments().then((r) => r.data || []).catch(() => [] as string[]),
        fetchTrainingDepartments().catch(() => [] as string[]),
      ])
      setMappings(m || [])
      setFeishuDepts(fd)
      setTrainingDepts(td)
    } catch (e) {
      message.error(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(loadData)
  }, [loadData, version])

  const modalRules = useMemo(() => getModalRules(), [version, mappings])

  // 行 = 飞书部门 ∪ 映射源（去重、过滤伪部门、排序）
  const rows: RowVM[] = useMemo(() => {
    const sources = new Set<string>(feishuDepts)
    for (const m of mappings) sources.add(m.source_name)
    // 过滤伪部门：冻结用户桶 / 公司 / 公司级 / exclude 类型源，均非真实部门
    const isPseudo = (s: string) =>
      s.startsWith('冻结用户') || s === '公司' || s === '公司级' ||
      mappings.some((m) => m.source_name === s && m.mapping_type === 'exclude')
    const list = [...sources].filter((s) => !isPseudo(s)).sort((a, b) => a.localeCompare(b, 'zh'))
    return list.map((source) => {
      const resolved = resolveTrainingDept(source, undefined, trainingDepts) || source
      const printName = unifyDept(resolved) || resolved
      const modalStatus: RowVM['modalStatus'] = modalRules.drop.has(source)
        ? 'drop'
        : modalRules.noExpand.has(source)
          ? 'no_expand'
          : modalRules.extra.includes(source)
            ? 'extra'
            : 'normal'
      const rule = mappings.find(
        (m) => m.source_name === source && (m.mapping_type === 'special' || m.mapping_type === 'alias'),
      )
      let color = '#f5f5f5' // 直通灰
      if (rule) {
        if (rule.mapping_type === 'special' && rule.match_level === 'both') color = '#f6ffed' // 201归一绿
        else if (rule.mapping_type === 'special') color = '#fff2e8' // 特殊橙
        else if (source.startsWith('仓储部')) color = '#e6f4ff' // 仓储蓝
        else color = '#fffbe6' // 别名黄
      }
      return { source, resolved, printName, modalStatus, color, hasRule: !!rule }
    })
  }, [feishuDepts, mappings, trainingDepts, modalRules])

  // 弹窗下拉选项：培训部门 + 当前行已用值，供选择目标部门
  const deptOptions = useMemo(() => {
    const set = new Set<string>(trainingDepts)
    rows.forEach((r) => { set.add(r.resolved); set.add(r.printName) })
    if (dataTarget) set.add(dataTarget)
    if (signinTarget) set.add(signinTarget)
    return [...set].filter(Boolean).sort((a, b) => a.localeCompare(b, 'zh')).map((d) => ({ value: d, label: d }))
  }, [trainingDepts, rows, dataTarget, signinTarget])

  if (forbidden) {
    return (
      <Result
        status="403"
        title="无权限访问"
        subTitle="只有具备 hr:write 权限的管理员可以维护培训部门映射"
      />
    )
  }

  // ── 规则 upsert / remove 辅助（通过 Server Actions）──
  const findRule = (source: string, type: string) =>
    mappings.find((m) => m.source_name === source && m.mapping_type === type)

  const upsertRule = async (
    source: string,
    type: TrainingDeptMappingCreateInput['mapping_type'],
    target: string | null,
    matchLevel: 'first' | 'second' | 'both' = 'first',
    priority = 100,
  ) => {
    const existing = findRule(source, type)
    const payload: TrainingDeptMappingCreateInput = {
      source_name: source,
      target_name: target,
      mapping_type: type,
      match_level: matchLevel,
      priority,
      enabled: true,
    }
    if (existing) {
      const updatePayload: TrainingDeptMappingUpdateInput = {
        target_name: target,
        match_level: matchLevel,
        priority,
        enabled: true,
      }
      await updateTrainingDeptMappingAction(existing.id, updatePayload)
    } else {
      await createTrainingDeptMappingAction(payload)
    }
  }

  const removeRule = async (source: string, type: string) => {
    const existing = findRule(source, type)
    if (existing) await deleteTrainingDeptMappingAction(existing.id)
  }

  const afterMutate = async () => {
    await refreshDeptMappings().catch(() => {})
    await loadData()
  }

  // ── 统一编辑按钮：打开“按页编辑”弹窗（大白话，无技术字段）──
  const openEdit = (row: RowVM) => {
    setEditingSource(row.source)
    setNewSource('')
    setDataTarget(row.resolved || '')
    setSigninTarget(row.printName || '')
    setModalOpen(true)
  }

  const openNew = () => {
    setEditingSource(null)
    setNewSource('')
    setDataTarget('')
    setSigninTarget('')
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const source = (editingSource ?? newSource).trim()
    if (!source) {
      message.error('请填写飞书源部门名')
      return
    }
    setSaving(true)
    try {
      const dt = dataTarget.trim()
      const st = signinTarget.trim()
      // 7 个数据页（台账/年度计划/培训师/岗位清单/计划跟踪/新员工/员工清单）共用一个部门
      await removeRule(source, 'alias')
      await removeRule(source, 'special')
      if (dt && dt !== source) await upsertRule(source, 'alias', dt, 'first', 100)
      // 签到表/通知/考核 打印显示名（可与数据页不同）
      await removeRule(source, 'print_unify')
      if (st && st !== dt) await upsertRule(source, 'print_unify', st)
      message.success(`已保存「${source}」的部门映射`)
      setModalOpen(false)
      await afterMutate()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // ── 弹窗列下拉（3.A）──
  const handleModalChange = async (row: RowVM, value: string) => {
    try {
      await removeRule(row.source, 'modal_drop')
      await removeRule(row.source, 'modal_no_expand')
      await removeRule(row.source, 'modal_extra')
      if (value === 'drop') await upsertRule(row.source, 'modal_drop', null)
      else if (value === 'no_expand') await upsertRule(row.source, 'modal_no_expand', null)
      else if (value === 'extra') await upsertRule(row.source, 'modal_extra', null)
      await afterMutate()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  const handleDeleteRow = async (row: RowVM) => {
    try {
      for (const t of ['alias', 'special', 'modal_drop', 'modal_no_expand', 'modal_extra', 'print_unify']) {
        await removeRule(row.source, t)
      }
      message.success(`已删除「${row.source}」的全部映射（回退直通）`)
      await afterMutate()
    } catch (e) {
      message.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  const columns = [
    {
      title: '飞书联系人（源部门）',
      dataIndex: 'source',
      key: 'source',
      fixed: 'left' as const,
      width: 190,
      render: (_: unknown, row: RowVM) => (
        <Space>
          <Typography.Text strong>{row.source}</Typography.Text>
          <Space size={4}>
            <Tooltip title="编辑该飞书部门在各培训页面显示的部门"><Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} /></Tooltip>
            <Popconfirm title={`删除「${row.source}」全部映射？`} onConfirm={() => handleDeleteRow(row)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        </Space>
      ),
    },
    ...PAGE_COLS.map((col) => ({
      title: col.title,
      key: col.key,
      width: 150,
      render: (_: unknown, row: RowVM) => {
        const isSignin = col.key === 'signin'
        const val = isSignin ? row.printName : row.resolved
        const isDiff = isSignin && row.printName !== row.resolved
        return <Tag color={isDiff ? 'cyan' : undefined} style={{ marginRight: 0 }}>{val}</Tag>
      },
    })),
    {
      title: '人员配置弹窗',
      key: 'modal',
      width: 130,
      render: (_: unknown, row: RowVM) => (
        <Select
          size="small"
          style={{ width: '100%' }}
          value={row.modalStatus}
          options={MODAL_OPTIONS}
          onChange={(v) => handleModalChange(row, v)}
        />
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <Tabs
        defaultActiveKey="dept"
        items={[
          {
            key: 'dept',
            label: '部门映射',
            children: (
              <div className="space-y-4">
                <Card>
                  <div className="space-y-3">
                    <div>
                      <Typography.Title level={5} style={{ marginTop: 0 }}>
                        培训部门映射对照表
                      </Typography.Title>
                      <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                        每行是一个源部门，每列是该部门在对应培训页面的显示名。点击任意数据格编辑该行统一目标
                        （所有列同步）；“人员配置弹窗”列用下拉选择 正常/不参与/不展开/额外补行。
                        新增飞书部门会自动出现在表中，无需改代码。
                      </Typography.Paragraph>
                    </div>
                    <Space>
                      <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>新增映射</Button>
                      <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
                    </Space>
                  </div>
                </Card>

                <Card>
                  <Table
                    rowKey="source"
                    loading={loading}
                    columns={columns}
                    dataSource={rows}
                    scroll={{ x: 1500 }}
                    pagination={{ pageSize: 30, showSizeChanger: false }}
                    rowClassName={(r: RowVM) => (r.color ? '' : '')}
                    onRow={(r: RowVM) => ({ style: { background: r.color } })}
                    locale={{ emptyText: '暂无部门，等待飞书同步或新增映射。' }}
                  />
                </Card>

                <Modal
                  title={editingSource ? `编辑部门映射：${editingSource}` : '新增部门映射'}
                  open={modalOpen}
                  onCancel={() => setModalOpen(false)}
                  onOk={handleSubmit}
                  confirmLoading={saving}
                  width={640}
                  okText="保存"
                  cancelText="取消"
                >
                  <div className="space-y-3">
                    {!editingSource && (
                      <div>
                        <Typography.Text strong>飞书联系人（源部门）</Typography.Text>
                        <Input
                          className="mt-1"
                          placeholder="如：103一车间 / 201二车间（多拉）"
                          value={newSource}
                          onChange={(e) => setNewSource(e.target.value)}
                          maxLength={128}
                        />
                      </div>
                    )}
                    <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                      设置这个飞书部门在每个培训页面显示的部门名称。下面 7 个数据页面共用一个部门；签到表/通知/考核可单独设置。
                    </Typography.Paragraph>
                    {PAGE_COLS.map((col) => {
                      const isSignin = col.key === 'signin'
                      const value = isSignin ? signinTarget : dataTarget
                      const onChange = isSignin ? setSigninTarget : setDataTarget
                      return (
                        <div key={col.key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <Typography.Text style={{ width: 150, flexShrink: 0 }}>{col.title}</Typography.Text>
                          <Select
                            style={{ flex: 1 }}
                            showSearch
                            allowClear
                            placeholder="留空 = 显示原名"
                            value={value || undefined}
                            onChange={(v) => onChange(v || '')}
                            options={deptOptions}
                            optionFilterProp="label"
                          />
                        </div>
                      )
                    })}
                  </div>
                </Modal>
              </div>
            ),
          },
          {
            key: 'person',
            label: '人员归属',
            children: (
              <Card>
                <PersonDeptMappingClient
                  mappings={mappings}
                  trainingDepts={trainingDepts}
                  loading={loading}
                  onChanged={afterMutate}
                />
              </Card>
            ),
          },
        ]}
      />
    </div>
  )
}
