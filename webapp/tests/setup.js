import { Window } from "happy-dom";

// Node 20 exposes an incomplete experimental localStorage object. Install a clean
// happy-dom implementation so the same tests behave on local Node 20 and CI Node 22.
const storage = new Window({ url: "http://localhost" }).localStorage;
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: storage,
});
