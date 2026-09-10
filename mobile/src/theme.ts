/**
 * Palette et tokens de design STAIRPILOT — professionnel BTP.
 * Blanc / gris anthracite / bleu technique / rouge-orange-vert pour alertes.
 */

export const colors = {
  bg: '#FFFFFF',
  bgSubtle: '#F5F6F8',
  bgCard: '#FFFFFF',
  border: '#D6D9DE',
  borderStrong: '#9AA1AC',

  text: '#1A1D22',
  textMuted: '#5A6270',
  textDim: '#8A929E',

  primary: '#0B5FFF',           // bleu technique
  primaryPressed: '#0847BF',
  primaryBg: '#E8F0FF',

  danger: '#D64545',            // rouge alerte
  dangerBg: '#FDECEC',
  warn: '#E38B1E',              // orange alerte
  warnBg: '#FDF3E5',
  ok: '#2F8F55',                // vert alerte
  okBg: '#E9F5EE',

  ink: '#111318',               // fond pour hero
};

export const spacing = {
  xs: 4,
  s: 8,
  m: 12,
  l: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
};

export const radius = {
  s: 6,
  m: 10,
  l: 14,
  xl: 20,
};

export const typography = {
  h1: { fontSize: 26, fontWeight: '700' as const, letterSpacing: -0.4 },
  h2: { fontSize: 20, fontWeight: '700' as const, letterSpacing: -0.2 },
  h3: { fontSize: 16, fontWeight: '700' as const },
  body: { fontSize: 15, fontWeight: '400' as const },
  bodyStrong: { fontSize: 15, fontWeight: '600' as const },
  small: { fontSize: 13, fontWeight: '400' as const },
  caption: { fontSize: 11, fontWeight: '500' as const, letterSpacing: 0.5 },
  mono: {
    fontFamily: 'Courier',
    fontSize: 15,
    fontWeight: '600' as const,
    letterSpacing: 0.4,
  },
  monoSmall: {
    fontFamily: 'Courier',
    fontSize: 11,
    fontWeight: '500' as const,
  },
};

export const shadow = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
};
