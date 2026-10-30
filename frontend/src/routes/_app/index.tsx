import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import { searchMembersOptions } from "@/client/@tanstack/react-query.gen";
import { PazosMark } from "@/components/brand/logo";
import { Kbd } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { NAV } from "@/features/shell/nav";
import { SystemStatus } from "@/features/system/system-status";
import { hasPermission, Perm } from "@/lib/auth/permissions";
import { useCan, useMe } from "@/lib/auth/use-me";

export const Route = createFileRoute("/_app/")({ component: HomePage });

const SHORTCUTS: [string, string][] = [
  ["Ctrl K", "Ir a cualquier pantalla"],
  ["/", "Buscar en la lista actual"],
  ["N", "Nuevo registro (en listas)"],
  ["↑ ↓ / Enter", "Recorrer filas y abrir"],
  ["Ctrl Enter", "Guardar el formulario"],
  ["Esc", "Cerrar diálogos"],
];

const QUICK_ACCESS: Record<string, string> = {
  "/nominations": "Captura y seguimiento de planillas, fórmulas y listas.",
  "/people": "Busca, registra y actualiza personas.",
  "/peace-movement/members":
    "Pacificadores, su red, avance contra la meta y enlaces de inscripción.",
  "/peace-movement/houses/map": "Casas de Paz sobre el mapa, con su estatus.",
  "/processes": "Cargos, ayuntamientos, reglas y coaliciones por proceso.",
  "/geography/map": "Secciones, distritos y municipios sobre el mapa.",
  "/users": "Invitaciones, roles y alcance geográfico.",
  "/audit": "Quién hizo qué, cuándo y desde dónde.",
};

function HomePage() {
  const me = useMe();
  const items = NAV.flatMap((section) => section.items).filter(
    (item) => item.to in QUICK_ACCESS && (!item.perm || (me && hasPermission(me, item.perm))),
  );
  return (
    <section aria-labelledby="titulo-inicio" className="space-y-8">
      <div className="bg-brand-gradient relative overflow-hidden rounded-3xl px-6 py-8 text-white shadow-brand-lg md:px-10 md:py-10">
        <PazosMark
          aria-hidden
          title=""
          className="pointer-events-none absolute -top-10 -right-10 size-64 text-white/[0.08]"
        />
        <p className="relative text-sm font-semibold tracking-widest text-white/70 uppercase">
          PAZOS
        </p>
        <h1 id="titulo-inicio" className="relative mt-1 text-3xl font-extrabold md:text-4xl">
          Panel de administración
        </h1>
        {me ? <p className="relative mt-2 text-lg text-white/85">Hola, {me.full_name}.</p> : null}
      </div>
      <PendingValidations />
      {items.length ? (
        <nav aria-label="Accesos rápidos">
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <li key={item.to}>
                <Link
                  to={item.to}
                  className="group flex h-full items-start gap-4 rounded-2xl border bg-card p-5 shadow-brand transition-all outline-none hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-brand-lg focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-secondary text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                    <item.icon className="size-5" aria-hidden />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-1 font-bold">
                      {item.label}
                      <ArrowRight
                        className="size-4 -translate-x-1 text-primary opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100"
                        aria-hidden
                      />
                    </span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      {QUICK_ACCESS[item.to]}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-2">
        <SystemStatus />
        <Card>
          <CardHeader>
            <CardTitle>
              <h2>Atajos de teclado</h2>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              {SHORTCUTS.map(([keys, label]) => (
                <div key={keys} className="contents">
                  <dt>
                    <Kbd>{keys}</Kbd>
                  </dt>
                  <dd>{label}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

/** Enrollments waiting for someone with `peace_movement.member.validate` (public link, app). */
function PendingValidations() {
  const can = useCan();
  const allowed = can(Perm.PEACE_MEMBER_VALIDATE);
  const pending = useQuery({
    ...searchMembersOptions({ query: { status: "pending_validation", limit: 50 } }),
    enabled: allowed,
  });
  const count = pending.data?.items.length ?? 0;
  if (!allowed || !count) return null;
  return (
    <Link
      to="/peace-movement/validation"
      className="flex items-center justify-between gap-4 rounded-2xl border border-primary/30 bg-secondary/60 p-4 text-sm outline-none transition-colors hover:bg-secondary focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <span>
        <strong>
          {pending.data?.has_more ? "Más de 50" : count}{" "}
          {count === 1 ? "inscripción pendiente" : "inscripciones pendientes"}
        </strong>{" "}
        de validar en el Movimiento de Paz.
      </span>
      <span className="flex items-center gap-1 font-semibold text-primary">
        Revisar <ArrowRight aria-hidden className="size-4" />
      </span>
    </Link>
  );
}
