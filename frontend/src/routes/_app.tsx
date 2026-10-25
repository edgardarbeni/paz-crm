import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createFileRoute, Link, Outlet, redirect, useNavigate } from "@tanstack/react-router";
import { LogOut, Menu, Search } from "lucide-react";
import { useState } from "react";
import { getMeOptions, logoutMutation } from "@/client/@tanstack/react-query.gen";
import { PazosLogo } from "@/components/brand/logo";
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
  const [paletteOpen, setPaletteOpen] = useState(false);
  const sections = NAV.map((section) => ({
    ...section,
    items: section.items.filter((item) => !item.perm || hasPermission(me, item.perm)),
  })).filter((section) => section.items.length);

  return (
    <div className="flex min-h-screen">
      <aside className="bg-brand-gradient sticky top-0 hidden h-screen w-64 shrink-0 flex-col text-sidebar-foreground md:flex">
        <div className="px-5 pt-5 pb-3">
          <Link
            to="/"
            aria-label="Inicio"
            className="block w-32 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring"
          >
            <PazosLogo className="h-auto w-full" />
          </Link>
          <SearchButton onClick={() => setPaletteOpen(true)} />
        </div>
        <Navigation sections={sections} />
        <UserBlock name={me.full_name} email={me.email} onLogout={() => logout.mutate({})} />
      </aside>
      <div className="min-w-0 flex-1">
        <header className="bg-brand-gradient sticky top-0 z-30 flex h-14 items-center justify-between px-2 text-sidebar-foreground shadow-brand md:hidden">
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Abrir menú"
                className="hover:bg-sidebar-accent hover:text-sidebar-foreground"
              >
                <Menu aria-hidden />
              </Button>
            </SheetTrigger>
            <SheetContent
              side="left"
              className="bg-brand-gradient flex w-72 flex-col border-0 p-0 text-sidebar-foreground"
            >
              <SheetHeader className="px-5 pt-6">
                <SheetTitle className="w-28 text-sidebar-foreground">
                  <PazosLogo className="h-auto w-full" />
                </SheetTitle>
              </SheetHeader>
              {/* biome-ignore lint/a11y/noStaticElementInteractions: closes the drawer after any link click */}
              {/* biome-ignore lint/a11y/useKeyWithClickEvents: links handle the keyboard themselves */}
              <div className="flex min-h-0 flex-1 flex-col" onClick={() => setMenuOpen(false)}>
                <Navigation sections={sections} />
              </div>
              <UserBlock name={me.full_name} email={me.email} onLogout={() => logout.mutate({})} />
            </SheetContent>
          </Sheet>
          <Link to="/" aria-label="Inicio" className="w-24">
            <PazosLogo className="h-auto w-full" />
          </Link>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Ir a…"
            className="hover:bg-sidebar-accent hover:text-sidebar-foreground"
            onClick={() => setPaletteOpen(true)}
          >
            <Search aria-hidden />
          </Button>
        </header>
        <main id="contenido" className="mx-auto max-w-7xl px-4 py-6 md:px-8 md:py-8">
          <Outlet />
        </main>
      </div>
      <CommandPalette sections={sections} open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}

function SearchButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-5 flex w-full items-center gap-2 rounded-full bg-white/12 px-3.5 py-2 text-sm text-white/80 ring-1 ring-white/15 transition-colors outline-none hover:bg-white/18 hover:text-white focus-visible:ring-2 focus-visible:ring-sidebar-ring"
    >
      <Search className="size-4" aria-hidden />
      <span className="flex-1 text-left">Ir a…</span>
      <kbd className="rounded-md bg-white/15 px-1.5 py-0.5 font-sans text-[0.68rem] font-semibold">
        Ctrl K
      </kbd>
    </button>
  );
}

function UserBlock({
  name,
  email,
  onLogout,
}: {
  name: string;
  email: string;
  onLogout: () => void;
}) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
  return (
    <div className="m-3 rounded-2xl bg-black/15 p-3 text-sm">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="grid size-9 shrink-0 place-items-center rounded-full bg-white font-bold text-primary"
        >
          {initials}
        </span>
        <div className="min-w-0">
          <Link to="/account" className="block truncate font-semibold hover:underline">
            {name}
          </Link>
          <p className="truncate text-xs text-white/65">{email}</p>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="mt-3 w-full justify-start text-white/85 hover:bg-sidebar-accent hover:text-white"
        onClick={onLogout}
      >
        <LogOut aria-hidden /> Cerrar sesión
      </Button>
    </div>
  );
}

function Navigation({ sections }: { sections: typeof NAV }) {
  return (
    <nav aria-label="Principal" className="flex-1 space-y-4 overflow-y-auto px-3 py-2">
      {sections.map((section) => (
        <div key={section.label}>
          <p className="px-3 pb-1.5 text-[0.68rem] font-bold tracking-widest text-white/55 uppercase">
            {section.label}
          </p>
          <ul className="space-y-0.5">
            {section.items.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  activeOptions={{ exact: item.to === "/" || item.to === "/geography" }}
                  className="flex items-center gap-2.5 rounded-full px-3 py-1.5 text-sm font-medium text-white/80 transition-colors outline-none hover:bg-sidebar-accent hover:text-white focus-visible:ring-2 focus-visible:ring-sidebar-ring data-[status=active]:bg-white data-[status=active]:font-semibold data-[status=active]:text-primary data-[status=active]:shadow-sm"
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
