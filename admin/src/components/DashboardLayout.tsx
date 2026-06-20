import { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import ThemeToggle from './ThemeToggle'

export interface NavItem {
  to: string
  label: string
  icon?: ReactNode
}

// 공유 대시보드 셸(ADR-0017): 좌측 사이드바 + 상단 바 + <Outlet/>. Operator/Tenant가 nav만 달리해 공유.
export default function DashboardLayout({
  brand,
  navItems,
  user,
  onLogout,
  onLogoutAll,
}: {
  brand: string
  navItems: NavItem[]
  user?: string | null
  onLogout: () => void
  onLogoutAll: () => void
}) {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="flex w-60 flex-shrink-0 flex-col border-r border-border bg-card">
        <div className="px-5 py-4 text-base font-semibold">{brand}</div>
        <nav className="flex flex-col gap-1 px-3" aria-label="주 메뉴">
          {navItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground',
                  isActive && 'bg-accent font-medium text-accent-foreground',
                )
              }
            >
              {item.icon}
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-2 border-b border-border px-6">
          {user && <span className="mr-2 text-sm text-muted-foreground">{user}</span>}
          <ThemeToggle />
          <Button variant="outline" size="sm" onClick={onLogout}>
            로그아웃
          </Button>
          <Button variant="ghost" size="sm" onClick={onLogoutAll}>
            모든 기기에서 로그아웃
          </Button>
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
