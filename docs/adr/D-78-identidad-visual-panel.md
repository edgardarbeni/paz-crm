# D-78 · Identidad visual del panel

- **Estado:** Aceptada
- **Área:** Fase C — geografía

Colores de identidad: morado PAZ `#682575` y blanco; tipografía Montserrat. Lineamientos tomados de partidopaz.mx: títulos gruesos, botones tipo píldora, tarjetas blancas con sombra morada suave y paneles con degradado morado (menú lateral, inicio de sesión y portada).
- **Paleta:** los tokens de `src/index.css` derivan del morado (OKLCH, tono 320.8). Los grises llevan un matiz morado. `--brand`, `--brand-strong` y `--brand-soft` quedan disponibles como utilidades (`bg-brand-soft`, `shadow-brand`, `bg-brand-gradient`).
- **Montserrat autoalojada** con `@fontsource-variable/montserrat`: son los mismos archivos de Google Fonts, empaquetados con el panel. No se carga desde el CDN de Google por tres razones: la CSP de producción solo permite fuentes del propio origen; no se envía la IP de cada usuario a un tercero (LFPDPPP); y no hay petición adicional a otro dominio. El navegador descarga solo el subconjunto latino (~38 kB, una fuente variable con todos los pesos).
- **Logotipo:** `components/brand/logo.tsx` genera `PazosLogo` (logotipo completo) y `PazosMark` (óvalo con la paloma) desde el arte oficial en `docs/brand/` (`pazos-logo-white.svg` y `pazos-logo-ovalo-white.svg`), con `currentColor`. El viewBox del componente se ajusta al área pintada, que incluye el contorno de 20 px de la S, con un margen de 6 px. Medirlo sin el contorno recorta la S. El favicon es el óvalo sobre morado.
- Solo tema claro (suposición 1 de la fase E). Los colores de las capas del mapa no cambian, porque cada nivel necesita un color distinto.
