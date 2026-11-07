// Testes locais do BIM Studio (sem backend real): yarn jest --config jest.bim.config.cjs
module.exports = {
  ...require("./jest.assistant.config.cjs"),
  testMatch: ["<rootDir>/src/components/bim/__tests__/*.test.js?(x)"],
  transformIgnorePatterns: ["/node_modules/(?!three/examples/)"],
  setupFiles: ["<rootDir>/src/components/bim/__tests__/jest.setup.cjs"],
};
