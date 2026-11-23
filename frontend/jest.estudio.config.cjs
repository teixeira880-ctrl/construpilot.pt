module.exports = {
  rootDir: __dirname,
  testEnvironment: "node",
  testMatch: ["<rootDir>/src/components/licenciamento/__tests__/estudioGeo.test.js"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  transform: {
    "^.+\\.[jt]sx?$": ["babel-jest", { presets: [["babel-preset-react-app", { runtime: "automatic" }]] }],
  },
};
