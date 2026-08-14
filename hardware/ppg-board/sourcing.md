# Sourcing reality check — JLCPCB / LCSC

Queried live against the JLC catalogue on **2026-08-10**. Stock and price move; re-check before
ordering. Price is USD unit price at the quantity tier the catalogue reports.

This file exists because the obvious design (bare MAX30102) turned out to be **unsourceable**,
and that single fact drove the architecture away from an integrated AFE toward a discrete
front end. Recording the evidence so the decision is auditable later.

## Integrated PPG AFEs — all bad options

| Part | LCSC | Lib | Stock | Unit $ | Package | Verdict |
|---|---|---|---|---|---|---|
| MAX30102EFD+T | C6454833 | Extended | **6** | 11.61 | OESIP-14 | Dead. No stock, absurd price. |
| MAX30101EFD+T | C2859066 | Extended | 843 | 10.57 | OLGA-14 (3.3×5.6) | Stocked but £8+ and an optical package that is unpleasant to hand-place. |
| MAX86141ENP+T | C5328762 | Extended | 18 | 4.72 | **WLP-20 (2×1.8)** | Wafer-level. Not hand-solderable, not reworkable, 18 in stock. |
| AFE4404YZPR | C486038 | Extended | **1** | 3.53 | DSBGA-15 | Dead. |
| AFE4490RHAR | C2651608 | Extended | 58 | 11.36 | VQFN-40 (6×6) | Solderable on a hot plate, but £9 and needs external LEDs + PD anyway. |
| MAX30105 / MAX30100 / ADPD105 / ADPD144RI | — | — | — | — | — | Not in catalogue at all. |

**Conclusion:** every integrated AFE is either out of stock, unsolderable by hand, or costs more
than the entire rest of the board. The "just use a MAX30102" default is not actually available.

## Discrete front end — cheap, abundant, and better

| Function | Part | LCSC | Lib | Stock | Unit $ | Package |
|---|---|---|---|---|---|---|
| 24-bit ADC | ADS1256IDBR | C28186 | Extended | 2 865 | 5.37 | SSOP-28 (easy to solder) |
| 16-bit ADC | ADS1115IDGST | C468683 | Extended | 220 | 1.16 | VSSOP-10 0.5 mm |
| 18-bit ADC | MCP3421A0T-E/CH | C29454 | Extended | 26 380 | 1.29 | SOT-23-6 |
| Zero-drift TIA | OPA333AIDBVR | C30878 | Extended | 12 669 | 0.42 | SOT-23-5 |
| Precision TIA | OPA381AIDGKT | C92496 | Extended | 38 | 1.63 | VSSOP-8 (low stock) |
| General op-amp | MCP6002T-I/SN | C7377 | **PREFERRED** | 40 631 | 0.24 | SOIC-8 |
| Rail-rail op-amp | TLV9001IDBVR | C398363 | Extended | 11 222 | 0.09 | SOT-23-5 |

A discrete chain (LEDs + photodiode + TIA + ADC) costs **under $8** and every part is in stock in
quantity. It is cheaper *and* better sourced than any integrated AFE, and it is the only path that
lets us choose our own wavelengths.

## Emitters — the isosbestic question

The hemoglobin isosbestic point (where HbO2 and Hb have equal molar extinction, so absorbance
tracks **total** Hb independent of saturation) sits near **805–810 nm**.

| Wavelength | Part | LCSC | Stock | Unit $ | Package | Note |
|---|---|---|---|---|---|---|
| 660 + 850 **dual-die** | CT-3030SUR660/850C-PT | C53191416 | 4 911 | 0.14 | SMD3030-4P | Two wavelengths, **one package, matched optical geometry** |
| ~810 | JNJ-L-3535AW30-81042-SL-G1 | C25170639 | 45 | 1.00 | SMD3535-3P | Genuine ~810 nm. **Low stock.** |
| ~810 | JNJ-L-3535AW30-80530-SL-J2-D3 | C22447934 | 307 | 0.98 | SMD3535-3P | Better stock, verify exact peak λ on datasheet |
| 850 | XL-2012HIRC-850 | C965888 | 17 716 | 0.03 | 0805 | Abundant fallback |
| 940 | IR17-21C/TR8 | C131250 | 10 113 | 0.05 | 0805 | Abundant |

⚠️ **Search trap:** querying "805nm LED" returns `JNJ-L-2835CW-80514` and similar — those are
**cool-white** LEDs where `805`/`8051` is a CCT/CRI bin code, *not* a wavelength. Do not order them.
True ~810 nm emitters are the 3535 IR parts above, and they are scarce and ~20× the price of a
commodity 850 nm part.

## ADC — the decision, and a near-miss worth recording

The design initially converged on the MCP3564R. Live catalogue checks killed it:

| Part | LCSC | Stock | Unit $ | Note |
|---|---|---|---|---|
| MCP3564RT-E/ST | C5227404 | **22** | 8.80 | One other customer's order from zero |
| MCP3564-E/ST | C1012816 | 99 | 10.40 | ⚠️ **No internal reference** — the non-R part |
| MCP3561-E/ST | C1012815 | 48 | 6.24 | |
| MCP3561RT-E/ST | C1518045 | **1** | 5.24 | |
| **ADS131M02IPWR** | **C2922448** | **7 481** | **3.65** | **CHOSEN** — TSSOP-20, hand-solderable |
| ADS131M02IRUKR | C5215160 | 10 121 | 2.50 | WQFN-20, cheaper but harder to hand-solder |
| ADS1220IPWR | C48263 | 19 199 | 1.82 | Fallback: 24-bit but only 2 kSPS |
| REF3325AIDBZR | C69039 | 10 587 | 0.60 | Not needed — ADS131M02 has an internal reference |

Two traps avoided. The "three pin-compatible variants are a stock hedge" argument was **false** —
MCP3561/3562 are effectively dry. And the similarly-named `MCP3564-E/ST` is well stocked but has
**no internal voltage reference**: ordering it by name off a BOM line reading "MCP3564" would give
a board whose converter never produces a valid reading, for a one-character difference.

The ADS131M02 also turned out to be the *better* part on merit, not just on stock: its **two
simultaneously-sampling 24-bit channels (64 kSPS)** let both photodiodes read the same LED pulse,
so LED output drift cancels in the far/near ratio. It also runs natively on 2.7–3.6 V, where the
ADS1256 alternative needs a 5 V analog supply — that would have forced a boost converter and put
switching noise straight into the optical measurement. That capability is what the whole spatially-resolved
measurement rests on. Caveat: it needs an external CLKIN (~8.192 MHz), sourced from an ESP32-S3
LEDC PWM.

## Photodiodes

| Part | LCSC | Stock | Unit $ | Package | Note |
|---|---|---|---|---|---|
| VEMD5010X01 | C3151612 | 2 307 | 0.66 | SMD-4P 5×4 mm | Large active area — best signal |
| VEMD2020X01 | C3210968 | 6 892 | 0.47 | SMD | Smaller, cheaper |
| VEMD8081 | C3001848 | 5 924 | 0.68 | SMD-8P | Wide angle |
| VEMD10940FX01 | C7104273 | 2 200 | 0.30 | SMD | 940 nm-filtered — **rejects ambient**, but blocks 660 nm |

## Power and support parts — all abundant

| Function | Part | LCSC | Lib | Stock | Unit $ | Package |
|---|---|---|---|---|---|---|
| 3V3 LDO | XC6206P332MR-G | C5446 | **BASIC** | 829 905 | 0.095 | SOT-23-3 |
| 3V3 LDO (better PSRR) | TLV75533PDBVR | C404027 | Extended | 30 147 | 0.19 | SOT-23-5 |
| LiPo charger | TP4056-42-ESOP8 | C16581 | **PREFERRED** | 105 363 | 0.19 | ESOP-8 |
| LiPo charger (alt) | MCP73831T-2ACI/OT | C424093 | Extended | 2 727 | 0.87 | SOT-23-5 |
| USB ESD | USBLC6-2SC6 | C2687116 | Extended | 231 248 | 0.035 | SOT-23-6 |
| N-MOSFET | AO3400A | C20917 | **BASIC** | 1 345 927 | 0.067 | SOT-23-3 |

## MCU

| Part | LCSC | Stock | Unit $ | Note |
|---|---|---|---|---|
| ESP32-C3-MINI-1-N4 | C2838502 | 16 416 | 2.79 | 4 MB flash, RISC-V single core |
| ESP32-S3-MINI-1-N8 | C2913206 | 7 105 | 4.68 | 8 MB flash, vector DSP instructions for on-device inference |

## Standing notes

- **Nothing** in the analog chain is a JLC *Basic* part, so JLCPCB assembly would incur the
  per-part loading fee on most of the BOM. Hand assembly is assumed; every chosen package is
  hand-solderable (SOT-23, SOIC, SSOP, 0805) by design.
- Re-run `scratchpad/jlcverify.py <term>` to refresh. It queries the jlcsearch JSON mirror via
  curl (this Mac's Python has no CA bundle configured, so `urllib` fails TLS verification).
