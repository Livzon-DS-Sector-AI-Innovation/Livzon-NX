import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import dayjs from 'dayjs';
import * as XLSX from 'xlsx-js-style';
import {
  FileDown, Filter, ChevronLeft, ChevronRight, Trash2, Pencil, CalendarIcon,
} from 'lucide-react';
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader,
  AlertDialogTitle, AlertDialogDescription,
  AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from '@/components/ui/alert-dialog';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { logger } from '@lark-apaas/client-toolkit/logger';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';
import {
  getMergedPressureRecords, getExportByArea,
  deleteMergedPressureRow, batchDeleteMergedPressureRows,
  updateMergedPressureRow,
} from '@client/src/api';
import type { MergedPressureRow, PressureRecordQuery } from '@shared/api.interface';
import { AREA_OPTIONS } from '@shared/api.interface';
import OcrTasksSection from './OcrTasksSection';

const PAGE_SIZE = 20;
const DEFAULT_TIME_SLOTS = ['08:00', '10:00', '12:00', '14:00', '16:00', '18:00'];

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  pending: {
    label: '待审核',
    className: 'bg-[hsl(32_80%_95%)] text-[hsl(32_85%_40%)] border-[hsl(32_60%_80%)]',
  },
  approved: {
    label: '已通过',
    className: 'bg-[hsl(152_55%_95%)] text-[hsl(152_60%_32%)] border-[hsl(152_45%_78%)]',
  },
  rejected: {
    label: '已驳回',
    className: 'bg-[hsl(4_70%_96%)] text-[hsl(4_75%_42%)] border-[hsl(4_55%_80%)]',
  },
};

type RowKey = string;
type DeleteTarget = { type: 'single'; key: RowKey; pointId: string; date: string }
  | { type: 'batch'; keys: RowKey[] };

const getRowKey = (row: MergedPressureRow): RowKey => `${row.pointId}|${row.date}`;

const RecordsPage: React.FC = () => {
  const [filterArea, setFilterArea] = useState<string>('all');
  const [filterStartDate, setFilterStartDate] = useState<Date | undefined>();
  const [filterEndDate, setFilterEndDate] = useState<Date | undefined>();
  const [filterPointId, setFilterPointId] = useState<string>('');
  const [filterInputType, setFilterInputType] = useState<string>('all');
  const [filtersOpen, setFiltersOpen] = useState<boolean>(true);
  const [rows, setRows] = useState<MergedPressureRow[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedKeys, setSelectedKeys] = useState<Set<RowKey>>(new Set());
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState<boolean>(false);
  const [timeSlots, setTimeSlots] = useState<string[]>(DEFAULT_TIME_SLOTS);
  const [editDialogOpen, setEditDialogOpen] = useState<boolean>(false);
  const [editRow, setEditRow] = useState<MergedPressureRow | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});

  const buildParams = useCallback(
    (p: number): PressureRecordQuery => {
      const params: PressureRecordQuery = { page: p, pageSize: PAGE_SIZE };
      if (filterArea !== 'all') params.area = filterArea as PressureRecordQuery['area'];
      if (filterStartDate) params.startDate = dayjs(filterStartDate).format('YYYY-MM-DD');
      if (filterEndDate) params.endDate = dayjs(filterEndDate).format('YYYY-MM-DD');
      if (filterPointId.trim()) params.pointId = filterPointId.trim();
      if (filterInputType !== 'all') params.inputType = filterInputType as PressureRecordQuery['inputType'];
      return params;
    },
    [filterArea, filterStartDate, filterEndDate, filterPointId, filterInputType],
  );

  const fetchRows = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const data = await getMergedPressureRecords(buildParams(p));
      setRows(data.items);
      setTotal(data.total);
      const allSlots = new Set<string>(DEFAULT_TIME_SLOTS);
      for (const item of data.items) {
        for (const slot of Object.keys(item.timeSlotValues)) {
          allSlots.add(slot);
        }
      }
      const sorted = Array.from(allSlots).sort();
      setTimeSlots(sorted);
    } catch {
      toast.error('获取压差记录失败');
    } finally {
      setLoading(false);
    }
  }, [buildParams]);

  useEffect(() => { fetchRows(page); }, [page, fetchRows]);

  const handleSearch = () => { setPage(1); fetchRows(1); };
  const handleReset = () => {
    setFilterArea('all');
    setFilterStartDate(undefined);
    setFilterEndDate(undefined);
    setFilterPointId('');
    setFilterInputType('all');
    setPage(1);
  };

  const openDeleteDialog = (target: DeleteTarget) => {
    setDeleteTarget(target);
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    setActionLoading(true);
    try {
      if (deleteTarget && deleteTarget.type === 'single') {
        await deleteMergedPressureRow({ pointId: deleteTarget.pointId, date: deleteTarget.date });
        toast.success('已删除');
      } else if (deleteTarget && deleteTarget.type === 'batch') {
        const rowsToDelete = rows
          .filter((r: MergedPressureRow) => deleteTarget.keys.includes(getRowKey(r)))
          .map((r: MergedPressureRow) => ({ pointId: r.pointId, date: r.date }));
        const result = await batchDeleteMergedPressureRows(rowsToDelete);
        toast.success(`已删除 ${result.successCount} 条记录`);
        setSelectedKeys(new Set());
      }
      setDeleteDialogOpen(false);
      fetchRows(page);
    } catch {
      toast.error('删除失败');
    } finally {
      setActionLoading(false);
    }
  };

  const openEditDialog = (row: MergedPressureRow) => {
    setEditRow(row);
    const vals: Record<string, string> = {};
    for (const slot of timeSlots) {
      vals[slot] = row.timeSlotValues[slot] != null ? String(row.timeSlotValues[slot]) : '';
    }
    setEditValues(vals);
    setEditDialogOpen(true);
  };

  const handleEditSlotChange = (slot: string, value: string) => {
    setEditValues((prev) => ({ ...prev, [slot]: value }));
  };

  const handleEditSave = async () => {
    if (!editRow) return;
    setActionLoading(true);
    try {
      const timeSlotValues: Record<string, number | null> = {};
      for (const [slot, val] of Object.entries(editValues)) {
        if (val.trim() === '') {
          timeSlotValues[slot] = editRow.timeSlotValues[slot] ?? null;
        } else {
          timeSlotValues[slot] = parseInt(val, 10);
        }
      }
      await updateMergedPressureRow({
        pointId: editRow.pointId,
        date: editRow.date,
        timeSlotValues,
      });
      toast.success('修改成功');
      setEditDialogOpen(false);
      fetchRows(page);
    } catch {
      toast.error('修改失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedKeys(new Set(rows.map((r: MergedPressureRow) => getRowKey(r))));
    } else {
      setSelectedKeys(new Set());
    }
  };

  const handleSelectOne = (key: RowKey, checked: boolean) => {
    const next = new Set(selectedKeys);
    if (checked) next.add(key); else next.delete(key);
    setSelectedKeys(next);
  };

  const BORDER_STYLE = {
    top: { style: 'thin' as const, color: { rgb: '999999' } },
    bottom: { style: 'thin' as const, color: { rgb: '999999' } },
    left: { style: 'thin' as const, color: { rgb: '999999' } },
    right: { style: 'thin' as const, color: { rgb: '999999' } },
  };
  const HEADER_FILL = { fgColor: { rgb: 'E8F0FE' } };
  const HEADER_FONT = { bold: true, sz: 11 };

  const handleExportExcel = async () => {
    try {
      toast.info('正在导出...');
      const params = buildParams(1);
      delete params.page;
      delete params.pageSize;
      const areaDataList = await getExportByArea(params);
      if (areaDataList.length === 0) { toast.error('暂无可导出的数据'); return; }
      const wb = XLSX.utils.book_new();
      let sheetCount = 0;
      areaDataList.forEach((areaData) => {
        if (areaData.rows.length === 0) return;
        const header = ['位点编号', '区域', ...areaData.timeSlots, '日期'];
        const dataRows = areaData.rows.map((row) => [
          row.pointId,
          areaData.area,
          ...areaData.timeSlots.map((slot: string) => row.values[slot] ?? ''),
          row.date,
        ]);
        const aoa = [header, ...dataRows];
        const ws = XLSX.utils.aoa_to_sheet(aoa);
        const colWidths = header.map((h: string, colIdx: number) => {
          let maxLen = h.length * 2;
          for (const row of dataRows) {
            const cellLen = String(row[colIdx] ?? '').length * 2;
            if (cellLen > maxLen) maxLen = cellLen;
          }
          return { wch: Math.max(maxLen + 2, 10) };
        });
        ws['!cols'] = colWidths;
        const range = XLSX.utils.decode_range(ws['!ref'] ?? 'A1');
        for (let R = range.s.r; R <= range.e.r; R++) {
          for (let C = range.s.c; C <= range.e.c; C++) {
            const addr = XLSX.utils.encode_cell({ r: R, c: C });
            if (!ws[addr]) ws[addr] = { v: '' };
            ws[addr].s = R === 0
              ? { border: BORDER_STYLE, fill: HEADER_FILL, font: HEADER_FONT, alignment: { horizontal: 'center', vertical: 'center' } }
              : { border: BORDER_STYLE, alignment: { horizontal: 'center', vertical: 'center' } };
          }
        }
        XLSX.utils.book_append_sheet(wb, ws, areaData.area);
        sheetCount++;
      });
      if (sheetCount === 0) { toast.error('暂无可导出的数据'); return; }
      XLSX.writeFile(wb, `压差巡检记录_${dayjs().format('YYYY-MM-DD')}.xlsx`);
      toast.success(`已导出 ${sheetCount} 个区域的Sheet`);
    } catch {
      toast.error('导出失败');
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const allSelected = rows.length > 0 && rows.every((r: MergedPressureRow) => selectedKeys.has(getRowKey(r)));
  const formatDateDisplay = (d: Date | undefined): string => d ? dayjs(d).format('YYYY-MM-DD') : '选择日期';

  return (
    <div className="max-w-[1400px] mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-foreground">数据记录</h1>
        <Button variant="outline" size="sm" onClick={handleExportExcel} disabled={total === 0}>
            <FileDown className="size-4" />导出Excel
          </Button>
      </div>

      <OcrTasksSection />

      <Card>
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3 md:hidden">
            <span className="text-sm font-medium text-foreground flex items-center gap-1.5">
              <Filter className="size-4" />筛选条件
            </span>
            <Button variant="ghost" size="sm" onClick={() => setFiltersOpen(!filtersOpen)}>
              {filtersOpen ? '收起' : '展开'}
            </Button>
          </div>
          <div className={cn('flex flex-col gap-3 md:flex-row md:flex-wrap md:items-end', !filtersOpen && 'hidden md:flex')}>
            <div className="flex flex-col gap-1.5 min-w-[140px]">
              <label className="text-xs text-muted-foreground">区域</label>
              <Select value={filterArea} onValueChange={setFilterArea}>
                <SelectTrigger className="w-full"><SelectValue placeholder="全部区域" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部区域</SelectItem>
                  {AREA_OPTIONS.map((a: string) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5 min-w-[150px]">
              <label className="text-xs text-muted-foreground">开始日期</label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="w-full justify-start text-left font-normal">
                    <CalendarIcon className="size-4 mr-1.5 opacity-50" />{formatDateDisplay(filterStartDate)}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar mode="single" selected={filterStartDate} onSelect={setFilterStartDate} autoFocus />
                </PopoverContent>
              </Popover>
            </div>
            <div className="flex flex-col gap-1.5 min-w-[150px]">
              <label className="text-xs text-muted-foreground">结束日期</label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="w-full justify-start text-left font-normal">
                    <CalendarIcon className="size-4 mr-1.5 opacity-50" />{formatDateDisplay(filterEndDate)}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar mode="single" selected={filterEndDate} onSelect={setFilterEndDate} autoFocus />
                </PopoverContent>
              </Popover>
            </div>
            <div className="flex flex-col gap-1.5 min-w-[140px]">
              <label className="text-xs text-muted-foreground">位点编号</label>
              <Input placeholder="搜索位点编号" value={filterPointId} onChange={(e) => setFilterPointId(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }} />
            </div>
            <div className="flex flex-col gap-1.5 min-w-[130px]">
              <label className="text-xs text-muted-foreground">录入方式</label>
              <Select value={filterInputType} onValueChange={setFilterInputType}>
                <SelectTrigger className="w-full"><SelectValue placeholder="全部" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="manual">手动填写</SelectItem>
                  <SelectItem value="ocr">图片OCR</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-2">
              <Button size="default" onClick={handleSearch}>查询</Button>
              <Button variant="ghost" size="default" onClick={handleReset}>重置</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : rows.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <Filter className="size-12 mb-3 opacity-40" />
              <p className="text-sm">暂无数据记录</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12 sticky left-0 bg-card z-10">
                        <Checkbox checked={allSelected} onCheckedChange={(c) => handleSelectAll(c === true)} />
                      </TableHead>
                    <TableHead className="min-w-[100px] sticky left-12 bg-card z-10">位点编号</TableHead>
                    <TableHead className="min-w-[80px]">区域</TableHead>
                    {timeSlots.map((slot: string) => (
                      <TableHead key={slot} className="text-right w-[50px] px-1">{slot}</TableHead>
                    ))}
                    <TableHead className="min-w-[100px]">日期</TableHead>
                    <TableHead className="min-w-[80px]">状态</TableHead>
                    <TableHead className="text-right w-[100px] sticky right-0 bg-card z-10">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row: MergedPressureRow) => {
                    const st = STATUS_BADGE[row.status] ?? STATUS_BADGE.pending;
                    const key = getRowKey(row);
                    return (
                      <TableRow key={key}>
                          <TableCell className="sticky left-0 bg-card z-10">
                            <Checkbox checked={selectedKeys.has(key)} onCheckedChange={(c) => handleSelectOne(key, c === true)} />
                          </TableCell>
                        <TableCell className="font-medium sticky left-12 bg-card z-10">{row.pointId}</TableCell>
                        <TableCell>{row.area}</TableCell>
                        {timeSlots.map((slot: string) => (
                          <TableCell key={slot} className="text-right tabular-nums font-semibold px-1">
                            {row.timeSlotValues[slot] != null ? row.timeSlotValues[slot] : '-'}
                          </TableCell>
                        ))}
                        <TableCell className="text-muted-foreground">{row.date}</TableCell>
                        <TableCell><Badge variant="outline" className={st.className}>{st.label}</Badge></TableCell>
                          <TableCell className="text-right sticky right-0 bg-card z-10">
                            <div className="flex items-center justify-end gap-0.5">
                              <Button
                                size="sm" variant="ghost" disabled={actionLoading}
                                onClick={() => openEditDialog(row)}
                                className="text-muted-foreground hover:text-primary hover:bg-accent h-8 w-8 p-0"
                              >
                                <Pencil className="size-3.5" />
                              </Button>
                              <Button
                                size="sm" variant="ghost" disabled={actionLoading}
                                onClick={() => openDeleteDialog({ type: 'single', key, pointId: row.pointId, date: row.date })}
                                className="text-muted-foreground hover:text-[hsl(4_75%_52%)] hover:bg-[hsl(4_70%_96%)] h-8 w-8 p-0"
                              >
                                <Trash2 className="size-3.5" />
                              </Button>
                            </div>
                          </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
          {total > 0 && (
            <div className="flex items-center justify-between px-4 py-3 border-t">
              <p className="text-sm text-muted-foreground">共 {total} 条，第 {page}/{totalPages} 页</p>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p: number) => p - 1)}>
                  <ChevronLeft className="size-4" />上一页
                </Button>
                <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p: number) => p + 1)}>
                  下一页<ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {selectedKeys.size > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-40 bg-card border-t shadow-lg">
          <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Checkbox checked={true} onCheckedChange={() => setSelectedKeys(new Set())} />
              <span className="text-sm text-foreground">
                已选择 <span className="font-semibold text-primary">{selectedKeys.size}</span> 条记录
              </span>
            </div>
            <Button
              variant="outline" size="sm" disabled={actionLoading}
              onClick={() => openDeleteDialog({ type: 'batch', keys: Array.from(selectedKeys) })}
              className="text-[hsl(4_75%_52%)] border-[hsl(4_75%_52%)] hover:bg-[hsl(4_70%_96%)]"
            >
              <Trash2 className="size-3.5 mr-1" />批量删除
            </Button>
          </div>
        </div>
      )}

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget?.type === 'single'
                ? `确认删除位点 ${deleteTarget.pointId} 在 ${deleteTarget.date} 的所有压差记录吗？`
                : deleteTarget?.type === 'batch'
                  ? `确认删除已选中的 ${deleteTarget.keys.length} 组记录吗？`
                  : ''}
              删除后数据不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={actionLoading}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={actionLoading}
              className="bg-[hsl(4_75%_52%)] hover:bg-[hsl(4_75%_42%)] text-white"
            >
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle>修改压差数据</DialogTitle>
            <DialogDescription>
              位点 {editRow?.pointId} / {editRow?.date} / {editRow?.area}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            {timeSlots.map((slot: string) => (
              <div key={slot} className="flex items-center gap-3">
                <Label className="w-16 shrink-0 text-right text-sm">{slot}</Label>
                <Input
                  type="number"
                  value={editValues[slot] ?? ''}
                  onChange={(e) => handleEditSlotChange(slot, e.target.value)}
                  placeholder={editRow?.timeSlotValues[slot] != null ? String(editRow.timeSlotValues[slot]) : '-'}
                  className="flex-1"
                />
                <span className="text-xs text-muted-foreground w-8">Pa</span>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)} disabled={actionLoading}>取消</Button>
            <Button onClick={handleEditSave} disabled={actionLoading}>保存修改</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default RecordsPage;
