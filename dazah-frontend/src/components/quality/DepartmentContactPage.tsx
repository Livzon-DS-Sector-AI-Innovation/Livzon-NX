'use client'

import { qualityTokens } from './themeTokens'
import { useCallback, useMemo, useRef, useState } from 'react'
import { App, Avatar, Button, Input, Modal, Select, Space, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useRouter } from 'next/navigation'
import { updateDepartmentContactFeishu } from '@/actions/quality'
import { PersonCell } from './index'
import type { DepartmentContact, UpdateFeishuDepartmentContactRequest } from '@/types/quality'
import { searchFeishuMembers, type FeishuContactVM } from '@/lib/api/client/hr'

interface DepartmentContactPageProps {
  items: DepartmentContact[]
  total: number
  page: number
  pageSize: number
  activeDepartment: string
  departmentOptions: string[]
}

interface DepartmentContactTableRow extends DepartmentContact {
  name_display: string
  department_display: string
  enterprise_email_display: string
  department_head_name_display: string
}

interface EditFormValues {
  open_id: string | undefined
  department_head_open_id: string | undefined
  department: string
  enterprise_email: string
}

interface PersonPickOption {
  value: string
  label: string
  avatarUrl: string | null
}

interface PersonPickerSelectProps {
  value?: string
  onChange?: (value?: string) => void
  placeholder?: string
  allowClear?: boolean
  currentPerson?: { open_id?: string | null; name?: string | null; avatar_url?: string | null }
}

function buildDepartmentContactsHref(params: {
  department?: string
  page?: number
  pageSize?: number
}): string {
  const searchParams = new URLSearchParams()

  if (params.department && params.department !== '全部') {
    searchParams.set('department', params.department)
  }
  if (params.page && params.page > 1) {
    searchParams.set('page', String(params.page))
  }
  if (params.pageSize && params.pageSize !== 20) {
    searchParams.set('page_size', String(params.pageSize))
  }

  const query = searchParams.toString()
  return `/quality/department-contacts${query ? `?${query}` : ''}`
}

function getVisiblePages(page: number, totalPages: number): number[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1)
  }

  const candidates = new Set([1, totalPages, page - 1, page, page + 1])
  return Array.from(candidates)
    .filter((value) => value >= 1 && value <= totalPages)
    .sort((a, b) => a - b)
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function toPickOption(item: FeishuContactVM): PersonPickOption | null {
  if (!item.open_id) return null
  return {
    value: item.open_id,
    label: item.name || '-',
    avatarUrl: item.avatar_url || null,
  }
}

function PersonPickerSelect({
  value,
  onChange,
  placeholder,
  allowClear,
  currentPerson,
}: PersonPickerSelectProps) {
  const [options, setOptions] = useState<PersonPickOption[]>([])
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const runSearch = useCallback((keyword: string) => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => {
      void (async () => {
        if (!keyword || keyword.trim().length < 1) {
          setOptions([])
          return
        }
        const members = await searchFeishuMembers(keyword.trim())
        setOptions(members.map(toPickOption).filter((o): o is PersonPickOption => o !== null))
      })()
    }, 250)
  }, [])

  // 把当前人员注入为已知选项，保证已选值能回显姓名而非裸 open_id
  const mergedOptions = useMemo(() => {
    const merged: PersonPickOption[] = [...options]
    if (currentPerson?.open_id && (currentPerson.name || currentPerson.avatar_url)) {
      const exists = merged.some((o) => o.value === currentPerson.open_id)
      if (!exists) {
        merged.unshift({
          value: currentPerson.open_id,
          label: currentPerson.name || '-',
          avatarUrl: currentPerson.avatar_url || null,
        })
      }
    }
    return merged
  }, [options, currentPerson])

  return (
    <Select
      style={{ width: '100%' }}
      placeholder={placeholder}
      allowClear={allowClear}
      showSearch
      filterOption={false}
      onSearch={runSearch}
      value={value}
      onChange={(val?: string) => onChange?.(val)}
      options={mergedOptions}
      optionRender={(option) => (
        <Space size={6}>
          <Avatar
            size={20}
            src={option.data.avatarUrl || undefined}
            style={{ background: qualityTokens.brand, flexShrink: 0 }}
          >
            {String(option.data.label || '?').slice(0, 1)}
          </Avatar>
          <span>{option.data.label}</span>
        </Space>
      )}
    />
  )
}

export function DepartmentContactPage({
  items,
  total,
  page,
  pageSize,
  activeDepartment,
  departmentOptions,
}: DepartmentContactPageProps) {
  const { message } = App.useApp()
  const router = useRouter()
  const [modalOpen, setModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<DepartmentContact | null>(null)
  const [formValues, setFormValues] = useState<EditFormValues>({
    open_id: undefined,
    department_head_open_id: undefined,
    department: '',
    enterprise_email: '',
  })
  const [saving, setSaving] = useState(false)

  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const visiblePages = getVisiblePages(page, totalPages)
  const tableData: DepartmentContactTableRow[] = items.map((item) => ({
    ...item,
    name_display: item.name || '-',
    department_display: item.department || '-',
    enterprise_email_display: item.enterprise_email || '-',
    department_head_name_display: item.department_head_name || '-',
  }))

  const openEdit = (record: DepartmentContact) => {
    setEditingRecord(record)
    setFormValues({
      open_id: record.open_id || undefined,
      department_head_open_id: record.department_head_open_id || undefined,
      department: record.department || '',
      enterprise_email: record.enterprise_email || '',
    })
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditingRecord(null)
  }

  const handleSubmit = async () => {
    if (!editingRecord) return
    const payload: UpdateFeishuDepartmentContactRequest = {
      open_id: formValues.open_id || null,
      department_head_open_id: formValues.department_head_open_id || null,
      department: formValues.department.trim() || null,
      enterprise_email: formValues.enterprise_email.trim() || null,
    }
    try {
      setSaving(true)
      await updateDepartmentContactFeishu(editingRecord.id, payload)
      message.success('部门联系人已更新')
      closeModal()
      router.refresh()
    } catch (error) {
      message.error(getErrorMessage(error, '更新部门联系人失败'))
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnsType<DepartmentContactTableRow> = [
    {
      title: '姓名',
      dataIndex: 'name_display',
      key: 'name',
      width: 220,
      render: (value: string, record) => (
        <PersonCell name={record.name} avatarUrl={record.avatar_url} />
      ),
    },
    {
      title: '部门',
      dataIndex: 'department_display',
      key: 'department',
      width: 260,
    },
    {
      title: '企业邮箱',
      dataIndex: 'enterprise_email_display',
      key: 'enterprise_email',
      width: 360,
    },
    {
      title: '上级负责人姓名',
      dataIndex: 'department_head_name_display',
      key: 'department_head_name',
      width: 240,
      render: (value: string, record) => (
        <PersonCell name={record.department_head_name} avatarUrl={record.department_head_avatar_url} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 90,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => openEdit(record)}>
          修改
        </Button>
      ),
    },
  ]

  return (
    <div style={{ padding: '4px 8px 20px' }}>
      <div style={{ maxWidth: 1680, margin: '0 auto' }}>
        <div style={{ marginBottom: 12 }}>
          <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>部门联系人台账</h1>
        </div>
        <div
          style={{
            marginBottom: 14,
            padding: '8px 12px',
            background: '#fff',
            border: '1px solid #f0f0f0',
            borderRadius: 10,
          }}
        >
          <Space wrap size={[6, 6]}>
            {departmentOptions.map((department) => {
              const active = activeDepartment === department
              return (
                <Button
                  key={department}
                  href={buildDepartmentContactsHref({ department, page: 1, pageSize })}
                  type="text"
                  size="small"
                  style={{
                    height: 28,
                    padding: '0 12px',
                    borderRadius: 999,
                    border: active ? '1px solid #6f5ef9' : '1px solid #d9d9d9',
                    background: active ? qualityTokens.brand : '#fff',
                    color: active ? '#fff' : '#262626',
                    fontSize: 12,
                    fontWeight: active ? 600 : 400,
                    boxShadow: active ? '0 3px 8px rgba(111, 94, 249, 0.16)' : 'none',
                  }}
                >
                  {department}
                </Button>
              )
            })}
          </Space>
        </div>
        <div
          style={{
            background: '#fff',
            borderRadius: 14,
            padding: 10,
            boxShadow: '0 6px 18px rgba(15, 23, 42, 0.05)',
          }}
        >
          <Table
            columns={columns}
            dataSource={tableData}
            rowKey="id"
            size="middle"
            scroll={{ x: 1400 }}
            pagination={false}
          />
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              marginTop: 12,
              flexWrap: 'wrap',
            }}
          >
            <div style={{ color: '#595959', fontSize: 13 }}>共 {total} 条</div>
            <Space wrap size={[6, 6]}>
              {[20, 50, 100].map((size) => {
                const active = pageSize === size
                return (
                  <Button
                    key={size}
                    href={buildDepartmentContactsHref({ department: activeDepartment, page: 1, pageSize: size })}
                    size="small"
                    type="text"
                    style={{
                      height: 28,
                      padding: '0 10px',
                      borderRadius: 999,
                      border: active ? '1px solid #6f5ef9' : '1px solid #d9d9d9',
                      background: active ? '#f3f0ff' : '#fff',
                      color: active ? qualityTokens.brand : '#595959',
                      fontSize: 12,
                    }}
                  >
                    {size}条/页
                  </Button>
                )
              })}
            </Space>
            <Space wrap size={[6, 6]}>
              <Button
                href={buildDepartmentContactsHref({
                  department: activeDepartment,
                  page: Math.max(1, page - 1),
                  pageSize,
                })}
                disabled={page <= 1}
                size="small"
              >
                上一页
              </Button>
              {visiblePages.map((pageNumber) => {
                const active = pageNumber === page
                return (
                  <Button
                    key={pageNumber}
                    href={buildDepartmentContactsHref({
                      department: activeDepartment,
                      page: pageNumber,
                      pageSize,
                    })}
                    size="small"
                    type={active ? 'primary' : 'default'}
                    style={active ? { background: qualityTokens.brand, borderColor: qualityTokens.brand } : undefined}
                  >
                    {pageNumber}
                  </Button>
                )
              })}
              <Button
                href={buildDepartmentContactsHref({
                  department: activeDepartment,
                  page: Math.min(totalPages, page + 1),
                  pageSize,
                })}
                disabled={page >= totalPages}
                size="small"
              >
                下一页
              </Button>
            </Space>
          </div>
        </div>
      </div>

      <Modal
        title={`修改联系人：${editingRecord?.name || '-'}`}
        open={modalOpen}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
        width={560}
      >
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 16, marginTop: 8 }}>
          <div>
            <div style={{ marginBottom: 6, color: '#262626', fontSize: 14, fontWeight: 500 }}>姓名</div>
            <PersonPickerSelect
              placeholder="搜索选择人员"
              value={formValues.open_id}
              onChange={(value) => setFormValues((prev) => ({ ...prev, open_id: value }))}
              currentPerson={{
                open_id: editingRecord?.open_id,
                name: editingRecord?.name,
                avatar_url: editingRecord?.avatar_url,
              }}
            />
          </div>
          <div>
            <div style={{ marginBottom: 6, color: '#262626', fontSize: 14, fontWeight: 500 }}>上级负责人</div>
            <PersonPickerSelect
              placeholder="搜索选择上级负责人"
              allowClear
              value={formValues.department_head_open_id}
              onChange={(value) => setFormValues((prev) => ({ ...prev, department_head_open_id: value }))}
              currentPerson={{
                open_id: editingRecord?.department_head_open_id,
                name: editingRecord?.department_head_name,
                avatar_url: editingRecord?.department_head_avatar_url,
              }}
            />
          </div>
          <div>
            <div style={{ marginBottom: 6, color: '#262626', fontSize: 14, fontWeight: 500 }}>部门</div>
            <Input
              placeholder="请输入部门"
              value={formValues.department}
              onChange={(e) => setFormValues((prev) => ({ ...prev, department: e.target.value }))}
            />
          </div>
          <div>
            <div style={{ marginBottom: 6, color: '#262626', fontSize: 14, fontWeight: 500 }}>企业邮箱</div>
            <Input
              placeholder="请输入企业邮箱"
              value={formValues.enterprise_email}
              onChange={(e) => setFormValues((prev) => ({ ...prev, enterprise_email: e.target.value }))}
            />
          </div>
        </div>
      </Modal>
    </div>
  )
}