module.exports = {
  rootDir: __dirname,
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/src/components/atelier/__tests__/*.test.jsx"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  transform: {
    "^.+\\.[jt]sx?$": ["babel-jest", { presets: [["babel-preset-react-app", { runtime: "automatic" }]] }],
  },
  transformIgnorePatterns: ["/node_modules/(?!lucide-react)"],
};
