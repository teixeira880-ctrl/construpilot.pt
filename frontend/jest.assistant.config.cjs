// Suite locale ciblée, aucune requête vers le backend réel.
module.exports = {
  rootDir: __dirname,
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/src/components/assistant/__tests__/*.test.jsx"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  transform: { "^.+\\.[jt]sx?$": ["babel-jest", { presets: [["babel-preset-react-app", { runtime: "automatic" }]] }] },
};
