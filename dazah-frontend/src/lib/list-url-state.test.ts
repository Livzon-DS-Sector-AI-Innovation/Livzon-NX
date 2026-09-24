import { describe, expect, it } from 'vitest'
import { detailHrefWithReturnTo, getSafeListReturnHref, positiveListNumber, updateListUrl } from './list-url-state'

describe('list URL state', () => {
  it('keeps unrelated query values and resets page when filters change', () => {
    expect(updateListUrl('/purchasing/supplier', new URLSearchParams('tab=active&page=4&supplier=旧'), {
      supplier: '新', page_size: 50,
    }, true)).toBe('/purchasing/supplier?tab=active&supplier=%E6%96%B0&page_size=50')
    expect(updateListUrl('/purchasing/supplier', new URLSearchParams('page=2&auth_token=private'), { page: 3 }))
      .toBe('/purchasing/supplier?page=3')
  })

  it('rejects invalid page numbers', () => {
    expect(positiveListNumber('-2', 1)).toBe(1)
    expect(positiveListNumber('NaN', 20)).toBe(20)
    expect(positiveListNumber('51', 20, 50)).toBe(20)
  })

  it('returns only to the expected internal list path', () => {
    const href = detailHrefWithReturnTo('/registration/validation-audit/7', '/registration/validation-audit?page=3&page_size=50')
    const returnTo = new URL(href, 'https://example.test').searchParams.get('returnTo')
    expect(getSafeListReturnHref(returnTo, '/registration/validation-audit/7')).toBe('/registration/validation-audit?page=3&page_size=50')
    expect(getSafeListReturnHref('//evil.test', '/registration/validation-audit/7')).toBeUndefined()
    expect(getSafeListReturnHref('/quality/deviations?page=3', '/registration/validation-audit/7')).toBeUndefined()
    expect(getSafeListReturnHref('/registration?page=3', '/registration/validation-audit/7', '/registration/validation-audit')).toBeUndefined()
    expect(detailHrefWithReturnTo('/registration/validation-audit/7', '/registration/validation-audit?page=3&auth_token=private')).not.toContain('auth_token')
    expect(detailHrefWithReturnTo('/registration/validation-audit/7', '/registration/validation-audit?page=3&returnTo=%2Fother'))
      .not.toContain('%2Fother')
    expect(getSafeListReturnHref('/registration/validation-audit?auth_token=private', '/registration/validation-audit/7')).toBeUndefined()
  })
})
