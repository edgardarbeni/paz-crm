import {
  Building2,
  ClipboardList,
  FileClock,
  Flag,
  Home,
  Landmark,
  type LucideIcon,
  Map as MapIcon,
  MapPinned,
  ScrollText,
  Shield,
  Upload,
  UserRound,
  Users,
  Vote,
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
