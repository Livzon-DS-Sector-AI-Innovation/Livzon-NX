import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import {
  Clock,
  CheckCircle2,
  XCircle,
  ShieldCheck,
  FileText,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { UserDisplay } from '@/components/business-ui/user-display';
import {
  getAuditStats,
  getPendingRecords,
  auditRecord,
  batchAuditRecords,
} from '@client/src/api';
import type { AuditStats, AuditRecordItem } from '@shared/api.interface';

const PAGE_SIZE = 20;

const INPUT_TYPE_LABELS: Record<string, string> = {
  manual: '手动录入',
  ocr: 'OCR识别',
};

const AuditManagementPage: React.FC = () => {
  const [stats, setStats] = useState<AuditStats>({
    pendingCount: 0,
    todayApprovedCount: 0,
    rejectedCount: 0,
  });
  const [records, setRecords] = useState<AuditRecordItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [rejectDialogOpen, setRejectDialogOpen] = useState<boolean>(false);
  const [rejectReason, setRejectReason] = useState<string>('');
  const [rejectTarget, setRejectTarget] = useState<
    | { type: 'single'; id: string }
    | { type: 'batch'; ids: string[] }
    | null
  >(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [approvedIds, setApprovedIds] = useState<Set<string>>(new Set());

  const fetchStats = useCallback(async () => {
    try {
      const data = await getAuditStats();
      setStats(data);
    } catch {
      toast.error('获取审核统计失败');
    }
  }, []);

  const fetchRecords = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const data = await getPendingRecords(p, PAGE_SIZE);
      setRecords(data.items);
      setTotal(data.total);
    } catch {
      toast.error('获取待审核记录失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    fetchRecords(page);
  }, [page, fetchStats, fetchRecords]);

  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      const allIds = new Set(records.map((r: AuditRecordItem) => r.id));
      setSelectedIds(allIds);
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    const next = new Set(selectedIds);
    if (checked) {
      next.add(id);
    } else {
      next.delete(id);
    }
    setSelectedIds(next);
  };

  const handleApprove = async (id: string) => {
    setActionLoading(true);
    try {
      await auditRecord(id, 'approved');
      setApprovedIds((prev) => new Set(prev).add(id));
      toast.success('审核通过');
      setTimeout(() => {
        setRecords((prev) => prev.filter((r: AuditRecordItem) => r.id !== id));
        setTotal((prev) => prev - 1);
        setStats((prev) => ({
          ...prev,
          pendingCount: Math.max(0, prev.pendingCount - 1),
          todayApprovedCount: prev.todayApprovedCount + 1,
        }));
      }, 600);
    } catch {
      toast.error('审核操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  const openRejectDialog = (
    target: { type: 'single'; id: string } | { type: 'batch'; ids: string[] },
  ) => {
    setRejectTarget(target);
    setRejectReason('');
    setRejectDialogOpen(true);
  };

  const handleRejectConfirm = async () => {
    if (!rejectReason.trim()) {
      toast.error('请填写驳回原因');
      return;
    }
    setActionLoading(true);
    try {
      if (rejectTarget?.type === 'single') {
        await auditRecord(rejectTarget.id, 'rejected', rejectReason.trim());
        toast.success('已驳回');
        setRecords((prev) =>
          prev.filter((r: AuditRecordItem) => r.id !== rejectTarget.id),
        );
        setTotal((prev) => prev - 1);
        setStats((prev) => ({
          ...prev,
          pendingCount: Math.max(0, prev.pendingCount - 1),
          rejectedCount: prev.rejectedCount + 1,
        }));
      } else if (rejectTarget?.type === 'batch') {
        const result = await batchAuditRecords(
          rejectTarget.ids,
          'rejected',
          rejectReason.trim(),
        );
        toast.success(`已驳回 ${result.successCount} 条记录`);
        const rejectedSet = new Set(rejectTarget.ids);
        setRecords((prev) =>
          prev.filter((r: AuditRecordItem) => !rejectedSet.has(r.id)),
        );
        setTotal((prev) => prev - result.successCount);
        setStats((prev) => ({
          ...prev,
          pendingCount: Math.max(0, prev.pendingCount - result.successCount),
          rejectedCount: prev.rejectedCount + result.successCount,
        }));
        setSelectedIds(new Set());
      }
      setRejectDialogOpen(false);
    } catch {
      toast.error('驳回操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleBatchApprove = async () => {
    if (selectedIds.size === 0) {
      toast.error('请先选择要审核的记录');
      return;
    }
    setActionLoading(true);
    try {
      const ids = Array.from(selectedIds);
      const result = await batchAuditRecords(ids, 'approved');
      toast.success(`已通过 ${result.successCount} 条记录`);
      ids.forEach((id: string) => {
        setApprovedIds((prev) => new Set(prev).add(id));
      });
      setTimeout(() => {
        const approvedSet = new Set(ids);
        setRecords((prev) =>
          prev.filter((r: AuditRecordItem) => !approvedSet.has(r.id)),
        );
        setTotal((prev) => prev - result.successCount);
        setStats((prev) => ({
          ...prev,
          pendingCount: Math.max(0, prev.pendingCount - result.successCount),
          todayApprovedCount: prev.todayApprovedCount + result.successCount,
        }));
        setSelectedIds(new Set());
      }, 600);
    } catch {
      toast.error('批量审核操作失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleBatchReject = () => {
    if (selectedIds.size === 0) {
      toast.error('请先选择要驳回的记录');
      return;
    }
    openRejectDialog({ type: 'batch', ids: Array.from(selectedIds) });
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const allSelected =
    records.length > 0 && records.every((r: AuditRecordItem) => selectedIds.has(r.id));

  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center gap-3">
        <ShieldCheck className="size-6 text-primary" />
        <h1 className="text-xl font-bold text-foreground">审核管理</h1>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="border-l-4 border-l-[hsl(32_85%_50%)]">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-[hsl(32_80%_95%)]">
              <Clock className="size-6 text-[hsl(32_85%_50%)]" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">待审核</p>
              <p className="text-2xl font-semibold tabular-nums text-[hsl(32_85%_50%)]">
                {stats.pendingCount}
              </p>
              <p className="text-xs text-muted-foreground">条记录待处理</p>
            </div>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-[hsl(152_60%_42%)]">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-[hsl(152_55%_95%)]">
              <CheckCircle2 className="size-6 text-[hsl(152_60%_42%)]" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">今日已审核</p>
              <p className="text-2xl font-semibold tabular-nums text-[hsl(152_60%_42%)]">
                {stats.todayApprovedCount}
              </p>
              <p className="text-xs text-muted-foreground">条记录已通过</p>
            </div>
          </CardContent>
        </Card>

        <Card className="border-l-4 border-l-[hsl(4_75%_52%)]">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-[hsl(4_70%_96%)]">
              <XCircle className="size-6 text-[hsl(4_75%_52%)]" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">已驳回</p>
              <p className="text-2xl font-semibold tabular-nums text-[hsl(4_75%_52%)]">
                {stats.rejectedCount}
              </p>
              <p className="text-xs text-muted-foreground">条记录被退回</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 待审核列表 */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <FileText className="size-4 text-muted-foreground" />
              <h2 className="text-base font-semibold text-foreground">
                待审核记录
              </h2>
              <Badge variant="secondary">{total} 条</Badge>
            </div>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
            </div>
          ) : records.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
              <CheckCircle2 className="size-12 mb-3 opacity-40" />
              <p className="text-sm">暂无待审核记录</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">
                      <Checkbox
                        checked={allSelected}
                        onCheckedChange={(checked) =>
                          handleSelectAll(checked === true)
                        }
                      />
                    </TableHead>
                    <TableHead>位点编号</TableHead>
                    <TableHead>区域</TableHead>
                    <TableHead>压差值(Pa)</TableHead>
                    <TableHead>标准压差(Pa)</TableHead>
                    <TableHead>记录时间</TableHead>
                    <TableHead>录入方式</TableHead>
                    <TableHead>提交人</TableHead>
                    <TableHead className="text-right">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {records.map((record: AuditRecordItem) => {
                    const isApproved = approvedIds.has(record.id);
                    return (
                      <TableRow
                        key={record.id}
                        className={
                          isApproved
                            ? 'bg-[hsl(152_55%_95%)] transition-opacity duration-500 opacity-0'
                            : ''
                        }
                      >
                        <TableCell>
                          <Checkbox
                            checked={selectedIds.has(record.id)}
                            onCheckedChange={(checked) =>
                              handleSelectOne(record.id, checked === true)
                            }
                          />
                        </TableCell>
                        <TableCell className="font-medium">
                          {record.pointId}
                        </TableCell>
                        <TableCell>{record.area}</TableCell>
                        <TableCell className="tabular-nums">
                          {record.pressureValue}
                        </TableCell>
                        <TableCell className="tabular-nums">
                          {record.standardPressure}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {new Date(record.recordTime).toLocaleString('zh-CN', {
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {INPUT_TYPE_LABELS[record.inputType] ?? record.inputType}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <UserDisplay value={[record.creator]} size="small" />
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex items-center justify-end gap-3">
                            <Button
                              size="sm"
                              variant="default"
                              disabled={actionLoading}
                              onClick={() => handleApprove(record.id)}
                              className="bg-[hsl(152_60%_42%)] border-[hsl(152_60%_38%)] hover:bg-[hsl(152_60%_38%)] text-white"
                            >
                              通过
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              disabled={actionLoading}
                              onClick={() =>
                                openRejectDialog({
                                  type: 'single',
                                  id: record.id,
                                })
                              }
                              className="text-[hsl(4_75%_52%)] hover:text-[hsl(4_75%_45%)]"
                            >
                              驳回
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

          {/* 分页 */}
          {total > PAGE_SIZE && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t">
              <p className="text-sm text-muted-foreground">
                共 {total} 条，第 {page}/{totalPages} 页
              </p>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="size-4" />
                  上一页
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  下一页
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 批量操作栏 */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-40 bg-card border-t shadow-lg">
          <div className="max-w-[1400px] mx-auto px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Checkbox
                checked={true}
                onCheckedChange={() => setSelectedIds(new Set())}
              />
              <span className="text-sm text-foreground">
                已选择{' '}
                <span className="font-semibold text-primary">
                  {selectedIds.size}
                </span>{' '}
                条记录
              </span>
            </div>
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                disabled={actionLoading}
                onClick={handleBatchReject}
                className="text-[hsl(4_75%_52%)] border-[hsl(4_75%_52%)] hover:bg-[hsl(4_70%_96%)]"
              >
                批量驳回
              </Button>
              <Button
                size="sm"
                disabled={actionLoading}
                onClick={handleBatchApprove}
                className="bg-[hsl(152_60%_42%)] border-[hsl(152_60%_38%)] hover:bg-[hsl(152_60%_38%)] text-white"
              >
                批量通过
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* 驳回原因弹窗 */}
      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>驳回原因</DialogTitle>
            <DialogDescription>
              请填写驳回原因，提交后将通知录入人修改
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Textarea
              placeholder="请输入驳回原因，例如：压差值异常，请核实后重新录入..."
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              className="min-h-[120px]"
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRejectDialogOpen(false)}
              disabled={actionLoading}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleRejectConfirm}
              disabled={actionLoading || !rejectReason.trim()}
            >
              确认驳回
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AuditManagementPage;
