"""Catalogue de profils acier EN 10365 (IPE/HEA/HEB/UPN) + classification de section EN 1993-1-1.

Propriétés VÉRIFIÉES : A, Iy, Iz, Wel,y, Wpl,y calculées par intégration de la section
réelle EN 10365 (congés inclus) — concordance <0,1 % avec les tables publiées. Av,z suit
EN 1993-1-1 §6.2.6(3). It (St-Venant, El Darwish & Johnston 1965) et Iw (section bi-symétrique)
sont des formules reconnues (écart ~2 % des tables) servant au Mcr indicatif. Profilés en U
(UPN) : section mono-symétrique → Mcr non calculé automatiquement (maintien latéral / Mcr manuel).

Classification §5.5 / Table 5.2 : ε=√(235/fy), ratios c/t du banzo (outstand) et de l'âme
(flexion ou compression). Rien n'est validé — valeurs indicatives, à vérifier par l'ingénieur.
"""
from __future__ import annotations

import math

VERSION = "profiles-en10365-0.1.0"
SOURCE = ("Géométrie EN 10365 (DIN 1026 pour UPN) ; A/Iy/Iz/Wel/Wpl par intégration section réelle ; "
          "Av §6.2.6(3) ; It El Darwish & Johnston 1965 ; Iw bi-symétrique — à vérifier")
GRADES = {"S235": 235, "S275": 275, "S355": 355}  # fy (MPa), t ≤ 40 mm
# Limites c/t de la Table 5.2 (× ε) : classe 1/2/3
FLANGE_LIMITS = (9.0, 10.0, 14.0)          # banzo en console, compression
WEB_BENDING_LIMITS = (72.0, 83.0, 124.0)   # âme interne en flexion
WEB_COMPRESSION_LIMITS = (33.0, 38.0, 42.0)  # âme interne en compression pure

PROFILE_DATA = {
    'IPE80': {'A': 7.6447, 'Wel': 20.0379, 'Wpl': 23.2211, 'Iy': 80.1514, 'Iz': 8.4892, 'It': 0.6723, 'Iw': 118.744, 'Av': 3.5783, 'tw': 3.8, 'tf': 5.2, 'b': 46.0, 'h': 80.0, 'r': 5.0, 'family': 'IPE', 'mono': False},
    'IPE100': {'A': 10.3257, 'Wel': 34.2111, 'Wpl': 39.4172, 'Iy': 171.0553, 'Iz': 15.9193, 'It': 1.1574, 'Iw': 353.906, 'Av': 5.0874, 'tw': 4.1, 'tf': 5.7, 'b': 55.0, 'h': 100.0, 'r': 7.0, 'family': 'IPE', 'mono': False},
    'IPE120': {'A': 13.2127, 'Wel': 52.9697, 'Wpl': 60.7377, 'Iy': 317.8182, 'Iz': 27.6689, 'It': 1.6901, 'Iw': 894.236, 'Av': 6.3079, 'tw': 4.4, 'tf': 6.3, 'b': 64.0, 'h': 120.0, 'r': 7.0, 'family': 'IPE', 'mono': False},
    'IPE140': {'A': 16.4285, 'Wel': 77.3307, 'Wpl': 88.3593, 'Iy': 541.3148, 'Iz': 44.9185, 'It': 2.3995, 'Iw': 1989.3973, 'Av': 7.6448, 'tw': 4.7, 'tf': 6.9, 'b': 73.0, 'h': 140.0, 'r': 7.0, 'family': 'IPE', 'mono': False},
    'IPE160': {'A': 20.0954, 'Wel': 108.6862, 'Wpl': 123.888, 'Iy': 869.4896, 'Iz': 68.3162, 'It': 3.5406, 'Iw': 3977.1588, 'Av': 9.6614, 'tw': 5.0, 'tf': 7.4, 'b': 82.0, 'h': 160.0, 'r': 9.0, 'family': 'IPE', 'mono': False},
    'IPE180': {'A': 23.9514, 'Wel': 146.3569, 'Wpl': 166.4471, 'Iy': 1317.2125, 'Iz': 100.8522, 'It': 4.7264, 'Iw': 7459.0255, 'Av': 11.2554, 'tw': 5.3, 'tf': 8.0, 'b': 91.0, 'h': 180.0, 'r': 9.0, 'family': 'IPE', 'mono': False},
    'IPE200': {'A': 28.4914, 'Wel': 194.3721, 'Wpl': 220.7019, 'Iy': 1943.7208, 'Iz': 142.373, 'It': 6.9158, 'Iw': 13052.8495, 'Av': 14.0074, 'tw': 5.6, 'tf': 8.5, 'b': 100.0, 'h': 200.0, 'r': 12.0, 'family': 'IPE', 'mono': False},
    'IPE220': {'A': 33.3778, 'Wel': 252.0468, 'Wpl': 285.4761, 'Iy': 2772.5153, 'Iz': 204.891, 'It': 9.0306, 'Iw': 22761.6717, 'Av': 15.8886, 'tw': 5.9, 'tf': 9.2, 'b': 110.0, 'h': 220.0, 'r': 12.0, 'family': 'IPE', 'mono': False},
    'IPE240': {'A': 39.1276, 'Wel': 324.4062, 'Wpl': 366.7642, 'Iy': 3892.8739, 'Iz': 283.6449, 'It': 12.9535, 'Iw': 37577.3023, 'Av': 19.1552, 'tw': 6.2, 'tf': 9.8, 'b': 120.0, 'h': 240.0, 'r': 15.0, 'family': 'IPE', 'mono': False},
    'IPE270': {'A': 45.9564, 'Wel': 428.9927, 'Wpl': 484.1323, 'Iy': 5791.4019, 'Iz': 419.8799, 'It': 15.9031, 'Iw': 70850.5753, 'Av': 22.1496, 'tw': 6.6, 'tf': 10.2, 'b': 135.0, 'h': 270.0, 'r': 15.0, 'family': 'IPE', 'mono': False},
    'IPE300': {'A': 53.8234, 'Wel': 557.2097, 'Wpl': 628.5078, 'Iy': 8358.1448, 'Iz': 603.79, 'It': 19.9187, 'Iw': 126334.7483, 'Av': 25.6931, 'tw': 7.1, 'tf': 10.7, 'b': 150.0, 'h': 300.0, 'r': 15.0, 'family': 'IPE', 'mono': False},
    'IPE330': {'A': 62.6226, 'Wel': 713.36, 'Wpl': 804.5708, 'Iy': 11770.4392, 'Iz': 788.1645, 'It': 28.0624, 'Iw': 199882.9491, 'Av': 30.8251, 'tw': 7.5, 'tf': 11.5, 'b': 160.0, 'h': 330.0, 'r': 18.0, 'family': 'IPE', 'mono': False},
    'IPE360': {'A': 72.7456, 'Wel': 903.8811, 'Wpl': 1019.4097, 'Iy': 16269.8594, 'Iz': 1043.4751, 'It': 37.4401, 'Iw': 314652.8589, 'Av': 35.1536, 'tw': 8.0, 'tf': 12.7, 'b': 170.0, 'h': 360.0, 'r': 18.0, 'family': 'IPE', 'mono': False},
    'IPE400': {'A': 84.4858, 'Wel': 1156.7748, 'Wpl': 1307.5455, 'Iy': 23135.495, 'Iz': 1317.865, 'It': 51.2779, 'Iw': 492164.0919, 'Av': 42.7168, 'tw': 8.6, 'tf': 13.5, 'b': 180.0, 'h': 400.0, 'r': 21.0, 'family': 'IPE', 'mono': False},
    'IPE450': {'A': 98.843, 'Wel': 1500.0932, 'Wpl': 1702.2442, 'Iy': 33752.0967, 'Iz': 1675.9043, 'It': 66.7481, 'Iw': 794266.1961, 'Av': 50.8674, 'tw': 9.4, 'tf': 14.6, 'b': 190.0, 'h': 450.0, 'r': 21.0, 'family': 'IPE', 'mono': False},
    'IPE500': {'A': 115.5438, 'Wel': 1928.3977, 'Wpl': 2194.6215, 'Iy': 48209.9426, 'Iz': 2141.7331, 'It': 89.0973, 'Iw': 1254284.5935, 'Av': 59.8958, 'tw': 10.2, 'tf': 16.0, 'b': 200.0, 'h': 500.0, 'r': 21.0, 'family': 'IPE', 'mono': False},
    'IPE550': {'A': 134.4451, 'Wel': 2441.2566, 'Wpl': 2787.7293, 'Iy': 67134.5576, 'Iz': 2667.6588, 'It': 122.8143, 'Iw': 1893209.6718, 'Av': 72.3703, 'tw': 11.1, 'tf': 17.2, 'b': 210.0, 'h': 550.0, 'r': 24.0, 'family': 'IPE', 'mono': False},
    'IPE600': {'A': 156.0135, 'Wel': 3070.1671, 'Wpl': 3513.1908, 'Iy': 92105.0119, 'Iz': 3387.4213, 'It': 165.2115, 'Iw': 2858653.3015, 'Av': 83.8135, 'tw': 12.0, 'tf': 19.0, 'b': 220.0, 'h': 600.0, 'r': 24.0, 'family': 'IPE', 'mono': False},
    'HEA100': {'A': 21.2434, 'Wel': 72.7747, 'Wpl': 83.039, 'Iy': 349.3184, 'Iz': 133.8154, 'It': 5.2835, 'Iw': 2590.6659, 'Av': 7.5634, 'tw': 5.0, 'tf': 8.0, 'b': 100.0, 'h': 96.0, 'r': 12.0, 'family': 'HEA', 'mono': False},
    'HEA120': {'A': 25.3434, 'Wel': 106.368, 'Wpl': 119.523, 'Iy': 606.2973, 'Iz': 230.9008, 'It': 6.0412, 'Iw': 6486.0036, 'Av': 8.4634, 'tw': 5.0, 'tf': 8.0, 'b': 120.0, 'h': 114.0, 'r': 12.0, 'family': 'HEA', 'mono': False},
    'HEA140': {'A': 31.4234, 'Wel': 155.3894, 'Wpl': 173.534, 'Iy': 1033.3395, 'Iz': 389.3259, 'It': 8.1017, 'Iw': 15086.6231, 'Av': 10.1309, 'tw': 5.5, 'tf': 8.5, 'b': 140.0, 'h': 133.0, 'r': 12.0, 'family': 'HEA', 'mono': False},
    'HEA160': {'A': 38.7828, 'Wel': 220.1854, 'Wpl': 245.2172, 'Iy': 1673.4089, 'Iz': 615.5834, 'It': 12.0983, 'Iw': 31470.1642, 'Av': 13.2228, 'tw': 6.0, 'tf': 9.0, 'b': 160.0, 'h': 152.0, 'r': 15.0, 'family': 'HEA', 'mono': False},
    'HEA180': {'A': 45.2628, 'Wel': 293.6671, 'Wpl': 324.9327, 'Iy': 2510.8541, 'Iz': 924.6158, 'It': 14.8899, 'Iw': 60290.1534, 'Av': 14.4828, 'tw': 6.0, 'tf': 9.5, 'b': 180.0, 'h': 171.0, 'r': 15.0, 'family': 'HEA', 'mono': False},
    'HEA200': {'A': 53.8476, 'Wel': 388.7543, 'Wpl': 429.613, 'Iy': 3693.1662, 'Iz': 1335.5301, 'It': 21.0489, 'Iw': 108177.9387, 'Av': 18.0976, 'tw': 6.5, 'tf': 10.0, 'b': 200.0, 'h': 190.0, 'r': 18.0, 'family': 'HEA', 'mono': False},
    'HEA220': {'A': 64.3576, 'Wel': 515.3292, 'Wpl': 568.6004, 'Iy': 5410.9562, 'Iz': 1954.5821, 'It': 28.6143, 'Iw': 193508.5122, 'Av': 20.6876, 'tw': 7.0, 'tf': 11.0, 'b': 220.0, 'h': 210.0, 'r': 18.0, 'family': 'HEA', 'mono': False},
    'HEA240': {'A': 76.8578, 'Wel': 675.2362, 'Wpl': 744.8354, 'Iy': 7765.2159, 'Iz': 2768.8463, 'It': 42.1426, 'Iw': 328966.634, 'Av': 25.1978, 'tw': 7.5, 'tf': 12.0, 'b': 240.0, 'h': 230.0, 'r': 21.0, 'family': 'HEA', 'mono': False},
    'HEA260': {'A': 86.8485, 'Wel': 836.648, 'Wpl': 920.0726, 'Iy': 10458.1001, 'Iz': 3667.6243, 'It': 54.1937, 'Iw': 517192.3282, 'Av': 28.786, 'tw': 7.5, 'tf': 12.5, 'b': 260.0, 'h': 250.0, 'r': 24.0, 'family': 'HEA', 'mono': False},
    'HEA280': {'A': 97.2935, 'Wel': 1013.1142, 'Wpl': 1112.5525, 'Iy': 13677.0422, 'Iz': 4762.7045, 'It': 63.4562, 'Iw': 786429.6701, 'Av': 31.7735, 'tw': 8.0, 'tf': 13.0, 'b': 280.0, 'h': 270.0, 'r': 24.0, 'family': 'HEA', 'mono': False},
    'HEA300': {'A': 112.5646, 'Wel': 1259.9257, 'Wpl': 1383.7171, 'Iy': 18268.9233, 'Iz': 6309.6572, 'It': 87.7609, 'Iw': 1201611.1134, 'Av': 37.3146, 'tw': 8.5, 'tf': 14.0, 'b': 300.0, 'h': 290.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA320': {'A': 124.4046, 'Wel': 1479.6646, 'Wpl': 1628.5663, 'Iy': 22934.801, 'Iz': 6985.3395, 'It': 111.864, 'Iw': 1514600.5955, 'Av': 41.1696, 'tw': 9.0, 'tf': 15.5, 'b': 300.0, 'h': 310.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA340': {'A': 133.5096, 'Wel': 1678.8002, 'Wpl': 1850.9855, 'Iy': 27700.204, 'Iz': 7436.1026, 'It': 131.4054, 'Iw': 1827092.2399, 'Av': 44.9871, 'tw': 9.5, 'tf': 16.5, 'b': 300.0, 'h': 330.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA360': {'A': 142.7946, 'Wel': 1891.3049, 'Wpl': 2089.0167, 'Iy': 33097.8351, 'Iz': 7886.9495, 'It': 153.3421, 'Iw': 2179878.9142, 'Av': 48.9946, 'tw': 10.0, 'tf': 17.5, 'b': 300.0, 'h': 350.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA400': {'A': 159.0146, 'Wel': 2311.7732, 'Wpl': 2562.4102, 'Iy': 45079.5766, 'Iz': 8563.9403, 'It': 193.1714, 'Iw': 2946873.2635, 'Av': 57.3646, 'tw': 11.0, 'tf': 19.0, 'b': 300.0, 'h': 390.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA450': {'A': 178.0646, 'Wel': 2897.0372, 'Wpl': 3216.5631, 'Iy': 63734.8195, 'Iz': 9465.4478, 'It': 250.1091, 'Iw': 4154408.7028, 'Av': 65.8196, 'tw': 11.5, 'tf': 21.0, 'b': 300.0, 'h': 440.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA500': {'A': 197.5746, 'Wel': 3550.6678, 'Wpl': 3949.6371, 'Iy': 86991.3611, 'Iz': 10367.1726, 'It': 317.8154, 'Iw': 5652415.7483, 'Av': 74.7546, 'tw': 12.0, 'tf': 23.0, 'b': 300.0, 'h': 490.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA550': {'A': 211.7946, 'Wel': 4146.3985, 'Wpl': 4622.6861, 'Iy': 111952.7592, 'Iz': 10819.1701, 'It': 360.3556, 'Iw': 7201672.3608, 'Av': 83.7546, 'tw': 12.5, 'tf': 24.0, 'b': 300.0, 'h': 540.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEA600': {'A': 226.4946, 'Wel': 4787.5603, 'Wpl': 5351.343, 'Iy': 141233.0291, 'Iz': 11271.4399, 'It': 406.8806, 'Iw': 8995313.5022, 'Av': 93.2446, 'tw': 13.0, 'tf': 25.0, 'b': 300.0, 'h': 590.0, 'r': 27.0, 'family': 'HEA', 'mono': False},
    'HEB100': {'A': 26.0434, 'Wel': 89.9277, 'Wpl': 104.239, 'Iy': 449.6384, 'Iz': 167.277, 'It': 9.3309, 'Iw': 3387.3599, 'Av': 9.0434, 'tw': 6.0, 'tf': 10.0, 'b': 100.0, 'h': 100.0, 'r': 12.0, 'family': 'HEB', 'mono': False},
    'HEB120': {'A': 34.0134, 'Wel': 144.0864, 'Wpl': 165.2445, 'Iy': 864.5182, 'Iz': 317.5268, 'It': 13.9346, 'Iw': 9431.3396, 'Av': 10.9684, 'tw': 6.5, 'tf': 11.0, 'b': 120.0, 'h': 120.0, 'r': 12.0, 'family': 'HEB', 'mono': False},
    'HEB140': {'A': 42.9634, 'Wel': 215.6344, 'Wpl': 245.465, 'Iy': 1509.4408, 'Iz': 549.6718, 'It': 20.1567, 'Iw': 22514.5565, 'Av': 13.0834, 'tw': 7.0, 'tf': 12.0, 'b': 140.0, 'h': 140.0, 'r': 12.0, 'family': 'HEB', 'mono': False},
    'HEB160': {'A': 54.2628, 'Wel': 311.5542, 'Wpl': 354.0352, 'Iy': 2492.4333, 'Iz': 889.2473, 'It': 31.2736, 'Iw': 48039.3618, 'Av': 17.6028, 'tw': 8.0, 'tf': 13.0, 'b': 160.0, 'h': 160.0, 'r': 15.0, 'family': 'HEB', 'mono': False},
    'HEB180': {'A': 65.2628, 'Wel': 425.7445, 'Wpl': 481.5277, 'Iy': 3831.7002, 'Iz': 1362.8595, 'It': 42.2107, 'Iw': 93887.3922, 'Av': 20.2528, 'tw': 8.5, 'tf': 14.0, 'b': 180.0, 'h': 180.0, 'r': 15.0, 'family': 'HEB', 'mono': False},
    'HEB200': {'A': 78.0976, 'Wel': 569.7187, 'Wpl': 642.6755, 'Iy': 5697.187, 'Iz': 2003.3937, 'It': 59.7027, 'Iw': 171415.3752, 'Av': 24.8476, 'tw': 9.0, 'tf': 15.0, 'b': 200.0, 'h': 200.0, 'r': 18.0, 'family': 'HEB', 'mono': False},
    'HEB220': {'A': 91.0576, 'Wel': 735.6564, 'Wpl': 827.1904, 'Iy': 8092.2202, 'Iz': 2843.292, 'It': 77.0281, 'Iw': 295816.0995, 'Av': 27.9376, 'tw': 9.5, 'tf': 16.0, 'b': 220.0, 'h': 220.0, 'r': 18.0, 'family': 'HEB', 'mono': False},
    'HEB240': {'A': 106.0078, 'Wel': 938.4448, 'Wpl': 1053.3579, 'Iy': 11261.337, 'Iz': 3922.7034, 'It': 103.8833, 'Iw': 487680.299, 'Av': 33.2478, 'tw': 10.0, 'tf': 17.0, 'b': 240.0, 'h': 240.0, 'r': 21.0, 'family': 'HEB', 'mono': False},
    'HEB260': {'A': 118.4735, 'Wel': 1147.8901, 'Wpl': 1283.2132, 'Iy': 14922.5715, 'Iz': 5134.5879, 'It': 126.6737, 'Iw': 754864.6472, 'Av': 37.6235, 'tw': 10.0, 'tf': 17.5, 'b': 260.0, 'h': 260.0, 'r': 24.0, 'family': 'HEB', 'mono': False},
    'HEB280': {'A': 131.3935, 'Wel': 1376.7155, 'Wpl': 1534.7625, 'Iy': 19274.0169, 'Iz': 6594.5946, 'It': 146.0923, 'Iw': 1131698.3852, 'Av': 41.1235, 'tw': 10.5, 'tf': 18.0, 'b': 280.0, 'h': 280.0, 'r': 24.0, 'family': 'HEB', 'mono': False},
    'HEB300': {'A': 149.1146, 'Wel': 1678.0737, 'Wpl': 1869.1196, 'Iy': 25171.1051, 'Iz': 8562.942, 'It': 189.1784, 'Iw': 1690346.166, 'Av': 47.4646, 'tw': 11.0, 'tf': 19.0, 'b': 300.0, 'h': 300.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB320': {'A': 161.3796, 'Wel': 1926.8595, 'Wpl': 2149.7169, 'Iy': 30829.7518, 'Iz': 9238.9396, 'It': 230.4529, 'Iw': 2071837.9793, 'Av': 51.8071, 'tw': 11.5, 'tf': 20.5, 'b': 300.0, 'h': 320.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB340': {'A': 170.9346, 'Wel': 2156.6763, 'Wpl': 2408.6161, 'Iy': 36663.4972, 'Iz': 9690.0558, 'It': 262.8468, 'Iw': 2457452.6506, 'Av': 56.1246, 'tw': 12.0, 'tf': 21.5, 'b': 300.0, 'h': 340.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB360': {'A': 180.6696, 'Wel': 2400.0833, 'Wpl': 2683.5323, 'Iy': 43201.4992, 'Iz': 10141.2892, 'It': 298.3365, 'Iw': 2887890.5584, 'Av': 60.6321, 'tw': 12.5, 'tf': 22.5, 'b': 300.0, 'h': 360.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB400': {'A': 197.8146, 'Wel': 2884.5353, 'Wpl': 3232.3502, 'Iy': 57690.706, 'Iz': 10819.1695, 'It': 361.0278, 'Iw': 3823927.2717, 'Av': 70.0146, 'tw': 13.5, 'tf': 24.0, 'b': 300.0, 'h': 400.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB450': {'A': 218.0146, 'Wel': 3551.1446, 'Wpl': 3983.0656, 'Iy': 79900.7526, 'Iz': 11721.4602, 'It': 447.9744, 'Iw': 5268093.0838, 'Av': 79.6946, 'tw': 14.0, 'tf': 26.0, 'b': 300.0, 'h': 450.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB500': {'A': 238.6746, 'Wel': 4287.6948, 'Wpl': 4815.3471, 'Iy': 107192.3691, 'Iz': 12624.054, 'It': 548.1375, 'Iw': 7031093.0907, 'Av': 89.8546, 'tw': 14.5, 'tf': 28.0, 'b': 300.0, 'h': 500.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB550': {'A': 254.0946, 'Wel': 4971.3242, 'Wpl': 5591.4761, 'Iy': 136711.4152, 'Iz': 13077.0342, 'It': 610.1734, 'Iw': 8874108.0742, 'Av': 100.1046, 'tw': 15.0, 'tf': 29.0, 'b': 300.0, 'h': 550.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'HEB600': {'A': 269.9946, 'Wel': 5702.201, 'Wpl': 6426.093, 'Iy': 171066.0291, 'Iz': 13530.3846, 'It': 677.1262, 'Iw': 10990054.8792, 'Av': 110.8446, 'tw': 15.5, 'tf': 30.0, 'b': 300.0, 'h': 600.0, 'r': 27.0, 'family': 'HEB', 'mono': False},
    'UPN80': {'A': 11.0246, 'Wel': 26.4845, 'Wpl': 31.9014, 'Iy': 105.938, 'Iz': 19.3553, 'It': 1.9968, 'Iw': 0.0, 'Av': 4.608, 'tw': 6.0, 'tf': 8.0, 'b': 45.0, 'h': 80.0, 'r': 8.0, 'family': 'UPN', 'mono': True},
    'UPN100': {'A': 13.4692, 'Wel': 41.0925, 'Wpl': 49.0087, 'Iy': 205.4623, 'Iz': 28.9734, 'It': 2.6447, 'Iw': 0.0, 'Av': 5.976, 'tw': 6.0, 'tf': 8.5, 'b': 50.0, 'h': 100.0, 'r': 9.0, 'family': 'UPN', 'mono': True},
    'UPN120': {'A': 16.9716, 'Wel': 60.642, 'Wpl': 72.6157, 'Iy': 363.852, 'Iz': 42.8167, 'It': 3.8392, 'Iw': 0.0, 'Av': 8.568, 'tw': 7.0, 'tf': 9.0, 'b': 55.0, 'h': 120.0, 'r': 9.0, 'family': 'UPN', 'mono': True},
    'UPN140': {'A': 20.3716, 'Wel': 86.409, 'Wpl': 102.7829, 'Iy': 604.8632, 'Iz': 62.4765, 'It': 5.372, 'Iw': 0.0, 'Av': 10.08, 'tw': 7.0, 'tf': 10.0, 'b': 60.0, 'h': 140.0, 'r': 10.0, 'family': 'UPN', 'mono': True},
    'UPN160': {'A': 24.0342, 'Wel': 115.6624, 'Wpl': 137.646, 'Iy': 925.2993, 'Iz': 84.6462, 'It': 6.9711, 'Iw': 0.0, 'Av': 12.51, 'tw': 7.5, 'tf': 10.5, 'b': 65.0, 'h': 160.0, 'r': 11.0, 'family': 'UPN', 'mono': True},
    'UPN180': {'A': 27.9474, 'Wel': 150.2874, 'Wpl': 178.959, 'Iy': 1352.5865, 'Iz': 112.9896, 'It': 8.9079, 'Iw': 0.0, 'Av': 15.168, 'tw': 8.0, 'tf': 11.0, 'b': 70.0, 'h': 180.0, 'r': 11.0, 'family': 'UPN', 'mono': True},
    'UPN200': {'A': 32.2293, 'Wel': 191.3937, 'Wpl': 228.1202, 'Iy': 1913.937, 'Iz': 147.7637, 'It': 11.2277, 'Iw': 0.0, 'Av': 18.054, 'tw': 8.5, 'tf': 11.5, 'b': 75.0, 'h': 200.0, 'r': 12.0, 'family': 'UPN', 'mono': True},
    'UPN220': {'A': 37.4683, 'Wel': 244.7844, 'Wpl': 291.6817, 'Iy': 2692.6285, 'Iz': 195.116, 'It': 15.1552, 'Iw': 0.0, 'Av': 21.06, 'tw': 9.0, 'tf': 12.5, 'b': 80.0, 'h': 220.0, 'r': 13.0, 'family': 'UPN', 'mono': True},
    'UPN240': {'A': 42.2857, 'Wel': 299.6709, 'Wpl': 357.425, 'Iy': 3596.0512, 'Iz': 246.5188, 'It': 18.5656, 'Iw': 0.0, 'Av': 24.396, 'tw': 9.5, 'tf': 13.0, 'b': 85.0, 'h': 240.0, 'r': 13.0, 'family': 'UPN', 'mono': True},
    'UPN260': {'A': 48.2861, 'Wel': 371.1227, 'Wpl': 442.445, 'Iy': 4824.5948, 'Iz': 317.2261, 'It': 24.1973, 'Iw': 0.0, 'Av': 27.84, 'tw': 10.0, 'tf': 14.0, 'b': 90.0, 'h': 260.0, 'r': 14.0, 'family': 'UPN', 'mono': True},
    'UPN280': {'A': 53.3962, 'Wel': 447.977, 'Wpl': 531.6454, 'Iy': 6271.6778, 'Iz': 396.8833, 'It': 29.7083, 'Iw': 0.0, 'Av': 30.0, 'tw': 10.0, 'tf': 15.0, 'b': 95.0, 'h': 280.0, 'r': 15.0, 'family': 'UPN', 'mono': True},
    'UPN300': {'A': 58.7671, 'Wel': 535.2235, 'Wpl': 632.4207, 'Iy': 8028.3525, 'Iz': 493.0834, 'It': 36.24, 'Iw': 0.0, 'Av': 32.16, 'tw': 10.0, 'tf': 16.0, 'b': 100.0, 'h': 300.0, 'r': 16.0, 'family': 'UPN', 'mono': True},
}


# ------- Backward-compat : ancien sous-ensemble (clés utilisées par les tests/anciens appels) -------
def _legacy_subset():
    keys = ("A", "Wel", "Wpl", "Iy", "Iz", "It", "Iw", "Av", "tw", "tf", "b", "h", "r")
    return {name: {k: props[k] for k in keys} for name, props in PROFILE_DATA.items()}


def families() -> dict:
    out: dict[str, list[str]] = {}
    for name, p in PROFILE_DATA.items():
        out.setdefault(p["family"], []).append(name)
    return out


def epsilon(fy_mpa: float) -> float:
    return math.sqrt(235.0 / fy_mpa)


def _class_from_ratio(ratio: float, limits: tuple[float, float, float], eps: float) -> int:
    l1, l2, l3 = (x * eps for x in limits)
    if ratio <= l1:
        return 1
    if ratio <= l2:
        return 2
    if ratio <= l3:
        return 3
    return 4


def classify(name: str, fy_mpa: float, state: str = "bending") -> dict:
    """Classe de section EN 1993-1-1 Table 5.2 (banzo comprimé + âme selon l'état).

    state : "bending" (âme en flexion, poutres) ou "compression" (âme comprimée, poteaux).
    """
    p = PROFILE_DATA[name]
    b, tw, tf, h, r = p["b"], p["tw"], p["tf"], p["h"], p["r"]
    eps = epsilon(fy_mpa)
    if p["family"] == "UPN":
        c_flange = b - tw - r          # aile de U : console complète
    else:
        c_flange = b / 2.0 - tw / 2.0 - r
    c_web = h - 2 * tf - 2 * r
    ratio_f = c_flange / tf
    ratio_w = c_web / tw
    cls_f = _class_from_ratio(ratio_f, FLANGE_LIMITS, eps)
    web_limits = WEB_COMPRESSION_LIMITS if state == "compression" else WEB_BENDING_LIMITS
    cls_w = _class_from_ratio(ratio_w, web_limits, eps)
    return {"section_class": max(cls_f, cls_w), "flange_class": cls_f, "web_class": cls_w,
            "c_tf_ratio": round(ratio_f, 2), "c_tw_ratio": round(ratio_w, 2),
            "epsilon": round(eps, 3), "state": state, "governed_by": "âme" if cls_w >= cls_f else "banzo"}


def buckling_curves(name: str, fy_mpa: float) -> dict:
    """Courbes de flambement EN 1993-1-1 Table 6.2 (sections laminées, acier ≤ S355)."""
    p = PROFILE_DATA[name]
    if p["family"] == "UPN":
        return {"y": "c", "z": "c", "lt": "c"}  # profilés en U
    hb = p["h"] / p["b"]
    tf = p["tf"]
    if tf <= 40:
        y, z = ("a", "b") if hb > 1.2 else ("b", "c")
    else:  # 40 < tf ≤ 100 mm
        y, z = ("b", "c") if hb > 1.2 else ("c", "d")
    lt = "a" if hb <= 2.0 else "b"  # déversement, sections laminées (Table 6.4)
    return {"y": y, "z": z, "lt": lt}


def catalog_rows() -> list[dict]:
    rows = []
    for name, p in PROFILE_DATA.items():
        rows.append({"key": name, "family": p["family"], "mono": p["mono"],
                     **{k: p[k] for k in ("A", "Wel", "Wpl", "Iy", "Iz", "It", "Iw", "Av", "tw", "tf", "b", "h", "r")}})
    return rows
