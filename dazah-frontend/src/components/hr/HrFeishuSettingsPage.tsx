'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import {
  LinkOutlined,
  ReloadOutlined,
  SaveOutlined,
  SecurityScanOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  testHrFeishuAppSettings,
  testHrFeishuEntitySetting,
  updateEmailConfig,
  testEmailConfig,
  updateHrFeishuAppSettings,
  updateHrFeishuEntitySetting,
  browseFolderAction,
  uploadOfferTemplateAction,
} from '@/actions/hr'
import {
  fetchEmailConfig,
  fetchHrFeishuAppSettings,
  fetchHrFeishuEntityFieldMappingBundle,
  fetchHrFeishuEntitySettings,
  fetchHrFeishuEntityTables,
  formatHrFeishuTestSummary,
} from '@/lib/api/hr'
import type {
  HrFeishuAppSettingsDetail,
  HrFeishuEntityFieldMappingBundle,
  HrFeishuEntitySettingItem,
  HrFeishuFieldMappingItem,
  HrFeishuTableOption,
  UpdateHrFeishuAppSettingsRequest,
  UpdateHrFeishuEntitySettingRequest,
} from '@/types/hr'
import { parseFeishuBitableUrl } from '@/lib/feishu-url'

type EntityDraftMap = Record<string, UpdateHrFeishuEntitySettingRequest>
type EntityTableOptionsMap = Record<string, HrFeishuTableOption[]>
type ResultNotice = {
  type: 'success' | 'error' | 'info' | 'warning'
  title: string
  description?: string
} | null

const EMPTY_APP_FORM: UpdateHrFeishuAppSettingsRequest = {
  app_id: '',
  app_secret: '',
  is_enabled: true,
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function createEntityDraft(
  item: HrFeishuEntitySettingItem
): UpdateHrFeishuEntitySettingRequest {
  return {
    app_token: item.app_token || '',
    base_table_name: item.base_table_name || '',
    base_table_id: item.base_table_id || '',
    is_enabled: item.is_enabled,
    enable_push_to_feishu: item.enable_push_to_feishu,
    enable_pull_from_feishu: item.enable_pull_from_feishu,
    field_mappings: item.field_mappings || [],
  }
}

function renderStatusTag(value: string | null | undefined) {
  if (value === 'success') return <Tag color="success">正常</Tag>
  if (value === 'failed') return <Tag color="error">失败</Tag>
  return <Tag>未测试</Tag>
}

function getManualMappingFields(
  bundle: HrFeishuEntityFieldMappingBundle | null
): Array<{ field_key: string; field_label: string; direction: string }> {
  if (!bundle) return []
  const feishuFieldNames = new Set(
    bundle.feishu_fields.map((item) => item.field_name.trim()).filter(Boolean)
  )
  const savedMappings = new Map(
    bundle.field_mappings
      .filter((item) => item.feishu_field?.trim())
      .map((item) => [item.system_field, item.feishu_field!.trim()])
  )
  return bundle.system_fields.filter((field) => {
    const saved = savedMappings.get(field.field_key)
    if (saved) {
      return saved !== field.field_label
    }
    return !feishuFieldNames.has(field.field_label)
  })
}

export function HrFeishuSettingsPage() {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const [resultNotice, setResultNotice] = useState<ResultNotice>(null)
  const [appForm, setAppForm] = useState<UpdateHrFeishuAppSettingsRequest>(EMPTY_APP_FORM)
  const [entityDrafts, setEntityDrafts] = useState<EntityDraftMap>({})
  const [appSaving, setAppSaving] = useState(false)
  const [appTesting, setAppTesting] = useState(false)
  const [rowSaving, setRowSaving] = useState<Record<string, boolean>>({})
  const [rowTesting, setRowTesting] = useState<Record<string, boolean>>({})
  const [rowLoadingTables, setRowLoadingTables] = useState<Record<string, boolean>>({})
  const [rowTableOptions, setRowTableOptions] = useState<EntityTableOptionsMap>({})
  const [mappingOpen, setMappingOpen] = useState(false)
  const [mappingSaving, setMappingSaving] = useState(false)
  const [mappingEntityCode, setMappingEntityCode] = useState<string | null>(null)
  const [mappingDrafts, setMappingDrafts] = useState<Record<string, string>>({})
  // 分组展开状态（数据加载后默认全展开，避免因异步数据导致面板折叠）
  const [activeGroups, setActiveGroups] = useState<string[]>([])
  const [fillUrlEntityCode, setFillUrlEntityCode] = useState<string | null>(null)
  const [fillUrlValue, setFillUrlValue] = useState('')

  const [emailTestResult, setEmailTestResult] = useState<string | null>(null)
  const [emailTesting, setEmailTesting] = useState(false)
  const [emailSaving, setEmailSaving] = useState(false)
  const [emailForm] = Form.useForm()

  const emailQuery = useQuery({
    queryKey: ['email-config'],
    queryFn: fetchEmailConfig,
  })

  // 数据加载后同步到表单
  useEffect(() => {
    if (emailQuery.data?.data) {
      const d = emailQuery.data.data
      // 延迟确保 Form 已完全挂载（Collapse 内的字段延迟渲染）
      const timer = setTimeout(() => {
        emailForm.setFieldsValue({
          imap_host: d.imap_host || '',
          imap_port: d.imap_port || '993',
          imap_user: d.imap_user || '',
          imap_pass: '',
          smtp_host: d.smtp_host || '',
          smtp_port: d.smtp_port || '465',
          smtp_user: d.smtp_user || '',
          smtp_pass: '',
          from_addr: d.from_addr || '',
          fetch_enabled: d.fetch_enabled || false,
          watch_dir: d.watch_dir || 'data/hr/resumes',
          offer_subject: d.offer_subject || '录用通知 - {name}',
          offer_body: d.offer_body || '',
          reject_subject: d.reject_subject || '面试结果通知 - {name}',
          reject_body: d.reject_body || '',
        })
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [emailForm, emailQuery.data])

  const appQuery = useQuery<HrFeishuAppSettingsDetail>({
    queryKey: ['hr-feishu-settings', 'app'],
    queryFn: fetchHrFeishuAppSettings,
  })

  const entitiesQuery = useQuery<HrFeishuEntitySettingItem[]>({
    queryKey: ['hr-feishu-settings', 'entities'],
    queryFn: fetchHrFeishuEntitySettings,
  })

  const appSettings = appQuery.data ?? null
  const entityItems = useMemo(() => entitiesQuery.data ?? [], [entitiesQuery.data])
  const loading = appQuery.isLoading || entitiesQuery.isLoading
  const loadError = appQuery.error instanceof Error
    ? appQuery.error.message
    : entitiesQuery.error instanceof Error
      ? entitiesQuery.error.message
      : null

  useEffect(() => {
    if (appQuery.data) {
      queueMicrotask(() => {
        setAppForm({
          app_id: appQuery.data?.app_id || '',
          app_secret: '',
          is_enabled: appQuery.data?.is_enabled ?? false,
        })
      })
    }
  }, [appQuery.data])

  useEffect(() => {
    if (entitiesQuery.data) {
      queueMicrotask(() => {
        setEntityDrafts(
          (entitiesQuery.data ?? []).reduce<EntityDraftMap>((acc, item) => {
            acc[item.entity_code] = createEntityDraft(item)
            return acc
          }, {}),
        )
        setRowTableOptions({})
      })
    }
  }, [entitiesQuery.data])

  const mappingBundleParams = useMemo(() => ({
    app_token: (mappingEntityCode ? entityDrafts[mappingEntityCode]?.app_token : '') || '',
    table_id: (mappingEntityCode ? entityDrafts[mappingEntityCode]?.base_table_id : '') || '',
  }), [mappingEntityCode, entityDrafts])

  const mappingQuery = useQuery<HrFeishuEntityFieldMappingBundle>({
    queryKey: ['hr-feishu-settings', 'field-mapping', mappingEntityCode, mappingBundleParams],
    queryFn: () => fetchHrFeishuEntityFieldMappingBundle(mappingEntityCode!, mappingBundleParams),
    enabled: mappingOpen && !!mappingEntityCode,
  })

  const mappingBundle = mappingQuery.data ?? null
  const mappingLoading = mappingQuery.isLoading

  useEffect(() => {
    if (mappingQuery.error && mappingOpen) {
      const description = mappingQuery.error instanceof Error
        ? mappingQuery.error.message
        : '读取字段对齐配置失败'
      queueMicrotask(() => {
        setMappingOpen(false)
        setResultNotice({ type: 'error', title: '读取字段对齐配置失败', description })
        message.error(description)
      })
    }
  }, [mappingQuery.error, mappingOpen, message])

  useEffect(() => {
    if (mappingBundle) {
      queueMicrotask(() =>
        setMappingDrafts(
          mappingBundle.field_mappings.reduce<Record<string, string>>((acc, item) => {
            acc[item.system_field] = item.feishu_field || ''
            return acc
          }, {}),
        ),
      )
    }
  }, [mappingBundle])

  const patchEntityDraft = useCallback(
    (entityCode: string, patch: Partial<UpdateHrFeishuEntitySettingRequest>) => {
      setEntityDrafts((current) => ({
        ...current,
        [entityCode]: {
          ...(current[entityCode] || {
            app_token: '',
            base_table_name: '',
            base_table_id: '',
            is_enabled: false,
            enable_push_to_feishu: false,
            enable_pull_from_feishu: false,
            field_mappings: [],
          }),
          ...patch,
        },
      }))
    },
    []
  )

  const handleSaveApp = useCallback(async () => {
    try {
      setAppSaving(true)
      await updateHrFeishuAppSettings({ ...appForm, app_id: appForm.app_id.trim() })
      setAppForm((current) => ({ ...current, app_secret: '' }))
      setResultNotice({ type: 'success', title: '飞书应用配置已保存' })
      message.success('飞书应用配置已保存')
      queryClient.invalidateQueries({ queryKey: ['hr-feishu-settings', 'app'] })
    } catch (error) {
      const description = error instanceof Error ? (error instanceof Error ? error.message : '') : '保存飞书应用配置失败'
      setResultNotice({ type: 'error', title: '保存飞书应用配置失败', description })
      message.error(error instanceof Error ? (error instanceof Error ? error.message : '') : '保存飞书应用配置失败')
    } finally {
      setAppSaving(false)
    }
  }, [appForm, message, queryClient])

  const handleTestApp = useCallback(async () => {
    try {
      setAppTesting(true)
      const result = await testHrFeishuAppSettings() as { success?: boolean; message?: string }
      if (result?.success) {
        setResultNotice({ type: 'success', title: '飞书应用连接测试成功', description: formatHrFeishuTestSummary(result) })
        message.success(formatHrFeishuTestSummary(result))
      } else {
        setResultNotice({ type: 'warning', title: '飞书应用连接测试未通过', description: formatHrFeishuTestSummary(result) })
        message.error(formatHrFeishuTestSummary(result))
      }
      queryClient.invalidateQueries({ queryKey: ['hr-feishu-settings', 'app'] })
    } catch (error) {
      const description = error instanceof Error ? (error instanceof Error ? error.message : '') : '测试飞书应用连接失败'
      setResultNotice({ type: 'error', title: '测试飞书应用连接失败', description })
      message.error(error instanceof Error ? (error instanceof Error ? error.message : '') : '测试飞书应用连接失败')
    } finally {
      setAppTesting(false)
    }
  }, [message, queryClient])

  const handleSaveEntity = useCallback(
    async (entityCode: string) => {
      try {
        setRowSaving((current) => ({ ...current, [entityCode]: true }))
        const draft = entityDrafts[entityCode]
        if (!draft) return
        const result = await updateHrFeishuEntitySetting(entityCode, {
          ...draft,
          base_table_name: draft.base_table_name?.trim() || '',
          base_table_id: draft.base_table_id?.trim() || '',
        }) as { entity_name?: string } | null
        if (!result) return
        setResultNotice({ type: 'success', title: `${result.entity_name} 配置已保存` })
        message.success(`${result.entity_name} 配置已保存`)
        queryClient.invalidateQueries({ queryKey: ['hr-feishu-settings', 'entities'] })
      } catch (error) {
        const description = error instanceof Error ? (error instanceof Error ? error.message : '') : '保存实体配置失败'
        setResultNotice({ type: 'error', title: '保存实体配置失败', description })
        message.error(error instanceof Error ? (error instanceof Error ? error.message : '') : '保存实体配置失败')
      } finally {
        setRowSaving((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [entityDrafts, message, queryClient]
  )

  const handleTestEntity = useCallback(
    async (entityCode: string, entityName: string) => {
      try {
        setRowTesting((current) => ({ ...current, [entityCode]: true }))
        const result = await testHrFeishuEntitySetting(entityCode) as { success?: boolean; message?: string }
        if (result?.success) {
          setResultNotice({ type: 'success', title: `${entityName} 连接测试成功`, description: formatHrFeishuTestSummary(result) })
          message.success(formatHrFeishuTestSummary(result))
        } else {
          setResultNotice({ type: 'warning', title: `${entityName} 连接测试未通过`, description: formatHrFeishuTestSummary(result) })
          message.error(formatHrFeishuTestSummary(result))
        }
        queryClient.invalidateQueries({ queryKey: ['hr-feishu-settings', 'entities'] })
      } catch (error) {
        const description = error instanceof Error ? (error instanceof Error ? error.message : '') : `${entityName} 连接测试失败`
        setResultNotice({ type: 'error', title: `${entityName} 连接测试失败`, description })
        message.error(error instanceof Error ? (error instanceof Error ? error.message : '') : `${entityName} 连接测试失败`)
      } finally {
        setRowTesting((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [message, queryClient]
  )

  const openFieldMapping = useCallback((record: HrFeishuEntitySettingItem) => {
    setMappingEntityCode(record.entity_code)
    setMappingOpen(true)
  }, [])

  const openFillUrl = useCallback((entityCode: string) => {
    setFillUrlValue('')
    setFillUrlEntityCode(entityCode)
  }, [])

  const handleFillFromUrl = useCallback(() => {
    if (!fillUrlEntityCode) return
    const url = fillUrlValue.trim()
    if (!url) {
      message.warning('请先粘贴多维表格网址')
      return
    }
    const parsed = parseFeishuBitableUrl(url)
    if (!parsed) {
      message.error('无法识别该网址，请检查格式')
      return
    }
    patchEntityDraft(fillUrlEntityCode, {
      app_token: parsed.app_token,
      base_table_id: parsed.table_id,
    })
    message.success('已填充 App Token 和 Table ID，请确认后点击保存')
    setFillUrlEntityCode(null)
    setFillUrlValue('')
  }, [fillUrlEntityCode, fillUrlValue, message, patchEntityDraft])

  const saveFieldMapping = useCallback(async () => {
    if (!mappingBundle) return
    try {
      setMappingSaving(true)
      const currentDraft = entityDrafts[mappingBundle.entity_code]
      if (!currentDraft) return
      const fieldMappings: HrFeishuFieldMappingItem[] = getManualMappingFields(mappingBundle)
        .map((item) => ({
          system_field: item.field_key,
          feishu_field: mappingDrafts[item.field_key] || null,
        }))
        .filter((item) => item.feishu_field)
      const result = await updateHrFeishuEntitySetting(mappingBundle.entity_code, {
        ...currentDraft,
        field_mappings: fieldMappings,
      })
      if (!result) return
      setResultNotice({ type: 'success', title: `${mappingBundle.entity_name} 字段对齐已保存` })
      setMappingOpen(false)
      message.success(`${mappingBundle.entity_name} 字段对齐已保存`)
      queryClient.invalidateQueries({ queryKey: ['hr-feishu-settings', 'entities'] })
    } catch (error) {
      setResultNotice({ type: 'error', title: '保存字段对齐配置失败', description: error instanceof Error ? (error instanceof Error ? error.message : '') : '保存字段对齐配置失败' })
      message.error(error instanceof Error ? (error instanceof Error ? error.message : '') : '保存字段对齐配置失败')
    } finally {
      setMappingSaving(false)
    }
  }, [entityDrafts, mappingBundle, mappingDrafts, message, queryClient])

  const manualMappingFields = useMemo(() => getManualMappingFields(mappingBundle), [mappingBundle])

  const handleLoadTables = useCallback(
    async (entityCode: string) => {
      try {
        setRowLoadingTables((current) => ({ ...current, [entityCode]: true }))
        const tables = await fetchHrFeishuEntityTables(entityCode, entityDrafts[entityCode]?.app_token || '')
        setRowTableOptions((current) => ({ ...current, [entityCode]: tables }))
        setResultNotice({ type: 'success', title: '飞书表列表读取成功', description: `已读取 ${tables.length} 张表` })
        message.success(`已读取 ${tables.length} 张表`)
      } catch (error) {
        setResultNotice({ type: 'error', title: '读取飞书表列表失败', description: error instanceof Error ? (error instanceof Error ? error.message : '') : '读取飞书表列表失败' })
        message.error(error instanceof Error ? (error instanceof Error ? error.message : '') : '读取飞书表列表失败')
      } finally {
        setRowLoadingTables((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [entityDrafts, message]
  )

  const handleEmailSave = async (values: Record<string, unknown>) => {
    setEmailSaving(true)
    try {
      // 确保 fetch_interval_hours 是数字类型
      const payload = { ...values }
      if (payload.fetch_interval_hours !== undefined && payload.fetch_interval_hours !== null) {
        payload.fetch_interval_hours = Number(payload.fetch_interval_hours)
      }
      await updateEmailConfig(payload)
      message.success('邮箱配置保存成功')
      emailQuery.refetch()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '保存失败')
    } finally {
      setEmailSaving(false)
    }
  }

  const handleEmailTest = async () => {
    setEmailTesting(true)
    setEmailTestResult(null)
    try {
      const res = await testEmailConfig()
      const results = res.data || {}
      setEmailTestResult(`IMAP: ${results.imap || '未测试'} | SMTP: ${results.smtp || '未测试'}`)
      message.success('测试完成')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '测试失败')
    } finally {
      setEmailTesting(false)
    }
  }

  const [browsing, setBrowsing] = useState(false)
  const handleBrowseFolder = async () => {
    setBrowsing(true)
    try {
      const json = await browseFolderAction()
      if (json.data?.path) {
        emailForm.setFieldValue('watch_dir', json.data.path)
        message.success('已选择: ' + json.data.path)
      } else if (json.data?.error) {
        message.warning('对话框未能打开: ' + json.data.error)
      }
    } catch {
      message.error('打开文件夹对话框失败')
    } finally {
      setBrowsing(false)
    }
  }

  const groupedEntities = useMemo(() => {
    const groups: Record<string, HrFeishuEntitySettingItem[]> = {}
    for (const item of entityItems) {
      const group = item.entity_group || '未分组'
      if (!groups[group]) groups[group] = []
      groups[group].push(item)
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b, 'zh-CN'))
  }, [entityItems])

  // 数据加载后默认展开全部分组（defaultActiveKey 依赖异步数据时首次渲染为空，会导致面板折叠）
  useEffect(() => {
    if (groupedEntities.length > 0) {
      queueMicrotask(() => {
        setActiveGroups(groupedEntities.map(([group]) => group))
      })
    }
  }, [groupedEntities])

  const columns = useMemo(
    () => [
      {
        title: '实体',
        dataIndex: 'entity_name',
        key: 'entity_name',
        width: 180,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Space orientation="vertical" size={2}>
            <Typography.Text>{record.entity_name}</Typography.Text>
            {record.source_note ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{record.source_note}</Typography.Text>
            ) : null}
          </Space>
        ),
      },
      {
        title: 'App Token',
        key: 'app_token',
        width: 220,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Input
            value={entityDrafts[record.entity_code]?.app_token || ''}
            placeholder="例如：bascnxxxxxxxx"
            onChange={(event) => patchEntityDraft(record.entity_code, { app_token: event.target.value })}
          />
        ),
      },
      {
        title: 'Base 表名称',
        key: 'base_table_name',
        width: 220,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Select
            showSearch
            allowClear
            placeholder="可读取后直接选择"
            value={entityDrafts[record.entity_code]?.base_table_name || undefined}
            options={(rowTableOptions[record.entity_code] || []).map((item) => ({
              label: item.table_name,
              value: item.table_name,
            }))}
            onChange={(value) => {
              const option = (rowTableOptions[record.entity_code] || []).find((item) => item.table_name === value)
              patchEntityDraft(record.entity_code, {
                base_table_name: value || '',
                base_table_id: option?.table_id || entityDrafts[record.entity_code]?.base_table_id || '',
              })
            }}
            onClear={() => patchEntityDraft(record.entity_code, { base_table_name: '' })}
          />
        ),
      },
      {
        title: 'Base Table ID',
        key: 'base_table_id',
        width: 200,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Input
            value={entityDrafts[record.entity_code]?.base_table_id || ''}
            placeholder="例如：tblxxxxxxxx"
            onChange={(event) => patchEntityDraft(record.entity_code, { base_table_id: event.target.value })}
          />
        ),
      },
      {
        title: '启用',
        key: 'is_enabled',
        width: 80,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.is_enabled || false}
            onChange={(checked) => patchEntityDraft(record.entity_code, { is_enabled: checked })}
          />
        ),
      },
      {
        title: '推送',
        key: 'enable_push_to_feishu',
        width: 80,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.enable_push_to_feishu || false}
            onChange={(checked) => patchEntityDraft(record.entity_code, { enable_push_to_feishu: checked })}
          />
        ),
      },
      {
        title: '回拉',
        key: 'enable_pull_from_feishu',
        width: 80,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.enable_pull_from_feishu || false}
            onChange={(checked) => patchEntityDraft(record.entity_code, { enable_pull_from_feishu: checked })}
          />
        ),
      },
      {
        title: '最近状态',
        key: 'last_status',
        width: 180,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Space orientation="vertical" size={2}>
            {renderStatusTag(record.last_sync_status)}
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              最近测试：{formatDateTime(record.last_synced_at)}
            </Typography.Text>
          </Space>
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 260,
        fixed: 'right' as const,
        render: (_: unknown, record: HrFeishuEntitySettingItem) => (
          <Space>
            <Button size="small" icon={<LinkOutlined />} onClick={() => void openFillUrl(record.entity_code)}>
              URL填充
            </Button>
            <Button size="small" loading={rowLoadingTables[record.entity_code]} onClick={() => void handleLoadTables(record.entity_code)}>
              读取表
            </Button>
            <Button size="small" onClick={() => void openFieldMapping(record)}>
              字段对齐
            </Button>
            <Button size="small" type="primary" icon={<SaveOutlined />} loading={rowSaving[record.entity_code]} onClick={() => void handleSaveEntity(record.entity_code)}>
              保存
            </Button>
            <Button size="small" icon={<SecurityScanOutlined />} loading={rowTesting[record.entity_code]} onClick={() => void handleTestEntity(record.entity_code, record.entity_name)}>
              测试
            </Button>
          </Space>
        ),
      },
    ],
    [entityDrafts, handleLoadTables, handleSaveEntity, handleTestEntity, openFillUrl, patchEntityDraft, rowLoadingTables, rowSaving, rowTableOptions, rowTesting]
  )

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 8 }}>HR设置</Typography.Title>
        <Typography.Text type="secondary">
          在这里统一维护人事模块的飞书应用、邮箱通道、推送模板/接收人，以及手动执行连接测试。
        </Typography.Text>
      </div>

      {loadError ? (
        <Alert type="error" showIcon title="飞书设置加载失败" description={loadError} />
      ) : null}
      {resultNotice ? (
        <Alert
          type={resultNotice.type}
          showIcon
          closable
          onClose={() => setResultNotice(null)}
          title={resultNotice.title}
          description={resultNotice.description}
        />
      ) : null}

      <Card
        title="飞书应用信息"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => queryClient.invalidateQueries({ queryKey: ['hr-feishu-settings'] })} loading={loading}>
              刷新
            </Button>
            <Button icon={<SecurityScanOutlined />} onClick={() => void handleTestApp()} loading={appTesting}>
              测试连接
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={() => void handleSaveApp()} loading={appSaving}>
              保存配置
            </Button>
          </Space>
        }
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>App ID</Button>
            <Input
              value={appForm.app_id}
              placeholder="请输入飞书应用 App ID"
              onChange={(event) => setAppForm((current) => ({ ...current, app_id: event.target.value }))}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>App Secret</Button>
            <Input.Password
              value={appForm.app_secret}
              placeholder={appSettings?.app_secret_masked || '留空则保持当前 Secret 不变'}
              onChange={(event) => setAppForm((current) => ({ ...current, app_secret: event.target.value }))}
              onCopy={(e) => e.preventDefault()}
              onCut={(e) => e.preventDefault()}
            />
          </Space.Compact>
          <Space size={12}>
            <Typography.Text>启用飞书同步</Typography.Text>
            <Switch checked={appForm.is_enabled} onChange={(checked) => setAppForm((current) => ({ ...current, is_enabled: checked }))} />
            {renderStatusTag(appSettings?.last_test_status)}
            <Typography.Text type="secondary">最近测试：{formatDateTime(appSettings?.last_tested_at)}</Typography.Text>
          </Space>
          {appSettings?.last_test_error ? (
            <Alert type="warning" showIcon title={appSettings.last_test_error} />
          ) : null}
        </Space>
      </Card>

      <Card title="人事实体同步配置">
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Alert
            type="info"
            showIcon
            title="配置说明"
            description="顶部维护飞书应用的 App ID 和 App Secret；每个实体单独维护自己的 App Token 和 Table ID。填入 App Token 后可直接点击「读取表」辅助选择。"
          />
          <Collapse
            activeKey={activeGroups}
            onChange={(keys) => setActiveGroups(keys as string[])}
            items={groupedEntities.map(([group, items]) => ({
              key: group,
              label: (
                <Space>
                  <Typography.Text strong>{group}</Typography.Text>
                  <Tag color="blue">{items.length}</Tag>
                </Space>
              ),
              children: (
                <Table<HrFeishuEntitySettingItem>
                  rowKey="entity_code"
                  loading={loading}
                  columns={columns}
                  dataSource={items}
                  pagination={false}
                  scroll={{ x: 1500 }}
                  size="small"
                />
              ),
            }))}
          />
        </Space>
      </Card>

      <Modal
        title="多维表格 URL 填充"
        open={!!fillUrlEntityCode}
        onCancel={() => setFillUrlEntityCode(null)}
        onOk={() => void handleFillFromUrl()}
        okText="填充"
        cancelText="取消"
      >
        <div className="mb-2 text-[13px] text-gray-500">
          粘贴飞书多维表格网址（https://xxx.feishu.cn/base/xxx?table=xxx），自动填充本行的 App Token 和 Table ID。
        </div>
        <Input
          placeholder="https://xxx.feishu.cn/base/bascnxxx?table=tblxxx"
          value={fillUrlValue}
          onChange={(e) => setFillUrlValue(e.target.value)}
          onPressEnter={() => void handleFillFromUrl()}
        />
      </Modal>

      <Drawer
        title={mappingBundle ? `${mappingBundle.entity_name} 字段对齐` : '字段对齐'}
        open={mappingOpen}
        size="large"
        onClose={() => setMappingOpen(false)}
        extra={
          <Space>
            <Button onClick={() => setMappingOpen(false)}>关闭</Button>
            <Button type="primary" loading={mappingSaving} onClick={() => void saveFieldMapping()}>
              保存字段对齐
            </Button>
          </Space>
        }
      >
        {mappingLoading ? (
          <Typography.Text type="secondary">正在读取字段信息...</Typography.Text>
        ) : mappingBundle ? (
          <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
            <Alert
              type="info"
              showIcon
              title="这里只维护需要人工指定的字段别名"
              description="飞书字段名与系统字段名完全一致的部分，系统会按各模块代码里的默认字段直接同步；这里只展示名称不一致、需要你手工指定映射的字段。"
            />
            {manualMappingFields.length ? (
              <Table
                rowKey="field_key"
                pagination={false}
                dataSource={manualMappingFields}
                columns={[
                  { title: '系统字段', dataIndex: 'field_label', key: 'field_label', width: 220 },
                  {
                    title: '方向',
                    dataIndex: 'direction',
                    key: 'direction',
                    width: 100,
                    render: (value: string) => {
                      if (value === 'push') return <Tag color="blue">推送</Tag>
                      if (value === 'pull') return <Tag color="green">回拉</Tag>
                      return <Tag color="purple">双向</Tag>
                    },
                  },
                  {
                    title: '飞书字段',
                    key: 'feishu_field',
                    render: (_: unknown, record: { field_key: string }) => (
                      <Select
                        showSearch
                        allowClear
                        placeholder="请选择飞书字段"
                        value={mappingDrafts[record.field_key] || undefined}
                        options={mappingBundle.feishu_fields.map((item) => ({
                          label: item.field_name,
                          value: item.field_name,
                        }))}
                        onChange={(value) =>
                          setMappingDrafts((current) => ({ ...current, [record.field_key]: value || '' }))
                        }
                      />
                    ),
                  },
                ]}
              />
            ) : (
              <Alert
                type="success"
                showIcon
                title="当前实体没有需要手工配置的字段别名"
                description="同名字段会按模块里现有代码直接同步，不需要再额外维护字段映射。"
              />
            )}
          </Space>
        ) : (
          <Alert type="warning" showIcon title="未读取到字段对齐信息" />
        )}
      </Drawer>
      <Card
        size="small"
        title="邮箱通道配置"
        extra={
          <Space>
            <Button size="small" icon={<SecurityScanOutlined />} onClick={handleEmailTest} loading={emailTesting}>测试连接</Button>
          </Space>
        }
        style={{ marginTop: 16 }}
      >
        <div className="text-xs text-gray-400 mb-3">
          配置后系统将每10分钟自动扫描收件箱中的简历PDF附件，自动完成AI分析并写入候选人表
        </div>
        <Form
          layout="vertical"
          size="small"
          form={emailForm}
          onFinish={handleEmailSave}
          initialValues={{
            imap_host: emailQuery.data?.data?.imap_host || '',
            imap_port: emailQuery.data?.data?.imap_port || '993',
            imap_user: emailQuery.data?.data?.imap_user || '',
            imap_pass: '',
            smtp_host: emailQuery.data?.data?.smtp_host || '',
            smtp_port: emailQuery.data?.data?.smtp_port || '465',
            smtp_user: emailQuery.data?.data?.smtp_user || '',
            smtp_pass: '',
            from_addr: emailQuery.data?.data?.from_addr || '',
            fetch_enabled: emailQuery.data?.data?.fetch_enabled || false,
            fetch_interval_hours: emailQuery.data?.data?.fetch_interval_hours || 1,
            fetch_schedule_hours: emailQuery.data?.data?.fetch_schedule_hours || [],
            watch_dir: emailQuery.data?.data?.watch_dir || 'data/hr/resumes',
          }}
        >
          <Collapse
            defaultActiveKey={['imap', 'smtp', 'storage']}
            ghost
            items={[
              {
                key: 'imap',
                label: <span style={{ fontWeight: 600, color: '#1677ff' }}>收件设置（IMAP）- 简历抓取</span>,
                children: (
                  <div style={{ maxWidth: 480 }}>
                    <Form.Item name="imap_host" label="IMAP 服务器" rules={[{ required: true }]}>
                      <Input placeholder="imap.qq.com" />
                    </Form.Item>
                    <Form.Item name="imap_port" label="端口">
                      <Input placeholder="993" />
                    </Form.Item>
                    <Form.Item name="imap_user" label="邮箱地址" rules={[{ required: true }]}>
                      <Input placeholder="hr@公司.com" />
                    </Form.Item>
                    <Form.Item name="imap_pass" label="授权码" extra="已保存的授权码不会回显">
                      <Input.Password placeholder="保持为空则不修改" autoComplete="off" onCopy={(e) => e.preventDefault()} onCut={(e) => e.preventDefault()} />
                    </Form.Item>
                  </div>
                ),
              },
              {
                key: 'smtp',
                label: <span style={{ fontWeight: 600, color: '#1677ff' }}>发件设置（SMTP）- 邮件推送</span>,
                children: (
                  <div style={{ maxWidth: 480 }}>
                    <Form.Item name="smtp_host" label="SMTP 服务器" rules={[{ required: true }]}>
                      <Input placeholder="smtp.qq.com" />
                    </Form.Item>
                    <Form.Item name="smtp_port" label="端口">
                      <Input placeholder="465" />
                    </Form.Item>
                    <Form.Item name="smtp_user" label="发件邮箱" rules={[{ required: true }]}>
                      <Input placeholder="通常与收件邮箱相同" />
                    </Form.Item>
                    <Form.Item name="smtp_pass" label="授权码">
                      <Input.Password placeholder="保持为空则不修改" autoComplete="off" onCopy={(e) => e.preventDefault()} onCut={(e) => e.preventDefault()} />
                    </Form.Item>
                    <Form.Item name="from_addr" label="发件人名称">
                      <Input placeholder="HR部 <hr@公司.com>" />
                    </Form.Item>
                  </div>
                ),
              },
              {
                key: 'storage',
                label: <span style={{ fontWeight: 600, color: '#1677ff' }}>本地存储与自动抓取</span>,
                children: (
                  <div style={{ maxWidth: 480 }}>
                    <Form.Item name="watch_dir" label="简历下载文件夹路径" extra="抓取的简历PDF将保存到此文件夹，处理成功并上传飞书后自动删除">
                      <Space.Compact block>
                        <Input placeholder="data/hr/resumes" />
                        <Button loading={browsing} onClick={handleBrowseFolder}>浏览…</Button>
                      </Space.Compact>
                    </Form.Item>
                    <Form.Item name="fetch_enabled" label="启用自动抓取" valuePropName="checked" extra="开启后按设定时间自动扫描收件箱下载简历附件">
                      <Switch />
                    </Form.Item>
                    <Form.Item name="fetch_schedule_hours" label="定时抓取时间" extra="选择每天自动抓取的小时（0-23），不选则按间隔时间抓取">
                      <Select
                        mode="multiple"
                        placeholder="选择小时，如 9, 10, 14"
                        style={{ width: '100%' }}
                        options={Array.from({ length: 24 }, (_, i) => ({ value: i, label: `${i}:00` }))}
                      />
                    </Form.Item>
                    <Form.Item name="fetch_interval_hours" label="抓取间隔（小时）" extra="未设置定时时间时生效，默认1小时，最大48小时">
                      <Input type="number" min={1} max={48} placeholder="1" />
                    </Form.Item>
                  </div>
                ),
              },
            ]}
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12 }}>
            {emailTestResult && <Tag color="blue">{emailTestResult}</Tag>}
          </div>

          {/* 邮件模板配置 */}
          <Card title="邮件模板配置" size="small" style={{ marginTop: 16 }}>
          <Collapse
            defaultActiveKey={['offer', 'reject']}
            ghost
            items={[
              {
                key: 'offer',
                label: <span style={{ fontWeight: 600, color: '#1677ff' }}>Offer 录用通知邮件</span>,
                children: (
                  <div style={{ maxWidth: 480 }}>
                    <Form.Item name="offer_subject" label="邮件标题">
                      <Input placeholder="录用通知 - {name}" />
                    </Form.Item>
                    <Form.Item name="offer_body" label="邮件正文（HTML）">
                      <Input.TextArea rows={12} placeholder="<h2>录用通知书</h2>..." />
                    </Form.Item>
                    <Form.Item label="录用通知书 PDF 附件">
                      <Upload
                        accept=".pdf"
                        maxCount={1}
                        customRequest={async (options) => {
                          const formData = new FormData()
                          formData.append('file', options.file as File)
                          try {
                            const res = await uploadOfferTemplateAction(formData)
                            message.success('PDF 模板上传成功')
                            options.onSuccess?.(res)
                          } catch (err) {
                            message.error((err instanceof Error ? err.message : '') || '上传失败')
                            options.onError?.(
                              err instanceof Error ? err : new Error('上传失败'),
                            )
                          }
                        }}
                      >
                        <Button icon={<UploadOutlined />}>上传 PDF 模板</Button>
                      </Upload>
                      <div style={{ marginTop: 8 }}>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          上传的 PDF 将作为附件随 Offer 邮件一起发送
                        </Typography.Text>
                      </div>
                    </Form.Item>
                  </div>
                ),
              },
              {
                key: 'reject',
                label: <span style={{ fontWeight: 600, color: '#ff4d4f' }}>不符合拒绝邮件</span>,
                children: (
                  <div style={{ maxWidth: 480 }}>
                    <Form.Item name="reject_subject" label="邮件标题">
                      <Input placeholder="面试结果通知 - {name}" />
                    </Form.Item>
                    <Form.Item name="reject_body" label="邮件正文（HTML）">
                      <Input.TextArea rows={12} placeholder="<h2>面试结果通知</h2>..." />
                    </Form.Item>
                  </div>
                ),
              },
            ]}
          />
          <div style={{ marginTop: 12 }}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              可用变量：{'{name}'} 姓名、{'{position}'} 职位、{'{department}'} 部门、{'{interview_time}'} 面试时间、{'{onboard_date}'} 入职日期
            </Typography.Text>
          </div>
          </Card>

          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12 }}>
            <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={emailSaving}>保存邮箱配置</Button>
          </div>
        </Form>
      </Card>
    </Space>
  )
}
