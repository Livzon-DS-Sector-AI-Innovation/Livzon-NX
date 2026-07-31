export function getEquipmentRecoveryNeeds(
  categoryCount: number,
  locationCount: number,
  departmentCount: number,
) {
  return {
    categories: categoryCount === 0,
    locations: locationCount === 0,
    departments: departmentCount === 0,
  }
}
