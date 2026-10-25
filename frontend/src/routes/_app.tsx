import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, Outlet, redirect, useNavigate } from "@tanstack/react-router";
import { LogOut, Menu } from "lucide-react";
import { useState } from "react";
import { getMeOptions, logoutMutation } from "@/client/@tanstack/react-query.gen";
import { Kbd } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { CommandPalette } from "@/features/shell/command-palette";
import { NAV } from "@/features/shell/nav";
import { hasPermission } from "@/lib/auth/permissions";
import { clearSession, getSession, refreshAccessToken } from "@/lib/auth/session";
import { useMe } from "@/lib/auth/use-me";

/** Authenticated area: restores the session from the refresh cookie on reload, sends users
 * still enrolling TOTP to /enroll-mfa and loads the profile with permissions. */
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context, location }) => {
    if (!getSession().accessToken && !(await refreshAccessToken())) {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
    if (getSession().scope === "mfa_enrollment") throw redirect({ to: "/enroll-mfa" });
    const me = await context.queryClient.ensureQueryData(getMeOptions());
    return { me };
  },
  component: AppLayout,
});

function AppLayout() {
  const context = Route.useRouteContext();
  const me = useMe() ?? context.me;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useMutation({
    ...logoutMutation(),
    onSettled: () => {
      clearSession();
      queryClient.clear();
      navigate({ to: "/login" });
    },
  });
  const [menuOpen, setMenuOpen] = useState(false);
  const sections = NAV.map((section) => ({
    ...section,
    items: section.items.filter((item) => !item.perm || hasPermission(me, item.perm)),
  })).filter((section) => section.items.length);

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-sidebar md:flex">
        <div className="flex h-14 items-center justify-between border-b px-4">
          <Link to="/" className="font-semibold tracking-tight">
            PAZOS
          </Link>
          <span className="text-xs text-muted-foreground">
            <Kbd>Ctrl K</Kbd>
          </span>
        </div>
        <Navigation sections={sections} />
        <div className="border-t p-3 text-sm">
          <p className="truncate font-medium">{me.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">{me.email}</p>
          <Button
            variant="ghost"
            size="sm"
            className="mt-2 w-full justify-start"
            onClick={() => logout.mutate({})}
          >
            <LogOut aria-hidden /> Cerrar sesión
          </Button>
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex h-14 items-center justify-between border-b px-4 md:hidden">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Abrir menú">
                <Menu aria-hidden />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <SheetHeader>
                <SheetTitle>PAZOS</SheetTitle>
              </SheetHeader>
              {/* biome-ignore lint/a11y/noStaticElementInteractions: closes the drawer after any link click */}
              {/* biome-ignore lint/a11y/useKeyWithClickEvents: links handle the keyboard themselves */}
              <div onClick={() => setMenuOpen(false)}>
                <Navigation sections={sections} />
              </div>
            </SheetContent>
          </Sheet>
          <Link to="/" className="font-semibold">
            PAZOS
          </Link>
          <Button variant="ghost" size="sm" onClick={() => logout.mutate({})}>
            Salir
          </Button>
        </header>
        <main id="contenido" className="mx-auto max-w-7xl px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
      <CommandPalette sections={sections} />
    </div>
  );
}

function Navigation({ sections }: { sections: typeof NAV }) {
  return (
    <nav aria-label="Principal" className="flex-1 space-y-4 overflow-y-auto p-3">
      {sections.map((section) => (
        <div key={section.label}>
          <p className="px-2 pb-1 text-xs font-medium text-muted-foreground">{section.label}</p>
          <ul className="space-y-0.5">
            {section.items.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  activeOptions={{ exact: item.to === "/" || item.to === "/geography" }}
                  className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-sidebar-accent data-[status=active]:bg-sidebar-accent data-[status=active]:font-medium"
                >
                  <item.icon className="size-4" aria-hidden />
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
