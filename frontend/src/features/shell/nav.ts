import {
  BookOpen,
  Building2,
  ChartColumn,
  ClipboardList,
  FileClock,
  FileUp,
  Flag,
  HandHeart,
  Home,
  House,
  Landmark,
  Link2,
  ListChecks,
  type LucideIcon,
  Map as MapIcon,
  MapPinHouse,
  MapPinned,
  Network,
  ScrollText,
  Settings2,
  Shield,
  TriangleAlert,
  Upload,
  UserRound,
  Users,
  Vote,
  Waypoints,
} from "lucide-react";
import { Perm, type PermCode } from "@/lib/auth/permissions";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  perm?: PermCode;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

export const NAV: NavSection[] = [
  { label: "General", items: [{ to: "/", label: "Inicio", icon: Home }] },
  {
    label: "Candidaturas",
    items: [
      { to: "/nominations", label: "Postulaciones", icon: Vote, perm: Perm.CANDIDACIES_READ },
      {
        to: "/processes",
        label: "Procesos electorales",
        icon: ClipboardList,
        perm: Perm.CANDIDACIES_READ,
      },
      { to: "/parties", label: "Partidos", icon: Flag, perm: Perm.CANDIDACIES_READ },
      { to: "/office-types", label: "Cargos", icon: Landmark, perm: Perm.CANDIDACIES_READ },
    ],
  },
  {
    label: "Estructura del partido",
    items: [
      {
        to: "/structure/bodies",
        label: "Órganos y cargos",
        icon: Network,
        perm: Perm.STRUCTURE_BODY_READ,
      },
      {
        to: "/structure/coordinations",
        label: "Coordinaciones",
        icon: Waypoints,
        perm: Perm.STRUCTURE_COORDINATION_READ,
      },
      {
        to: "/structure/catalog",
        label: "Catálogo estatutario",
        icon: BookOpen,
        perm: Perm.STRUCTURE_BODY_READ,
      },
      {
        to: "/structure/territory",
        label: "Territorio por resolver",
        icon: TriangleAlert,
        perm: Perm.STRUCTURE_CATALOG_MANAGE,
      },
    ],
  },
  {
    label: "Movimiento de Paz",
    items: [
      {
        to: "/peace-movement/members",
        label: "Pacificadores",
        icon: HandHeart,
        perm: Perm.PEACE_MEMBER_READ,
      },
      {
        to: "/peace-movement/validation",
        label: "Validación",
        icon: ListChecks,
        perm: Perm.PEACE_MEMBER_VALIDATE,
      },
      {
        to: "/peace-movement/houses",
        label: "Casas de Paz",
        icon: House,
        perm: Perm.PEACE_HOUSE_READ,
      },
      {
        to: "/peace-movement/houses/map",
        label: "Mapa de casas",
        icon: MapPinHouse,
        perm: Perm.PEACE_HOUSE_READ,
      },
      {
        to: "/peace-movement/houses/to-link",
        label: "Casas por enlazar",
        icon: Link2,
        perm: Perm.PEACE_HOUSE_LINK,
      },
      {
        to: "/peace-movement/stats",
        label: "Estadísticas",
        icon: ChartColumn,
        perm: Perm.PEACE_STATS_READ,
      },
      {
        to: "/peace-movement/imports",
        label: "Importar",
        icon: FileUp,
        perm: Perm.PEACE_MEMBER_IMPORT,
      },
      {
        to: "/peace-movement/settings",
        label: "Configuración",
        icon: Settings2,
        perm: Perm.PEACE_GOAL_MANAGE,
      },
    ],
  },
  {
    label: "Personas",
    items: [{ to: "/people", label: "Personas", icon: UserRound, perm: Perm.PERSON_READ }],
  },
  {
    label: "Geografía",
    items: [
      { to: "/geography", label: "Explorador", icon: Building2, perm: Perm.GEOGRAPHY_READ },
      { to: "/geography/map", label: "Mapa", icon: MapIcon, perm: Perm.GEOGRAPHY_READ },
      {
        to: "/geography/locate",
        label: "Ubicar coordenada",
        icon: MapPinned,
        perm: Perm.GEOGRAPHY_READ,
      },
      {
        to: "/geography/imports",
        label: "Importaciones",
        icon: Upload,
        perm: Perm.GEOGRAPHY_IMPORT_READ,
      },
    ],
  },
  {
    label: "Administración",
    items: [
      { to: "/users", label: "Usuarios", icon: Users, perm: Perm.USER_READ },
      { to: "/roles", label: "Roles y permisos", icon: Shield, perm: Perm.ROLE_READ },
      { to: "/audit", label: "Bitácora", icon: ScrollText, perm: Perm.AUDIT_READ },
    ],
  },
  { label: "Cuenta", items: [{ to: "/account", label: "Mi cuenta", icon: FileClock }] },
];
