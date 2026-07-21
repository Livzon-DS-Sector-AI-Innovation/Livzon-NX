import { create } from 'zustand'
import type {
  ProductDossier,
  Chapter,
  ChapterDetail,
} from '@/types/dossier-writer'
import {
  fetchProductDossiers,
  fetchProductDossier,
  fetchChapterTree,
  fetchChapterDetail,
} from '@/lib/api/dossier-writer-client'

interface DossierWriterState {
  // 品种资料列表
  dossiers: ProductDossier[]
  dossiersTotal: number
  dossiersLoading: boolean

  // 当前品种资料
  currentDossier: ProductDossier | null
  currentDossierLoading: boolean

  // 章节树
  chapterTree: Chapter[]
  chapterTreeLoading: boolean

  // 当前章节
  currentChapter: ChapterDetail | null
  currentChapterLoading: boolean

  // Actions
  loadDossiers: (skip?: number, limit?: number) => Promise<void>
  loadDossier: (id: string) => Promise<void>
  loadChapterTree: (dossierId: string) => Promise<void>
  loadChapterDetail: (chapterId: string) => Promise<void>
  setCurrentDossier: (dossier: ProductDossier | null) => void
  setCurrentChapter: (chapter: ChapterDetail | null) => void
}

export const useDossierWriterStore = create<DossierWriterState>((set) => ({
  // 初始状态
  dossiers: [],
  dossiersTotal: 0,
  dossiersLoading: false,

  currentDossier: null,
  currentDossierLoading: false,

  chapterTree: [],
  chapterTreeLoading: false,

  currentChapter: null,
  currentChapterLoading: false,

  // Actions
  loadDossiers: async (skip = 0, limit = 100) => {
    set({ dossiersLoading: true })
    try {
      const data = await fetchProductDossiers(skip, limit)
      set({
        dossiers: data.items,
        dossiersTotal: data.total,
        dossiersLoading: false,
      })
    } catch {
      set({ dossiersLoading: false })
    }
  },

  loadDossier: async (id: string) => {
    set({ currentDossierLoading: true })
    try {
      const dossier = await fetchProductDossier(id)
      set({ currentDossier: dossier, currentDossierLoading: false })
    } catch {
      set({ currentDossierLoading: false })
    }
  },

  loadChapterTree: async (dossierId: string) => {
    set({ chapterTreeLoading: true })
    try {
      const tree = await fetchChapterTree(dossierId)
      set({ chapterTree: tree, chapterTreeLoading: false })
    } catch {
      set({ chapterTreeLoading: false })
    }
  },

  loadChapterDetail: async (chapterId: string) => {
    set({ currentChapterLoading: true })
    try {
      const detail = await fetchChapterDetail(chapterId)
      set({ currentChapter: detail, currentChapterLoading: false })
    } catch {
      set({ currentChapterLoading: false })
    }
  },

  setCurrentDossier: (dossier) => set({ currentDossier: dossier }),
  setCurrentChapter: (chapter) => set({ currentChapter: chapter }),
}))
