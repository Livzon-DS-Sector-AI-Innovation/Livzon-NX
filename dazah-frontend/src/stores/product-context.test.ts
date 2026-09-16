/* @vitest-environment happy-dom */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { restoreProductContext, useProductContextStore } from './product-context'

describe('product context store', () => {
  beforeEach(() => {
    useProductContextStore.getState().setProductCode('FA')
  })

  it('defaults to the FA product context', () => {
    expect(useProductContextStore.getState().productCode).toBe('FA')
  })

  it('switches the product code shared across pages', () => {
    useProductContextStore.getState().setProductCode('MC')
    expect(useProductContextStore.getState().productCode).toBe('MC')

    useProductContextStore.getState().setProductCode('FA')
    expect(useProductContextStore.getState().productCode).toBe('FA')
  })

  it('persists the selection to local storage on switch', () => {
    useProductContextStore.getState().setProductCode('DR')
    expect(window.localStorage.getItem('dazah.production.product-context')).toBe('DR')
  })

  it('restores the persisted product on mount', () => {
    window.localStorage.setItem('dazah.production.product-context', 'LV')
    restoreProductContext()
    expect(useProductContextStore.getState().productCode).toBe('LV')
  })

  it('ignores unknown persisted codes and keeps the default', () => {
    window.localStorage.setItem('dazah.production.product-context', 'XX')
    restoreProductContext()
    expect(useProductContextStore.getState().productCode).toBe('FA')
  })

  it('accepts the SUMMARY product tab persisted on mount', () => {
    window.localStorage.setItem('dazah.production.product-context', 'SUMMARY')
    restoreProductContext()
    expect(useProductContextStore.getState().productCode).toBe('SUMMARY')
  })

  it('keeps the default when storage is unavailable', () => {
    const getItem = vi
      .spyOn(Storage.prototype, 'getItem')
      .mockImplementation(() => {
        throw new Error('storage blocked')
      })
    restoreProductContext()
    expect(useProductContextStore.getState().productCode).toBe('FA')
    getItem.mockRestore()
  })
})
