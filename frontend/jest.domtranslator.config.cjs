// Testes do tradutor automático (DomTranslator) — sem backend.
module.exports = {
  ...require("./jest.assistant.config.cjs"),
  testMatch: ["<rootDir>/src/components/DomTranslator.perf.test.jsx"],
};
