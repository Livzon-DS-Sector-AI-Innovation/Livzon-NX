import { describe, expect, it } from 'vitest'

import {
  cnToInt,
  extractAnnexRefs,
  formatTopicForSignin,
  matchDrugCategory,
  matchTrainingType,
} from './TrainingSignInTabsClient'

describe('TrainingSignInTabsClient helpers', () => {
  describe('matchTrainingType', () => {
    it('returns 管理类 when file code present in topic or content', () => {
      expect(matchTrainingType('岗位培训', 'SOP-QA-001/02 文件')).toBe('管理类')
    })
    it('matches topic keywords first, then full text', () => {
      expect(matchTrainingType('消防安全与应急疏散', '')).toBe('EHS培训')
      expect(matchTrainingType('', 'GMP质量体系培训内容')).toBe('质量培训')
    })
    it('returns undefined when no keyword matches', () => {
      expect(matchTrainingType('', '没有匹配关键词的内容')).toBeUndefined()
    })
  })

  describe('matchDrugCategory', () => {
    it('prefers veterinary keywords then human drug', () => {
      expect(matchDrugCategory('', '兽药多拉菌素')).toBe('兽药')
      expect(matchDrugCategory('GMP培训', '')).toBe('人药')
    })
    it('returns undefined when no category matches', () => {
      expect(matchDrugCategory('', '普通行政培训')).toBeUndefined()
    })
  })

  describe('formatTopicForSignin', () => {
    it('formats up to 2 entries with codes', () => {
      const out = formatTopicForSignin([
        { name: '指南', code: 'SOP-1' },
        { name: '手册', resolvedCode: 'TR-2' },
      ])
      expect(out).toBe('《指南》（SOP-1）、《手册》（TR-2）')
    })
    it('truncates beyond 2 entries and appends remainder note', () => {
      const out = formatTopicForSignin([
        { name: 'A', code: 'C1' },
        { name: 'B', code: 'C2' },
        { name: 'C', code: 'C3' },
        { name: 'D' },
      ])
      expect(out).toBe('《A》（C1）、《B》（C2）等4份文件详见附件')
    })
  })

  describe('cnToInt', () => {
    it('handles arabic and full-width digits', () => {
      expect(cnToInt('3')).toBe(3)
      expect(cnToInt('１２')).toBe(12)
    })
    it('handles Chinese numerals with tens', () => {
      expect(cnToInt('十')).toBe(10)
      expect(cnToInt('十二')).toBe(12)
      expect(cnToInt('二十三')).toBe(23)
      expect(cnToInt('一')).toBe(1)
    })
    it('returns null for non-numeric input', () => {
      expect(cnToInt('abc')).toBeNull()
    })
  })

  describe('extractAnnexRefs', () => {
    it('extracts and dedupes annex references in order', () => {
      expect(extractAnnexRefs('见附件1和附件二，另见附件１')).toEqual([
        '附件1',
        '附件2',
      ])
    })
    it('returns empty array when no references', () => {
      expect(extractAnnexRefs('无附件引用')).toEqual([])
    })
  })
})
