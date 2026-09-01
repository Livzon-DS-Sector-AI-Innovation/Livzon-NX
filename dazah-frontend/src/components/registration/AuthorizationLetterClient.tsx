'use client'

import { DeleteOutlined, DownloadOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import {
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import {
  createAuthorizationFdaEntry,
  createAuthorizationLedgerMain,
  createAuthorizationLedgerUpdate,
  deleteAuthorizationFdaEntry,
  deleteAuthorizationLedgerMain,
  deleteAuthorizationLedgerUpdate,
  updateAuthorizationFdaEntry,
  updateAuthorizationLedgerMain,
  updateAuthorizationLedgerUpdate,
} from '@/actions/registration'
import { AuthorizationLetterDashboard } from '@/components/registration'
import { fetchAuthorizationFdaExport, fetchAuthorizationLedgerExport } from '@/lib/api/client/registration'
import type {
  AuthorizationFdaEntryInput,
  AuthorizationFdaRecord,
  AuthorizationLedgerEntryInput,
  AuthorizationLedgerMainCreateInput,
  AuthorizationLedgerMainUpdateInput,
  AuthorizationLedgerRecord,
  AuthorizationLedgerUpdateCreateInput,
  AuthorizationLedgerUpdateRecord,
  AuthorizationLedgerUpdateUpdateInput,
} from '@/types/registration'

const STATUS_OPTIONS = ['待确认', '未递交', '已递交', '待更新', '已收回']

const EMPTY_LEDGER_MAIN_FORM_VALUES: AuthorizationLedgerEntryInput = {
  product_name: '',
  market_name: '',
  source_sequence: '',
  authorization_file_name: '',
  quality_standard: '',
  company_name: '',
  country: '',
  customer_code: '',
  purpose: '',
  authorization_date: '',
  handler: '',
  status: '待确认',
  remarks: '',
}

type LedgerUpdateFormValues = Pick<
  AuthorizationLedgerEntryInput,
  'authorization_date' | 'handler' | 'remarks'
>

const EMPTY_LEDGER_UPDATE_FORM_VALUES: LedgerUpdateFormValues = {
  authorization_date: '',
  handler: '',
  remarks: '',
}

const EMPTY_FDA_FORM_VALUES: AuthorizationFdaEntryInput = {
  product_name: '',
  source_sequence: null,
  company_name: '',
  address: '',
  reference_number: '',
  loa_date: '',
  submission_date: '',
  referenced_sections: '',
}

const docCellStyle = {
  border: '1px solid var(--color-hairline)',
  padding: '10px 8px',
  verticalAlign: 'middle' as const,
  textAlign: 'center' as const,
  wordBreak: 'break-word' as const,
  whiteSpace: 'pre-wrap' as const,
}

const docCellStyleCentered = {
  ...docCellStyle,
}

const fdaTableHeaderCellStyle = {
  textAlign: 'center' as const,
  verticalAlign: 'middle' as const,
  fontSize: 14,
  lineHeight: 1.75,
  fontWeight: 600,
  padding: '10px 8px',
}

const fdaTableBodyCellStyle = {
  textAlign: 'center' as const,
  verticalAlign: 'middle' as const,
  fontSize: 14,
  lineHeight: 1.75,
  padding: '10px 8px',
  whiteSpace: 'pre-wrap' as const,
  wordBreak: 'break-word' as const,
}

interface AuthorizationLetterClientProps {
  initialRecords: AuthorizationLedgerRecord[]
  initialFdaRecords: AuthorizationFdaRecord[]
}

interface LedgerDocumentSection {
  product_name: string
  records: AuthorizationLedgerRecord[]
}

type LedgerMainModalMode = 'create' | 'edit'
type LedgerUpdateModalMode = 'create' | 'edit'

export function buildLedgerGroupKey(record: AuthorizationLedgerRecord): string {
  return [
    record.product_name,
    record.market_name || '',
    record.source_sequence || '',
    record.authorization_file_name || '',
    record.quality_standard || '',
    record.company_name || '',
    record.country || '',
    record.customer_code || '',
    record.purpose || '',
  ].join('||')
}

export function normalizeNullableText(value: string | null | undefined): string | null {
  const normalized = String(value || '').trim()
  return normalized || null
}

export function normalizeRequiredText(value: string | null | undefined): string {
  return String(value || '').trim()
}

export function displayText(value: string | null | undefined): string {
  return normalizeRequiredText(value) || '-'
}

export function buildSelectOptions(values: Array<string | null | undefined>) {
  return Array.from(new Set(values.filter(Boolean))).map((value) => ({
    label: value as string,
    value: value as string,
  }))
}

export function getLedgerDateSortValue(value: string | null | undefined): number {
  const normalized = String(value || '').trim()
  if (!normalized) {
    return Number.MAX_SAFE_INTEGER
  }

  const match = normalized.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})$/)
  if (!match) {
    return Number.MAX_SAFE_INTEGER
  }

  const [, year, month, day] = match
  return Number(`${year}${month.padStart(2, '0')}${day.padStart(2, '0')}`)
}

export function sortLedgerUpdates(updates: AuthorizationLedgerUpdateRecord[]): AuthorizationLedgerUpdateRecord[] {
  return [...updates].sort((a, b) => {
    const sortOrderCompare = a.sort_order - b.sort_order
    if (sortOrderCompare !== 0) {
      return sortOrderCompare
    }

    return String(a.id).localeCompare(String(b.id), 'zh-CN')
  })
}

export function normalizeLedgerRecord(record: AuthorizationLedgerRecord): AuthorizationLedgerRecord {
  return {
    ...record,
    updates: sortLedgerUpdates(record.updates || []),
  }
}

export function sortLedgerRecords(records: AuthorizationLedgerRecord[]): AuthorizationLedgerRecord[] {
  return [...records].map(normalizeLedgerRecord).sort((a, b) => {
    const productCompare = String(a.product_name || '').localeCompare(String(b.product_name || ''), 'zh-CN')
    if (productCompare !== 0) {
      return productCompare
    }

    const marketCompare = String(a.market_name || '').localeCompare(String(b.market_name || ''), 'zh-CN')
    if (marketCompare !== 0) {
      return marketCompare
    }

    const groupCompare = buildLedgerGroupKey(a).localeCompare(buildLedgerGroupKey(b), 'zh-CN')
    if (groupCompare !== 0) {
      return groupCompare
    }

    const dateCompare =
      getLedgerDateSortValue(a.updates[0]?.authorization_date) -
      getLedgerDateSortValue(b.updates[0]?.authorization_date)
    if (dateCompare !== 0) {
      return dateCompare
    }

    return String(a.id).localeCompare(String(b.id), 'zh-CN')
  })
}

export function replaceLedgerMainRecord(
  records: AuthorizationLedgerRecord[],
  nextRecord: AuthorizationLedgerRecord
): AuthorizationLedgerRecord[] {
  return sortLedgerRecords(
    records.map((item) => (item.id === nextRecord.id ? normalizeLedgerRecord(nextRecord) : item))
  )
}

export function upsertLedgerUpdateRecord(
  records: AuthorizationLedgerRecord[],
  mainId: string,
  nextUpdate: AuthorizationLedgerUpdateRecord
): AuthorizationLedgerRecord[] {
  return sortLedgerRecords(
    records.map((item) => {
      if (item.id !== mainId) {
        return item
      }

      const nextUpdates = item.updates.some((update) => update.id === nextUpdate.id)
        ? item.updates.map((update) => (update.id === nextUpdate.id ? nextUpdate : update))
        : [...item.updates, nextUpdate]

      return {
        ...item,
        updates: sortLedgerUpdates(nextUpdates),
      }
    })
  )
}

export function removeLedgerUpdateRecord(
  records: AuthorizationLedgerRecord[],
  mainId: string,
  updateId: string
): AuthorizationLedgerRecord[] {
  return sortLedgerRecords(
    records.map((item) => {
      if (item.id !== mainId) {
        return item
      }

      return {
        ...item,
        updates: item.updates.filter((update) => update.id !== updateId),
      }
    })
  )
}

export function buildLedgerMainCreatePayload(values: AuthorizationLedgerEntryInput): AuthorizationLedgerMainCreateInput {
  return {
    product_name: normalizeRequiredText(values.product_name),
    market_name: normalizeNullableText(values.market_name),
    source_sequence: normalizeNullableText(values.source_sequence),
    authorization_file_name: normalizeRequiredText(values.authorization_file_name),
    quality_standard: normalizeNullableText(values.quality_standard),
    company_name: normalizeNullableText(values.company_name),
    country: normalizeNullableText(values.country),
    customer_code: normalizeNullableText(values.customer_code),
    purpose: normalizeNullableText(values.purpose),
    status: normalizeNullableText(values.status) || '待确认',
    initial_update: {
      authorization_date: normalizeNullableText(values.authorization_date),
      handler: normalizeNullableText(values.handler),
      remarks: normalizeNullableText(values.remarks),
    },
  }
}

export function buildLedgerMainUpdatePayload(values: AuthorizationLedgerEntryInput): AuthorizationLedgerMainUpdateInput {
  return {
    product_name: normalizeRequiredText(values.product_name),
    market_name: normalizeNullableText(values.market_name),
    source_sequence: normalizeNullableText(values.source_sequence),
    authorization_file_name: normalizeRequiredText(values.authorization_file_name),
    quality_standard: normalizeNullableText(values.quality_standard),
    company_name: normalizeNullableText(values.company_name),
    country: normalizeNullableText(values.country),
    customer_code: normalizeNullableText(values.customer_code),
    purpose: normalizeNullableText(values.purpose),
    status: normalizeNullableText(values.status) || '待确认',
  }
}

export function buildLedgerUpdateCreatePayload(values: LedgerUpdateFormValues): AuthorizationLedgerUpdateCreateInput {
  return {
    authorization_date: normalizeNullableText(values.authorization_date),
    handler: normalizeNullableText(values.handler),
    remarks: normalizeNullableText(values.remarks),
  }
}

export function buildLedgerUpdatePatchPayload(values: LedgerUpdateFormValues): AuthorizationLedgerUpdateUpdateInput {
  return {
    authorization_date: normalizeNullableText(values.authorization_date),
    handler: normalizeNullableText(values.handler),
    remarks: normalizeNullableText(values.remarks),
  }
}

export function buildCompanyCountryDisplay(record: AuthorizationLedgerRecord): string {
  return [record.company_name, record.country].filter(Boolean).join('\n') || '-'
}

export default function AuthorizationLetterClient({
  initialRecords,
  initialFdaRecords,
}: AuthorizationLetterClientProps) {
  const { message } = App.useApp()
  const [ledgerMainForm] = Form.useForm<AuthorizationLedgerEntryInput>()
  const [ledgerUpdateForm] = Form.useForm<LedgerUpdateFormValues>()
  const [fdaForm] = Form.useForm<AuthorizationFdaEntryInput>()

  const [ledgerRecords, setLedgerRecords] = useState(() => sortLedgerRecords(initialRecords))
  const [fdaRecords, setFdaRecords] = useState(initialFdaRecords)

  const [editingLedgerMain, setEditingLedgerMain] = useState<AuthorizationLedgerRecord | null>(null)
  const [editingLedgerUpdate, setEditingLedgerUpdate] = useState<AuthorizationLedgerUpdateRecord | null>(null)
  const [updateParentRecord, setUpdateParentRecord] = useState<AuthorizationLedgerRecord | null>(null)
  const [editingFdaRecord, setEditingFdaRecord] = useState<AuthorizationFdaRecord | null>(null)

  const [ledgerMainModalMode, setLedgerMainModalMode] = useState<LedgerMainModalMode>('create')
  const [ledgerUpdateModalMode, setLedgerUpdateModalMode] = useState<LedgerUpdateModalMode>('create')

  const [selectedLedgerMainId, setSelectedLedgerMainId] = useState<string | null>(null)
  const [selectedLedgerUpdateId, setSelectedLedgerUpdateId] = useState<string | null>(null)
  const [selectedFdaRecordKey, setSelectedFdaRecordKey] = useState<string | null>(null)

  const [ledgerMainModalOpen, setLedgerMainModalOpen] = useState(false)
  const [ledgerUpdateModalOpen, setLedgerUpdateModalOpen] = useState(false)
  const [fdaModalOpen, setFdaModalOpen] = useState(false)
  const [ledgerMainSubmitting, setLedgerMainSubmitting] = useState(false)
  const [ledgerUpdateSubmitting, setLedgerUpdateSubmitting] = useState(false)
  const [fdaSubmitting, setFdaSubmitting] = useState(false)
  const [exportingFda, setExportingFda] = useState(false)
  const [exportingLedger, setExportingLedger] = useState(false)
  const [statusUpdatingId, setStatusUpdatingId] = useState<string | null>(null)

  const [filters, setFilters] = useState({
    product_name: '',
    market_name: '',
    status: '',
    keyword: '',
  })

  const tentativeProductOptions = useMemo(() => {
    if (filters.market_name) {
      return buildSelectOptions(
        ledgerRecords
          .filter((item) => item.market_name === filters.market_name)
          .map((item) => item.product_name)
      )
    }

    return buildSelectOptions([
      ...ledgerRecords.map((item) => item.product_name),
      ...fdaRecords.map((item) => item.product_name),
    ])
  }, [fdaRecords, filters.market_name, ledgerRecords])

  const effectiveProductFilter = useMemo(() => {
    if (!filters.product_name) {
      return ''
    }

    return tentativeProductOptions.some((option) => option.value === filters.product_name)
      ? filters.product_name
      : ''
  }, [filters.product_name, tentativeProductOptions])

  const tentativeMarketOptions = useMemo(
    () =>
      buildSelectOptions(
        ledgerRecords
          .filter((item) => !effectiveProductFilter || item.product_name === effectiveProductFilter)
          .map((item) => item.market_name)
      ),
    [effectiveProductFilter, ledgerRecords]
  )

  const effectiveMarketFilter = useMemo(() => {
    if (!filters.market_name) {
      return ''
    }

    return tentativeMarketOptions.some((option) => option.value === filters.market_name)
      ? filters.market_name
      : ''
  }, [filters.market_name, tentativeMarketOptions])

  const productOptions = useMemo(() => {
    if (effectiveMarketFilter) {
      return buildSelectOptions(
        ledgerRecords
          .filter((item) => item.market_name === effectiveMarketFilter)
          .map((item) => item.product_name)
      )
    }

    return buildSelectOptions([
      ...ledgerRecords.map((item) => item.product_name),
      ...fdaRecords.map((item) => item.product_name),
    ])
  }, [effectiveMarketFilter, fdaRecords, ledgerRecords])

  const marketOptions = useMemo(
    () =>
      buildSelectOptions(
        ledgerRecords
          .filter((item) => !effectiveProductFilter || item.product_name === effectiveProductFilter)
          .map((item) => item.market_name)
      ),
    [effectiveProductFilter, ledgerRecords]
  )

  const filteredLedgerRecords = useMemo(() => {
    return ledgerRecords.filter((item) => {
      const matchesProduct = !effectiveProductFilter || item.product_name === effectiveProductFilter
      const matchesMarket = !effectiveMarketFilter || item.market_name === effectiveMarketFilter
      const matchesStatus = !filters.status || item.status === filters.status
      const keyword = filters.keyword.trim().toLowerCase()
      const matchesUpdateKeyword = item.updates.some((update) =>
        [update.authorization_date, update.handler, update.remarks]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(keyword))
      )
      const matchesKeyword =
        !keyword ||
        [
          item.product_name,
          item.market_name,
          item.authorization_file_name,
          item.company_name,
          item.country,
          item.customer_code,
          item.purpose,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(keyword)) ||
        matchesUpdateKeyword

      return matchesProduct && matchesMarket && matchesStatus && matchesKeyword
    })
  }, [effectiveMarketFilter, effectiveProductFilter, filters.keyword, filters.status, ledgerRecords])

  const filteredFdaRecords = useMemo(() => {
    return fdaRecords.filter((item) => {
      const matchesProduct = !effectiveProductFilter || item.product_name === effectiveProductFilter
      const keyword = filters.keyword.trim().toLowerCase()
      const matchesKeyword =
        !keyword ||
        [
          item.product_name,
          item.company_name,
          item.address,
          item.reference_number,
          item.loa_date,
          item.submission_date,
          item.referenced_sections,
        ]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(keyword))

      return matchesProduct && matchesKeyword
    })
  }, [effectiveProductFilter, fdaRecords, filters.keyword])

  const filteredFdaSequenceMap = useMemo(() => {
    return new Map(
      filteredFdaRecords.map((record, index) => [
        record.id || `${record.product_name}-${record.sequence}-${record.company_name}`,
        index + 1,
      ])
    )
  }, [filteredFdaRecords])

  const filteredLedgerSequenceMap = useMemo(() => {
    return new Map(filteredLedgerRecords.map((record, index) => [record.id, index + 1]))
  }, [filteredLedgerRecords])

  const ledgerDocumentSections = useMemo<LedgerDocumentSection[]>(() => {
    const sections = new Map<string, LedgerDocumentSection>()

    filteredLedgerRecords.forEach((record) => {
      const productName = record.product_name || '未命名产品'
      const currentSection: LedgerDocumentSection = sections.get(productName) || {
        product_name: productName,
        records: [],
      }

      currentSection.records.push(record)
      sections.set(productName, currentSection)
    })

    return Array.from(sections.values())
  }, [filteredLedgerRecords])

  const selectedLedgerMain = useMemo(() => {
    return filteredLedgerRecords.find((record) => record.id === selectedLedgerMainId) || filteredLedgerRecords[0] || null
  }, [filteredLedgerRecords, selectedLedgerMainId])

  const selectedLedgerMainEffectiveId = selectedLedgerMain?.id || null

  const selectedLedgerUpdate = useMemo(() => {
    if (!selectedLedgerMain) {
      return null
    }

    return (
      selectedLedgerMain.updates.find((update) => update.id === selectedLedgerUpdateId) ||
      selectedLedgerMain.updates[0] ||
      null
    )
  }, [selectedLedgerMain, selectedLedgerUpdateId])

  const selectedLedgerUpdateEffectiveId = selectedLedgerUpdate?.id || null

  const validFdaRecordKeys = useMemo(
    () =>
      filteredFdaRecords.map(
        (record) => record.id || `${record.product_name}-${record.sequence}-${record.company_name}`
      ),
    [filteredFdaRecords]
  )

  const selectedFdaRecordEffectiveKey = useMemo(() => {
    if (!validFdaRecordKeys.length) {
      return null
    }

    return selectedFdaRecordKey && validFdaRecordKeys.includes(selectedFdaRecordKey)
      ? selectedFdaRecordKey
      : validFdaRecordKeys[0]
  }, [selectedFdaRecordKey, validFdaRecordKeys])

  const selectedFdaRecord = useMemo(
    () =>
      filteredFdaRecords.find(
        (record) =>
          (record.id || `${record.product_name}-${record.sequence}-${record.company_name}`) ===
          selectedFdaRecordEffectiveKey
      ) || null,
    [filteredFdaRecords, selectedFdaRecordEffectiveKey]
  )

  useEffect(() => {
    if (!ledgerMainModalOpen) {
      return
    }

    if (ledgerMainModalMode === 'edit' && editingLedgerMain) {
      ledgerMainForm.setFieldsValue({
        product_name: editingLedgerMain.product_name || '',
        market_name: editingLedgerMain.market_name || '',
        source_sequence: editingLedgerMain.source_sequence || '',
        authorization_file_name: editingLedgerMain.authorization_file_name || '',
        quality_standard: editingLedgerMain.quality_standard || '',
        company_name: editingLedgerMain.company_name || '',
        country: editingLedgerMain.country || '',
        customer_code: editingLedgerMain.customer_code || '',
        purpose: editingLedgerMain.purpose || '',
        authorization_date: '',
        handler: '',
        status: editingLedgerMain.status || '待确认',
        remarks: '',
      })
      return
    }

    ledgerMainForm.setFieldsValue({
      ...EMPTY_LEDGER_MAIN_FORM_VALUES,
      product_name: effectiveProductFilter || '',
      market_name: effectiveMarketFilter || '',
      status: filters.status || '待确认',
    })
  }, [
    editingLedgerMain,
    effectiveMarketFilter,
    effectiveProductFilter,
    filters.status,
    ledgerMainForm,
    ledgerMainModalMode,
    ledgerMainModalOpen,
  ])

  useEffect(() => {
    if (!ledgerUpdateModalOpen) {
      return
    }

    if (ledgerUpdateModalMode === 'edit' && editingLedgerUpdate) {
      ledgerUpdateForm.setFieldsValue({
        authorization_date: editingLedgerUpdate.authorization_date || '',
        handler: editingLedgerUpdate.handler || '',
        remarks: editingLedgerUpdate.remarks || '',
      })
      return
    }

    ledgerUpdateForm.setFieldsValue(EMPTY_LEDGER_UPDATE_FORM_VALUES)
  }, [editingLedgerUpdate, ledgerUpdateForm, ledgerUpdateModalMode, ledgerUpdateModalOpen])

  useEffect(() => {
    if (!fdaModalOpen) {
      return
    }

    if (editingFdaRecord) {
      fdaForm.setFieldsValue({
        product_name: editingFdaRecord.product_name || '',
        source_sequence: editingFdaRecord.sequence || null,
        company_name: editingFdaRecord.company_name || '',
        address: editingFdaRecord.address || '',
        reference_number: editingFdaRecord.reference_number || '',
        loa_date: editingFdaRecord.loa_date || '',
        submission_date: editingFdaRecord.submission_date || '',
        referenced_sections: editingFdaRecord.referenced_sections || '',
      })
      return
    }

    fdaForm.setFieldsValue(EMPTY_FDA_FORM_VALUES)
  }, [editingFdaRecord, fdaForm, fdaModalOpen])

  function resetLedgerMainModal() {
    setLedgerMainModalOpen(false)
    setLedgerMainModalMode('create')
    setEditingLedgerMain(null)
    ledgerMainForm.resetFields()
  }

  function resetLedgerUpdateModal() {
    setLedgerUpdateModalOpen(false)
    setLedgerUpdateModalMode('create')
    setEditingLedgerUpdate(null)
    setUpdateParentRecord(null)
    ledgerUpdateForm.resetFields()
  }

  function openCreateLedgerMainModal() {
    setLedgerMainModalMode('create')
    setEditingLedgerMain(null)
    setLedgerMainModalOpen(true)
  }

  function openEditLedgerMainModal(record: AuthorizationLedgerRecord) {
    setLedgerMainModalMode('edit')
    setEditingLedgerMain(record)
    setLedgerMainModalOpen(true)
  }

  function openCreateLedgerUpdateModal(record: AuthorizationLedgerRecord) {
    setLedgerUpdateModalMode('create')
    setUpdateParentRecord(record)
    setEditingLedgerUpdate(null)
    setLedgerUpdateModalOpen(true)
  }

  function openEditLedgerUpdateModal(
    record: AuthorizationLedgerRecord,
    update: AuthorizationLedgerUpdateRecord
  ) {
    setLedgerUpdateModalMode('edit')
    setUpdateParentRecord(record)
    setEditingLedgerUpdate(update)
    setLedgerUpdateModalOpen(true)
  }

  function openCreateFdaModal() {
    setEditingFdaRecord(null)
    setFdaModalOpen(true)
  }

  function openEditFdaModal(record: AuthorizationFdaRecord) {
    setEditingFdaRecord(record)
    setFdaModalOpen(true)
  }

  function selectLedgerRow(record: AuthorizationLedgerRecord, update: AuthorizationLedgerUpdateRecord) {
    setSelectedLedgerMainId(record.id)
    setSelectedLedgerUpdateId(update.id)
  }

  async function handleLedgerMainSubmit() {
    const values = await ledgerMainForm.validateFields()
    setLedgerMainSubmitting(true)

    try {
      if (ledgerMainModalMode === 'edit' && editingLedgerMain?.id) {
        const updated = (await updateAuthorizationLedgerMain(
          editingLedgerMain.id,
          buildLedgerMainUpdatePayload(values)
        )) as AuthorizationLedgerRecord

        setLedgerRecords((prev) => replaceLedgerMainRecord(prev, updated))
        setSelectedLedgerMainId(updated.id)
        setSelectedLedgerUpdateId(updated.updates[0]?.id || null)
        message.success('主记录已更新')
      } else {
        const created = (await createAuthorizationLedgerMain(
          buildLedgerMainCreatePayload(values)
        )) as AuthorizationLedgerRecord

        setLedgerRecords((prev) => sortLedgerRecords([...prev, created]))
        setSelectedLedgerMainId(created.id)
        setSelectedLedgerUpdateId(created.updates[0]?.id || null)
        message.success('市场授权已新增')
      }

      resetLedgerMainModal()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setLedgerMainSubmitting(false)
    }
  }

  async function handleLedgerUpdateSubmit() {
    if (!updateParentRecord?.id) {
      message.error('未找到对应的主记录')
      return
    }

    const values = await ledgerUpdateForm.validateFields()
    setLedgerUpdateSubmitting(true)

    try {
      if (ledgerUpdateModalMode === 'edit' && editingLedgerUpdate?.id) {
        const updated = (await updateAuthorizationLedgerUpdate(
          editingLedgerUpdate.id,
          buildLedgerUpdatePatchPayload(values)
        )) as AuthorizationLedgerUpdateRecord

        setLedgerRecords((prev) => upsertLedgerUpdateRecord(prev, updateParentRecord.id, updated))
        setSelectedLedgerMainId(updateParentRecord.id)
        setSelectedLedgerUpdateId(updated.id)
        message.success('更新子行已更新')
      } else {
        const created = (await createAuthorizationLedgerUpdate(
          updateParentRecord.id,
          buildLedgerUpdateCreatePayload(values)
        )) as AuthorizationLedgerUpdateRecord

        setLedgerRecords((prev) => upsertLedgerUpdateRecord(prev, updateParentRecord.id, created))
        setSelectedLedgerMainId(updateParentRecord.id)
        setSelectedLedgerUpdateId(created.id)
        message.success('更新子行已新增')
      }

      resetLedgerUpdateModal()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setLedgerUpdateSubmitting(false)
    }
  }

  async function handleFdaSubmit() {
    const values = await fdaForm.validateFields()
    setFdaSubmitting(true)

    try {
      if (editingFdaRecord?.id) {
        const updated = (await updateAuthorizationFdaEntry(editingFdaRecord.id, values)) as AuthorizationFdaRecord
        setFdaRecords((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
        message.success('FDA授权已更新')
      } else {
        const created = (await createAuthorizationFdaEntry(values)) as AuthorizationFdaRecord
        setFdaRecords((prev) => [created, ...prev])
        message.success('FDA授权已新增')
      }

      setFdaModalOpen(false)
      fdaForm.resetFields()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      setFdaSubmitting(false)
    }
  }

  async function handleDeleteLedgerMain(record: AuthorizationLedgerRecord) {
    if (!record.id) {
      return
    }

    try {
      await deleteAuthorizationLedgerMain(record.id)
      setLedgerRecords((prev) => sortLedgerRecords(prev.filter((item) => item.id !== record.id)))
      message.success('主记录已删除')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  async function handleDeleteLedgerUpdate(
    record: AuthorizationLedgerRecord,
    update: AuthorizationLedgerUpdateRecord
  ) {
    if (!record.id || !update.id) {
      return
    }

    if (record.updates.length <= 1) {
      message.warning('当前主记录只剩一条更新，请删除主记录')
      return
    }

    try {
      await deleteAuthorizationLedgerUpdate(update.id)
      setLedgerRecords((prev) => removeLedgerUpdateRecord(prev, record.id, update.id))
      message.success('更新子行已删除')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  async function handleDeleteFda(record: AuthorizationFdaRecord) {
    if (!record.id) {
      return
    }

    try {
      await deleteAuthorizationFdaEntry(record.id)
      setFdaRecords((prev) => prev.filter((item) => item.id !== record.id))
      message.success('FDA授权已删除')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  async function handleExportFda() {
    setExportingFda(true)

    try {
      await fetchAuthorizationFdaExport({
        product_name: effectiveProductFilter || undefined,
        keyword: filters.keyword || undefined,
      })
      message.success('FDA授权已开始下载')
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'FDA授权导出失败')
    } finally {
      setExportingFda(false)
    }
  }

  async function handleExportLedger() {
    setExportingLedger(true)

    try {
      await fetchAuthorizationLedgerExport({
        product_name: effectiveProductFilter || undefined,
        market_name: effectiveMarketFilter || undefined,
        status: filters.status || undefined,
        keyword: filters.keyword || undefined,
      })
      message.success('市场授权已开始下载')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '市场授权导出失败')
    } finally {
      setExportingLedger(false)
    }
  }

  async function handleQuickStatusChange(record: AuthorizationLedgerRecord, status: string) {
    if (!record.id || record.status === status) {
      return
    }

    setStatusUpdatingId(record.id)

    try {
      const updated = (await updateAuthorizationLedgerMain(record.id, {
        status,
      })) as AuthorizationLedgerRecord

      setLedgerRecords((prev) => replaceLedgerMainRecord(prev, updated))
      message.success('主记录状态已更新')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '状态更新失败')
    } finally {
      setStatusUpdatingId(null)
    }
  }

  const fdaColumns = [
    {
      title: '序号',
      key: 'display_sequence',
      width: 72,
      fixed: 'left' as const,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
      render: (_: unknown, record: AuthorizationFdaRecord) =>
        filteredFdaSequenceMap.get(record.id || `${record.product_name}-${record.sequence}-${record.company_name}`) || '-',
    },
    {
      title: '选择',
      key: 'select',
      width: 72,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
      render: (_: unknown, record: AuthorizationFdaRecord) => {
        const recordKey = record.id || `${record.product_name}-${record.sequence}-${record.company_name}`
        return (
          <Radio
            checked={selectedFdaRecordEffectiveKey === recordKey}
            onChange={() => setSelectedFdaRecordKey(recordKey)}
          />
        )
      },
    },
    {
      title: '产品',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 120,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
    },
    {
      title: 'FDA客户/公司',
      dataIndex: 'company_name',
      key: 'company_name',
      width: 260,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
    },
    {
      title: '地址',
      dataIndex: 'address',
      key: 'address',
      width: 360,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: 'Reference No.',
      dataIndex: 'reference_number',
      key: 'reference_number',
      width: 140,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: 'LOA日期',
      dataIndex: 'loa_date',
      key: 'loa_date',
      width: 150,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: '递交日期',
      dataIndex: 'submission_date',
      key: 'submission_date',
      width: 150,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
      render: (value: string | null | undefined) => value || '-',
    },
    {
      title: '引用章节',
      dataIndex: 'referenced_sections',
      key: 'referenced_sections',
      width: 150,
      align: 'center' as const,
      onHeaderCell: () => ({ style: fdaTableHeaderCellStyle }),
      onCell: () => ({ style: fdaTableBodyCellStyle }),
      render: (value: string | null | undefined) => value || '-',
    },
  ]

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Card styles={{ body: { padding: 20 } }}>
        <Space wrap size={12}>
          <Select
            allowClear
            placeholder="筛选产品"
            style={{ width: 180 }}
            options={productOptions}
            value={effectiveProductFilter || undefined}
            onChange={(value) => setFilters((prev) => ({ ...prev, product_name: value || '' }))}
          />
          <Select
            allowClear
            placeholder="筛选市场"
            style={{ width: 180 }}
            options={marketOptions}
            value={effectiveMarketFilter || undefined}
            onChange={(value) => setFilters((prev) => ({ ...prev, market_name: value || '' }))}
          />
          <Select
            allowClear
            placeholder="筛选状态"
            style={{ width: 160 }}
            options={STATUS_OPTIONS.map((item) => ({ label: item, value: item }))}
            value={filters.status || undefined}
            onChange={(value) => setFilters((prev) => ({ ...prev, status: value || '' }))}
          />
          <Input.Search
            allowClear
            placeholder="搜索客户/用途/备注/FDA公司"
            style={{ width: 320 }}
            value={filters.keyword}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, keyword: event.target.value }))
            }
          />
        </Space>
      </Card>

      <AuthorizationLetterDashboard
        filteredFdaRecords={filteredFdaRecords}
        filteredLedgerRecords={filteredLedgerRecords}
      />

      <Card
        title={
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space>
              <Typography.Text strong>FDA 授权</Typography.Text>
              <Tag color="blue">{filteredFdaRecords.length} 条</Tag>
            </Space>
            <Space>
              <Button icon={<DownloadOutlined />} loading={exportingFda} onClick={() => void handleExportFda()}>
                导出FDA授权
              </Button>
              <Button icon={<PlusOutlined />} onClick={openCreateFdaModal}>
                新增FDA授权
              </Button>
              <Button
                icon={<EditOutlined />}
                disabled={!selectedFdaRecord}
                onClick={() => {
                  if (!selectedFdaRecord) {
                    message.warning('请先选择一条FDA授权')
                    return
                  }
                  openEditFdaModal(selectedFdaRecord)
                }}
              >
                编辑选中
              </Button>
              <Popconfirm
                title="确定删除选中的 FDA 授权吗？"
                disabled={!selectedFdaRecord}
                onConfirm={() => {
                  if (!selectedFdaRecord) {
                    message.warning('请先选择一条FDA授权')
                    return Promise.resolve()
                  }
                  return handleDeleteFda(selectedFdaRecord)
                }}
              >
                <Button danger icon={<DeleteOutlined />} disabled={!selectedFdaRecord}>
                  删除选中
                </Button>
              </Popconfirm>
            </Space>
          </Space>
        }
        styles={{ body: { padding: 12 } }}
      >
        <Table<AuthorizationFdaRecord>
          rowKey={(record) => record.id || `${record.product_name}-${record.sequence}-${record.company_name}`}
          columns={fdaColumns}
          dataSource={filteredFdaRecords}
          pagination={false}
          scroll={{ x: 1680 }}
          size="middle"
          style={{ fontSize: 14, lineHeight: 1.75 }}
        />
      </Card>

      <Card
        title={
          <Space style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space>
              <Typography.Text strong>市场授权台账</Typography.Text>
              <Tag color="purple">{filteredLedgerRecords.length} 条主记录</Tag>
            </Space>
            <Space wrap>
              <Button icon={<DownloadOutlined />} loading={exportingLedger} onClick={() => void handleExportLedger()}>
                导出市场授权
              </Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreateLedgerMainModal}>
                新增市场授权
              </Button>
              <Button
                onClick={() => {
                  if (!selectedLedgerMain) {
                    message.warning('请先选择一条主记录')
                    return
                  }
                  openCreateLedgerUpdateModal(selectedLedgerMain)
                }}
                disabled={!selectedLedgerMain}
              >
                新增更新
              </Button>
              <Button
                icon={<EditOutlined />}
                disabled={!selectedLedgerMain}
                onClick={() => {
                  if (!selectedLedgerMain) {
                    message.warning('请先选择一条主记录')
                    return
                  }
                  openEditLedgerMainModal(selectedLedgerMain)
                }}
              >
                编辑主记录
              </Button>
              <Button
                icon={<EditOutlined />}
                disabled={!selectedLedgerMain || !selectedLedgerUpdate}
                onClick={() => {
                  if (!selectedLedgerMain || !selectedLedgerUpdate) {
                    message.warning('请先选择一条更新子行')
                    return
                  }
                  openEditLedgerUpdateModal(selectedLedgerMain, selectedLedgerUpdate)
                }}
              >
                编辑更新
              </Button>
              <Popconfirm
                title="确定删除选中的主记录吗？"
                disabled={!selectedLedgerMain}
                onConfirm={() => {
                  if (!selectedLedgerMain) {
                    message.warning('请先选择一条主记录')
                    return Promise.resolve()
                  }
                  return handleDeleteLedgerMain(selectedLedgerMain)
                }}
              >
                <Button danger icon={<DeleteOutlined />} disabled={!selectedLedgerMain}>
                  删除主记录
                </Button>
              </Popconfirm>
              <Popconfirm
                title="确定删除选中的更新子行吗？"
                disabled={!selectedLedgerMain || !selectedLedgerUpdate}
                onConfirm={() => {
                  if (!selectedLedgerMain || !selectedLedgerUpdate) {
                    message.warning('请先选择一条更新子行')
                    return Promise.resolve()
                  }
                  return handleDeleteLedgerUpdate(selectedLedgerMain, selectedLedgerUpdate)
                }}
              >
                <Button danger disabled={!selectedLedgerMain || !selectedLedgerUpdate}>
                  删除更新
                </Button>
              </Popconfirm>
            </Space>
          </Space>
        }
        styles={{ body: { padding: 12 } }}
      >
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Card size="small" styles={{ body: { padding: '12px 16px' } }}>
            <Space wrap size={[12, 8]} style={{ width: '100%', justifyContent: 'space-between' }}>
              <Space wrap size={[12, 8]}>
                <Typography.Text type="secondary">点击任一更新行即可同时选中主记录和更新子行。</Typography.Text>
                <Tag color={selectedLedgerMain ? 'purple' : 'default'}>
                  {selectedLedgerMain ? `当前主记录：${displayText(selectedLedgerMain.market_name)} / ${selectedLedgerMain.authorization_file_name}` : '未选择主记录'}
                </Tag>
                <Tag color={selectedLedgerUpdate ? 'geekblue' : 'default'}>
                  {selectedLedgerUpdate ? `当前更新：${displayText(selectedLedgerUpdate.authorization_date)} / ${displayText(selectedLedgerUpdate.handler)}` : '未选择更新子行'}
                </Tag>
              </Space>
              <Space wrap size={[8, 8]}>
                <Typography.Text type="secondary">主记录状态</Typography.Text>
                <Select
                  size="small"
                  style={{ width: 128 }}
                  value={selectedLedgerMain?.status || '待确认'}
                  disabled={!selectedLedgerMain}
                  loading={statusUpdatingId === selectedLedgerMain?.id}
                  options={STATUS_OPTIONS.map((item) => ({ label: item, value: item }))}
                  onChange={(nextValue) => {
                    if (selectedLedgerMain) {
                      void handleQuickStatusChange(selectedLedgerMain, nextValue)
                    }
                  }}
                />
              </Space>
            </Space>
          </Card>

          {ledgerDocumentSections.length ? (
            ledgerDocumentSections.map((section) => (
              <div key={section.product_name}>
                <Typography.Title level={5} style={{ margin: '0 0 12px' }}>
                  产品名称：{section.product_name}
                </Typography.Title>
                <div style={{ overflowX: 'auto' }}>
                  <table
                    style={{
                      width: '100%',
                      minWidth: 1360,
                      borderCollapse: 'collapse',
                      tableLayout: 'fixed',
                      fontSize: 14,
                      lineHeight: 1.75,
                    }}
                  >
                    <thead>
                      <tr>
                        {[
                          ['序号', 64],
                          ['市场/地区', 120],
                          ['授权文件名称', 220],
                          ['质量标准', 100],
                          ['单位名称/国家', 220],
                          ['客户信息编号', 120],
                          ['用途', 260],
                          ['授权日期', 120],
                          ['经手人', 120],
                          ['备注', 220],
                        ].map(([title, width]) => (
                          <th
                            key={title}
                            style={{
                              border: '1px solid var(--color-hairline)',
                              padding: '10px 8px',
                              textAlign: 'center',
                              verticalAlign: 'middle',
                              background: 'var(--color-surface-soft)',
                              fontWeight: 600,
                              width,
                            }}
                          >
                            {title}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {section.records.map((record) => {
                        const updates = sortLedgerUpdates(record.updates)
                        const totalLineCount = Math.max(updates.length, 1)

                        return updates.map((update, updateIndex) => {
                          const isSelectedMain = selectedLedgerMainEffectiveId === record.id
                          const isSelectedUpdate = selectedLedgerUpdateEffectiveId === update.id
                          const rowBackground = isSelectedUpdate
                            ? 'var(--color-primary-bg, #ede9f8)'
                            : isSelectedMain
                              ? '#faf7ff'
                              : undefined

                          return (
                            <tr
                              key={update.id}
                              onClick={() => selectLedgerRow(record, update)}
                              style={{
                                background: rowBackground,
                                cursor: 'pointer',
                              }}
                            >
                              {updateIndex === 0 ? (
                                <>
                                  <td rowSpan={totalLineCount} style={docCellStyleCentered}>
                                    {filteredLedgerSequenceMap.get(record.id) || '-'}
                                  </td>
                                  <td rowSpan={totalLineCount} style={docCellStyle}>
                                    {displayText(record.market_name)}
                                  </td>
                                  <td rowSpan={totalLineCount} style={docCellStyle}>
                                    {displayText(record.authorization_file_name)}
                                  </td>
                                  <td rowSpan={totalLineCount} style={docCellStyleCentered}>
                                    {displayText(record.quality_standard)}
                                  </td>
                                  <td rowSpan={totalLineCount} style={docCellStyle}>
                                    {buildCompanyCountryDisplay(record)}
                                  </td>
                                  <td rowSpan={totalLineCount} style={docCellStyleCentered}>
                                    {displayText(record.customer_code)}
                                  </td>
                                  <td rowSpan={totalLineCount} style={docCellStyle}>
                                    {displayText(record.purpose)}
                                  </td>
                                </>
                              ) : null}
                              <td style={docCellStyleCentered}>{displayText(update.authorization_date)}</td>
                              <td style={docCellStyleCentered}>{displayText(update.handler)}</td>
                              <td style={docCellStyle}>{displayText(update.remarks)}</td>
                            </tr>
                          )
                        })
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            ))
          ) : (
            <Card size="small">
              <Typography.Text type="secondary">当前筛选条件下暂无市场授权记录。</Typography.Text>
            </Card>
          )}
        </Space>
      </Card>

      <Modal
        title={editingFdaRecord ? '编辑 FDA 授权' : '新增 FDA 授权'}
        open={fdaModalOpen}
        onCancel={() => setFdaModalOpen(false)}
        onOk={() => void handleFdaSubmit()}
        confirmLoading={fdaSubmitting}
        width={920}
        destroyOnHidden
      >
        <Form form={fdaForm} layout="vertical" initialValues={EMPTY_FDA_FORM_VALUES}>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item
                label="产品"
                name="product_name"
                rules={[{ required: true, message: '请输入产品名称' }]}
              >
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="序号" name="source_sequence">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                label="FDA客户/公司"
                name="company_name"
                rules={[{ required: true, message: '请输入 FDA 客户/公司' }]}
              >
                <Input />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="地址" name="address">
            <Input.TextArea rows={3} />
          </Form.Item>

          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="Reference No." name="reference_number">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="LOA日期" name="loa_date">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="递交日期" name="submission_date">
                <Input />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="引用章节" name="referenced_sections">
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={ledgerMainModalMode === 'edit' ? '编辑市场授权主记录' : '新增市场授权主记录'}
        open={ledgerMainModalOpen}
        onCancel={resetLedgerMainModal}
        onOk={() => void handleLedgerMainSubmit()}
        confirmLoading={ledgerMainSubmitting}
        width={980}
        destroyOnHidden
      >
        <Form form={ledgerMainForm} layout="vertical" initialValues={EMPTY_LEDGER_MAIN_FORM_VALUES}>
          {ledgerMainModalMode === 'create' ? (
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              首次新增需要填写文档完整字段，创建后再通过“新增更新”只补录授权日期、经手人、备注。
            </Typography.Text>
          ) : (
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
              主记录编辑只处理主体字段和状态；更新信息请使用“编辑更新”。
            </Typography.Text>
          )}

          <Row gutter={12}>
            <Col span={8}>
              <Form.Item
                label="产品"
                name="product_name"
                rules={[{ required: true, message: '请输入产品名称' }]}
              >
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="市场/地区" name="market_name">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="序号" name="source_sequence">
                <Input />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            label="授权文件名称"
            name="authorization_file_name"
            rules={[{ required: true, message: '请输入授权文件名称' }]}
          >
            <Input />
          </Form.Item>

          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="质量标准" name="quality_standard">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="单位名称" name="company_name">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="国家" name="country">
                <Input />
              </Form.Item>
            </Col>
          </Row>

          <Row gutter={12}>
            <Col span={12}>
              <Form.Item label="客户信息编号" name="customer_code">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="状态" name="status">
                <Select options={STATUS_OPTIONS.map((item) => ({ label: item, value: item }))} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="用途" name="purpose">
            <Input.TextArea rows={3} />
          </Form.Item>

          {ledgerMainModalMode === 'create' ? (
            <>
              <Typography.Text strong style={{ display: 'block', marginBottom: 12 }}>
                首次更新信息
              </Typography.Text>
              <Row gutter={12}>
                <Col span={8}>
                  <Form.Item label="授权日期" name="authorization_date">
                    <Input placeholder="如 2024.02.19" />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="经手人" name="handler">
                    <Input />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item label="备注" name="remarks">
                    <Input />
                  </Form.Item>
                </Col>
              </Row>
            </>
          ) : null}
        </Form>
      </Modal>

      <Modal
        title={ledgerUpdateModalMode === 'edit' ? '编辑更新子行' : '新增更新子行'}
        open={ledgerUpdateModalOpen}
        onCancel={resetLedgerUpdateModal}
        onOk={() => void handleLedgerUpdateSubmit()}
        confirmLoading={ledgerUpdateSubmitting}
        width={760}
        destroyOnHidden
      >
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          当前主记录：{updateParentRecord ? `${displayText(updateParentRecord.market_name)} / ${updateParentRecord.authorization_file_name}` : '-'}
        </Typography.Text>
        <Form form={ledgerUpdateForm} layout="vertical" initialValues={EMPTY_LEDGER_UPDATE_FORM_VALUES}>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item label="授权日期" name="authorization_date">
                <Input placeholder="如 2024.02.19" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="经手人" name="handler">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="备注" name="remarks">
                <Input />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </Space>
  )
}
