import React from 'react';
import { Link } from 'react-router-dom';
import dayjs from 'dayjs';
import {
  PenLine,
  Camera,
  FileText,
  MapPin,
  ShieldCheck,
  ClipboardList,
  Clock,
} from 'lucide-react';
import { CanRole } from '@lark-apaas/client-toolkit/auth';
import { logger } from '@lark-apaas/client-toolkit/logger';
import {
  Card,
  CardContent,
} from '@/components/ui/card';
import { dashboard, getOcrTasks } from '@/api';
import type { DashboardStats, OcrTaskItem } from '@shared/api.interface';

const OCR_STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  pending: { label: '等待中', cls: 'bg-[hsl(210_55%_95%)] text-[hsl(210_85%_40%)]' },
  processing: { label: '识别中', cls: 'bg-[hsl(210_55%_95%)] text-[hsl(210_85%_40%)]' },
  completed: { label: '已完成', cls: 'bg-[hsl(152_55%_95%)] text-[hsl(152_60%_32%)]' },
  failed: { label: '失败', cls: 'bg-[hsl(4_70%_96%)] text-[hsl(4_75%_42%)]' },
  cancelled: { label: '已取消', cls: 'bg-[hsl(210_10%_94%)] text-[hsl(210_10%_45%)]' },
  submitted: { label: '已提交', cls: 'bg-[hsl(152_55%_95%)] text-[hsl(152_60%_32%)]' },
};

function formatTime(isoString: string | null): string {
  if (!isoString) return '--:--';
  const date = new Date(isoString);
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${hours}:${minutes}`;
}

const HomePage: React.FC = () => {
  const [stats, setStats] = React.useState<DashboardStats | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [ocrTasks, setOcrTasks] = React.useState<OcrTaskItem[]>([]);

  React.useEffect(() => {
    getOcrTasks()
      .then((data: OcrTaskItem[]) => setOcrTasks(data.slice(0, 3)))
      .catch(() => {});
  }, []);

  React.useEffect(() => {
    dashboard
      .getDashboardStats()
      .then((data: DashboardStats) => {
        setStats(data);
      })
      .catch((err: unknown) => {
        logger.error('获取首页统计数据失败', err);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  return (
    <div className="max-w-[1400px] mx-auto space-y-8">
      {/* 标题区 */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          302车间差压监控系统
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          差压数据采集与合规管理
        </p>
      </div>

      {/* 双模式入口区 */}
      <div className="flex flex-col md:flex-row gap-4">
        {/* 手动填写卡片 */}
        <Link to="/manual-input" className="flex-1 group">
          <Card className="bg-primary text-primary-foreground border-primary hover:shadow-md transition-shadow cursor-pointer h-full">
            <CardContent className="p-6 flex items-center gap-5">
              <div className="flex-shrink-0 w-14 h-14 rounded-xl bg-primary-foreground/20 flex items-center justify-center">
                <PenLine className="size-7" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">手动填写</h2>
                <p className="text-sm text-primary-foreground/80 mt-1">
                  30秒快速录入
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>

        {/* OCR识别卡片 */}
        <Link to="/ocr-input" className="flex-1 group">
          <Card className="border-primary border-2 hover:shadow-md transition-shadow cursor-pointer h-full">
            <CardContent className="p-6 flex items-center gap-5">
              <div className="flex-shrink-0 w-14 h-14 rounded-xl bg-accent flex items-center justify-center">
                <Camera className="size-7 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-foreground">
                  图片OCR识别
                </h2>
                <p className="text-sm text-muted-foreground mt-1">
                  拍照自动识别
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* 今日概况区 */}
      <div>
        <h3 className="text-sm font-medium text-muted-foreground mb-3">今日概况</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="p-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
                <ClipboardList className="size-5 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">今日已录入</p>
                <p className="text-2xl font-semibold tabular-nums text-foreground">{loading ? '-' : (stats?.todayCount ?? 0)}</p>
                <p className="text-xs text-muted-foreground">条</p>
              </div>
            </CardContent>
          </Card>
          <CanRole roles={['admin']} fallback={null}>
            <Card>
              <CardContent className="p-5 flex items-center gap-4">
                <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
                  <ShieldCheck className="size-5 text-warning" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">待审核</p>
                  <p className="text-2xl font-semibold tabular-nums text-warning">{loading ? '-' : (stats?.pendingCount ?? 0)}</p>
                  <p className="text-xs text-muted-foreground">条</p>
                </div>
              </CardContent>
            </Card>
          </CanRole>
          <Card>
            <CardContent className="p-5 flex items-center gap-4">
              <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center flex-shrink-0">
                <Clock className="size-5 text-primary" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">最近录入</p>
                <p className="text-2xl font-semibold tabular-nums text-foreground">{loading ? '-' : formatTime(stats?.lastRecordTime ?? null)}</p>
                <p className="text-xs text-muted-foreground">{stats?.lastRecordTime ? '今日' : '暂无记录'}</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* OCR任务区 */}
      {ocrTasks.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-muted-foreground">OCR识别任务</h3>
            <Link to="/records" className="text-xs text-primary hover:underline">查看全部</Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {ocrTasks.map((task: OcrTaskItem) => {
              const cfg = OCR_STATUS_LABEL[task.status] ?? OCR_STATUS_LABEL.pending;
              return (
                <Link key={task.id} to={`/ocr-result/${task.id}`}>
                  <Card className="hover:shadow-md transition-shadow cursor-pointer">
                    <CardContent className="p-4 flex items-center gap-3">
                      {task.imageUrl && (
                        <img src={task.imageUrl} alt="OCR" className="size-10 rounded object-cover flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <span className={`inline-block text-[11px] px-1.5 py-0.5 rounded font-medium ${cfg.cls}`}>{cfg.label}</span>
                        <p className="text-xs text-muted-foreground mt-1">{dayjs(task.createdAt).format('MM-DD HH:mm')}</p>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        </div>
      )}

      {/* 快捷入口区 */}
      <div>
        <h3 className="text-sm font-medium text-muted-foreground mb-3">快捷入口</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          <Link to="/records">
            <Card className="hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="p-4 flex items-center gap-3">
                <FileText className="size-5 text-primary flex-shrink-0" />
                <span className="text-sm font-medium text-foreground">数据记录</span>
              </CardContent>
            </Card>
          </Link>
          <CanRole roles={['admin']} fallback={null}>
            <Link to="/point-management">
              <Card className="hover:shadow-md transition-shadow cursor-pointer">
                <CardContent className="p-4 flex items-center gap-3">
                  <MapPin className="size-5 text-primary flex-shrink-0" />
                  <span className="text-sm font-medium text-foreground">位点管理</span>
                </CardContent>
              </Card>
            </Link>
          </CanRole>
          <CanRole roles={['admin']} fallback={null}>
            <Link to="/audit-management">
              <Card className="hover:shadow-md transition-shadow cursor-pointer">
                <CardContent className="p-4 flex items-center gap-3">
                  <ShieldCheck className="size-5 text-primary flex-shrink-0" />
                  <span className="text-sm font-medium text-foreground">审核管理</span>
                </CardContent>
              </Card>
            </Link>
          </CanRole>
        </div>
      </div>
    </div>
  );
};

export default HomePage;
