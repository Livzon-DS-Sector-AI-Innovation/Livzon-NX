import React from 'react';
import dayjs from 'dayjs';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Image } from '@/components/ui/image';
import { UserDisplay } from '@/components/business-ui/user-display';
import type { PressureRecordItem } from '@shared/api.interface';

const STATUS_CONFIG: Record<
  string,
  { label: string; className: string }
> = {
  pending: {
    label: '待审核',
    className:
      'bg-[hsl(32_80%_95%)] text-[hsl(32_85%_40%)] border-[hsl(32_60%_80%)]',
  },
  approved: {
    label: '已通过',
    className:
      'bg-[hsl(152_55%_95%)] text-[hsl(152_60%_32%)] border-[hsl(152_45%_78%)]',
  },
  rejected: {
    label: '已驳回',
    className:
      'bg-[hsl(4_70%_96%)] text-[hsl(4_75%_42%)] border-[hsl(4_55%_80%)]',
  },
};

const INPUT_TYPE_LABELS: Record<string, string> = {
  manual: '手动填写',
  ocr: '图片OCR',
};

interface RecordDetailSheetProps {
  record: PressureRecordItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 py-2.5 border-b border-border/50 last:border-0">
      <span className="text-xs text-muted-foreground">{label}</span>
      <div className="text-sm text-foreground">{children}</div>
    </div>
  );
}

const RecordDetailSheet: React.FC<RecordDetailSheetProps> = ({
  record,
  open,
  onOpenChange,
}) => {
  if (!record) return null;

  const statusCfg = STATUS_CONFIG[record.status] ?? STATUS_CONFIG.pending;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="sm:max-w-md w-full overflow-y-auto"
      >
        <SheetHeader className="px-0">
          <SheetTitle className="text-lg">记录详情</SheetTitle>
        </SheetHeader>

        <div className="flex flex-col mt-2">
          <DetailRow label="位点编号">
            <span className="font-medium">{record.pointId}</span>
          </DetailRow>

          <DetailRow label="区域">{record.area}</DetailRow>

          <DetailRow label="压差值">
            <span className="tabular-nums font-semibold">
              {record.pressureValue}
            </span>{' '}
            <span className="text-muted-foreground text-xs">Pa</span>
          </DetailRow>

          <DetailRow label="标准压差">
            <span className="tabular-nums">{record.standardPressure}</span>{' '}
            <span className="text-muted-foreground text-xs">Pa</span>
          </DetailRow>

          <DetailRow label="记录时间">
            {dayjs(record.recordTime).format('YYYY-MM-DD HH:mm')}
          </DetailRow>

          <DetailRow label="录入方式">
            <Badge variant="outline">
              {INPUT_TYPE_LABELS[record.inputType] ?? record.inputType}
            </Badge>
          </DetailRow>

          <DetailRow label="审核状态">
            <Badge variant="outline" className={statusCfg.className}>
              {statusCfg.label}
            </Badge>
          </DetailRow>

          <DetailRow label="提交人">
            <UserDisplay value={[record.creator]} size="small" />
          </DetailRow>

          {record.rejectReason && (
            <DetailRow label="驳回原因">
              <span className="text-[hsl(4_75%_42%)]">
                {record.rejectReason}
              </span>
            </DetailRow>
          )}

          {record.imageUrl && (
            <DetailRow label="图片附件">
              <Image
                src={record.imageUrl}
                alt="压差记录图片"
                width={320}
                className="rounded-lg border border-border object-cover max-h-60"
              />
            </DetailRow>
          )}

          {record.remark && (
            <DetailRow label="备注">{record.remark}</DetailRow>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default RecordDetailSheet;
