// jsdom não expõe TextEncoder/TextDecoder (necessários ao react-router 7)
const { TextEncoder, TextDecoder } = require("util");
global.TextEncoder = global.TextEncoder || TextEncoder;
global.TextDecoder = global.TextDecoder || TextDecoder;
