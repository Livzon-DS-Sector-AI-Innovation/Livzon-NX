'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  App,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  TeamOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import { HR_DISPLAY_DATE_FORMAT } from '@/lib/dayjs-config'
import { fetchNewEmployeeTrainingPlan, fetchAvailableTrainees, exportPositionTrainingConfirmation } from '@/lib/api/client/hr'
import {
  addNewEmployeeTrainingItem,
  deleteNewEmployeeTrainingPlan,
  startNewEmployeeTraining,
} from '@/actions/hr'
import type { NewEmployeeTrainingItem, NewEmployeeTrainingPlan } from '@/types/hr'
import { resolveTrainingDept } from './trainingDept'

export default function NewEmployeeTrainingDetailClient({ planId }: { planId: string }) {
  const { message, modal } = App.useApp()
  const router = useRouter()
  const [plan, setPlan] = useState<NewEmployeeTrainingPlan | null>(null)
  const [loading, setLoading] = useState(false)
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([])
  const [starting, setStarting] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [traineeModalOpen, setTraineeModalOpen] = useState(false)
  const [trainees, setTrainees] = useState<{ key: string; title: string }[]>([])
  const [selectedTrainees, setSelectedTrainees] = useState<string[]>([])
  const [traineeLoading, setTraineeLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [addForm] = Form.useForm()

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchNewEmployeeTrainingPlan(planId)
      setPlan(data)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载培训计划失败')
    } finally {
      setLoading(false)
    }
  }, [planId, message])

  useEffect(() => {
    loadData()
    // 完成状态变化后清空已勾选的已完成项
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planId])

  // 勾选项变化：过滤掉已完成项
  useEffect(() => {
    if (!plan) return
    const doneIds = new Set(
      plan.items.filter((i) => i.completed_date).map((i) => i.id)
    )
    setSelectedItemIds((prev) => prev.filter((id) => !doneIds.has(id)))
  }, [plan])

  const handleAddTrainees = async () => {
    if (!plan) return
    setTraineeLoading(true)
    setTraineeModalOpen(true)
    setSelectedTrainees([])
    try {
      // 传参部门按培训规则解析（与列表页 Tab 一致）：
      // 手动新增计划存 department=培训部门名，档案员工计划存 department=一级+sub_department=二级，
      // 归一后两种存储格式都能被后端正确匹配，不会混入其他车间人员
      const trainingDept = resolveTrainingDept(plan.department, plan.sub_department, [])
      const traineeList = await fetchAvailableTrainees({
        department: trainingDept || undefined,
        exclude_plan_id: plan.id,
      })
      setTrainees(traineeList.map((t) => ({ key: t.name, title: `${t.name}（${t.department}）` })))
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载参训人员列表失败')
      setTraineeModalOpen(false)
    } finally {
      setTraineeLoading(false)
    }
  }

  const handleStartTraining = async () => {
    if (!plan) return
    if (selectedItemIds.length === 0) {
      message.warning('请先勾选待培训教材')
      return
    }
    setStarting(true)
    try {
      const additional_trainees = selectedTrainees.map((name) => {
        const t = trainees.find((tt) => tt.key === name)
        const dept = t ? t.title.split('（')[1].replace('）', '') : plan.department
        return { name, department: dept }
      })
      const res = await startNewEmployeeTraining(plan.id, {
        item_ids: selectedItemIds,
        additional_trainees,
      })
      const data = res.data
      // 新 tab 打开培训资料页面，通过 session 恢复预填内容
      window.open(`/hr/training/sign-in?session=${data.session_id}&doc=sign_in`, '_blank')
      message.success(res.message || '已创建培训会话，请在培训资料页面完善信息')
      setTraineeModalOpen(false)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '开始培训失败')
    } finally {
      setStarting(false)
    }
  }

  const handleAddItem = async () => {
    if (!plan) return
    try {
      const values = await addForm.validateFields()
      const res = await addNewEmployeeTrainingItem(plan.id, {
        level: values.level || '部门级',
        textbook_name: values.textbook_name,
        textbook_code: values.textbook_code || null,
        assessment_method: values.assessment_method || null,
        remark: values.remark || null,
      })
      message.success(res.message || '已添加培训教材')
      setAddOpen(false)
      addForm.resetFields()
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '添加失败')
    }
  }

  const handleDelete = () => {
    modal.confirm({
      title: '删除新员工培训计划',
      content: '删除后该员工的培训计划将移除（培训台账记录不受影响），确定继续吗？',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteNewEmployeeTrainingPlan(planId)
          message.success('已删除')
          router.push('/hr/training/new-employee')
        } catch (err) {
          message.error((err instanceof Error ? err.message : '') || '删除失败')
        }
      },
    })
  }

  const handleExportConfirmation = async () => {
    if (!plan) return
    setExporting(true)
    try {
      const blob = await exportPositionTrainingConfirmation(planId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `岗位培训确认表_${plan.employee_name}_${plan.employee_number || 'nonumber'}.xlsx`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      message.success('岗位培训确认表已导出')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  if (!plan) {
    return (
      <Card loading={loading} className="mt-4">
        <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/hr/training/new-employee')}>
          返回列表
        </Button>
      </Card>
    )
  }

  const doneIds = new Set(plan.items.filter((i) => i.completed_date).map((i) => i.id))

  const columns: ColumnsType<NewEmployeeTrainingItem> = [
    {
      title: '勾选',
      key: 'select',
      width: 60,
      render: (_, record) =>
        record.completed_date ? (
          <Checkbox disabled checked />
        ) : (
          <Checkbox
            checked={selectedItemIds.includes(record.id || '')}
            disabled={!!record.completed_date}
            onChange={(e) => {
              const id = record.id || ''
              setSelectedItemIds((prev) =>
                e.target.checked
                  ? [...prev, id]
                  : prev.filter((x) => x !== id)
              )
            }}
          />
        ),
    },
    {
      title: '培训教材',
      dataIndex: 'textbook_name',
      key: 'textbook_name',
      render: (v: string, record) => (
        <Space size={6}>
          <span>{v}</span>
          {record.manual && <Tag color="orange">手动添加</Tag>}
        </Space>
      ),
    },
    {
      title: '编号',
      dataIndex: 'textbook_code',
      key: 'textbook_code',
      width: 160,
      render: (v: string | null) => v || '-',
    },
    {
      title: '考核方式',
      dataIndex: 'assessment_method',
      key: 'assessment_method',
      width: 100,
      render: (v: string | null) => v || '-',
    },
    {
      title: '状态',
      key: 'status',
      width: 140,
      render: (_, record) =>
        record.completed_date ? (
          <Tag color="success">✓ 已完成 {dayjs(record.completed_date).format(HR_DISPLAY_DATE_FORMAT)}</Tag>
        ) : (
          <Tag>待培训</Tag>
        ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/hr/training/new-employee')}>
          返回列表
        </Button>
        <h1 className="text-[20px] font-semibold text-[var(--color-charcoal)] m-0">
          {plan.employee_name} · 新员工培训计划
        </h1>
        <Popconfirm title="确定删除该培训计划吗？" onConfirm={handleDelete} okButtonProps={{ danger: true }}>
          <Button danger icon={<DeleteOutlined />} className="ml-auto">
            删除计划
          </Button>
        </Popconfirm>
      </div>

      {/* 员工信息卡 */}
      <Card size="small" title="员工信息">
        <Descriptions
          size="small"
          column={{ xs: 1, sm: 2, md: 4 }}
          items={[
            { key: 'department', label: '部门', children: plan.department },
            { key: 'position', label: '岗位', children: plan.position },
            { key: 'hire_date', label: '入职日期', children: plan.hire_date ? dayjs(plan.hire_date).format(HR_DISPLAY_DATE_FORMAT) : '-' },
            { key: 'deadline', label: '截止日期', children: plan.deadline_date ? dayjs(plan.deadline_date).format(HR_DISPLAY_DATE_FORMAT) : '-' },
            {
              key: 'status',
              label: '状态',
              children: (
                <Tag color={{ 待安排: 'default', 已完成: 'success', 逾期: 'error' }[plan.status] || 'default'}>
                  {plan.status}
                </Tag>
              ),
            },
          ]}
        />
      </Card>

      {/* 部门级培训计划 */}
      <Card
        size="small"
        title={`部门级培训计划（${plan.completed_count}/${plan.total_count} 已完成）`}
        extra={
          <Space>
            <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
              新增教材
            </Button>
            <Button
              icon={<TeamOutlined />}
              onClick={handleAddTrainees}
              disabled={selectedItemIds.length === 0}
            >
              添加参训人员{selectedTrainees.length > 0 ? `（${selectedTrainees.length}）` : ''}
            </Button>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={starting}
              disabled={selectedItemIds.length === 0}
              onClick={handleStartTraining}
            >
              开始培训（{selectedItemIds.length} 份）
            </Button>
            <Button
              icon={<DownloadOutlined />}
              loading={exporting}
              onClick={handleExportConfirmation}
            >
              导出岗位培训确认表
            </Button>
          </Space>
        }
      >
        <div className="mb-3">
          <Progress
            percent={plan.progress}
            status={plan.progress >= 100 ? 'success' : 'active'}
          />
        </div>
        <div className="mb-3 flex gap-4 text-sm">
          <Tag color="success">已完成 {plan.completed_count}</Tag>
          <Tag>待培训 {plan.total_count - plan.completed_count}</Tag>
          <Tag>总计 {plan.total_count}</Tag>
        </div>
        <Table
          rowKey={(record) => record.id || record.textbook_name}
          columns={columns}
          dataSource={plan.items}
          pagination={false}
          size="small"
          locale={{ emptyText: '暂无培训教材，请点击「新增教材」添加' }}
        />
        <div className="mt-2 text-xs text-gray-500">
          提示：勾选待培训教材后点击「开始培训」，将跳转至培训资料页面制作签到/评估/考核资料；培训完成后在培训资料页面「添加到培训台账」，本页面进度自动更新（按教材名匹配台账培训内容）。
        </div>
      </Card>

      {/* 手动添加教材 Modal */}
      <Modal
        title="新增培训教材"
        open={addOpen}
        onOk={handleAddItem}
        onCancel={() => setAddOpen(false)}
        destroyOnHidden
      >
        <Form form={addForm} layout="vertical" className="mt-4">
          <Form.Item name="level" label="级别" initialValue="部门级">
            <Select
              options={[
                { label: '部门级', value: '部门级' },
                { label: '岗位级', value: '岗位级' },
              ]}
            />
          </Form.Item>
          <Form.Item name="textbook_name" label="培训教材名称" rules={[{ required: true, message: '请输入教材名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="textbook_code" label="编号">
            <Input placeholder="如 SOP-001" />
          </Form.Item>
          <Form.Item name="assessment_method" label="考核方式">
            <Input placeholder="笔试/口试/实操" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 选择参训人员 Modal */}
      <Modal
        title="选择参训人员（可多选）"
        open={traineeModalOpen}
        onOk={handleStartTraining}
        onCancel={() => setTraineeModalOpen(false)}
        okText="开始培训"
        confirmLoading={starting}
        loading={traineeLoading}
        width={600}
      >
        <div className="mt-4">
          <div className="mb-2 text-sm text-gray-600">
            当前部门：{plan?.department} | 已选 {selectedTrainees.length} 人
          </div>
          <Select
            mode="multiple"
            placeholder="请选择参训人员"
            style={{ width: '100%' }}
            value={selectedTrainees}
            onChange={(values) => setSelectedTrainees(values)}
            options={trainees.map((t) => ({ value: t.key, label: t.title }))}
            optionFilterProp="label"
            showSearch
            allowClear
          />
        </div>
      </Modal>
    </div>
  )
}