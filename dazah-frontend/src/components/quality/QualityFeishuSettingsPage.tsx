'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Card,
  Collapse,
  Drawer,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  CloudDownloadOutlined,
  LinkOutlined,
  ReloadOutlined,
  SaveOutlined,
  SecurityScanOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { parseFeishuBaseUrl, parseFeishuBitableUrl } from '@/lib/feishu-url'
import { pullQualityRecordsFromFeishu, testQualityFeishuAppSettings, testQualityFeishuEntitySetting, updateQualityFeishuAppSettings, updateQualityFeishuEntitySetting } from '@/actions/quality'
import { fetchQualityFeishuAppSettings, fetchQualityFeishuEntityFieldMappingBundle, fetchQualityFeishuEntitySettings, fetchQualityFeishuEntityTables, formatQualityFeishuTestSummary, formatQualitySyncSummary } from '@/lib/api/client/quality'
import type {
  QualityFeishuAppSettingsDetail,
  QualityFeishuEntityFieldMappingBundle,
  QualityFeishuEntitySettingItem,
  QualityFeishuFieldMappingItem,
  QualityFeishuTableOption,
  UpdateQualityFeishuAppSettingsRequest,
  UpdateQualityFeishuEntitySettingRequest,
} from '@/types/quality'

type EntityDraftMap = Record<string, UpdateQualityFeishuEntitySettingRequest>
type EntityTableOptionsMap = Record<string, QualityFeishuTableOption[]>
type ResultNotice = {
  type: 'success' | 'error' | 'info' | 'warning'
  title: string
  description?: string
} | null

const EMPTY_APP_FORM: UpdateQualityFeishuAppSettingsRequest = {
  app_id: '',
  app_secret: '',
  is_enabled: true,
  deviation_report_form_url: '',
  deviation_investigation_push_form_url: '',
  oos_oot_report_form_url: '',
  oos_oot_investigation_push_form_url: '',
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN')
}

function createEntityDraft(
  item: QualityFeishuEntitySettingItem
): UpdateQualityFeishuEntitySettingRequest {
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
  bundle: QualityFeishuEntityFieldMappingBundle | null
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

/** 按名称匹配子表：优先精确匹配（实体名/已配置表名 === 子表名），其次包含匹配 */
function matchTableForEntity(
  entity: QualityFeishuEntitySettingItem,
  tables: QualityFeishuTableOption[]
): QualityFeishuTableOption | undefined {
  const names = [entity.entity_name, entity.base_table_name].filter(Boolean) as string[]
  if (names.length === 0) return undefined
  // 1. 精确匹配
  const exact = tables.find((t) => names.includes(t.table_name))
  if (exact) return exact
  // 2. 包含匹配（实体名包含在子表名中，或子表名包含在实体名中）
  return tables.find((t) => names.some((n) => t.table_name.includes(n) || n.includes(t.table_name)))
}

export function QualityFeishuSettingsPage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [resultNotice, setResultNotice] = useState<ResultNotice>(null)
  const [appForm, setAppForm] = useState<UpdateQualityFeishuAppSettingsRequest>(EMPTY_APP_FORM)
  const [entityDrafts, setEntityDrafts] = useState<EntityDraftMap>({})
  const [appSaving, setAppSaving] = useState(false)
  const [appTesting, setAppTesting] = useState(false)
  const [pulling, setPulling] = useState(false)
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
  // 每个分组的 URL 批量更新输入（key = 分组名）
  const [groupUrlInputs, setGroupUrlInputs] = useState<Record<string, string>>({})
  const [batchLoading, setBatchLoading] = useState(false)

  const appQuery = useQuery<QualityFeishuAppSettingsDetail>({
    queryKey: ['quality-feishu-settings', 'app'],
    queryFn: fetchQualityFeishuAppSettings,
  })

  const entitiesQuery = useQuery<QualityFeishuEntitySettingItem[]>({
    queryKey: ['quality-feishu-settings', 'entities'],
    queryFn: fetchQualityFeishuEntitySettings,
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
      setAppForm({
        app_id: appQuery.data.app_id || '',
        app_secret: '',
        is_enabled: appQuery.data.is_enabled,
        deviation_report_form_url: appQuery.data.deviation_report_form_url || '',
        deviation_investigation_push_form_url: appQuery.data.deviation_investigation_push_form_url || '',
        oos_oot_report_form_url: appQuery.data.oos_oot_report_form_url || '',
        oos_oot_investigation_push_form_url: appQuery.data.oos_oot_investigation_push_form_url || '',
      })
    }
  }, [appQuery.data])

  useEffect(() => {
    if (entitiesQuery.data) {
      setEntityDrafts(
        entitiesQuery.data.reduce<EntityDraftMap>((acc, item) => {
          acc[item.entity_code] = createEntityDraft(item)
          return acc
        }, {})
      )
      setRowTableOptions({})
    }
  }, [entitiesQuery.data])

  const mappingBundleParams = useMemo(() => ({
    app_token: (mappingEntityCode ? entityDrafts[mappingEntityCode]?.app_token : '') || '',
    table_id: (mappingEntityCode ? entityDrafts[mappingEntityCode]?.base_table_id : '') || '',
  }), [mappingEntityCode, entityDrafts])

  const mappingQuery = useQuery<QualityFeishuEntityFieldMappingBundle>({
    queryKey: ['quality-feishu-settings', 'field-mapping', mappingEntityCode, mappingBundleParams],
    queryFn: () => fetchQualityFeishuEntityFieldMappingBundle(mappingEntityCode!, mappingBundleParams),
    enabled: mappingOpen && !!mappingEntityCode,
  })

  const mappingBundle = mappingQuery.data ?? null
  const mappingLoading = mappingQuery.isLoading

  useEffect(() => {
    if (mappingQuery.error && mappingOpen) {
      setMappingOpen(false)
      const description = mappingQuery.error instanceof Error ? mappingQuery.error.message : '读取字段对齐配置失败'
      setResultNotice({
        type: 'error',
        title: '读取字段对齐配置失败',
        description,
      })
      message.error(description)
    }
  }, [mappingQuery.error, mappingOpen, message])

  useEffect(() => {
    if (mappingBundle) {
      setMappingDrafts(
        mappingBundle.field_mappings.reduce<Record<string, string>>((acc, item) => {
          acc[item.system_field] = item.feishu_field || ''
          return acc
        }, {})
      )
    }
  }, [mappingBundle])

  const patchEntityDraft = useCallback(
    (entityCode: string, patch: Partial<UpdateQualityFeishuEntitySettingRequest>) => {
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

  const groupedEntities = useMemo(() => {
    const groups: Record<string, QualityFeishuEntitySettingItem[]> = {}
    for (const item of entityItems) {
      const group = item.entity_group || '未分组'
      if (!groups[group]) groups[group] = []
      groups[group].push(item)
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b, 'zh-CN'))
  }, [entityItems])

  const handleSaveApp = useCallback(async () => {
    try {
      setAppSaving(true)
      await updateQualityFeishuAppSettings({
        ...appForm,
        app_id: appForm.app_id.trim(),
      })
      setAppForm((current) => ({ ...current, app_secret: '' }))
      setResultNotice({
        type: 'success',
        title: '飞书应用配置已保存',
      })
      message.success('飞书应用配置已保存')
      queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings', 'app'] })
    } catch (error) {
      const description = error instanceof Error ? error.message : '保存飞书应用配置失败'
      setResultNotice({
        type: 'error',
        title: '保存飞书应用配置失败',
        description,
      })
      message.error(error instanceof Error ? error.message : '保存飞书应用配置失败')
    } finally {
      setAppSaving(false)
    }
  }, [appForm, message, queryClient])

  const handleTestApp = useCallback(async () => {
    try {
      setAppTesting(true)
      const result = await testQualityFeishuAppSettings()
      if (result?.success) {
        setResultNotice({
          type: 'success',
          title: '飞书应用连接测试成功',
          description: formatQualityFeishuTestSummary(result),
        })
        message.success(formatQualityFeishuTestSummary(result))
      } else {
        setResultNotice({
          type: 'warning',
          title: '飞书应用连接测试未通过',
          description: formatQualityFeishuTestSummary(result),
        })
        message.error(formatQualityFeishuTestSummary(result))
      }
      queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings', 'app'] })
    } catch (error) {
      const description = error instanceof Error ? error.message : '测试飞书应用连接失败'
      setResultNotice({
        type: 'error',
        title: '测试飞书应用连接失败',
        description,
      })
      message.error(error instanceof Error ? error.message : '测试飞书应用连接失败')
    } finally {
      setAppTesting(false)
    }
  }, [message, queryClient])

  const handlePull = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullQualityRecordsFromFeishu()
      if (!result) {
        throw new Error('未收到飞书回拉结果')
      }
      setResultNotice({
        type: result.failed > 0 || result.conflicts > 0 ? 'warning' : 'success',
        title: '飞书回拉已执行',
        description: formatQualitySyncSummary(result),
      })
      message.success(formatQualitySyncSummary(result))
      queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings'] })
    } catch (error) {
      const description = error instanceof Error ? error.message : '执行飞书回拉失败'
      setResultNotice({
        type: 'error',
        title: '执行飞书回拉失败',
        description,
      })
      message.error(error instanceof Error ? error.message : '执行飞书回拉失败')
    } finally {
      setPulling(false)
    }
  }, [message, queryClient])

  const handleSaveEntity = useCallback(
    async (entityCode: string) => {
      try {
        setRowSaving((current) => ({ ...current, [entityCode]: true }))
        const draft = entityDrafts[entityCode]
        if (!draft) return
        const result = await updateQualityFeishuEntitySetting(entityCode, {
          ...draft,
          base_table_name: draft.base_table_name?.trim() || '',
          base_table_id: draft.base_table_id?.trim() || '',
        })
        if (!result) return
        setResultNotice({
          type: 'success',
          title: `${result.entity_name} 配置已保存`,
        })
        message.success(`${result.entity_name} 配置已保存`)
        queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings', 'entities'] })
      } catch (error) {
        const description = error instanceof Error ? error.message : '保存实体配置失败'
        setResultNotice({
          type: 'error',
          title: '保存实体配置失败',
          description,
        })
        message.error(error instanceof Error ? error.message : '保存实体配置失败')
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
        const result = await testQualityFeishuEntitySetting(entityCode)
        if (result?.success) {
          setResultNotice({
            type: 'success',
            title: `${entityName} 连接测试成功`,
            description: formatQualityFeishuTestSummary(result),
          })
          message.success(formatQualityFeishuTestSummary(result))
        } else {
          setResultNotice({
            type: 'warning',
            title: `${entityName} 连接测试未通过`,
            description: formatQualityFeishuTestSummary(result),
          })
          message.error(formatQualityFeishuTestSummary(result))
        }
        queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings', 'entities'] })
      } catch (error) {
        const description =
          error instanceof Error ? error.message : `${entityName} 连接测试失败`
        setResultNotice({
          type: 'error',
          title: `${entityName} 连接测试失败`,
          description,
        })
        message.error(
          error instanceof Error ? error.message : `${entityName} 连接测试失败`
        )
      } finally {
        setRowTesting((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [message, queryClient]
  )

  const openFieldMapping = useCallback(
    (record: QualityFeishuEntitySettingItem) => {
      setMappingEntityCode(record.entity_code)
      setMappingOpen(true)
    },
    []
  )

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

  // 分组批量更新：粘贴 URL 后，将该分组下所有实体的 App Token / Table ID 统一更新
  const handleBatchUpdate = useCallback(
    async (groupName: string) => {
      const url = groupUrlInputs[groupName]?.trim()
      if (!url) {
        message.warning('请先粘贴多维表格网址')
        return
      }
      const parsed = parseFeishuBitableUrl(url)
      if (!parsed) {
        message.error('无法识别该网址，请检查格式')
        return
      }
      const group = groupedEntities.find(([name]) => name === groupName)
      if (!group || group[1].length === 0) return

      modal.confirm({
        title: '批量更新确认',
        content: (
          <div>
            <p>
              将把「{groupName}」分组下 <b>{group[1].length}</b> 个实体的配置更新为：
            </p>
            <p className="mt-1 text-[13px]">
              app_token：<code>{parsed.app_token}</code>
            </p>
            <p className="text-[13px]">
              table_id：<code>{parsed.table_id}</code>
            </p>
          </div>
        ),
        okText: '确认更新',
        cancelText: '取消',
        onOk: async () => {
          setBatchLoading(true)
          const results = await Promise.allSettled(
            group[1].map((item) =>
              updateQualityFeishuEntitySetting(item.entity_code, {
                ...(entityDrafts[item.entity_code] ?? createEntityDraft(item)),
                app_token: parsed.app_token,
                base_table_id: parsed.table_id,
              }),
            ),
          )
          const successCount = results.filter((r) => r.status === 'fulfilled').length
          const failCount = results.filter((r) => r.status === 'rejected').length
          queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings', 'entities'] })
          // 清空该分组输入框
          setGroupUrlInputs((prev) => {
            const next = { ...prev }
            delete next[groupName]
            return next
          })
          if (failCount === 0) {
            message.success(`已更新 ${successCount} 个实体配置`)
          } else {
            message.warning(`更新完成：成功 ${successCount} 个，失败 ${failCount} 个`)
          }
          setBatchLoading(false)
        },
      })
    },
    [groupUrlInputs, groupedEntities, entityDrafts, message, modal, queryClient],
  )

  // 按名称自动匹配：粘贴 Base 地址 → 读取该 Base 所有子表 → 按实体名称匹配并批量更新
  const handleAutoMatchTables = useCallback(
    async (groupName: string) => {
      const url = groupUrlInputs[groupName]?.trim()
      if (!url) {
        message.warning('请先粘贴多维表格网址')
        return
      }
      const parsed = parseFeishuBitableUrl(url)
      const appToken = parsed?.app_token ?? parseFeishuBaseUrl(url)
      if (!appToken) {
        message.error('无法识别该网址，请检查格式')
        return
      }
      const group = groupedEntities.find(([name]) => name === groupName)
      if (!group || group[1].length === 0) return

      // 读取该 Base 下所有子表
      setBatchLoading(true)
      let tables: QualityFeishuTableOption[] = []
      try {
        const firstCode = group[1][0].entity_code
        tables = await fetchQualityFeishuEntityTables(firstCode, appToken)
      } catch (error) {
        message.error(error instanceof Error ? error.message : '读取子表列表失败')
        return
      } finally {
        setBatchLoading(false)
      }
      if (tables.length === 0) {
        message.warning('该 Base 下未读取到子表，请确认网址是否正确')
        return
      }

      // 按名称匹配
      const matched: Array<{ entity: QualityFeishuEntitySettingItem; table: QualityFeishuTableOption }> = []
      const unmatched: QualityFeishuEntitySettingItem[] = []
      for (const entity of group[1]) {
        const table = matchTableForEntity(entity, tables)
        if (table) matched.push({ entity, table })
        else unmatched.push(entity)
      }

      if (matched.length === 0) {
        message.warning('没有实体能按名称匹配到子表，请检查实体名称与子表名称是否一致')
        return
      }

      modal.confirm({
        title: `按名称匹配确认（${groupName}）`,
        content: (
          <div>
            <p>
              将把「{groupName}」下 <b>{matched.length}</b> 个实体更新到 Base：<code>{appToken}</code>
            </p>
            {unmatched.length > 0 && (
              <p className="text-[13px] text-orange-600">
                ⚠ {unmatched.length} 个实体未匹配到子表（保持不变）：
                {unmatched.slice(0, 5).map((e) => e.entity_name).join('、')}
                {unmatched.length > 5 ? ' 等' : ''}
              </p>
            )}
            <ul className="mt-1 max-h-40 overflow-auto text-[13px]">
              {matched.slice(0, 10).map(({ entity, table }) => (
                <li key={entity.entity_code}>
                  {entity.entity_name} → {table.table_name}
                </li>
              ))}
              {matched.length > 10 && <li>…共 {matched.length} 个匹配项</li>}
            </ul>
          </div>
        ),
        okText: '确认更新',
        cancelText: '取消',
        onOk: async () => {
          setBatchLoading(true)
          const results = await Promise.allSettled(
            matched.map(({ entity, table }) =>
              updateQualityFeishuEntitySetting(entity.entity_code, {
                ...(entityDrafts[entity.entity_code] ?? createEntityDraft(entity)),
                app_token: appToken,
                base_table_id: table.table_id,
                base_table_name: table.table_name,
              }),
            ),
          )
          const successCount = results.filter((r) => r.status === 'fulfilled').length
          const failCount = results.filter((r) => r.status === 'rejected').length
          queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings', 'entities'] })
          // 清空该分组输入框
          setGroupUrlInputs((prev) => {
            const next = { ...prev }
            delete next[groupName]
            return next
          })
          if (failCount === 0) {
            message.success(`已按名称匹配并更新 ${successCount} 个实体`)
          } else {
            message.warning(`更新完成：成功 ${successCount} 个，失败 ${failCount} 个`)
          }
          setBatchLoading(false)
        },
      })
    },
    [groupUrlInputs, groupedEntities, entityDrafts, message, modal, queryClient],
  )

  // 渲染分组标题栏（含 URL 批量更新输入框 + 按钮）
  const renderGroupLabel = (group: string, itemCount: number) => {
    const urlValue = groupUrlInputs[group] ?? ''
    const parsed = urlValue ? parseFeishuBitableUrl(urlValue) : null
    return (
      <Space size={12} wrap align="center">
        <Typography.Text strong>{group}</Typography.Text>
        <Tag color="blue">{itemCount}</Tag>
        <Input
          size="small"
          style={{ width: 380 }}
          placeholder="粘贴多维表格网址，批量填充本组 App Token 和 Table ID"
          value={urlValue}
          onChange={(e) => setGroupUrlInputs((prev) => ({ ...prev, [group]: e.target.value }))}
          onPressEnter={() => void handleBatchUpdate(group)}
          disabled={batchLoading}
        />
        {parsed && (
          <span className="text-[12px] text-green-600">
            ✓ {parsed.app_token} / {parsed.table_id}
          </span>
        )}
        <Button
          size="small"
          type="primary"
          onClick={() => void handleBatchUpdate(group)}
          loading={batchLoading}
          disabled={!urlValue.trim()}
        >
          批量更新
        </Button>
        <Button
          size="small"
          onClick={() => void handleAutoMatchTables(group)}
          loading={batchLoading}
          disabled={!urlValue.trim()}
        >
          按名称匹配
        </Button>
      </Space>
    )
  }

  const saveFieldMapping = useCallback(async () => {
    if (!mappingBundle) return
    try {
      setMappingSaving(true)
      const currentDraft = entityDrafts[mappingBundle.entity_code]
      if (!currentDraft) return
      const fieldMappings: QualityFeishuFieldMappingItem[] = getManualMappingFields(mappingBundle)
        .map((item) => ({
          system_field: item.field_key,
          feishu_field: mappingDrafts[item.field_key] || null,
        }))
        .filter((item) => item.feishu_field)
      const result = await updateQualityFeishuEntitySetting(mappingBundle.entity_code, {
        ...currentDraft,
        field_mappings: fieldMappings,
      })
      if (!result) return
      setResultNotice({
        type: 'success',
        title: `${mappingBundle.entity_name} 字段对齐已保存`,
      })
      setMappingOpen(false)
      message.success(`${mappingBundle.entity_name} 字段对齐已保存`)
      queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings', 'entities'] })
    } catch (error) {
      setResultNotice({
        type: 'error',
        title: '保存字段对齐配置失败',
        description: error instanceof Error ? error.message : '保存字段对齐配置失败',
      })
      message.error(error instanceof Error ? error.message : '保存字段对齐配置失败')
    } finally {
      setMappingSaving(false)
    }
  }, [entityDrafts, mappingBundle, mappingDrafts, message, queryClient])

  const manualMappingFields = useMemo(
    () => getManualMappingFields(mappingBundle),
    [mappingBundle]
  )

  const handleLoadTables = useCallback(
    async (entityCode: string) => {
      try {
        setRowLoadingTables((current) => ({ ...current, [entityCode]: true }))
        const tables = await fetchQualityFeishuEntityTables(
          entityCode,
          entityDrafts[entityCode]?.app_token || ''
        )
        setRowTableOptions((current) => ({ ...current, [entityCode]: tables }))
        setResultNotice({
          type: 'success',
          title: '飞书表列表读取成功',
          description: `已读取 ${tables.length} 张表`,
        })
        message.success(`已读取 ${tables.length} 张表`)
      } catch (error) {
        setResultNotice({
          type: 'error',
          title: '读取飞书表列表失败',
          description: error instanceof Error ? error.message : '读取飞书表列表失败',
        })
        message.error(error instanceof Error ? error.message : '读取飞书表列表失败')
      } finally {
        setRowLoadingTables((current) => ({ ...current, [entityCode]: false }))
      }
    },
    [entityDrafts, message]
  )

  // 数据加载后默认展开全部分组（defaultActiveKey 依赖异步数据时首次渲染为空，会导致面板折叠）
  useEffect(() => {
    if (groupedEntities.length > 0) {
      setActiveGroups(groupedEntities.map(([group]) => group))
    }
  }, [groupedEntities])

  const columns = useMemo(
    () => [
      {
        title: '实体',
        dataIndex: 'entity_name',
        key: 'entity_name',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Space orientation="vertical" size={2}>
            <Typography.Text>{record.entity_name}</Typography.Text>
            {record.source_note ? (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {record.source_note}
              </Typography.Text>
            ) : null}
          </Space>
        ),
      },
      {
        title: 'App Token',
        key: 'app_token',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Input
            value={entityDrafts[record.entity_code]?.app_token || ''}
            placeholder="例如：bascnxxxxxxxx"
            onChange={(event) =>
              patchEntityDraft(record.entity_code, { app_token: event.target.value })
            }
          />
        ),
      },
      {
        title: 'Base 表名称',
        key: 'base_table_name',
        width: 260,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
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
              const option = (rowTableOptions[record.entity_code] || []).find(
                (item) => item.table_name === value
              )
              patchEntityDraft(record.entity_code, {
                base_table_name: value || '',
                base_table_id: option?.table_id || entityDrafts[record.entity_code]?.base_table_id || '',
              })
            }}
            onClear={() =>
              patchEntityDraft(record.entity_code, {
                base_table_name: '',
              })
            }
          />
        ),
      },
      {
        title: 'Base Table ID',
        key: 'base_table_id',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Input
            value={entityDrafts[record.entity_code]?.base_table_id || ''}
            placeholder="例如：tblxxxxxxxx"
            onChange={(event) =>
              patchEntityDraft(record.entity_code, { base_table_id: event.target.value })
            }
          />
        ),
      },
      {
        title: '启用',
        key: 'is_enabled',
        width: 90,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.is_enabled || false}
            onChange={(checked) => patchEntityDraft(record.entity_code, { is_enabled: checked })}
          />
        ),
      },
      {
        title: '推送',
        key: 'enable_push_to_feishu',
        width: 90,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.enable_push_to_feishu || false}
            onChange={(checked) =>
              patchEntityDraft(record.entity_code, { enable_push_to_feishu: checked })
            }
          />
        ),
      },
      {
        title: '回拉',
        key: 'enable_pull_from_feishu',
        width: 90,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Switch
            checked={entityDrafts[record.entity_code]?.enable_pull_from_feishu || false}
            onChange={(checked) =>
              patchEntityDraft(record.entity_code, { enable_pull_from_feishu: checked })
            }
          />
        ),
      },
      {
        title: '最近状态',
        key: 'last_status',
        width: 220,
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
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
        render: (_: unknown, record: QualityFeishuEntitySettingItem) => (
          <Space>
            <Button size="small" icon={<LinkOutlined />} onClick={() => void openFillUrl(record.entity_code)}>
              URL填充
            </Button>
            <Button
              size="small"
              loading={rowLoadingTables[record.entity_code]}
              onClick={() => void handleLoadTables(record.entity_code)}
            >
              读取表
            </Button>
            <Button
              size="small"
              onClick={() => void openFieldMapping(record)}
            >
              字段对齐
            </Button>
            <Button
              size="small"
              type="primary"
              icon={<SaveOutlined />}
              loading={rowSaving[record.entity_code]}
              onClick={() => void handleSaveEntity(record.entity_code)}
            >
              保存
            </Button>
            <Button
              size="small"
              icon={<SecurityScanOutlined />}
              loading={rowTesting[record.entity_code]}
              onClick={() => void handleTestEntity(record.entity_code, record.entity_name)}
            >
              测试
            </Button>
          </Space>
        ),
      },
    ],
    [
      entityDrafts,
      handleLoadTables,
      handleSaveEntity,
      handleTestEntity,
      openFillUrl,
      patchEntityDraft,
      rowLoadingTables,
      rowSaving,
      rowTableOptions,
      rowTesting,
    ]
  )

  return (
    <Space orientation="vertical" size={16} style={{ display: 'flex' }}>
      <div>
        <Typography.Title level={4} style={{ marginBottom: 8 }}>
          飞书设置
        </Typography.Title>
        <Typography.Text type="secondary">
          在这里维护质量模块的飞书应用信息、各台账对应的 Base 表，以及手动执行回拉验证。
        </Typography.Text>
      </div>

      {loadError ? (
        <Alert
          type="error"
          showIcon
          title="飞书设置加载失败"
          description={loadError}
        />
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
            <Button icon={<ReloadOutlined />} onClick={() => queryClient.invalidateQueries({ queryKey: ['quality-feishu-settings'] })} loading={loading}>
              刷新
            </Button>
            <Button
              icon={<SecurityScanOutlined />}
              onClick={() => void handleTestApp()}
              loading={appTesting}
            >
              测试连接
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              onClick={() => void handleSaveApp()}
              loading={appSaving}
            >
              保存配置
            </Button>
          </Space>
        }
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>
              App ID
            </Button>
            <Input
              value={appForm.app_id}
              placeholder="请输入飞书应用 App ID"
              onChange={(event) =>
                setAppForm((current) => ({ ...current, app_id: event.target.value }))
              }
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>
              App Secret
            </Button>
            <Input.Password
              value={appForm.app_secret}
              placeholder={appSettings?.app_secret_masked || '留空则保持当前 Secret 不变'}
              onChange={(event) =>
                setAppForm((current) => ({ ...current, app_secret: event.target.value }))
              }
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>
              新建表单链接
            </Button>
            <Input
              value={appForm.deviation_report_form_url || ''}
              placeholder="偏差报告新建表单链接，例如 https://xxx.feishu.cn/share/base/form/xxx"
              onChange={(event) =>
                setAppForm((current) => ({ ...current, deviation_report_form_url: event.target.value }))
              }
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>调查推送表单链接</Button>
            <Input
              value={appForm.deviation_investigation_push_form_url || ''}
              placeholder="偏差调查推送新建表单链接，例如 https://xxx.feishu.cn/share/base/form/xxx"
              onChange={(event) => setAppForm((current) => ({ ...current, deviation_investigation_push_form_url: event.target.value }))}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>OOSOOT报告记录表单链接</Button>
            <Input
              value={appForm.oos_oot_report_form_url || ''}
              placeholder="OOS/OOT报告记录新建表单链接"
              onChange={(event) => setAppForm((current) => ({ ...current, oos_oot_report_form_url: event.target.value }))}
            />
          </Space.Compact>
          <Space.Compact block>
            <Button disabled style={{ cursor: 'default', width: 120 }}>OOSOOT调查推送表单链接</Button>
            <Input
              value={appForm.oos_oot_investigation_push_form_url || ''}
              placeholder="OOS/OOT调查推送新建表单链接"
              onChange={(event) => setAppForm((current) => ({ ...current, oos_oot_investigation_push_form_url: event.target.value }))}
            />
          </Space.Compact>
          <Space size={12}>
            <Typography.Text>启用飞书同步</Typography.Text>
            <Switch
              checked={appForm.is_enabled}
              onChange={(checked) =>
                setAppForm((current) => ({ ...current, is_enabled: checked }))
              }
            />
            {renderStatusTag(appSettings?.last_test_status)}
            <Typography.Text type="secondary">
              最近测试：{formatDateTime(appSettings?.last_tested_at)}
            </Typography.Text>
          </Space>
          {appSettings?.last_test_error ? (
            <Alert type="warning" showIcon title={appSettings.last_test_error} />
          ) : null}
        </Space>
      </Card>

      <Card
        title="质量实体同步配置"
        extra={
          <Button
            type="primary"
            icon={<CloudDownloadOutlined />}
            onClick={() => void handlePull()}
            loading={pulling}
          >
            手动回拉已启用数据
          </Button>
        }
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Alert
            type="info"
            showIcon
            title="当前同步链路已切为数据库优先"
            description="顶部只维护飞书应用的 App ID 和 App Secret；每个质量实体单独维护自己的 App Token 和 Table ID。填入 App Token 后可直接点击读取表辅助选择。"
          />
          <Collapse
            activeKey={activeGroups}
            onChange={(keys) => setActiveGroups(keys as string[])}
            items={groupedEntities.map(([group, items]) => ({
              key: group,
              label: renderGroupLabel(group, items.length),
              children: (
                <Table<QualityFeishuEntitySettingItem>
                  rowKey="entity_code"
                  loading={loading}
                  columns={columns}
                  dataSource={items}
                  pagination={false}
                  scroll={{ x: 1720 }}
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
                  {
                    title: '系统字段',
                    dataIndex: 'field_label',
                    key: 'field_label',
                    width: 220,
                  },
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
                          setMappingDrafts((current) => ({
                            ...current,
                            [record.field_key]: value || '',
                          }))
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
    </Space>
  )
}
