"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  Bell,
  BarChart3,
  Fish,
  Settings,
  LogOut,
  Menu,
  TrendingUp,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { useProfile } from "@/hooks/use-user";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { usePathname } from "next/navigation";
import { useState } from "react";

const mobileNavItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/alerts", label: "Alerts", icon: Bell },
  { href: "/markets", label: "Markets", icon: BarChart3 },
  { href: "/whales", label: "Whales", icon: Fish },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function TopBar() {
  const router = useRouter();
  const pathname = usePathname();
  const logout = useAuthStore((s) => s.logout);
  const { data: profile } = useProfile();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <>
      <header className="flex h-16 items-center justify-between border-b bg-background px-4 lg:px-6">
        <div className="flex items-center gap-2 lg:hidden">
          <button onClick={() => setMobileOpen(!mobileOpen)} className="p-2">
            <Menu className="h-5 w-5" />
          </button>
          <TrendingUp className="h-5 w-5 text-emerald-600" />
          <span className="font-bold">PolyMarket AI</span>
        </div>
        <div className="hidden lg:block" />
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">
            {profile?.email}
          </span>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" />
            Logout
          </Button>
        </div>
      </header>
      {mobileOpen && (
        <nav className="border-b bg-background p-4 lg:hidden">
          {mobileNavItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
                  isActive
                    ? "bg-accent text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      )}
    </>
  );
}
