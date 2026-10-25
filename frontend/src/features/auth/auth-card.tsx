import { PazosLogo, PazosMark } from "@/components/brand/logo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Layout for the public screens: brand panel on the left (on top on phones), form on the right. */
export function AuthCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <aside className="bg-brand-gradient relative overflow-hidden px-6 py-8 text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        <PazosMark
          aria-hidden
          title=""
          className="pointer-events-none absolute -right-24 -bottom-24 hidden size-[28rem] text-white/[0.07] lg:block"
        />
        <PazosLogo className="h-auto w-36 lg:w-52" />
        <div className="relative hidden max-w-md space-y-4 lg:block">
          <p className="text-4xl leading-tight font-extrabold tracking-tight uppercase">
            México merece paz
          </p>
          <p className="text-lg text-white/80">
            Sistema de gestión del Partido PAZ: candidaturas, geografía electoral y organización en
            un solo lugar.
          </p>
        </div>
        <p className="relative hidden text-xs text-white/60 lg:block">
          Acceso exclusivo para personal autorizado.
        </p>
      </aside>
      <main id="contenido" className="flex items-start justify-center p-4 py-10 lg:items-center">
        <Card className="w-full max-w-md shadow-brand-lg">
          <CardHeader>
            <CardTitle>
              <h1 className="text-2xl font-extrabold">{title}</h1>
            </CardTitle>
            {description ? <CardDescription>{description}</CardDescription> : null}
          </CardHeader>
          <CardContent>{children}</CardContent>
        </Card>
      </main>
    </div>
  );
}
