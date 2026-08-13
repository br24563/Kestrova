import { describe, it, expect } from "vitest";
import { toMM, toM, toNm, MM_TO_M, M_TO_MM, NM_TO_M, M_TO_NM } from "./types";

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