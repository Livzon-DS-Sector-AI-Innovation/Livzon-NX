import { describe, expect, it } from 'vitest'

import { getEquipmentRecoveryNeeds } from './EquipmentPage.logic'

describe('getEquipmentRecoveryNeeds', () => {
  it('requests only resources missing from the server-rendered state', () => {
    expect(getEquipmentRecoveryNeeds(0, 1, 0)).toEqual({
      categories: true,
      locations: false,
      departments: true,
    })
  })

  it('does not refetch complete initial data', () => {
    expect(
      getEquipmentRecoveryNeeds(1, 1, 1),
    ).toEqual({
      categories: false,
      locations: false,
      departments: false,
    })
  })
})
