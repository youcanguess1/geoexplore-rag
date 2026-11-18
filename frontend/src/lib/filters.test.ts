import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS, filtersForRequest, normaliseFilters } from "./filters";

describe("retrieval filters", () => {
  it("omits an empty filter object from the request", () => {
    expect(filtersForRequest(EMPTY_FILTERS)).toBeUndefined();
  });

  it("normalises duplicate language and document ID values", () => {
    expect(normaliseFilters({ ...EMPTY_FILTERS, document_ids: ["geo-a", "geo-a"], languages: ["EN", "en"] })).toEqual({
      ...EMPTY_FILTERS,
      document_ids: ["geo-a"],
      languages: ["en"],
    });
  });
});
