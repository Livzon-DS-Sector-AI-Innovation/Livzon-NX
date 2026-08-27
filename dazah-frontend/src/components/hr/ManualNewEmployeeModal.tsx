'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { App, AutoComplete, DatePicker, Form, Input, Modal, Space, Tag } from 'antd'
import dayjs from 'dayjs'
import { createManualNewEmployeeTrainingPlan } from '@/actions/hr'
import { fetchEmployees } from '@/lib/api/hr'
import { fetchDepartmentPositions, fetchTrainingDepartments } from '@/lib/api/client/hr'
import { resolveTrainingDept, ensureDeptMappings } from './trainingDept'
import type { Employee } from '@/types/hr'
import type { NewEmployeeTrainingManualAddInput } from '@/types/hr'

interface ManualNewEmployeeModalProps {
  open: boolean
  onClose: () => void
  onCreated: (message: string) => void
}

interface FormValues {
  name: string
  department: string
  position: string
  training_position?: string
  hire_date: dayjs.Dayjs
}

/**
 * 手动新增新员工（离岗复训）弹窗。
 *
 * 输入姓名后防抖查询员工档案：
 * - 唯一命中：自动带出部门/岗位/入职日期（档案为准），并携带 employee_id
 * - 多个命中：展示候选列表供选择（选择后带出档案信息）
 * - 无命中：手动填写全部字段（不在档案员工走虚拟 UUID）
 */
export default function ManualNewEmployeeModal({
  open,
  onClose,
  onCreated,
}: ManualNewEmployeeModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)
  const [deptOptions, setDeptOptions] = useState<{ value: string }[]>([])
  const [positionOptions, setPositionOptions] = useState<{ value: string }[]>([])
  const [candidates, setCandidates] = useState<Employee[]>([])
  const [matchedId, setMatchedId] = useState<string | undefined>(undefined)
  const [matching, setMatching] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const nameTouched = useRef(false)

  // 部门下拉：培训部门列表
  useEffect(() => {
    if (!open) return
    ensureDeptMappings().catch(() => {})
    fetchTrainingDepartments()
      .then((depts) => setDeptOptions(depts.map((d) => ({ value: d }))))
      .catch(() => setDeptOptions([]))
  }, [open])

  // 部门变化时刷新该部门岗位培训清单岗位
  const department = Form.useWatch('department', form)
  useEffect(() => {
    if (!department) {
      setPositionOptions([])
      return
    }
    fetchDepartmentPositions(department)
      .then((positions) => setPositionOptions(positions.map((p) => ({ value: p }))))
      .catch(() => setPositionOptions([]))
  }, [department, form])

  // 弹窗关闭时重置表单
  useEffect(() => {
    if (!open) {
      form.resetFields()
      setCandidates([])
      setMatchedId(undefined)
      nameTouched.current = false
    }
  }, [open, form])

  // 姓名防抖匹配员工档案
  const handleNameChange = useCallback(
    (value: string) => {
      nameTouched.current = true
      // 手动修改姓名/清空后清除已匹配的档案关联
      setMatchedId(undefined)
      setCandidates([])
      if (debounceRef.current) clearTimeout(debounceRef.current)
      const keyword = (value || '').trim()
      if (!keyword) return
      debounceRef.current = setTimeout(async () => {
        setMatching(true)
        try {
          const res = await fetchEmployees({ keyword, page_size: 100 })
          const list = res.data || []
          const exact = list.filter((e) => e.name === keyword)
          if (exact.length === 1) {
            // 唯一命中：自动带出档案信息（入职日期以档案为准；部门按培训规则归一，
            // 档案一级部门 201车间/动力科 → 培训部门名 201一车间/动力部，与列表页 Tab 口径一致）
            const emp = exact[0]
            setMatchedId(emp.id)
            form.setFieldsValue({
              department: resolveTrainingDept(emp.department, emp.sub_department, []) || undefined,
              position: emp.position || undefined,
              hire_date: emp.hire_date ? dayjs(emp.hire_date) : undefined,
            })
            setCandidates([])
          } else if (exact.length > 1) {
            // 多个命中：展示候选列表
            setCandidates(exact)
          } else {
            setCandidates([])
          }
        } catch {
          // 匹配失败不阻断手动录入
        } finally {
          setMatching(false)
        }
      }, 400)
    },
    [form],
  )

  const handlePickCandidate = (emp: Employee) => {
    setMatchedId(emp.id)
    setCandidates([])
    form.setFieldsValue({
      department: resolveTrainingDept(emp.department, emp.sub_department, []) || undefined,
      position: emp.position || undefined,
      hire_date: emp.hire_date ? dayjs(emp.hire_date) : undefined,
    })
    message.success(`已带出「${emp.name}」的档案信息`)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const payload: NewEmployeeTrainingManualAddInput = {
        name: values.name.trim(),
        department: values.department.trim(),
        position: values.position.trim(),
        training_position: values.training_position?.trim() || undefined,
        hire_date: values.hire_date.format('YYYY-MM-DD'),
        employee_id: matchedId,
      }
      setSubmitting(true)
      const res = await createManualNewEmployeeTrainingPlan(payload)
      message.success(res.message || '已创建培训计划')
      onCreated(res.message || '已创建培训计划')
    } catch (err) {
      // 表单校验失败（(typeof err === 'object' && err !== null && 'errorFields' in err)）不提示；接口错误提示原因
      if (!(typeof err === 'object' && err !== null && 'errorFields' in err)) {
        message.error((err instanceof Error ? err.message : '') || '手动新增新员工失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="手动新增新员工"
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={submitting}
      okText="创建培训计划"
      cancelText="取消"
      destroyOnHidden
    >
      <Form form={form} layout="vertical" requiredMark="optional">
        <Form.Item
          name="name"
          label="姓名"
          rules={[{ required: true, message: '请输入姓名' }]}
          extra={matching ? '正在匹配员工档案…' : undefined}
        >
          <Input placeholder="输入姓名（在档案中自动带出信息）" onChange={(e) => handleNameChange(e.target.value)} />
        </Form.Item>
        {candidates.length > 0 && (
          <div className="mb-3">
            <div className="text-xs text-gray-500 mb-1">档案中有多个同名员工，请选择：</div>
            <Space size={6} wrap>
              {candidates.map((emp) => (
                <Tag
                  key={emp.id}
                  color="blue"
                  className="cursor-pointer"
                  onClick={() => handlePickCandidate(emp)}
                >
                  {emp.name} · {emp.department} · {emp.employee_number || '无工号'}
                </Tag>
              ))}
            </Space>
          </div>
        )}
        <Form.Item
          name="department"
          label="部门"
          rules={[{ required: true, message: '请输入部门' }]}
        >
          <AutoComplete
            placeholder="选择或输入部门"
            options={deptOptions}
            filterOption={(input, option) =>
              (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>
        <Form.Item
          name="position"
          label="岗位"
          rules={[{ required: true, message: '请输入岗位' }]}
        >
          <Input placeholder="输入岗位" />
        </Form.Item>
        <Form.Item name="training_position" label="培训岗位">
          <AutoComplete
            placeholder="选择或输入培训岗位"
            options={positionOptions}
            filterOption={(input, option) =>
              (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </Form.Item>
        <Form.Item
          name="hire_date"
          label="入职日期"
          rules={[{ required: true, message: '请选择入职日期' }]}
        >
          <DatePicker
            style={{ width: '100%' }}
            placeholder="选择入职日期"
            format="YYYY-MM-DD"
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
