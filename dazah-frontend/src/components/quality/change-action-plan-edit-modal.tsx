'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { DatePicker, Form, Input, Modal, Select } from 'antd'
import dayjs from 'dayjs'
import { fetchChanges, fetchDepartmentContacts } from '@/lib/api/quality'
import type {
  ChangeActionPlanListItem,
  ChangeListItem,
  DepartmentContact,
} from '@/types/quality'

interface ChangeActionPlanEditModalProps {
  open: boolean
  saving: boolean
  changeCode?: string
  initialValue?: ChangeActionPlanListItem | null
  onCancel: () => void
  onSubmit: (values: Record<string, unknown>) => Promise<void> | void
}

const statusOptions = [
  { label: '未启动', value: '未启动' },
  { label: '推进中', value: '推进中' },
  { label: '已完成', value: '已完成' },
  { label: '未按时完成', value: '未按时完成' },
]

const delayOptions = [
  { label: '否', value: '否' },
  { label: '是', value: '是' },
]

type PersonSelectOption = {
  label: string
  value: string
  personName: string
  department: string | null
  departmentHeadName: string | null
  departmentHeadOpenId: string | null
}

type ChangeCodeOption = {
  label: string
  value: string
  projectName: string
}

function buildOwnerOption(contact: DepartmentContact): PersonSelectOption | null {
  if (!contact.open_id || !contact.name) return null
  const details = [contact.department, contact.enterprise_email].filter(Boolean).join(' / ')
  return {
    label: details ? `${contact.name}（${details}）` : contact.name,
    value: contact.open_id,
    personName: contact.name,
    department: contact.department ?? null,
    departmentHeadName: contact.department_head_name ?? null,
    departmentHeadOpenId: contact.department_head_open_id ?? null,
  }
}

function buildDirectorOption(contact: DepartmentContact): PersonSelectOption | null {
  if (!contact.department_head_open_id || !contact.department_head_name) return null
  const details = [contact.department, contact.department_head_enterprise_email].filter(Boolean).join(' / ')
  return {
    label: details ? `${contact.department_head_name}（${details}）` : contact.department_head_name,
    value: contact.department_head_open_id,
    personName: contact.department_head_name,
    department: contact.department ?? null,
    departmentHeadName: contact.department_head_name,
    departmentHeadOpenId: contact.department_head_open_id,
  }
}

function buildChangeOption(change: ChangeListItem): ChangeCodeOption {
  return {
    label: `${change.change_code}${change.change_content ? ` - ${change.change_content}` : ''}`,
    value: change.change_code,
    projectName: change.change_content ?? '',
  }
}

export function ChangeActionPlanEditModal({
  open,
  saving,
  changeCode,
  initialValue,
  onCancel,
  onSubmit,
}: ChangeActionPlanEditModalProps) {
  const [form] = Form.useForm()
  const [changeOptions, setChangeOptions] = useState<ChangeCodeOption[]>([])
  const [ownerOptions, setOwnerOptions] = useState<PersonSelectOption[]>([])
  const [directorOptions, setDirectorOptions] = useState<PersonSelectOption[]>([])
  const [changeLoading, setChangeLoading] = useState(false)
  const [contactLoading, setContactLoading] = useState(false)
  const changesRef = useRef<ChangeListItem[]>([])
  const contactsRef = useRef<DepartmentContact[]>([])
  const changeMap = useMemo(
    () => new Map(changeOptions.map((item) => [item.value, item])),
    [changeOptions],
  )
  const ownerMap = useMemo(
    () => new Map(ownerOptions.map((item) => [item.value, item])),
    [ownerOptions],
  )
  const directorMap = useMemo(
    () => new Map(directorOptions.map((item) => [item.value, item])),
    [directorOptions],
  )

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      change_code: initialValue?.change_code ?? changeCode ?? '',
      project_name: initialValue?.project_name ?? '',
      related_work: initialValue?.related_work ?? '',
      owner_name: initialValue?.owner_name ?? '',
      owner_user_id: initialValue?.owner_user_id ?? null,
      director_name: initialValue?.director_name ?? '',
      director_user_id: initialValue?.director_user_id ?? null,
      deadline_date: initialValue?.deadline_date ? dayjs(initialValue.deadline_date) : null,
      status: initialValue?.status ?? undefined,
      delay_flag: initialValue?.delay_flag ?? undefined,
      delayed_deadline_date: initialValue?.delayed_deadline_date ? dayjs(initialValue.delayed_deadline_date) : null,
    })
  }, [changeCode, form, initialValue, open])

  useEffect(() => {
    if (!open) return
    let cancelled = false

    const loadOptions = async () => {
      setChangeLoading(true)
      setContactLoading(true)
      try {
        const [changeResult, contactResult] = await Promise.all([
          fetchChanges({ page: 1, page_size: 1000 }),
          fetchDepartmentContacts(),
        ])
        if (cancelled) return

        changesRef.current = changeResult.items
        contactsRef.current = contactResult

        const nextChangeOptions = changeResult.items.map(buildChangeOption)

        const ownerOptionMap = new Map<string, PersonSelectOption>()
        contactResult.forEach((contact) => {
          const option = buildOwnerOption(contact)
          if (option && !ownerOptionMap.has(option.value)) {
            ownerOptionMap.set(option.value, option)
          }
        })

        const directorOptionMap = new Map<string, PersonSelectOption>()
        contactResult.forEach((contact) => {
          const option = buildDirectorOption(contact)
          if (option && !directorOptionMap.has(option.value)) {
            directorOptionMap.set(option.value, option)
          }
        })

        if (initialValue?.owner_user_id && initialValue.owner_name && !ownerOptionMap.has(initialValue.owner_user_id)) {
          ownerOptionMap.set(initialValue.owner_user_id, {
            label: initialValue.owner_name,
            value: initialValue.owner_user_id,
            personName: initialValue.owner_name,
            department: null,
            departmentHeadName: null,
            departmentHeadOpenId: null,
          })
        }
        if (
          initialValue?.director_user_id &&
          initialValue.director_name &&
          !directorOptionMap.has(initialValue.director_user_id)
        ) {
          directorOptionMap.set(initialValue.director_user_id, {
            label: initialValue.director_name,
            value: initialValue.director_user_id,
            personName: initialValue.director_name,
            department: null,
            departmentHeadName: initialValue.director_name,
            departmentHeadOpenId: initialValue.director_user_id,
          })
        }

        setChangeOptions(nextChangeOptions)
        setOwnerOptions(Array.from(ownerOptionMap.values()))
        setDirectorOptions(Array.from(directorOptionMap.values()))
      } finally {
        if (!cancelled) {
          setChangeLoading(false)
          setContactLoading(false)
        }
      }
    }

    loadOptions()

    return () => {
      cancelled = true
    }
  }, [initialValue, open])

  useEffect(() => {
    if (!open) return
    const currentChangeCode = form.getFieldValue('change_code')
    const selectedCode = currentChangeCode || changeCode || initialValue?.change_code
    if (!selectedCode) return
    const matchedChange = changesRef.current.find((item) => item.change_code === selectedCode)
    if (!matchedChange) return
    const currentProjectName = form.getFieldValue('project_name')
    if (!currentProjectName || currentProjectName === initialValue?.project_name) {
      form.setFieldValue('project_name', matchedChange.change_content ?? '')
    }
  }, [changeCode, form, initialValue?.project_name, initialValue?.change_code, open, changeOptions])

  const handleChangeCodeChange = (value?: string) => {
    if (!value) {
      form.setFieldValue('project_name', '')
      return
    }
    const option = changeMap.get(value)
    form.setFieldsValue({
      change_code: value,
      project_name: option?.projectName ?? '',
    })
  }

  const handleOwnerChange = (value?: string) => {
    if (!value) {
      form.setFieldsValue({
        owner_user_id: null,
        owner_name: null,
        director_user_id: null,
        director_name: null,
      })
      return
    }
    const option = ownerMap.get(value)
    form.setFieldsValue({
      owner_user_id: value,
      owner_name: option?.personName ?? null,
      director_user_id: option?.departmentHeadOpenId ?? null,
      director_name: option?.departmentHeadName ?? null,
    })
  }

  const handleDirectorChange = (value?: string) => {
    if (!value) {
      form.setFieldsValue({
        director_user_id: null,
        director_name: null,
      })
      return
    }
    const option = directorMap.get(value)
    form.setFieldsValue({
      director_user_id: value,
      director_name: option?.personName ?? null,
    })
  }

  return (
    <Modal
      title={initialValue ? '编辑变更计划' : '新增变更计划'}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={saving}
      destroyOnHidden
      width={760}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) =>
          onSubmit({
            ...values,
            deadline_date: values.deadline_date ? values.deadline_date.format('YYYY-MM-DD') : null,
            delayed_deadline_date: values.delayed_deadline_date
              ? values.delayed_deadline_date.format('YYYY-MM-DD')
              : null,
          })
        }
      >
        <Form.Item label="变更控制号" name="change_code" rules={[{ required: true, message: '请选择变更控制号' }]}>
          <Select
            allowClear
            showSearch
            placeholder="请选择变更台账中的变更控制号"
            options={changeOptions}
            loading={changeLoading}
            optionFilterProp="label"
            onChange={handleChangeCodeChange}
          />
        </Form.Item>
        <Form.Item label="项目名称" name="project_name" rules={[{ required: true, message: '请输入项目名称' }]}>
          <Input placeholder="选择变更控制号后自动带出，可按需修改" />
        </Form.Item>
        <Form.Item label="涉及工作" name="related_work">
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item
          label="总负责人"
          name="owner_user_id"
          extra="从部门联系人中选择；选择后会自动带出对应部门负责人。"
        >
          <Select
            allowClear
            showSearch
            placeholder="请选择总负责人"
            options={ownerOptions}
            loading={contactLoading}
            optionFilterProp="label"
            onChange={handleOwnerChange}
          />
        </Form.Item>
        <Form.Item name="owner_name" hidden>
          <Input />
        </Form.Item>
        <Form.Item
          label="部门负责人"
          name="director_user_id"
          extra="默认按总负责人所属部门自动带出，也可以手动调整。"
        >
          <Select
            allowClear
            showSearch
            placeholder="请选择部门负责人"
            options={directorOptions}
            loading={contactLoading}
            optionFilterProp="label"
            onChange={handleDirectorChange}
          />
        </Form.Item>
        <Form.Item name="director_name" hidden>
          <Input />
        </Form.Item>
        <Form.Item label="项目截止时间" name="deadline_date">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="状态" name="status">
          <Select allowClear options={statusOptions} />
        </Form.Item>
        <Form.Item label="未完成是否延期" name="delay_flag">
          <Select allowClear options={delayOptions} />
        </Form.Item>
        <Form.Item label="延期后的日期" name="delayed_deadline_date">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
