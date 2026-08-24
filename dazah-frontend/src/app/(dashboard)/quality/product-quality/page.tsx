import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

export default function ProductQualityPage() {
  redirect('/quality/product-quality/mfn')
}
