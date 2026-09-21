/* Färgerna en beteckning har i hela produkten.
 *
 * Ett rör ska se likadant ut var det än visas: markerat på bladet, som prick i mängdtabellen, rest i 3D. Därför
 * bor paletten här och inte i den vy som råkade behöva den först. Nyckeln är beteckningen, inte identiteten:
 * ett och samma rörnamn har en enda färg även när bladet skriver ut dimensionen på ett ställe och utelämnar den
 * på ett annat, så att ett rör aldrig byter färg mitt i sin egen sträckning. Dimensionen står i tabellens
 * DN-kolumn, den behöver inte sägas en gång till med färg. Ingen färg är så mörk att den läses som ritningens
 * eget svarta streck.
 */
const PALETTE = ["#0d9a1a", "#0059e6", "#d91a1a", "#8c00b3", "#009999", "#cc7300", "#4d4de6", "#99591a",
                 "#e6007f", "#1a734d", "#808000", "#73bf00"];

/** Beteckningen ur en identitetsnyckel: `VS1-S13|DN22` och `VS1-S13|DN?` är samma namn och samma färg. */
export function colorKey(key: string): string {
  const cut = key.indexOf("|DN");
  return cut < 0 ? key : key.slice(0, cut);
}

export function identityColor(key: string): string {
  const name = colorKey(key);
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}
