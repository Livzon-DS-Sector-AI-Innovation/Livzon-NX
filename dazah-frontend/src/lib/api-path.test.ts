import { describe, expect, it } from 'vitest'

import { apiV1, backendAssetPath } from './api-path'

describe('apiV1', () => {
  it('normalizes relative API paths without duplicating the version prefix', () => {
    expect(apiV1('quality/records')).toBe('/api/v1/quality/records')
    expect(apiV1('/quality/records')).toBe('/api/v1/quality/records')
    expect(apiV1('/api/v1/quality/records')).toBe('/api/v1/quality/records')
  })

  it('returns the API prefix for an empty path', () => {
    expect(apiV1('')).toBe('/api/v1')
  })
})

describe('backendAssetPath', () => {
  it('preserves remote URLs and normalizes local asset paths', () => {
    expect(backendAssetPath('https://example.test/report.pdf')).toBe(
      'https://example.test/report.pdf'
    )
    expect(backendAssetPath('//uploads/report.pdf')).toBe('/uploads/report.pdf')
  })
})
