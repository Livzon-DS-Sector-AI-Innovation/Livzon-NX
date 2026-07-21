import { getFermentations, getSeedCultures } from '@/actions/production'
import { FermentationOperationsClient } from '@/components/production/FermentationOperationsClient'

export default async function FermentationPage() {
  const [fermentations, seedCultures] = await Promise.all([getFermentations(), getSeedCultures()])
  return <FermentationOperationsClient initialFermentations={fermentations.data || []} initialSeedCultures={seedCultures.data || []} />
}
