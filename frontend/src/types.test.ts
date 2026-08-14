import { describe, it, expect } from "vitest";
import {
  toMM, toM, toNm, MM_TO_M, M_TO_MM, NM_TO_M, M_TO_NM,
  fromMeters, toMeters, LENGTH_UNIT_FACTORS, LENGTH_UNIT_LABELS,
  DEFAULT_LENGTH_UNIT,
} from "./types";

describe("unit conversion helpers", () => {
  it("converts meters to millimeters", () => {
    expect(toMM(0.005)).toBe(5);
    expect(toMM(1)).toBe(1000);
    expect(toMM(0)).toBe(0);
  });

  it("converts millimeters to meters", () => {
    expect(toM(5)).toBe(0.005);
    expect(toM(1000)).toBe(1);
    expect(toM(0)).toBe(0);
  });

  it("converts meters to nanometers", () => {
    expect(toNm(550e-9)).toBe(550);
    expect(toNm(1)).toBe(1e9);
  });

  it("has correct constants", () => {
    expect(MM_TO_M).toBe(0.001);
    expect(M_TO_MM).toBe(1000);
    expect(NM_TO_M).toBe(1e-9);
    expect(M_TO_NM).toBe(1e9);
  });

  it("round-trips values correctly", () => {
    expect(toM(toMM(0.123))).toBeCloseTo(0.123);
    expect(toMM(toM(456))).toBeCloseTo(456);
  });
});

describe("display unit conversion helpers", () => {
  it("has correct length unit factors", () => {
    expect(LENGTH_UNIT_FACTORS.nm).toBe(1e-9);
    expect(LENGTH_UNIT_FACTORS.um).toBe(1e-6);
    expect(LENGTH_UNIT_FACTORS.mm).toBe(1e-3);
    expect(LENGTH_UNIT_FACTORS.cm).toBe(1e-2);
    expect(LENGTH_UNIT_FACTORS.m).toBe(1);
  });

  it("has labels for all units", () => {
    expect(LENGTH_UNIT_LABELS.nm).toBe("nm");
    expect(LENGTH_UNIT_LABELS.um).toBe("μm");
    expect(LENGTH_UNIT_LABELS.mm).toBe("mm");
    expect(LENGTH_UNIT_LABELS.cm).toBe("cm");
    expect(LENGTH_UNIT_LABELS.m).toBe("m");
  });

  it("defaults to mm", () => {
    expect(DEFAULT_LENGTH_UNIT).toBe("mm");
  });

  it("converts meters to display units", () => {
    expect(fromMeters(0.005, "mm")).toBe(5);
    expect(fromMeters(0.005, "cm")).toBe(0.5);
    expect(fromMeters(0.005, "m")).toBe(0.005);
    expect(fromMeters(0.005, "um")).toBe(5000);
    expect(fromMeters(0.005, "nm")).toBe(5000000);
  });

  it("converts display units to meters", () => {
    expect(toMeters(5, "mm")).toBe(0.005);
    expect(toMeters(0.5, "cm")).toBe(0.005);
    expect(toMeters(0.005, "m")).toBe(0.005);
    expect(toMeters(5000, "um")).toBe(0.005);
    expect(toMeters(5000000, "nm")).toBe(0.005);
  });

  it("round-trips through all units", () => {
    for (const unit of ["nm", "um", "mm", "cm", "m"] as const) {
      expect(toMeters(fromMeters(0.123, unit), unit)).toBeCloseTo(0.123);
    }
  });
});
