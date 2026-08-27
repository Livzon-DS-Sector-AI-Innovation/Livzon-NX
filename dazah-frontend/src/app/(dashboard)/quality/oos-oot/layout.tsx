import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'

export default function OosOotLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <QualityQueryProvider>{children}</QualityQueryProvider>
}
