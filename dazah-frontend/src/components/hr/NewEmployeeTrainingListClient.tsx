'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  App,
  Button,
  Card,
  Col,
  Input,
  Progress,
  Row,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import { EditOutlined, PlusOutlined, ReloadOutlined, UserAddOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { HR_DISPLAY_DATE_FORMAT } from '@/lib/dayjs-config'
import type { ColumnsType } from 'antd/es/table'
import {
  fetchNewEmployeeTrainingPlans,
  fetchNewEmployeeTrainingStats,
  fetchDepartmentPositions,
  fetchTrainingDepartments,
} from '@/lib/api/client/hr'
import { generateNewEmployeeTrainingPlan, createPositionTrainingMappingAction, updateNewEmployeeTrainingPlan } from '@/actions/hr'
import type { NewEmployeeTrainingListItem, NewEmployeeTrainingStats } from '@/types/hr'
import { resolveTrainingDept, ensureDeptMappings, useDeptMappings } from './trainingDept'
import ManualNewEmployeeModal from './ManualNewEmployeeModal'

const STATUS_COLORS: Record<string, string> = {
  待安排: 'default',
  培训中: 'processing',
  已完成: 'success',
  逾期: 'error',
}

export default function NewEmployeeTrainingListClient() {
  const { message } = App.useApp()
  const router = useRouter()
  const [items, setItems] = useState<NewEmployeeTrainingListItem[]>([])
  const [stats, setStats] = useState<NewEmployeeTrainingStats>({
    pending: 0,
    training: 0,
    completed: 0,
    overdue: 0,
  })
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [selectedDept, setSelectedDept] = useState<string>('')
  const [deptTabs, setDeptTabs] = useState<{ key: string; label: string }[]>([])
  const [status, setStatus] = useState<string | undefined>()
  const [keyword, setKeyword] = useState<string | undefined>()
  const [generatingId, setGeneratingId] = useState<string | null>(null)
  const [pulling, setPulling] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [positionOptions, setPositionOptions] = useState<string[]>([])
  const [positionCache, setPositionCache] = useState<Record<string, string[]>>({})
  // 部门 Tab 持久化到 URL（?dept=），刷新后停留在刷新前的部门
  const searchParams = useSearchParams()
  const initialUrlDept = useMemo(() => searchParams.get('dept'), [])

  const loadDepartments = useCallback(async () => {
    try {
      await ensureDeptMappings().catch(() => {})
      const depts = await fetchTrainingDepartments()
      const seen = new Set(depts)
      // 员工档案部门（sub_department/department）可能不在培训表中，拉取上限内全量补充（后端 page_size 上限 100）
      // 按培训规则解析：一级部门不在培训部门列表时回退二级部门，避免老部门名重新出现
      const allPlans = await fetchNewEmployeeTrainingPlans({ page: 1, page_size: 100 }).catch(() => null)
      if (allPlans) {
        for (const item of allPlans.data) {
          const d = resolveTrainingDept(item.department, item.sub_department, depts)
          if (d && !seen.has(d)) {
            seen.add(d)
            depts.push(d)
          }
        }
      }
      const tabs = depts.map((d) => ({ key: d, label: d }))
      setDeptTabs(tabs)
      if (tabs.length > 0) {
        // 优先级：已选中 > URL 中的部门（刷新恢复）> 第一个部门
        setSelectedDept((prev) => {
          if (prev) return prev
          if (initialUrlDept && depts.includes(initialUrlDept)) return initialUrlDept
          return tabs[0].key
        })
      }
    } catch {
      message.error('加载部门列表失败')
    }
  }, [message])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchNewEmployeeTrainingPlans({
        page,
        page_size: pageSize,
        department: selectedDept || undefined,
        status,
        keyword,
      })
      setItems(res.data)
      setTotal(res.total)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载新员工培训列表失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, selectedDept, status, keyword, message])

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchNewEmployeeTrainingStats()
      setStats(data)
    } catch {
      // 统计失败不阻塞
    }
  }, [])

  const { version: mappingVersion } = useDeptMappings()
  useEffect(() => {
    loadDepartments()
    // 映射配置加载/变更后重新加载部门 Tab
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mappingVersion])

  useEffect(() => {
    loadData()
    loadStats()
  }, [loadData, loadStats])

  // 部门变化时加载该部门的岗位培训清单岗位列表
  useEffect(() => {
    if (!selectedDept) {
      setPositionOptions([])
      return
    }
    if (positionCache[selectedDept]) {
      setPositionOptions(positionCache[selectedDept])
      return
    }
    fetchDepartmentPositions(selectedDept)
      .then((positions) => {
        setPositionOptions(positions)
        setPositionCache((prev) => ({ ...prev, [selectedDept]: positions }))
      })
      .catch(() => setPositionOptions([]))
  }, [selectedDept, positionCache])

  // 按行部门预加载岗位选项（跨部门搜索时也能正确显示）
  // 岗位选项按归一后的培训部门名缓存：员工档案一级部门（如 201车间）需归一为 201一车间/201二车间（MC）等清单部门名
  const deptNamesForResolve = useMemo(() => deptTabs.map((t) => t.key), [deptTabs])
  useEffect(() => {
    const depts = Array.from(
      new Set(
        items
          .map((i) => resolveTrainingDept(i.department, i.sub_department, deptNamesForResolve))
          .filter((d): d is string => !!d),
      ),
    ) as string[]
    depts.forEach((d) => {
      if (positionCache[d] === undefined) {
        fetchDepartmentPositions(d)
          .then((positions) => setPositionCache((prev) => ({ ...prev, [d]: positions })))
          .catch(() => setPositionCache((prev) => ({ ...prev, [d]: [] })))
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items])

  const handleGenerate = async (employeeId: string) => {
    setGeneratingId(employeeId)
    try {
      const res = await generateNewEmployeeTrainingPlan({ employee_id: employeeId })
      message.success(res.message || '培训计划已生成')
      loadData()
      loadStats()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '生成培训计划失败')
    } finally {
      setGeneratingId(null)
    }
  }

  // 培训岗位交互：选择 → 行内保存 → 锁定只读 → 编辑解锁（调岗）
  // 草稿值（未保存的选中项）与编辑态（已保存后再次修改）按员工隔离
  const [draftPositions, setDraftPositions] = useState<Record<string, string>>({})
  const [editingId, setEditingId] = useState<string | null>(null)

  // 培训岗位变更：保存（每人独立，存到计划自身；映射仅作初始默认）+ 自动生成/重算计划
  const handleTrainingPositionChange = async (
    record: NewEmployeeTrainingListItem,
    value: string
  ) => {
    setGeneratingId(record.employee_id)
    try {
      if (record.plan_id) {
        // 已有计划：更新培训岗位（后端按新岗位重算教材明细，已培训内容去重）
        await updateNewEmployeeTrainingPlan(record.plan_id, { training_position: value })
        message.success('培训岗位已更新，培训计划已重新生成')
      } else {
        // 未生成计划：记录初始默认映射 + 生成计划（培训岗位存入计划，每人独立，互不干扰）
        await createPositionTrainingMappingAction({
          department: resolveTrainingDept(record.department, record.sub_department, deptNamesForResolve),
          employee_position: record.position,
          training_position: value,
        })
        const res = await generateNewEmployeeTrainingPlan({
          employee_id: record.employee_id,
          training_position: value,
        })
        message.success(res.message || '培训计划已生成')
      }
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '操作失败')
    } finally {
      setGeneratingId(null)
      setDraftPositions((prev) => {
        const next = { ...prev }
        delete next[record.employee_id]
        return next
      })
      setEditingId(null)
      loadData()
      loadStats()
    }
  }

  // 行内"保存培训岗位"（草稿 → 保存）
  const handleSaveDraftPosition = (record: NewEmployeeTrainingListItem) => {
    const value = draftPositions[record.employee_id]
    if (!value) {
      message.warning('请先选择培训岗位')
      return
    }
    handleTrainingPositionChange(record, value)
  }

  // 编辑（调岗）：解锁该行，恢复已保存值为草稿
  const handleEditPosition = (record: NewEmployeeTrainingListItem) => {
    setEditingId(record.employee_id)
    setDraftPositions((prev) => ({ ...prev, [record.employee_id]: record.training_position || '' }))
  }

  const handleCancelEditPosition = (record: NewEmployeeTrainingListItem) => {
    setEditingId((prev) => (prev === record.employee_id ? null : prev))
    setDraftPositions((prev) => {
      const next = { ...prev }
      delete next[record.employee_id]
      return next
    })
  }

  // 拉取新员工：手动刷新近期入职员工列表
  const handlePullNewHires = async () => {
    setPulling(true)
    try {
      await loadData()
      await loadStats()
      await loadDepartments()
      message.success('已拉取最新新员工名单')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '拉取新员工失败')
    } finally {
      setPulling(false)
    }
  }

  const columns: ColumnsType<NewEmployeeTrainingListItem> = [
    { title: '姓名', dataIndex: 'employee_name', key: 'employee_name', width: 100 },
    {
      title: '部门',
      key: 'department',
      width: 140,
      render: (_, record) => record.sub_department || record.department,
    },
    { title: '岗位', dataIndex: 'position', key: 'position', width: 140, ellipsis: true },
    {
      title: '培训岗位',
      key: 'training_position',
      width: 300,
      render: (_, record) => {
        // 岗位选项按归一后的培训部门名取缓存（员工档案一级部门 201车间 → 201一车间/201二车间（MC）等）；
        // 缓存为空数组时回退到当前 Tab 的岗位选项，避免一级部门查清单为空导致永远无选项
        const deptKey = resolveTrainingDept(record.department, record.sub_department, deptNamesForResolve)
        const cached = positionCache[deptKey]
        const rowOptions = (cached && cached.length ? cached : positionOptions) || []
        const isEditing = editingId === record.employee_id
        const draft = draftPositions[record.employee_id]
        const saving = generatingId === record.employee_id
        // 已保存且未编辑：只读锁定 + 编辑按钮（调岗时解锁重新选择）
        if (record.training_position && !isEditing) {
          return (
            <Space size={4}>
              <Tag color="blue">{record.training_position}</Tag>
              <Button size="small" type="link" icon={<EditOutlined />} onClick={() => handleEditPosition(record)}>
                编辑
              </Button>
            </Space>
          )
        }
        return (
          <Space size={4} style={{ width: '100%' }}>
            <Select
              value={draft || record.training_position || undefined}
              onChange={(value) => setDraftPositions((prev) => ({ ...prev, [record.employee_id]: value }))}
              options={rowOptions.map((p) => ({ value: p, label: p }))}
              placeholder="请选择培训岗位"
              style={{ width: 170 }}
              loading={!rowOptions.length || saving}
              showSearch
              optionFilterProp="label"
            />
            <Button
              size="small"
              type="primary"
              disabled={!draft}
              loading={saving}
              onClick={() => handleSaveDraftPosition(record)}
            >
              保存
            </Button>
            {isEditing && (
              <Button size="small" onClick={() => handleCancelEditPosition(record)}>
                取消
              </Button>
            )}
          </Space>
        )
      },
    },
    {
      title: '入职日期',
      dataIndex: 'hire_date',
      key: 'hire_date',
      width: 110,
      render: (v: string) => v ? dayjs(v).format(HR_DISPLAY_DATE_FORMAT) : '-',
    },
    {
      title: '培训进度',
      key: 'progress',
      width: 180,
      render: (_, record) => (
        <Space size={6}>
          <Progress
            percent={record.progress}
            size="small"
            style={{ width: 100 }}
            status={record.progress >= 100 ? 'success' : 'active'}
          />
          <span className="text-xs text-gray-500">
            {record.completed_count}/{record.total_count}
          </span>
        </Space>
      ),
    },
    {
      title: '截止日期',
      dataIndex: 'deadline_date',
      key: 'deadline_date',
      width: 110,
      render: (v: string | null) => v ? dayjs(v).format(HR_DISPLAY_DATE_FORMAT) : '-',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string | null) => (v ? <Tag color={STATUS_COLORS[v]}>{v}</Tag> : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 130,
      render: (_, record) =>
        record.plan_id ? (
          <Button
            type="link"
            size="small"
            onClick={() => router.push(`/hr/training/new-employee/${record.plan_id}`)}
          >
            查看详情
          </Button>
        ) : (
          <Button
            type="link"
            size="small"
            icon={<PlusOutlined />}
            loading={generatingId === record.employee_id}
            onClick={() => handleGenerate(record.employee_id)}
          >
            生成计划
          </Button>
        ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* 统计卡片 */}
      <Row gutter={[16, 16]}>
        {[
          { key: 'pending', label: '待安排', value: stats.pending, color: 'default' },
          { key: 'training', label: '培训中', value: stats.training, color: 'processing' },
          { key: 'completed', label: '已完成', value: stats.completed, color: 'success' },
          { key: 'overdue', label: '逾期', value: stats.overdue, color: 'error' },
        ].map((card) => (
          <Col xs={12} sm={6} key={card.key}>
            <Card size="small" className="text-center">
              <div className="text-2xl font-semibold text-[var(--color-charcoal)]">
                {card.value}
              </div>
              <div className="text-[13px] text-[var(--color-steel)] mt-1">{card.label}</div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* 部门按钮组 */}
      <div className="flex flex-wrap gap-2">
        {deptTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setSelectedDept(tab.key)
              setPage(1)
              // 部门选择同步到 URL，刷新后停留在当前部门
              router.replace(
                `/hr/training/new-employee?dept=${encodeURIComponent(tab.key)}`,
                { scroll: false },
              )
            }}
            className={`px-4 py-2 rounded-lg border text-sm transition-all ${
              selectedDept === tab.key
                ? 'border-blue-500 bg-blue-50 text-blue-600'
                : 'border-gray-200 bg-white text-gray-600 hover:border-blue-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* 筛选栏 */}
      <Card size="small">
        <Space wrap size={12}>
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 120 }}
            value={status}
            onChange={(v: string | undefined) => { setStatus(v); setPage(1) }}
            options={['待安排', '培训中', '已完成', '逾期'].map((s) => ({ value: s, label: s }))}
          />
          <Input.Search
            placeholder="搜索姓名"
            allowClear
            style={{ width: 200 }}
            onSearch={(v) => { setKeyword(v || undefined); setPage(1) }}
          />
          <Button
            type="primary"
            icon={<UserAddOutlined />}
            loading={pulling}
            onClick={handlePullNewHires}
          >
            拉取新员工
          </Button>
          <Button icon={<PlusOutlined />} onClick={() => setManualOpen(true)}>
            手动新增新员工
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { loadData(); loadStats() }}>
            刷新
          </Button>
        </Space>
      </Card>

      {/* 表格 */}
      <Table
        rowKey={(record) => record.plan_id || `pending-${record.employee_id}`}
        columns={columns}
        dataSource={items}
        loading={loading}
        rowClassName={(record) => {
          if (record.status === '逾期') return 'bg-red-50'
          if (record.deadline_date) {
            const deadline = new Date(record.deadline_date)
            const now = new Date()
            const daysUntilDeadline = Math.ceil((deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24))
            if (daysUntilDeadline <= 7 && daysUntilDeadline > 0) return 'bg-yellow-50'
          }
          return ''
        }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        locale={{ emptyText: '暂无新员工培训记录' }}
      />

      <ManualNewEmployeeModal
        open={manualOpen}
        onClose={() => setManualOpen(false)}
        onCreated={() => {
          setManualOpen(false)
          loadData()
          loadStats()
          loadDepartments()
        }}
      />
    </div>
  )
}
