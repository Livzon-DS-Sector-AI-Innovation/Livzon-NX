import { beforeEach, describe, expect, it } from 'vitest'

import { useProductContextStore } from './product-context'

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
})
