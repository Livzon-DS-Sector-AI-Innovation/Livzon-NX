import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import 'dayjs/locale/zh-cn';
import {
  Bell,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  getNotifications,
  getUnreadCount,
  markNotificationRead,
  markAllNotificationsRead,
} from '@client/src/api';
import type { NotificationItem } from '@shared/api.interface';

dayjs.extend(relativeTime);
dayjs.locale('zh-cn');

const NOTIF_ICON: Record<string, React.ReactNode> = {
  ocr_completed: (
    <CheckCircle2 className="size-4 text-[hsl(152_60%_42%)]" />
  ),
  ocr_failed: <XCircle className="size-4 text-[hsl(4_75%_52%)]" />,
};

const NotificationBell: React.FC = () => {
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const fetchUnread = useCallback(async () => {
    try {
      const data = await getUnreadCount();
      setUnreadCount(data.count);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchUnread();
    const timer = setInterval(fetchUnread, 30000);
    return () => clearInterval(timer);
  }, [fetchUnread]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleOpen = async () => {
    setOpen(!open);
    if (!open) {
      setLoading(true);
      try {
        const data = await getNotifications();
        setItems(data.items);
      } catch {
        // silent
      } finally {
        setLoading(false);
      }
    }
  };

  const handleClickItem = async (item: NotificationItem) => {
    if (!item.isRead) {
      try {
        await markNotificationRead(item.id);
        setItems((prev: NotificationItem[]) =>
          prev.map((n: NotificationItem) =>
            n.id === item.id ? { ...n, isRead: true } : n,
          ),
        );
        setUnreadCount((prev: number) => Math.max(0, prev - 1));
      } catch {
        // silent
      }
    }
    if (item.relatedType === 'ocr_task' && item.relatedId) {
      setOpen(false);
      navigate(`/ocr-result/${item.relatedId}`);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setItems((prev: NotificationItem[]) =>
        prev.map((n: NotificationItem) => ({ ...n, isRead: true })),
      );
      setUnreadCount(0);
    } catch {
      // silent
    }
  };

  return (
    <div className="relative" ref={panelRef}>
      <button
        onClick={handleOpen}
        className="relative p-2 rounded-lg hover:bg-accent transition-colors"
      >
        <Bell className="size-5 text-foreground" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-[hsl(4_75%_52%)] text-white text-[10px] font-bold px-1">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-[360px] max-h-[400px] bg-card border rounded-lg shadow-lg z-50 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <span className="text-sm font-semibold text-foreground">通知</span>
            {unreadCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-7"
                onClick={handleMarkAllRead}
              >
                全部已读
              </Button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="size-5 animate-spin text-primary" />
              </div>
            ) : items.length === 0 ? (
              <div className="text-center py-8 text-sm text-muted-foreground">
                暂无通知
              </div>
            ) : (
              items.map((item: NotificationItem) => (
                <button
                  key={item.id}
                  className={`w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-accent transition-colors border-b last:border-b-0 ${
                    !item.isRead ? 'bg-[hsl(210_55%_98%)]' : ''
                  }`}
                  onClick={() => handleClickItem(item)}
                >
                  <div className="flex-shrink-0 mt-0.5">
                    {NOTIF_ICON[item.type] ?? (
                      <Bell className="size-4 text-muted-foreground" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground truncate">
                        {item.title}
                      </span>
                      {!item.isRead && (
                        <Badge
                          variant="outline"
                          className="text-[10px] px-1.5 py-0 bg-[hsl(210_85%_48%)] text-white border-none"
                        >
                          新
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {item.message}
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {dayjs(item.createdAt).fromNow()}
                    </p>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
