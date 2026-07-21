'use client'

import { useEffect, useState, useCallback } from 'react'
import { useParams, useRouter } from 'next/navigation'
import {
  App, Card, Tree, Button, Space, Tag, Upload, Spin, Empty, Descriptions,
  Divider, Popconfirm, Breadcrumb, Typography, Tabs, Modal, Select,
} from 'antd'
import {
  ArrowLeftOutlined, FileWordOutlined, UploadOutlined, DeleteOutlined,
  DownloadOutlined, FolderOutlined, FileOutlined, ReloadOutlined,
  EyeOutlined, CheckCircleOutlined, ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useDossierWriterStore } from '@/stores/dossier-writer'
import {
  uploadChapterAsset, deleteChapterAsset, exportDossier, uploadTemplates, parseTemplates,
  getDownloadUrl, getChapterPreview, matchAssetsToChapters, fillChapterFields, fetchChapterAssets,
  getChapterDocxUrl, updateAssetCategory, fetchAssetCategories,
} from '@/lib/api/dossier-writer-client'
import type { Chapter, ChapterAsset, AssetCategory } from '@/types/dossier-writer'
import type { UploadResponse, ChapterPreview } from '@/lib/api/dossier-writer-client'
import { AiFillPanel } from '@/components/registration/AiFillPanel'
import { DocxPreview } from '@/components/registration/DocxPreview'

const { Text, Title, Paragraph } = Typography

// M3 标准目录结构（固定）
const M3_STRUCTURE = [
  { code: "3.2", title: "主体数据", level: 1, parent_code: null },
  { code: "3.2.S", title: "原料药", level: 2, parent_code: "3.2" },
  { code: "3.2.S.1", title: "基本信息", level: 3, parent_code: "3.2.S" },
  { code: "3.2.S.1.1", title: "药品名称", level: 4, parent_code: "3.2.S.1" },
  { code: "3.2.S.1.2", title: "结构", level: 4, parent_code: "3.2.S.1" },
  { code: "3.2.S.1.3", title: "基本性质", level: 4, parent_code: "3.2.S.1" },
  { code: "3.2.S.2", title: "生产", level: 3, parent_code: "3.2.S" },
  { code: "3.2.S.2.1", title: "生产商", level: 4, parent_code: "3.2.S.2" },
  { code: "3.2.S.2.2", title: "生产工艺控制", level: 4, parent_code: "3.2.S.2" },
  { code: "3.2.S.2.3", title: "物料控制", level: 4, parent_code: "3.2.S.2" },
  { code: "3.2.S.2.4", title: "关键步骤和中间体的控制", level: 4, parent_code: "3.2.S.2" },
  { code: "3.2.S.2.5", title: "工艺验证和/或评价", level: 4, parent_code: "3.2.S.2" },
  { code: "3.2.S.2.6", title: "生产工艺的开发", level: 4, parent_code: "3.2.S.2" },
  { code: "3.2.S.3", title: "特性鉴定", level: 3, parent_code: "3.2.S" },
  { code: "3.2.S.3.1", title: "结构和理化性质", level: 4, parent_code: "3.2.S.3" },
  { code: "3.2.S.3.2", title: "杂质", level: 4, parent_code: "3.2.S.3" },
  { code: "3.2.S.4", title: "原料药的质量控制", level: 3, parent_code: "3.2.S" },
  { code: "3.2.S.4.1", title: "质量标准", level: 4, parent_code: "3.2.S.4" },
  { code: "3.2.S.4.2", title: "分析方法", level: 4, parent_code: "3.2.S.4" },
  { code: "3.2.S.4.3", title: "分析方法的验证", level: 4, parent_code: "3.2.S.4" },
  { code: "3.2.S.4.4", title: "批分析", level: 4, parent_code: "3.2.S.4" },
  { code: "3.2.S.4.5", title: "质量标准制定依据", level: 4, parent_code: "3.2.S.4" },
  { code: "3.2.S.5", title: "对照品", level: 3, parent_code: "3.2.S" },
  { code: "3.2.S.6", title: "包装系统", level: 3, parent_code: "3.2.S" },
  { code: "3.2.S.7", title: "稳定性", level: 3, parent_code: "3.2.S" },
  { code: "3.2.S.7.1", title: "稳定性总结和结论", level: 4, parent_code: "3.2.S.7" },
  { code: "3.2.S.7.2", title: "批准后稳定性研究方案和承诺", level: 4, parent_code: "3.2.S.7" },
  { code: "3.2.S.7.3", title: "稳定性数据", level: 4, parent_code: "3.2.S.7" },
]

interface ChapterWithAssets extends Chapter {
  assets: ChapterAsset[]
  working_file?: string
  source_file?: string
}

export default function DossierDetailPage() {
  const { message } = App.useApp()
  const params = useParams()
  const router = useRouter()
  const dossierId = params.id as string

  const {
    currentDossier, currentDossierLoading, loadDossier,
    chapterTree, chapterTreeLoading, loadChapterTree,
  } = useDossierWriterStore()

  const [selectedChapterId, setSelectedChapterId] = useState<string | null>(null)
  const [selectedChapter, setSelectedChapter] = useState<ChapterWithAssets | null>(null)
  const [exporting, setExporting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadTemplateOpen, setUploadTemplateOpen] = useState(false)
  const [parsing, setParsing] = useState(false)
  const [matching, setMatching] = useState(false)
  const [filling, setFilling] = useState(false)
  const [previewRefreshKey, setPreviewRefreshKey] = useState(0)
  const [assetCategories, setAssetCategories] = useState<AssetCategory[]>([])

  useEffect(() => {
    if (dossierId) {
      loadDossier(dossierId)
      loadChapterTree(dossierId)
    }
  }, [dossierId, loadDossier, loadChapterTree])

  // Sync selectedChapter when chapterTree updates (e.g. after template re-upload)
  useEffect(() => {
    if (!selectedChapterId || chapterTree.length === 0) return
    const findChapter = (chapters: any[]): any => {
      for (const ch of chapters) {
        if (ch.id === selectedChapterId) return ch
        if (ch.children) {
          const found = findChapter(ch.children)
          if (found) return found
        }
      }
      return null
    }
    const updated = findChapter(chapterTree)
    if (updated) {
      setSelectedChapter(prev => {
        if (!prev) return prev
        // Only update if something changed (working_file, has_content, etc.)
        if (prev.working_file !== updated.working_file ||
            prev.source_file !== updated.source_file ||
            prev.has_content !== updated.has_content) {
          return { ...prev, ...updated }
        }
        return prev
      })
    }
  }, [chapterTree, selectedChapterId])

  // 加载章节的素材分类
  const loadCategories = useCallback(async (chapterCode: string) => {
    try {
      const cats = await fetchAssetCategories(chapterCode)
      setAssetCategories(cats)
    } catch {
      setAssetCategories([])
    }
  }, [])

  // 构建树数据
  const buildTreeData = () => {
    const convertToTreeData = (chapters: any[]): any[] => {
      return chapters.map(ch => {
        const children = ch.children ? convertToTreeData(ch.children) : []
        return {
          key: ch.id,
          title: (
            <span className="flex items-center gap-2">
              <span className="text-gray-500">{ch.chapter_code}</span>
              <span className="font-medium">{ch.chapter_title}</span>
              {ch.has_assets && ch.asset_count > 0 && (
                <Tag color="blue" style={{ fontSize: 10, lineHeight: '14px' }}>
                  {ch.asset_count}素材
                </Tag>
              )}
              {ch.has_content && (
                <Tag color="green" style={{ fontSize: 10, lineHeight: '14px' }}>
                  已匹配
                </Tag>
              )}
            </span>
          ),
          chapter: ch,
          children,
          isLeaf: children.length === 0,
        }
      })
    }
    return convertToTreeData(chapterTree)
  }

  // 选择章节
  const handleSelectChapter = async (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      const chapterId = selectedKeys[0] as string
      const findChapter = (chapters: any[]): any => {
        for (const ch of chapters) {
          if (ch.id === chapterId) return ch
          if (ch.children) {
            const found = findChapter(ch.children)
            if (found) return found
          }
        }
        return null
      }

      const chapter = findChapter(chapterTree)
      if (chapter) {
        let assets: ChapterAsset[] = []
        try {
          assets = await fetchChapterAssets(chapterId)
        } catch {
          assets = []
        }
        setSelectedChapterId(chapterId)
        setSelectedChapter({ ...chapter, assets })
        setPreviewRefreshKey(prev => prev + 1)
        // 加载该章节的素材分类
        if (chapter.chapter_code) {
          loadCategories(chapter.chapter_code)
        }
      }
    }
  }

  // 上传素材
  const handleUploadAsset = async (file: File) => {
    if (!selectedChapterId) return false
    setUploading(true)
    try {
      await uploadChapterAsset(selectedChapterId, [file])
      message.success('素材上传成功')
      const assets = await fetchChapterAssets(selectedChapterId)
      setSelectedChapter(prev => prev ? { ...prev, assets } : prev)
      loadChapterTree(dossierId)
    } catch {
      message.error('上传失败')
    } finally {
      setUploading(false)
    }
    return false
  }

  // 删除素材
  const handleDeleteAsset = async (assetId: string) => {
    if (!selectedChapterId) return
    try {
      await deleteChapterAsset(assetId)
      message.success('删除成功')
      const assets = await fetchChapterAssets(selectedChapterId)
      setSelectedChapter(prev => prev ? { ...prev, assets } : prev)
      loadChapterTree(dossierId)
    } catch {
      message.error('删除失败')
    }
  }

  // 更新素材分类
  const handleCategoryChange = async (assetId: string, categoryId: string | null) => {
    try {
      await updateAssetCategory(assetId, categoryId)
      // 更新本地状态
      setSelectedChapter(prev => {
        if (!prev) return prev
        return {
          ...prev,
          assets: prev.assets.map(a =>
            a.id === assetId ? { ...a, category_id: categoryId } : a
          ),
        }
      })
      message.success('分类已更新')
    } catch (err: any) {
      message.error(err.message || '更新分类失败')
    }
  }

  // 上传模板
  const handleUploadTemplate = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setParsing(true)
    try {
      const fileArray = Array.from(files)
      const result: UploadResponse = await uploadTemplates(dossierId, fileArray)
      if (result.success_count > 0) {
        message.success(`上传成功 ${result.success_count} 个文件，已自动匹配 ${result.matched_count || 0} 个章节`)
      }
      if (result.failed_count > 0) {
        message.warning(`${result.failed_count} 个文件上传失败`)
      }
      setUploadTemplateOpen(false)
      
      // Reset the input element so the same file can be selected again
      const input = document.getElementById('detail-template-upload') as HTMLInputElement
      if (input) input.value = ''
      
      // Reload dossier and chapter tree (store will update asynchronously)
      loadDossier(dossierId)
      loadChapterTree(dossierId)
      
      // Trigger preview refresh
      setPreviewRefreshKey(prev => prev + 1)
    } catch (err: any) {
      message.error(err?.message || '上传失败')
    } finally {
      setParsing(false)
    }
  }

  // 智能匹配素材
  const handleMatchAssets = async () => {
    setMatching(true)
    try {
      if (!dossierId) return
      const result = await matchAssetsToChapters(dossierId)
      message.success(result.message)
      loadChapterTree(dossierId)
    } catch (err: any) {
      message.error(err?.message || '匹配失败')
    } finally {
      setMatching(false)
    }
  }

  // 导出
  const handleExportAll = async () => {
    if (!currentDossier) return
    setExporting(true)
    try {
      const result = await exportDossier(currentDossier.id)
      if (result.success) {
        message.success(`导出成功: ${result.filename}`)
        const downloadUrl = getDownloadUrl(currentDossier.id, result.filename!)
        window.open(downloadUrl, '_blank')
      } else {
        message.error(result.message)
      }
    } catch (err: any) {
      message.error(err?.message || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  const handleExportChapter = async () => {
    if (!currentDossier || !selectedChapterId) return
    setExporting(true)
    try {
      const result = await exportDossier(currentDossier.id, [selectedChapterId])
      if (result.success) {
        message.success(`导出成功: ${result.filename}`)
        const downloadUrl = getDownloadUrl(currentDossier.id, result.filename!)
        window.open(downloadUrl, '_blank')
      } else {
        message.error(result.message)
      }
    } catch (err: any) {
      message.error(err?.message || '导出失败')
    } finally {
      setExporting(false)
    }
  }

  // 下载当前章节工作副本
  const handleDownloadChapter = () => {
    if (!selectedChapterId) return
    const url = getChapterDocxUrl(selectedChapterId)
    window.open(url, '_blank')
  }

  // 填充章节字段
  const handleFillFields = async () => {
    if (!selectedChapterId) {
      message.warning('请先选择章节')
      return
    }
    try {
      setFilling(true)
      message.loading({ content: '正在从素材提取并填充内容...', key: 'filling', duration: 0 })
      const result = await fillChapterFields(selectedChapterId)
      message.destroy('filling')
      if (result.success) {
        message.success({ content: `填充完成：${result.filled_count}/${result.total_fields} 个字段`, duration: 5 })
        setPreviewRefreshKey(prev => prev + 1)
        if (dossierId) await loadDossier(dossierId)
      } else {
        message.warning(result.message)
      }
    } catch (error: any) {
      message.destroy('filling')
      message.error(error.message || '填充失败')
    } finally {
      setFilling(false)
    }
  }

  // AI 填充完成后刷新预览
  const handleFillComplete = useCallback(() => {
    setPreviewRefreshKey(prev => prev + 1)
  }, [])

  // 素材变更后刷新
  const handleAssetsChange = useCallback(async () => {
    if (selectedChapterId) {
      const assets = await fetchChapterAssets(selectedChapterId)
      setSelectedChapter(prev => prev ? { ...prev, assets } : prev)
      loadChapterTree(dossierId)
    }
  }, [selectedChapterId, dossierId, loadChapterTree])

  const treeData = buildTreeData()

  // 统计未分类素材数
  const uncategorizedCount = selectedChapter?.assets?.filter(a => !a.category_id).length || 0

  return (
    <App>
    <div className="h-full flex flex-col" style={{ height: 'calc(100vh - 64px)' }}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-5 py-3 bg-white border-b border-gray-200 flex-shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => router.push('/registration/dossier-writer')}
          />
          <div className="min-w-0">
            <h1 className="text-lg font-semibold truncate m-0">
              {currentDossier?.product_name || '加载中...'}
            </h1>
            <div className="text-xs text-gray-500">
              {currentDossier?.sterile_type && <span>{currentDossier.sterile_type}</span>}
              {currentDossier?.manufacturer && <span className="ml-2">{currentDossier.manufacturer}</span>}
            </div>
          </div>
          {currentDossier?.status && (
            <Tag color={currentDossier.status === 'active' ? 'green' : 'default'} className="ml-2">
              {currentDossier.status}
            </Tag>
          )}
        </div>

        <Space>
          <Button onClick={handleMatchAssets} loading={matching} disabled={!currentDossier}>
            智能匹配素材
          </Button>
          <Button onClick={handleFillFields} loading={filling} disabled={!selectedChapterId}>
            <ThunderboltOutlined /> 提取并填充
          </Button>
          <Button onClick={handleExportChapter} loading={exporting} disabled={!selectedChapterId}>
            导出当前章节
          </Button>
          <Button type="primary" onClick={handleExportAll} loading={exporting} disabled={!currentDossier}>
            导出全部
          </Button>
          <Button onClick={() => setUploadTemplateOpen(true)} icon={<UploadOutlined />}>
            上传模板
          </Button>
        </Space>
      </div>

      {/* Main content: left-right split */}
      <div className="flex flex-1 min-h-0">
        {/* Left panel */}
        <div className="w-[420px] flex-shrink-0 border-r border-gray-200 bg-white flex flex-col">
          {/* Chapter tree */}
          <div className="h-[260px] flex-shrink-0 border-b border-gray-200 overflow-auto p-3">
            <div className="text-xs text-gray-500 mb-2 font-medium">M3 目录结构</div>
            {chapterTreeLoading ? (
              <div className="flex justify-center py-8"><Spin /></div>
            ) : treeData.length > 0 ? (
              <Tree
                treeData={treeData}
                onSelect={handleSelectChapter}
                selectedKeys={selectedChapterId ? [selectedChapterId] : []}
                defaultExpandAll
                blockNode
                className="text-sm"
              />
            ) : (
              <Empty description="请先上传并解析模板" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </div>

          {/* Bottom panel: tabs for assets + AI fill */}
          <div className="flex-1 min-h-0 overflow-auto">
            {selectedChapter ? (
              <Tabs
                size="small"
                className="px-1"
                defaultActiveKey="assets"
                items={[
                  {
                    key: 'assets',
                    label: (
                      <span>
                        素材 ({selectedChapter.assets?.length || 0})
                        {uncategorizedCount > 0 && (
                          <Tag color="orange" style={{ marginLeft: 4, fontSize: 10, lineHeight: '14px' }}>
                            {uncategorizedCount}未分类
                          </Tag>
                        )}
                      </span>
                    ),
                    children: (
                      <div className="p-2">
                        <div className="mb-3">
                          <Upload
                            beforeUpload={handleUploadAsset}
                            showUploadList={false}
                            disabled={!selectedChapterId}
                          >
                            <Button type="primary" icon={<UploadOutlined />} loading={uploading} block>
                              上传素材
                            </Button>
                          </Upload>
                        </div>

                        {uncategorizedCount > 0 && (
                          <div className="mb-3 p-2 bg-orange-50 border border-orange-200 rounded text-xs text-orange-700">
                            <WarningOutlined /> 有 {uncategorizedCount} 个素材未分类，AI 填充时可能无法准确提取。请为每个素材指定正确的分类。
                          </div>
                        )}

                        {selectedChapter.assets?.length > 0 ? (
                          <div className="divide-y divide-gray-100">
                            {selectedChapter.assets.map((asset: ChapterAsset) => (
                              <div key={asset.id} className="py-2">
                                <div className="flex items-center gap-2 mb-1">
                                  <FileWordOutlined className="text-blue-500 flex-shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <div className="font-medium text-sm truncate">{asset.original_filename}</div>
                                    <div className="mt-0.5 flex items-center gap-2 text-xs text-gray-500">
                                      {asset.file_type && <Tag style={{ marginRight: 0 }}>{asset.file_type.toUpperCase()}</Tag>}
                                      {asset.file_size && <span>{(asset.file_size / 1024).toFixed(1)} KB</span>}
                                      <span>{dayjs(asset.uploaded_at).format('MM-DD HH:mm')}</span>
                                    </div>
                                  </div>
                                  <Popconfirm
                                    title="确定删除此素材？"
                                    onConfirm={() => handleDeleteAsset(asset.id)}
                                    okText="确定"
                                    cancelText="取消"
                                  >
                                    <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                                  </Popconfirm>
                                </div>
                                {/* Category dropdown */}
                                <div className="ml-5">
                                  <Select
                                    size="small"
                                    placeholder="选择分类"
                                    allowClear
                                    value={asset.category_id || undefined}
                                    onChange={(val) => handleCategoryChange(asset.id, val || null)}
                                    className="w-full"
                                    style={{ fontSize: 12 }}
                                    options={assetCategories.map(cat => ({
                                      label: cat.category_name,
                                      value: cat.id,
                                    }))}
                                    notFoundContent={<span className="text-xs text-gray-400">该章节暂无分类配置</span>}
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <Empty description="暂无素材" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        )}
                      </div>
                    ),
                  },
                  {
                    key: 'ai-fill',
                    label: 'AI 智能填充',
                    children: (
                      <AiFillPanel
                        chapterId={selectedChapter.id}
                        chapterCode={selectedChapter.chapter_code || undefined}
                        assets={selectedChapter.assets || []}
                        onAssetsChange={handleAssetsChange}
                        onFillComplete={handleFillComplete}
                      />
                    ),
                  },
                ]}
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <Empty description="请从上方目录选择一个章节" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </div>
            )}
          </div>
        </div>

        {/* Right panel: Document Preview */}
        <div className="flex-1 min-w-0">
          <DocxPreview
            chapterId={selectedChapterId}
            chapterTitle={selectedChapter ? `${selectedChapter.chapter_code} ${selectedChapter.chapter_title}` : undefined}
            onDownload={handleDownloadChapter}
            refreshKey={previewRefreshKey}
          />
        </div>
      </div>

      {/* 上传模板弹窗 */}
      <Modal
        title="上传申报资料模板"
        open={uploadTemplateOpen}
        onCancel={() => setUploadTemplateOpen(false)}
        footer={null}
        width={500}
      >
        <div className="py-4">
          <p className="mb-4 text-gray-600">
            请上传 Word 格式的申报资料模板文件（.docx），支持多文件批量上传
          </p>
          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
            <FileWordOutlined className="text-4xl text-blue-500 mb-4" />
            <p className="mb-4">点击或拖拽文件到此处上传（可多选）</p>
            <input
              type="file"
              accept=".docx"
              multiple
              onChange={(e) => handleUploadTemplate(e.target.files)}
              className="hidden"
              id="detail-template-upload"
            />
            <label
              htmlFor="detail-template-upload"
              className="cursor-pointer inline-block px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              {parsing ? '处理中...' : '选择文件'}
            </label>
          </div>
        </div>
      </Modal>
    </div>
    </App>
  )
}
