import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import dayjs from 'dayjs';
import {
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  Loader2,
  Clock,
  X,
  Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { getOcrTasks, cancelOcrTask, retryOcrTask, deleteOcrTask } from '@client/src/api';
import type { OcrTaskItem } from '@shared/api.interface';

const OCR_STATUS_CONFIG: Record<
  string,
  { label: string; className: string; icon: React.ReactNode }
> = {
  pending: {
    label: '等待中',
    className:
      'bg-[hsl(210_55%_95%)] text-[hsl(210_85%_40%)] border-[hsl(210_45%_80%)]',
    icon: <Clock className="size-3" />,
  },
  processing: {
    label: '识别中',
    className:
      'bg-[hsl(210_55%_95%)] text-[hsl(210_85%_40%)] border-[hsl(210_45%_80%)]',
    icon: <Loader2 className="size-3 animate-spin" />,
  },
  completed: {
    label: '已完成',
    className:
      'bg-[hsl(152_55%_95%)] text-[hsl(152_60%_32%)] border-[hsl(152_45%_78%)]',
    icon: <CheckCircle2 className="size-3" />,
  },
  failed: {
    label: '失败',
    className:
      'bg-[hsl(4_70%_96%)] text-[hsl(4_75%_42%)] border-[hsl(4_55%_80%)]',
    icon: <XCircle className="size-3" />,
  },
  cancelled: {
    label: '已取消',
    className:
      'bg-[hsl(210_10%_94%)] text-[hsl(210_10%_45%)] border-[hsl(210_10%_82%)]',
    icon: <X className="size-3" />,
  },
  submitted: {
    label: '已提交',
    className:
      'bg-[hsl(152_55%_95%)] text-[hsl(152_60%_32%)] border-[hsl(152_45%_78%)]',
    icon: <CheckCircle2 className="size-3" />,
  },
};

const OcrTasksSection: React.FC = () => {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<OcrTaskItem[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getOcrTasks();
      setTasks(data);
    } catch {
      toast.error('获取OCR任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  const handleCancel = async (taskId: string) => {
    try {
      await cancelOcrTask(taskId);
      toast.success('已取消任务');
      fetchTasks();
    } catch {
      toast.error('取消任务失败');
    }
  };

  const handleRetry = async (taskId: string) => {
    try {
      await retryOcrTask(taskId);
      toast.success('已重新提交任务');
      fetchTasks();
    } catch {
      toast.error('重试任务失败');
    }
  };

  const handleDelete = async (taskId: string) => {
    try {
      await deleteOcrTask(taskId);
      toast.success('已删除任务');
      fetchTasks();
    } catch {
      toast.error('删除任务失败');
    }
  };

  const handleTaskClick = (task: OcrTaskItem) => {
    if (task.status === 'completed' || task.status === 'submitted') {
      navigate(`/ocr-result/${task.id}`);
    }
  };

  if (tasks.length === 0 && !loading) return null;

  const activeTasks = tasks.filter(
    (t: OcrTaskItem) =>
      t.status === 'pending' ||
      t.status === 'processing' ||
      t.status === 'failed',
  );

  return (
    <Card>
      <CardContent className="p-4">
        <button
          className="flex items-center justify-between w-full"
          onClick={() => setExpanded(!expanded)}
        >
          <span className="text-sm font-medium text-foreground flex items-center gap-2">
            OCR识别任务
            {activeTasks.length > 0 && (
              <Badge
                variant="outline"
                className="bg-[hsl(210_55%_95%)] text-[hsl(210_85%_40%)]"
              >
                {activeTasks.length} 进行中
              </Badge>
            )}
          </span>
          {expanded ? (
            <ChevronUp className="size-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="size-4 text-muted-foreground" />
          )}
        </button>

        {expanded && (
          <div className="mt-3 space-y-2">
            {loading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="size-5 animate-spin text-primary" />
              </div>
            ) : (
              tasks.map((task: OcrTaskItem) => {
                const cfg =
                  OCR_STATUS_CONFIG[task.status] ?? OCR_STATUS_CONFIG.pending;
                return (
                  <div
                    key={task.id}
                    className={cn(
                      'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                      (task.status === 'completed' ||
                        task.status === 'submitted') &&
                        'cursor-pointer hover:bg-accent',
                    )}
                    onClick={() => handleTaskClick(task)}
                  >
                    {task.imageUrl && (
                      <img
                        src={task.imageUrl}
                        alt="OCR"
                        className="size-10 rounded object-cover flex-shrink-0"
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className={cn('text-xs', cfg.className)}>
                          {cfg.icon}
                          {cfg.label}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {dayjs(task.createdAt).format('MM-DD HH:mm')}
                        </span>
                      </div>
                      {task.status === 'failed' && task.errorMessage && (
                        <p className="text-xs text-[hsl(4_75%_52%)] mt-1 truncate">
                          {task.errorMessage}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {(task.status === 'pending' ||
                        task.status === 'processing') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs h-7"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            handleCancel(task.id);
                          }}
                        >
                          取消
                        </Button>
                      )}
                      {task.status === 'failed' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-xs h-7"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            handleRetry(task.id);
                          }}
                        >
                          重试
                        </Button>
                      )}
                      {(task.status === 'completed' ||
                        task.status === 'submitted') && (
                        <span className="text-xs text-primary">查看结果</span>
                      )}
                      {task.status !== 'processing' && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 text-muted-foreground hover:text-[hsl(4_75%_52%)]"
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            handleDelete(task.id);
                          }}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default OcrTasksSection;
