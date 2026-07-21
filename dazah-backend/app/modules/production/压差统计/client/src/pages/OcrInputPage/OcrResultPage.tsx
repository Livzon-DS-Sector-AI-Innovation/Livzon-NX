import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  Loader2,
  Plus,
  Trash2,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';
import { toast } from 'sonner';
import { logger } from '@lark-apaas/client-toolkit/logger';
import {
  AREA_OPTIONS,
  type AreaType,
  type OcrTaskItem,
  type SubmitOcrTaskResultRequest,
} from '@shared/api.interface';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getOcrTaskDetail, retryOcrTask, submitOcrTaskRecords } from '@/api';

interface EditRow {
  key: string;
  pointId: string;
  pressureValue: string;
  recordTime: string;
  recorder: string;
  timeSlot: string;
  area: string;
  remark: string;
}

const POLL_MS = 3000;
const MAX_POLLS = 100;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function createEmptyRow(): EditRow {
  return {
    key: crypto.randomUUID(),
    pointId: '',
    pressureValue: '',
    recordTime: new Date().toISOString().slice(0, 16).replace('T', ' '),
    recorder: '',
    timeSlot: '',
    area: '',
    remark: '',
  };
}

const PageHeader: React.FC<{ onBack: () => void; right?: React.ReactNode }> = ({ onBack, right }) => (
  <div className="flex items-center gap-3 mb-6">
    <button type="button" onClick={onBack} className="flex items-center justify-center w-9 h-9 rounded-lg hover:bg-accent transition-colors">
      <ArrowLeft className="size-5 text-foreground" />
    </button>
    <h1 className="text-xl font-bold text-foreground">识别结果</h1>
    {right}
  </div>
);

const OcrResultPage: React.FC = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<OcrTaskItem | null>(null);
  const [rows, setRows] = useState<EditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [areaErrors, setAreaErrors] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!taskId || !UUID_RE.test(taskId)) return;
    let active = true;
    let polls = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      try {
        const detail = await getOcrTaskDetail(taskId);
        if (!active) return;
        setTask(detail);
        if (
          (detail.status === 'pending' || detail.status === 'processing') &&
          polls < MAX_POLLS
        ) {
          polls++;
          timer = setTimeout(poll, POLL_MS);
        } else if (detail.status === 'completed' && detail.result?.records) {
          setRows(
            detail.result.records.map((r) => ({
              key: crypto.randomUUID(),
              pointId: r.pointId,
              pressureValue: String(r.pressureValue),
              recordTime: r.recordTime,
              recorder: r.recorder,
              timeSlot: r.timeSlot ?? '',
              area: '',
              remark: '',
            })),
          );
        }
      } catch (error: unknown) {
        if (!active) return;
        logger.error('获取OCR任务详情失败', error);
        toast.error('获取任务信息失败');
      } finally {
        if (active) setLoading(false);
      }
    };

    poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
    };
  }, [taskId]);

  const updateRow = useCallback(
    (key: string, field: keyof EditRow, value: string) => {
      setRows((prev) =>
        prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)),
      );
      if (field === 'area') {
        setAreaErrors((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [],
  );

  const addRow = useCallback(
    () => setRows((prev) => [...prev, createEmptyRow()]),
    [],
  );

  const deleteRow = useCallback(
    (key: string) => setRows((prev) => prev.filter((r) => r.key !== key)),
    [],
  );

  const handleRetry = useCallback(async () => {
    if (!taskId) return;
    setRetrying(true);
    try {
      await retryOcrTask(taskId);
      toast.success('任务已重新提交识别');
      window.location.reload();
    } catch (error: unknown) {
      logger.error('重试OCR任务失败', error);
      toast.error('重试失败，请稍后再试');
      setRetrying(false);
    }
  }, [taskId]);

  const handleSubmit = useCallback(async () => {
    if (!taskId) return;
    const filled = rows.filter((r) => r.pointId || r.pressureValue);
    if (filled.length === 0) {
      toast.error('没有可提交的数据');
      return;
    }
    const missing = new Set<string>();
    for (const r of filled) {
      if (!r.area) missing.add(r.key);
    }
    if (missing.size > 0) {
      setAreaErrors(missing);
      toast.error('请为所有数据行选择区域');
      return;
    }
    setSubmitting(true);
    try {
      const payload: SubmitOcrTaskResultRequest = {
        records: filled.map((r) => ({
          recordTime: r.recordTime,
          pointId: r.pointId,
          pressureValue: Number(r.pressureValue) || 0,
          area: r.area as AreaType,
          timeSlot: r.timeSlot || undefined,
          remark: r.remark || undefined,
        })),
      };
      const res = await submitOcrTaskRecords(taskId, payload);
      if (res.success) {
        toast.success(`成功提交 ${res.successCount} 条记录`);
        navigate('/');
      } else {
        toast.error(
          `提交部分失败：成功 ${res.successCount} 条，失败 ${res.failCount} 条`,
        );
      }
    } catch (error: unknown) {
      logger.error('提交OCR任务记录失败', error);
      toast.error('提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  }, [taskId, rows, navigate]);

  const goHome = useCallback(() => navigate('/'), [navigate]);
  const isProcessing =
    task?.status === 'pending' || task?.status === 'processing';

  return (
    <div className="max-w-[1400px] mx-auto">
      {loading && <PageHeader onBack={goHome} />}
      {loading && (
        <div className="flex flex-col items-center justify-center py-20">
          <Loader2 className="size-10 text-primary animate-spin mb-4" />
          <p className="text-muted-foreground">加载中...</p>
        </div>
      )}
      {!loading && !task && (
        <>
          <PageHeader onBack={goHome} />
          <div className="text-center py-20 text-muted-foreground">任务不存在</div>
        </>
      )}
      {!loading && isProcessing && (
        <>
          <PageHeader onBack={goHome} />
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="size-10 text-primary animate-spin mb-4" />
            <p className="text-base text-foreground mb-1">识别中...</p>
            <p className="text-sm text-muted-foreground">正在后台处理，请稍候</p>
          </div>
        </>
      )}
      {!loading && task?.status === 'failed' && (
        <>
          <PageHeader onBack={goHome} />
          <div className="flex flex-col items-center justify-center py-16">
            <AlertCircle className="size-10 text-destructive mb-4" />
            <p className="text-base text-foreground mb-2">识别失败</p>
            <p className="text-sm text-muted-foreground mb-6 text-center px-4">
              {task.errorMessage || 'OCR识别过程中发生错误'}
            </p>
            <Button onClick={handleRetry} disabled={retrying} className="min-h-12 px-8">
              {retrying && <Loader2 className="size-4 animate-spin mr-2" />}
              重新识别
            </Button>
          </div>
        </>
      )}
      {!loading && task && (task.status === 'submitted' || task.batchId) && (
        <>
          <PageHeader onBack={goHome} />
          <div className="flex flex-col items-center justify-center py-16">
            <CheckCircle2 className="size-10 text-emerald-500 mb-4" />
            <p className="text-base text-foreground mb-2">已提交</p>
            <p className="text-sm text-muted-foreground mb-6">该任务的记录已成功提交</p>
            <Button variant="outline" onClick={() => navigate('/records')}>查看记录</Button>
          </div>
        </>
      )}

      {!loading && task?.status === 'completed' && (
        <>
          <PageHeader
            onBack={goHome}
            right={
              <span className="ml-auto text-sm text-muted-foreground">
                共 {rows.filter((r) => r.pointId || r.pressureValue).length}{' '}
                条数据
              </span>
            }
          />
          <div className="bg-card rounded-lg border border-border shadow-sm overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 text-sm font-medium text-muted-foreground w-10">#</th>
                  <th className="text-left px-3 py-3 text-sm font-medium text-muted-foreground">位点编号</th>
                  <th className="text-left px-3 py-3 text-sm font-medium text-muted-foreground w-20">时段</th>
                  <th className="text-left px-3 py-3 text-sm font-medium text-muted-foreground w-24">压差值</th>
                  <th className="text-left px-3 py-3 text-sm font-medium text-muted-foreground">记录时间</th>
                  <th className="text-left px-3 py-3 text-sm font-medium text-muted-foreground w-36">
                    区域 <span className="text-destructive">*</span>
                  </th>
                  <th className="text-left px-3 py-3 text-sm font-medium text-muted-foreground">备注</th>
                  <th className="px-3 py-3 w-10" />
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx: number) => (
                  <tr
                    key={row.key}
                    className="border-b border-border last:border-b-0"
                  >
                    <td className="px-4 py-2 text-sm text-muted-foreground tabular-nums">
                      {idx + 1}
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={row.pointId}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          updateRow(row.key, 'pointId', e.target.value)
                        }
                        className="min-h-10"
                        placeholder="PD-XX-XXX"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={row.timeSlot}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          updateRow(row.key, 'timeSlot', e.target.value)
                        }
                        className="min-h-10"
                        placeholder="时段"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={row.pressureValue}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          updateRow(row.key, 'pressureValue', e.target.value)
                        }
                        className="min-h-10"
                        placeholder="0"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={row.recordTime}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          updateRow(row.key, 'recordTime', e.target.value)
                        }
                        className="min-h-10"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <Select
                        value={row.area}
                        onValueChange={(val: string) =>
                          updateRow(row.key, 'area', val)
                        }
                      >
                        <SelectTrigger
                          className={`min-h-10 ${areaErrors.has(row.key) ? 'border-destructive' : ''}`}
                        >
                          <SelectValue placeholder="选择区域" />
                        </SelectTrigger>
                        <SelectContent>
                          {AREA_OPTIONS.map((opt: string) => (
                            <SelectItem key={opt} value={opt}>
                              {opt}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-3 py-2">
                      <Input
                        value={row.remark}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          updateRow(row.key, 'remark', e.target.value)
                        }
                        className="min-h-10"
                        placeholder="选填"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => deleteRow(row.key)}
                        className="p-2 rounded-lg hover:bg-accent transition-colors"
                        aria-label="删除行"
                      >
                        <Trash2 className="size-4 text-muted-foreground" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && (
              <div className="text-center py-12 text-muted-foreground">
                暂无识别数据，请手动添加
              </div>
            )}
          </div>
          <div className="flex gap-3 mt-4">
            <Button type="button" variant="outline" className="min-h-12" onClick={addRow}>
              <Plus className="size-4 mr-1" />添加行
            </Button>
            <Button type="button" className="flex-1 min-h-12 text-lg" onClick={handleSubmit} disabled={submitting}>
              {submitting && <Loader2 className="size-4 animate-spin mr-2" />}
              提交记录
            </Button>
          </div>
        </>
      )}
    </div>
  );
};

export default OcrResultPage;
