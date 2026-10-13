module.exports = {
  rootDir: __dirname,
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/src/components/planTakeoff/__tests__/iter153.cad-import-info.test.jsx"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  transform: {
    "^.+\\.[jt]sx?$": [
      "babel-jest",
      { presets: [["babel-preset-react-app", { runtime: "automatic" }]] },
    ],
  },
};