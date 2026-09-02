'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  App, Button, Tag, Select, Input, Space, Alert,
  Badge, Empty, Spin, Card, Modal, Typography,
} from 'antd'
import {
  ThunderboltOutlined, CheckOutlined,
  ReloadOutlined, FileImageOutlined,
} from '@ant-design/icons'
import type { ChapterAsset, AssetCategory } from '@/types/dossier-writer'
import type { AIPreviewResult, AIFieldResult, PageSplitInfo } from '@/types/dossier-writer'
import {
  fetchAssetCategories, aiPreviewExtraction, aiConfirmAndFill,
  splitPreview, splitConfirmAndInsert,
} from '@/lib/api/dossier-writer-client'

const { Text, Paragraph } = Typography

interface AiFillPanelProps {
  chapterId: string
  chapterCode?: string
  assets: ChapterAsset[]
  onAssetsChange: () => void
  onFillComplete?: () => void
}

export function AiFillPanel({ chapterId, chapterCode, assets, onAssetsChange, onFillComplete }: AiFillPanelProps) {
  const { message } = App.useApp()

  // Categories (for display labels)
  const [categories, setCategories] = useState<AssetCategory[]>([])
  const [categoriesLoading, setCategoriesLoading] = useState(false)

  // AI preview
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewResult, setPreviewResult] = useState<AIPreviewResult | null>(null)
  const [editedFields, setEditedFields] = useState<AIFieldResult[]>([])
  // Get image fields that need pages
  const imageFields = editedFields.filter(f => f.field_type === 'image_appendix')

  // Page split
  const [splitModalOpen, setSplitModalOpen] = useState(false)
  const [splitLoading, setSplitLoading] = useState(false)
  const [splitAsset, setSplitAsset] = useState<ChapterAsset | null>(null)
  const [splitPages, setSplitPages] = useState<PageSplitInfo[]>([])
  const [splitInserting, setSplitInserting] = useState(false)

  // Asset selection modal (when multiple assets match a category)
  const [assetSelectModalOpen, setAssetSelectModalOpen] = useState(false)
  const [assetSelectCandidates, setAssetSelectCandidates] = useState<ChapterAsset[]>([])
  const [assetSelectTargetField, setAssetSelectTargetField] = useState<AIFieldResult | null>(null)

  // Fill
  const [filling, setFilling] = useState(false)
  const [fillDone, setFillDone] = useState(false)
  const [fillResults, setFillResults] = useState<Array<{field_name: string; status: string; message: string}>>([])

  const loadCategories = useCallback(async () => {
    if (!chapterCode) return
    setCategoriesLoading(true)
    try {
      const data = await fetchAssetCategories(chapterCode)
      setCategories(data)
    } catch {
      // Category labels are optional; assets remain usable without them.
    } finally {
      setCategoriesLoading(false)
    }
  }, [chapterCode])

  // Reset fill state when chapter changes
  useEffect(() => {
    setFillDone(false)
    setPreviewResult(null)
    setEditedFields([])
    setFillResults([])
  }, [chapterId])

  // Load categories for label display
  useEffect(() => {
    if (chapterCode) {
      loadCategories()
    }
  }, [chapterCode, loadCategories])

  // Build category name map from assets
  const getCategoryName = (asset: ChapterAsset): string | undefined => {
    if (!asset.category_id) return undefined
    const cat = categories.find(c => c.id === asset.category_id)
    return cat?.category_name
  }

  // Group assets by category for display
  const groupedAssets = categories.map(cat => ({
    category: cat,
    assets: assets.filter(a => a.category_id === cat.id),
  })).filter(g => g.assets.length > 0)

  const uncategorizedAssets = assets.filter(a => !a.category_id)

  // AI preview
  const handleAiPreview = async () => {
    setPreviewLoading(true)
    try {
      const result = await aiPreviewExtraction(chapterId)
      if (result.success) {
        setPreviewResult(result)
        setEditedFields(result.fields)
        message.success(`提取完成: ${result.fields.length} 个字段`)
      } else {
        message.warning(result.message)
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : 'AI 提取失败')
    } finally {
      setPreviewLoading(false)
    }
  }

  // Handle field edit
  const handleFieldEdit = (index: number, value: AIFieldResult['value']) => {
    setEditedFields(prev => {
      const next = [...prev]
      next[index] = { ...next[index], value }
      return next
    })
  }

  // Confirm and fill
  const handleConfirmFill = async () => {
    setFilling(true)
    try {
      const result = await aiConfirmAndFill(chapterId, { fields: editedFields })
      if (result.success) {
        setFillResults(result.results || [])
        setFillDone(true)
        onFillComplete?.()
        const filled = (result.results || []).filter((resultItem) => (
          resultItem.status === 'filled'
        )).length
        const total = (result.results || []).length
        message.success(`填充完成: ${filled}/${total} 个字段`)
      } else {
        message.warning(result.message || '填充失败')
      }
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '填充失败')
    } finally {
      setFilling(false)
    }
  }

  // Asset selection from category
  const handleChooseAssetForField = (field: AIFieldResult) => {

    if (!field.source_category) {
      message.warning('该字段未配置素材分类，请联系管理员')
      return
    }

    const targetCategory = categories.find(c => c.category_name === field.source_category)
    if (!targetCategory) {
      message.error(`未找到分类"${field.source_category}"，请确保素材分类配置正确`)
      console.error('[ChooseAsset] Category not found:', field.source_category, 'Available:', categories.map(c => c.category_name))
      return
    }


    const matchingAssets = assets.filter(a => a.category_id === targetCategory.id)

    if (matchingAssets.length === 0) {
      message.warning(`分类"${field.source_category}"下没有素材文件，请先在素材 Tab 中上传文件并选择此分类`)
      return
    }

    // If only one asset, proceed directly
    if (matchingAssets.length === 1) {
      handlePageSplit(matchingAssets[0])
      return
    }

    // Multiple assets: show selection modal
    setAssetSelectCandidates(matchingAssets)
    setAssetSelectTargetField(field)
    setAssetSelectModalOpen(true)
  }

  // Page split for image fields
  const handlePageSplit = async (asset: ChapterAsset) => {
    setSplitAsset(asset)
    setSplitLoading(true)
    setSplitModalOpen(true)
    try {
      const slots = imageFields.map(f => f.field_name)
      const result = await splitPreview(asset.id, slots)
      setSplitPages(result.pages || [])
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '页面拆分失败')
    } finally {
      setSplitLoading(false)
    }
  }

  const handleInsertPage = async (page: PageSplitInfo, slotName: string) => {
    if (!splitAsset) return
    setSplitInserting(true)
    try {
      await splitConfirmAndInsert(chapterId, [{
        split_id: `${splitAsset.id}_${page.page_number}`,
        appendix_slot: slotName,
        asset_id: splitAsset.id,
        page_number: page.page_number,
      }])
      message.success(`已插入第 ${page.page_number} 页到 ${slotName}`)
      
      // Close the split modal
      setSplitModalOpen(false)
      
      // Update the field value to show which page was inserted
      const fieldIndex = editedFields.findIndex(f => f.field_name === slotName)
      if (fieldIndex !== -1) {
        setEditedFields(prev => {
          const next = [...prev]
          next[fieldIndex] = { 
            ...next[fieldIndex], 
            value: `已插入: ${splitAsset.original_filename} 第${page.page_number}页`,
            source: `素材: ${splitAsset.original_filename}`
          }
          return next
        })
      }
      
      // Trigger refresh
      onAssetsChange()
    } catch (err: unknown) {
      message.error(err instanceof Error ? err.message : '插入失败')
    } finally {
      setSplitInserting(false)
    }
  }

  const hasUncategorized = uncategorizedAssets.length > 0

  return (
    <div className="p-2 space-y-3">
      {/* Asset overview (read-only) */}
      {assets.length > 0 && (
        <Card size="small" title={<span className="text-xs">素材概览 <Badge count={assets.length} showZero style={{ backgroundColor: '#8884' }} /></span>}>
          {groupedAssets.map(g => (
            <div key={g.category.id} className="mb-2">
              <div className="text-xs font-medium text-gray-600 mb-1">
                {g.category.category_name}
                <Tag style={{ marginLeft: 4 }}>{g.assets.length}</Tag>
              </div>
              {g.assets.map(a => (
                <div key={a.id} className="text-xs text-gray-500 truncate pl-2">
                  📄 {a.original_filename}
                </div>
              ))}
            </div>
          ))}
          {uncategorizedAssets.length > 0 && (
            <div className="mb-2">
              <div className="text-xs font-medium text-orange-600 mb-1">
                ⚠ 未分类
                <Tag color="orange" style={{ marginLeft: 4 }}>{uncategorizedAssets.length}</Tag>
              </div>
              {uncategorizedAssets.map(a => (
                <div key={a.id} className="text-xs text-orange-500 truncate pl-2">
                  📄 {a.original_filename}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {hasUncategorized && (
        <Alert
          type="warning"
          showIcon
          title="有素材未分类"
          description="请在素材 Tab 中为每个素材指定分类，否则 AI 提取可能不准确。"
          className="text-xs"
        />
      )}

      {/* AI Preview button */}
      <Button
        type="primary"
        icon={<ThunderboltOutlined />}
        loading={previewLoading}
        disabled={assets.length === 0}
        onClick={handleAiPreview}
        block
      >
        AI 智能提取
      </Button>

      {/* Preview results */}
      {previewResult && !fillDone && (
        <Card
          size="small"
          title={
            <span className="text-xs">
              提取结果 ({editedFields.filter(f => f.value != null).length}/{editedFields.length})
            </span>
          }
          extra={
            <Space>
              <Button size="small" icon={<ReloadOutlined />} onClick={handleAiPreview}>
                重新提取
              </Button>
              <Button
                size="small"
                type="primary"
                icon={<CheckOutlined />}
                onClick={handleConfirmFill}
                loading={filling}
              >
                确认并填充
              </Button>
            </Space>
          }
        >
          <div className="space-y-2 max-h-[400px] overflow-auto">
            {editedFields.map((field, idx) => (
              <div key={idx} className="border border-gray-100 rounded p-2">
                <div className="flex items-center justify-between mb-1">
                  <Text strong className="text-xs">{field.field_name}</Text>
                  <Space size={4}>
                    <Tag color={field.confidence >= 0.8 ? 'green' : field.confidence >= 0.5 ? 'orange' : 'red'} style={{ fontSize: 10 }}>
                      {Math.round(field.confidence * 100)}%
                    </Tag>
                    <Tag style={{ fontSize: 10 }}>{field.field_type}</Tag>
                  </Space>
                </div>

                {field.field_type === 'table' && Array.isArray(field.value) ? (
                  <div className="text-xs text-gray-500">
                    表格数据: {field.value.length} 行 × {field.value[0]?.length ?? 0} 列
                  </div>
                ) : field.field_type === 'image_appendix' ? (
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Tag color="purple" style={{ fontSize: 10 }}>图片字段</Tag>
                      <Text className="text-xs text-gray-500">{String(field.value || '待插入')}</Text>
                    </div>
                    <Button
                      size="small"
                      icon={<FileImageOutlined />}
                      onClick={() => handleChooseAssetForField(field)}
                    >
                      选择页
                    </Button>
                  </div>
                ) : (
                  <Input
                    size="small"
                    value={field.value as string}
                    onChange={(e) => handleFieldEdit(idx, e.target.value)}
                    className="w-full"
                  />
                )}

                <div className="text-xs text-gray-400 mt-1 truncate">
                  来源: {field.source || '未知'}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {fillDone && (
        <Alert
          type="success"
          title="填充完成"
          description={(() => {
            const textFilled = fillResults.filter(r => r.status === 'filled').filter(r => !r.message.includes('图片')).length
            const imgFilled = fillResults.filter(r => r.status === 'filled' && r.message.includes('图片')).length
            const imgFailed = fillResults.filter(r => r.status === 'failed' && r.message.includes('图片')).length
            const textFailed = fillResults.filter(r => r.status === 'failed' && !r.message.includes('图片')).length
            return (
              <div className="text-xs space-y-1">
                <div>文本字段: {textFilled} 成功{textFailed > 0 ? `, ${textFailed} 失败` : ''}</div>
                <div>图片插入: {imgFilled} 成功{imgFailed > 0 ? `, ${imgFailed} 失败（缺少对应素材文件，请在素材 Tab 上传）` : ''}</div>
              </div>
            )
          })()}
          showIcon
          className="flex-1"
          action={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => {
                setFillDone(false)
                setPreviewResult(null)
                setEditedFields([])
                setFillResults([])
              }}
            >
              重新填充
            </Button>
          }
        />
      )}

      {/* Page Split Modal */}
      <Modal
        title={`页面拆分 - ${splitAsset?.original_filename}`}
        open={splitModalOpen}
        onCancel={() => setSplitModalOpen(false)}
        footer={null}
        width={600}
      >
        {splitLoading ? (
          <div className="flex justify-center py-8"><Spin /></div>
        ) : splitPages.length > 0 ? (
          <div className="space-y-3 max-h-[400px] overflow-auto">
            {splitPages.map((page) => (
              <div key={page.page_number} className="border border-gray-200 rounded p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <Text strong>第 {page.page_number} 页</Text>
                    {page.content_summary && (
                      <Paragraph className="text-xs text-gray-500 mt-1 mb-0" ellipsis={{ rows: 2 }}>
                        {page.content_summary}
                      </Paragraph>
                    )}
                  </div>
                  <Select
                    size="small"
                    placeholder="插入到..."
                    style={{ width: 180 }}
                    onChange={(slot) => handleInsertPage(page, slot)}
                    disabled={splitInserting}
                    optionLabelProp="label"
                  >
                    {imageFields.map(f => (
                      <Select.Option 
                        key={f.field_name} 
                        value={f.value || f.field_name}
                        label={`${f.field_name} → ${f.value || '无位置'}`}
                      >
                        <div className="flex justify-between items-center">
                          <span className="text-sm">{f.field_name}</span>
                          <span className="text-gray-400 text-xs ml-2">{f.value || '待插入'}</span>
                        </div>
                      </Select.Option>
                    ))}
                  </Select>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty description="无法拆分页面" />
        )}
      </Modal>

      {/* Asset Selection Modal - shown when multiple assets match a category */}
      <Modal
        title={`选择素材文件 - ${assetSelectTargetField?.field_name || ''}`}
        open={assetSelectModalOpen}
        onCancel={() => setAssetSelectModalOpen(false)}
        footer={null}
        width={500}
      >
        <div className="space-y-2">
          <Text className="text-xs text-gray-500">
            分类「{assetSelectTargetField?.source_category}」下有 {assetSelectCandidates.length} 个素材文件，请选择要使用的文件：
          </Text>
          {assetSelectCandidates.map(asset => (
            <div
              key={asset.id}
              className="border border-gray-200 rounded-lg p-3 hover:border-blue-400 hover:bg-blue-50 cursor-pointer transition-colors"
              onClick={() => {
                setAssetSelectModalOpen(false)
                handlePageSplit(asset)
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileImageOutlined className="text-gray-400" />
                  <span className="text-sm font-medium">{asset.original_filename}</span>
                </div>
                <Tag color="blue" style={{ fontSize: 10 }}>
                  {asset.file_size ? `${(asset.file_size / 1024).toFixed(0)} KB` : ''}
                </Tag>
              </div>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  )
}
