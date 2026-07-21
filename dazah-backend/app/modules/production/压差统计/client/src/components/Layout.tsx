import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import {
  Home,
  PenLine,
  Camera,
  FileText,
  MapPin,
  ShieldCheck,
  Database,
} from 'lucide-react';
import { CanRole, useAuth, ROLE_SUBJECT } from '@lark-apaas/client-toolkit/auth';
import { useCurrentUserProfile } from '@lark-apaas/client-toolkit/hooks/useCurrentUserProfile';
import { useAppInfo } from '@lark-apaas/client-toolkit/hooks/useAppInfo';
import { getDataloom } from '@lark-apaas/client-toolkit/dataloom';
import { logger } from '@lark-apaas/client-toolkit/logger';
import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarTrigger,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
} from '@/components/ui/breadcrumb';
import { Image } from '@/components/ui/image';
import NotificationBell from './NotificationBell';

const GUEST_AVATAR =
  'https://lf3-static.bytednsdoc.com/obj/eden-cn/LMfspH/ljhwZthlaukjlkulzlp/miao/no-person.svg';

type NavItem = {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
};

const NAV_ITEMS: NavItem[] = [
  { path: '/', label: '首页', icon: Home },
  { path: '/manual-input', label: '手动填写', icon: PenLine },
  { path: '/ocr-input', label: 'OCR识别', icon: Camera },
  { path: '/records', label: '数据记录', icon: FileText },
  { path: '/point-management', label: '位点管理', icon: MapPin, adminOnly: true },
  { path: '/audit-management', label: '审核管理', icon: ShieldCheck, adminOnly: true },
];

function NavItemButton({ item, pathname }: { item: NavItem; pathname: string }) {
  const isActive = pathname === item.path;
  const Icon = item.icon;
  return (
    <SidebarMenuButton asChild isActive={isActive}>
      <Link to={item.path}>
        <Icon className="size-4" />
        <span>{item.label}</span>
      </Link>
    </SidebarMenuButton>
  );
}

function AdminNavItem({ item, pathname }: { item: NavItem; pathname: string }) {
  return (
    <CanRole
      roles={['admin']}
      fallback={null}
    >
      <SidebarMenuItem>
        <NavItemButton item={item} pathname={pathname} />
      </SidebarMenuItem>
    </CanRole>
  );
}

function UserInfo() {
  const userInfo = useCurrentUserProfile();
  const [showMenu, setShowMenu] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = async () => {
    const dataloom = await getDataloom();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const result = await (dataloom as any).service.session.signOut();
    if (result.error) {
      logger.error('退出登录失败:', result.error.message);
      return;
    }
    window.location.reload();
  };

  const handleLogin = async () => {
    const dataloom = await getDataloom();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (dataloom as any).service.session.redirectToLogin();
  };

  const avatar = userInfo?.avatar || GUEST_AVATAR;
  const name = userInfo?.name || '游客';
  const isLoggedIn = !!userInfo?.user_id;

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setShowMenu(!showMenu)}
        className="flex items-center gap-3 w-full p-2 rounded-lg hover:bg-sidebar-accent transition-colors"
      >
        <Image
          src={avatar}
          alt={name}
          width={32}
          height={32}
          className="rounded-full size-8 object-cover"
        />
        <div className="flex-1 min-w-0 text-left group-data-[collapsible=icon]:hidden">
          <p className="text-sm font-medium truncate">{name}</p>
        </div>
      </button>
      {showMenu && (
        <div className="absolute bottom-full left-0 mb-2 w-48 rounded-lg border bg-card shadow-md p-1 z-50">
          {isLoggedIn ? (
            <button
              onClick={handleLogout}
              className="w-full text-left px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors"
            >
              退出登录
            </button>
          ) : (
            <button
              onClick={handleLogin}
              className="w-full text-left px-3 py-2 text-sm rounded-md hover:bg-accent transition-colors"
            >
              登录
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function LayoutContent() {
  const { pathname } = useLocation();
  const { appName } = useAppInfo();

  const activeItem = NAV_ITEMS.find((item) => item.path === pathname);
  const activeTitle = activeItem?.label || '';

  return (
    <>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <Link to="/">
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
                    DP
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight group-data-[collapsible=icon]:hidden">
                    <span className="truncate font-semibold">
                      {appName || '差压监控系统'}
                    </span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {NAV_ITEMS.filter((item) => !item.adminOnly).map((item) => (
                  <SidebarMenuItem key={item.path}>
                    <NavItemButton item={item} pathname={pathname} />
                  </SidebarMenuItem>
                ))}
                {NAV_ITEMS.filter((item) => item.adminOnly).map((item) => (
                  <AdminNavItem key={item.path} item={item} pathname={pathname} />
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter>
          <Separator className="mb-2" />
          <UserInfo />
        </SidebarFooter>
      </Sidebar>

      <main className="flex-1 flex flex-col overflow-hidden p-6">
        <header className="flex items-center gap-2 mb-6">
          <SidebarTrigger />
          <Separator orientation="vertical" className="h-4" />
          <Breadcrumb className="self-center flex-1">
            <BreadcrumbList>
              <BreadcrumbItem className="text-foreground font-medium">
                {activeTitle}
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <NotificationBell />
        </header>
        <div className="flex-1 overflow-auto">
          <Outlet />
        </div>
      </main>
    </>
  );
}

const Layout = () => {
  return (
    <SidebarProvider>
      <LayoutContent />
    </SidebarProvider>
  );
};

export default Layout;
