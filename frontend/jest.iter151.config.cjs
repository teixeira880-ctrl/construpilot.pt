module.exports = {
  rootDir: __dirname,
  testEnvironment: "jsdom",
  testMatch: ["<rootDir>/src/components/radar/__tests__/iter151.postal.ui.test.jsx"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  transform: {
    "^.+\\.[jt]sx?$": [
      "babel-jest",
      { presets: [["babel-preset-react-app", { runtime: "automatic" }]] },
    ],
  },
};
