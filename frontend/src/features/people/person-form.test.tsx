import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { configureZod } from "@/lib/forms";
import { renderWithQuery } from "@/test/utils";
import { curpCheckDigit } from "./curp";
import { PersonForm } from "./person-form";

const CURP = `GALM850315MASRPR0${curpCheckDigit("GALM850315MASRPR0")}`;

describe("PersonForm", () => {
  configureZod();

  it("validates the CURP while typing and derives birth date, sex and entity", async () => {
    const onSubmit = vi.fn(async () => {});
    renderWithQuery(<PersonForm error={null} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText(/Nombre\(s\)/), "María");
    await userEvent.type(screen.getByLabelText(/Primer apellido/), "García");
    const curp = screen.getByLabelText("CURP");
    await userEvent.type(curp, `${CURP.slice(0, 17)}0`.toLowerCase());
    expect(
      await screen.findByText("El dígito verificador de la CURP no corresponde."),
    ).toBeInTheDocument();
    await userEvent.clear(curp);
    await userEvent.type(curp, CURP.toLowerCase());
    expect(curp).toHaveValue(CURP);
    await waitFor(() =>
      expect(screen.getByLabelText("Fecha de nacimiento")).toHaveValue("1985-03-15"),
    );
    expect(screen.getByLabelText("Sexo")).toHaveValue("M");
    expect(screen.getByLabelText("Entidad de nacimiento")).toHaveValue("AS");

    await userEvent.click(screen.getByRole("button", { name: "Guardar persona" }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        given_names: "María",
        paternal_surname: "García",
        maternal_surname: null,
        curp: CURP,
        sex: "M",
        birth_date: "1985-03-15",
        birth_entity: "AS",
        contacts: [],
      }),
    );
  });

  it("warns before saving when captured data contradicts the CURP", async () => {
    renderWithQuery(<PersonForm error={null} onSubmit={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("Sexo"), "H");
    await userEvent.type(screen.getByLabelText("CURP"), CURP);
    expect(await screen.findByText("La CURP no coincide con los datos")).toBeInTheDocument();
    expect(screen.getByText(/El sexo no coincide con la CURP/)).toBeInTheDocument();
    // Without people.person.read_sensitive the user cannot force it.
    expect(screen.queryByLabelText(/Registrar de todos modos/)).not.toBeInTheDocument();
  });
});
