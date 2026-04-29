import { vi } from "vitest";

vi.mock("@prisma/client", () => {
  class PrismaClient {
    course = {
      findMany: vi.fn(async () => [])
    };
  }
  return { PrismaClient };
});
