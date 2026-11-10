// Suite do Discovery Engine (/connect): regras offline, percurso adaptativo e renderização (sem backend real).
module.exports = {
  rootDir: __dirname,
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/src/connect/__tests__/*.test.{js,jsx}"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1", "\\.(css)$": "<rootDir>/src/connect/__tests__/styleStub.cjs",
    "^react-router-dom$": "<rootDir>/node_modules/react-router-dom/dist/index.js",
    "^react-router$": "<rootDir>/node_modules/react-router/dist/development/index.js",
    "^react-router/dom$": "<rootDir>/node_modules/react-router/dist/development/dom-export.js" },
  testEnvironmentOptions: { customExportConditions: [""] },
  setupFiles: ["<rootDir>/src/connect/__tests__/setup.cjs"],
  transform: { "^.+\\.[jt]sx?$": ["babel-jest", { presets: [["babel-preset-react-app", { runtime: "automatic" }]] }] },
  transformIgnorePatterns: ["/node_modules/(?!(axios)/)"],
};
