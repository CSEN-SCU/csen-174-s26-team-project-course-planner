import "@testing-library/jest-dom/vitest";

// Some Vitest suites run in non-jsdom environments (or with partially stubbed
// globals). Ensure a basic localStorage exists so onboarding/disclosure tests
// can persist "seen" flags without crashing.
const _memoryStorage = () => {
  let store: Record<string, string> = {};
  return {
    getItem(key: string) {
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
    setItem(key: string, value: string) {
      store[key] = String(value);
    },
    removeItem(key: string) {
      delete store[key];
    },
    clear() {
      store = {};
    },
    key(i: number) {
      return Object.keys(store)[i] ?? null;
    },
    get length() {
      return Object.keys(store).length;
    },
  };
};

const ls: any = (globalThis as any).localStorage;
if (
  !ls ||
  typeof ls.getItem !== "function" ||
  typeof ls.setItem !== "function" ||
  typeof ls.removeItem !== "function" ||
  typeof ls.clear !== "function"
) {
  // @ts-expect-error - define minimal Storage for tests
  (globalThis as any).localStorage = _memoryStorage();
}
