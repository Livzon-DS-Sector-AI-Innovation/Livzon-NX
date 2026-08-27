'use client'

import { useEffect, useRef, useState } from 'react'
import { DatePicker, Form, Input, Modal, Select } from 'antd'
import dayjs from 'dayjs'
import { searchChangeActionPlanPersons } from '@/lib/api/client/quality'
import type {
  ChangeActionPlanListItem,
  ChangeActionPlanPersonOption,
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

type PersonFieldKey = 'owner' | 'director'

type PersonSelectOption = {
  label: string
  value: string
  personName: string
}

function buildPersonOption(person: ChangeActionPlanPersonOption): PersonSelectOption {
  const details = [person.mobile, person.job_title, person.email].filter(Boolean).join(' / ')
  return {
    label: details ? `${person.name}（${details}）` : person.name,
    value: person.open_id,
    personName: person.name,
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
  const isEditingExisting = Boolean(initialValue)
  const [ownerOptions, setOwnerOptions] = useState<PersonSelectOption[]>([])
  const [directorOptions, setDirectorOptions] = useState<PersonSelectOption[]>([])
  const [ownerLoading, setOwnerLoading] = useState(false)
  const [directorLoading, setDirectorLoading] = useState(false)
  const searchCacheRef = useRef<Record<string, PersonSelectOption[]>>({})
  const searchTimerRef = useRef<Record<PersonFieldKey, number | null>>({
    owner: null,
    director: null,
  })
  const searchRequestIdRef = useRef<Record<PersonFieldKey, number>>({
    owner: 0,
    director: 0,
  })

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
    setOwnerOptions([])
    setDirectorOptions([])
  }, [changeCode, form, initialValue, open])

  useEffect(() => {
    return () => {
      if (searchTimerRef.current.owner) {
        window.clearTimeout(searchTimerRef.current.owner)
      }
      if (searchTimerRef.current.director) {
        window.clearTimeout(searchTimerRef.current.director)
      }
    }
  }, [])

  const runPersonSearch = (field: PersonFieldKey, rawKeyword: string) => {
    const keyword = rawKeyword.trim()
    const setLoading = field === 'owner' ? setOwnerLoading : setDirectorLoading
    const setOptions = field === 'owner' ? setOwnerOptions : setDirectorOptions
    const timerKey = searchTimerRef.current[field]

    if (timerKey) {
      window.clearTimeout(timerKey)
      searchTimerRef.current[field] = null
    }

    if (!keyword) {
      setOptions([])
      setLoading(false)
      return
    }

    const cachedOptions = searchCacheRef.current[keyword]
    if (cachedOptions) {
      setOptions(cachedOptions)
      setLoading(false)
      return
    }

    setLoading(true)
    searchTimerRef.current[field] = window.setTimeout(async () => {
      const requestId = searchRequestIdRef.current[field] + 1
      searchRequestIdRef.current[field] = requestId

      try {
        const people = await searchChangeActionPlanPersons(keyword)
        const options = people.map(buildPersonOption)
        searchCacheRef.current[keyword] = options
        if (searchRequestIdRef.current[field] === requestId) {
          setOptions(options)
        }
      } catch {
        if (searchRequestIdRef.current[field] === requestId) {
          setOptions([])
        }
      } finally {
        if (searchRequestIdRef.current[field] === requestId) {
          setLoading(false)
        }
      }
    }, 250)
  }

  const handlePersonChange = (
    nameField: 'owner_name' | 'director_name',
    option?: PersonSelectOption | PersonSelectOption[],
  ) => {
    if (!option || Array.isArray(option)) {
      form.setFieldValue(nameField, null)
      return
    }
    form.setFieldValue(nameField, option.personName)
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
        <Form.Item label="变更控制号" name="change_code" rules={[{ required: true, message: '请输入变更控制号' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="项目名称" name="project_name" rules={[{ required: true, message: '请输入项目名称' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="涉及工作" name="related_work">
          <Input.TextArea rows={3} />
        </Form.Item>
        {isEditingExisting ? (
          <Form.Item
            label="总负责人"
            name="owner_name"
            extra="后续人员维护请在飞书多维表中完成，修改后点击系统“同步多维表格”回写。"
          >
            <Input readOnly placeholder="请在飞书多维表中维护" />
          </Form.Item>
        ) : (
          <Form.Item
            label="总负责人"
            name="owner_user_id"
            extra="输入姓名、手机号或邮箱搜索飞书人员；创建成功后，后续维护请在飞书多维表中完成。"
          >
            <Select
              allowClear
              showSearch
              filterOption={false}
              placeholder="输入姓名、手机号或邮箱搜索飞书人员"
              options={ownerOptions}
              loading={ownerLoading}
              notFoundContent={ownerLoading ? '搜索中...' : '输入关键词搜索飞书人员'}
              onSearch={(value) => runPersonSearch('owner', value)}
              onChange={(_, option) => handlePersonChange('owner_name', option as PersonSelectOption | undefined)}
            />
          </Form.Item>
        )}
        {!isEditingExisting ? (
          <Form.Item name="owner_name" hidden>
            <Input />
          </Form.Item>
        ) : (
          <Form.Item name="owner_user_id" hidden>
            <Input />
          </Form.Item>
        )}
        {isEditingExisting ? (
          <Form.Item
            label="部门总监"
            name="director_name"
            extra="后续人员维护请在飞书多维表中完成，修改后点击系统“同步多维表格”回写。"
          >
            <Input readOnly placeholder="请在飞书多维表中维护" />
          </Form.Item>
        ) : (
          <Form.Item
            label="部门总监"
            name="director_user_id"
            extra="输入姓名、手机号或邮箱搜索飞书人员；创建成功后，后续维护请在飞书多维表中完成。"
          >
            <Select
              allowClear
              showSearch
              filterOption={false}
              placeholder="输入姓名、手机号或邮箱搜索飞书人员"
              options={directorOptions}
              loading={directorLoading}
              notFoundContent={directorLoading ? '搜索中...' : '输入关键词搜索飞书人员'}
              onSearch={(value) => runPersonSearch('director', value)}
              onChange={(_, option) => handlePersonChange('director_name', option as PersonSelectOption | undefined)}
            />
          </Form.Item>
        )}
        {!isEditingExisting ? (
          <Form.Item name="director_name" hidden>
            <Input />
          </Form.Item>
        ) : (
          <Form.Item name="director_user_id" hidden>
            <Input />
          </Form.Item>
        )}
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
