import { describe, expect, it } from "vitest";
import type { RegistrationPayload } from "../../api/types";
import { validateRegistration } from "./validation";

const valid: RegistrationPayload = {
  first_name: "Анна-Мария",
  last_name: "Иванова",
  email: "anna@example.ru",
  department: "it",
  password: "StrongPass7",
  password_confirmation: "StrongPass7",
  accepted_terms: true,
};

describe("registration validation", () => {
  it("accepts unicode names and a strong matching password", () => {
    expect(validateRegistration(valid)).toEqual({});
  });

  it("rejects control characters and weak passwords", () => {
    expect(validateRegistration({ ...valid, first_name: "A\nB", password: "weak",
      password_confirmation: "weak" })).toMatchObject({
      first_name: expect.any(String),
      password: expect.any(String),
    });
  });
});
