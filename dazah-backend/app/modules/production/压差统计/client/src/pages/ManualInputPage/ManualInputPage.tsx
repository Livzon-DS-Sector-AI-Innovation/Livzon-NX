import React, { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Calendar as CalendarIcon,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { logger } from '@lark-apaas/client-toolkit/logger';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { submitBatchManual } from '@client/src/api/index';
import { AREA_OPTIONS } from '@shared/api.interface';
import type { AreaType } from '@shared/api.interface';

const DEFAULT_TIME_SLOTS = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00'];

interface ManualRow {
  id: string;
  pointId: string;
  slotValues: Record<string, number | null>;
}

let rowCounter = 0;
const createEmptyRow = (): ManualRow => ({
  id: `row-${++rowCounter}`,
  pointId: '',
  slotValues: {},
});

interface TimeSlotHeaderProps {
  label: string;
  index: number;
  onEdit: (index: number, newLabel: string) => void;
}

const TimeSlotHeader: React.FC<TimeSlotHeaderProps> = ({ label, index, onEdit }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);

  const handleSave = () => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== label) {
      onEdit(index, trimmed);
    } else {
      setDraft(label);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <Input
        autoFocus
        value={draft}
        className="h-7 w-16 px-1 text-center text-xs"
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDraft(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e: React.KeyboardEvent) => {
          if (e.key === 'Enter') handleSave();
          if (e.key === 'Escape') { setDraft(label); setEditing(false); }
        }}
      />
    );
  }

  return (
    <button
      type="button"
      className="flex items-center gap-1 text-xs font-medium text-foreground hover:text-primary transition-colors cursor-pointer"
      onClick={() => { setDraft(label); setEditing(true); }}
    >
      <span>{label}</span>
      <Pencil className="size-3 text-muted-foreground" />
    </button>
  );
};

const ManualInputPage: React.FC = () => {
  const navigate = useNavigate();
  const [selectedArea, setSelectedArea] = useState<AreaType | ''>('');
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const [timeSlots, setTimeSlots] = useState<string[]>([...DEFAULT_TIME_SLOTS]);
  const [rows, setRows] = useState<ManualRow[]>([createEmptyRow()]);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [successCount, setSuccessCount] = useState(0);

  const handleAreaChange = useCallback((area: string) => {
    setSelectedArea(area as AreaType);
    setRows([createEmptyRow()]);
  }, []);

  const handleAddRow = useCallback(() => {
    setRows((prev) => [...prev, createEmptyRow()]);
  }, []);

  const handleRemoveRow = useCallback((rowId: string) => {
    setRows((prev) => prev.length <= 1 ? prev : prev.filter((r) => r.id !== rowId));
  }, []);

  const handlePointIdChange = useCallback((rowId: string, value: string) => {
    setRows((prev) =>
      prev.map((r) => (r.id === rowId ? { ...r, pointId: value } : r)),
    );
  }, []);

  const handleSlotValueChange = useCallback(
    (rowId: string, slot: string, raw: string) => {
      const val = raw === '' ? null : Number(raw);
      setRows((prev) =>
        prev.map((r) =>
          r.id === rowId
            ? { ...r, slotValues: { ...r.slotValues, [slot]: val } }
            : r,
        ),
      );
    },
    [],
  );

  const handleTimeSlotEdit = useCallback(
    (index: number, newLabel: string) => {
      setTimeSlots((prev) => {
        const oldLabel = prev[index];
        const next = [...prev];
        next[index] = newLabel;

        setRows((prevRows) =>
          prevRows.map((row) => {
            const oldVal = row.slotValues[oldLabel];
            if (oldVal === undefined) return row;
            const newSlotValues: Record<string, number | null> = {};
            for (const [k, v] of Object.entries(row.slotValues)) {
              if (k === oldLabel) {
                newSlotValues[newLabel] = v;
              } else {
                newSlotValues[k] = v;
              }
            }
            return { ...row, slotValues: newSlotValues };
          }),
        );

        return next;
      });
    },
    [],
  );

  const filledCount = useMemo(
    () =>
      rows.reduce(
        (acc, row) =>
          acc +
          Object.values(row.slotValues).filter(
            (v: number | null) => v !== null && v !== undefined,
          ).length,
        0,
      ),
    [rows],
  );

  const handleSubmit = async () => {
    if (!selectedArea) {
      toast.error('请选择区域');
      return;
    }
    const validRows = rows.filter((r) => r.pointId.trim());
    if (validRows.length === 0) {
      toast.error('请至少填写一个位点编号');
      return;
    }
    if (filledCount === 0) {
      toast.error('请至少填写一个压差值');
      return;
    }

    const values: Record<string, number | null> = {};
    for (const row of validRows) {
      for (const slot of timeSlots) {
        const val = row.slotValues[slot];
        if (val != null) {
          values[`${row.pointId.trim()}::${slot}`] = val;
        }
      }
    }

    setSubmitting(true);
    try {
      const dateStr = dayjs(selectedDate).format('YYYY-MM-DD');
      const res = await submitBatchManual({
        area: selectedArea,
        timeSlots,
        rows: [{ date: dateStr, values }],
      });
      setSuccessCount(res.successCount);
      setSubmitted(true);
      setTimeout(() => navigate('/'), 1500);
    } catch (err: unknown) {
      logger.error('批量提交失败', err);
      toast.error('提交失败，请重试');
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background">
        <div className="animate-in fade-in flex flex-col items-center gap-4 duration-500">
          <CheckCircle2 className="h-16 w-16 text-green-500" />
          <p className="text-lg font-medium text-foreground">
            提交成功，共 {successCount} 条记录
          </p>
        </div>
      </div>
    );
  }

  const dateStr = dayjs(selectedDate).format('YYYY-MM-DD');

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="flex items-center border-b border-border bg-card px-4 py-3">
        <Button
          variant="ghost"
          size="icon"
          className="h-10 w-10 shrink-0"
          onClick={() => navigate('/')}
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <h1 className="ml-2 text-lg font-bold text-foreground">手动填写</h1>
      </div>

      <div className="flex-1 px-4 py-4 space-y-4">
        <Card className="rounded-lg shadow-sm">
          <CardContent className="p-4 space-y-3">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">选择区域</label>
              <Select value={selectedArea} onValueChange={handleAreaChange}>
                <SelectTrigger className="h-12">
                  <SelectValue placeholder="请选择区域" />
                </SelectTrigger>
                <SelectContent>
                  {AREA_OPTIONS.map((area: string) => (
                    <SelectItem key={area} value={area}>
                      {area}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {selectedArea && (
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">选择日期</label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="h-12 w-full justify-start px-3 text-left">
                      <CalendarIcon className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="text-sm font-normal">{dateStr}</span>
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={selectedDate}
                      onSelect={(d: Date | undefined) => { if (d) setSelectedDate(d); }}
                    />
                  </PopoverContent>
                </Popover>
              </div>
            )}
          </CardContent>
        </Card>

        {!selectedArea && (
          <Card className="rounded-lg shadow-sm">
            <CardContent className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <p className="text-sm">请先选择区域</p>
            </CardContent>
          </Card>
        )}

        {selectedArea && (
          <Card className="rounded-lg shadow-sm">
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-border bg-accent/50">
                      <th className="sticky left-0 z-20 bg-accent/80 px-3 py-3 text-left font-medium text-foreground backdrop-blur-sm min-w-[140px]">
                        <div className="text-xs">位点编号</div>
                      </th>
                      {timeSlots.map((slot: string, idx: number) => (
                        <th
                          key={`${slot}-${idx}`}
                          className="px-1 py-3 text-center font-medium text-foreground min-w-[72px]"
                        >
                          <TimeSlotHeader
                            label={slot}
                            index={idx}
                            onEdit={handleTimeSlotEdit}
                          />
                        </th>
                      ))}
                      <th className="w-10 px-1 py-3" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row: ManualRow, rowIdx: number) => (
                      <tr
                        key={row.id}
                        className={
                          rowIdx % 2 === 1 ? 'border-b border-border/50 bg-muted/30' : 'border-b border-border/50'
                        }
                      >
                        <td className="sticky left-0 z-10 bg-card px-2 py-1.5 backdrop-blur-sm">
                          <Input
                            placeholder="输入位点编号"
                            className="h-10 w-full min-w-[120px] px-2 text-sm"
                            value={row.pointId}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                              handlePointIdChange(row.id, e.target.value)
                            }
                          />
                        </td>
                        {timeSlots.map((slot: string, slotIdx: number) => (
                          <td key={`${row.id}-${slot}-${slotIdx}`} className="px-1 py-1.5">
                            <Input
                              type="number"
                              inputMode="numeric"
                              placeholder="--"
                              className="h-10 w-full min-w-[64px] px-2 text-center text-sm [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                              value={row.slotValues[slot] ?? ''}
                              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                                handleSlotValueChange(row.id, slot, e.target.value)
                              }
                            />
                          </td>
                        ))}
                        <td className="px-1 py-1.5 text-center">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-muted-foreground hover:text-[hsl(4_75%_52%)]"
                            disabled={rows.length <= 1}
                            onClick={() => handleRemoveRow(row.id)}
                          >
                            <Trash2 className="size-3.5" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between border-t border-border px-4 py-3">
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5"
                  onClick={handleAddRow}
                >
                  <Plus className="size-3.5" />
                  新增行
                </Button>
                <span className="text-xs text-muted-foreground">
                  已填写 {filledCount} 项
                </span>
              </div>
            </CardContent>
          </Card>
        )}

        {selectedArea && (
          <Button
            disabled={submitting}
            className="h-12 w-full bg-primary text-lg text-primary-foreground hover:bg-primary/90"
            onClick={handleSubmit}
          >
            {submitting ? (
              <>
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                提交中...
              </>
            ) : (
              '提交记录'
            )}
          </Button>
        )}
      </div>
    </div>
  );
};

export default ManualInputPage;
