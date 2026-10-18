import { describe, expect, it } from 'vitest'

import {
  asAttachmentList,
  asPersonList,
  asUrlValue,
  columnOptions,
  displayFieldText,
  isPreviewableAttachment,
  toPageTableStats,
  toRecordRow,
  toRecordRows,
} from './safety-page-tables'

describe('safety page table helpers', () => {
  it('normalizes record rows that omit fields', () => {
    expect(toRecordRow({ record_id: 'rec-1' })).toEqual({
      record_id: 'rec-1',
      fields: {},
    })
    expect(toRecordRows(undefined)).toEqual([])
    expect(toRecordRows([{ record_id: 'a', fields: { x: 1 } }])).toEqual([
      { record_id: 'a', fields: { x: 1 } },
    ])
  })

  it('treats missing column options as an empty list', () => {
    expect(
      columnOptions({
        field_id: 'f1',
        name: '列',
        type: 1,
        kind: 'text',
        is_primary: false,
        editable: true,
      }),
    ).toEqual([])
  })

  it('keeps only well-formed people and attachments', () => {
    expect(
      asPersonList([
        { id: 'ou_1', name: '徐亮', avatar_url: 'https://a/v.png' },
        { id: 'ou_2', name: '杜伟伟' },
        { name: '缺 id' },
        'nope',
      ]),
    ).toEqual([
      { id: 'ou_1', name: '徐亮', avatar_url: 'https://a/v.png' },
      { id: 'ou_2', name: '杜伟伟', avatar_url: null },
    ])
    expect(asPersonList('not-a-list')).toEqual([])

    expect(
      asAttachmentList([
        { file_token: 'tok-1', name: 'a.jpg', type: 'image/jpeg' },
        { name: '缺 token' },
      ]),
    ).toEqual([{ file_token: 'tok-1', name: 'a.jpg', type: 'image/jpeg' }])
    expect(asAttachmentList(null)).toEqual([])
  })

  it('parses hyperlink values from objects and raw strings', () => {
    expect(asUrlValue({ link: 'https://a', text: '看这里' })).toEqual({
      link: 'https://a',
      text: '看这里',
    })
    expect(asUrlValue({ text: '没有链接' })).toBeNull()
    expect(asUrlValue('https://a')).toBeNull()
  })

  it('renders display text for each decoded value shape', () => {
    expect(displayFieldText(null)).toBe('')
    expect(displayFieldText('')).toBe('')
    expect(displayFieldText(true)).toBe('是')
    expect(displayFieldText(false)).toBe('否')
    expect(displayFieldText(12)).toBe('12')
    expect(displayFieldText('文本')).toBe('文本')
    expect(displayFieldText(['A', 'B'])).toBe('A、B')
    expect(displayFieldText([{ id: 'ou_1', name: '徐亮' }])).toBe('徐亮')
    expect(displayFieldText({ link: 'https://a', text: '看这里' })).toBe('看这里')
  })

  it('flags only inline-previewable attachment types', () => {
    expect(
      isPreviewableAttachment({ file_token: 't', name: 'a.jpg', type: 'image/jpeg' }),
    ).toBe(true)
    expect(
      isPreviewableAttachment({ file_token: 't', name: 'a.pdf', type: 'application/pdf' }),
    ).toBe(true)
    expect(
      isPreviewableAttachment({
        file_token: 't',
        name: 'a.docx',
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      }),
    ).toBe(false)
  })
})

describe('toPageTableStats', () => {
  it('returns null for missing stats and fills optional arrays', () => {
    expect(toPageTableStats(null)).toBeNull()
    expect(toPageTableStats(undefined)).toBeNull()

    const result = toPageTableStats({
      page_key: 'k',
      page_name: '24小时值班隐患',
      total: 3,
      groups: [
        { field: '值班日期', kind: 'date', mode: 'month' }, // 无 buckets
      ],
    } as never)
    expect(result).toEqual({
      page_key: 'k',
      page_name: '24小时值班隐患',
      total: 3,
      // 缺失时补 null，与后端仪表盘「到期摘要」可选口径一致
      due_summary: null,
      groups: [{ field: '值班日期', kind: 'date', mode: 'month', buckets: [] }],
    })
  })
})
