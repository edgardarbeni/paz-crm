import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/peace-movement/")({
  beforeLoad: () => {
    throw redirect({ to: "/peace-movement/members" });
  },
});
