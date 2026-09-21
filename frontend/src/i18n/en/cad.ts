/* CAD-rummen: mängdningsverktyget och byggmodellen
 *
 * En rad per sträng, svensk nyckel först. Saknas en rad visas svenskan.
 */
export const cad: Record<string, string> = {
  "Samlat resultat": "Combined result",
  "Förgreningar avstämda mot beteckningskontakter": "Branches reconciled with designation contacts",
  "En modellbekräftad huvudledning följs till nästa faktiska beteckningskontakt.": "A model-confirmed main continues to the next actual designation contact.",
  "Modellbedömningen har även granskat bilder av originalritningen.": "The model assessment also examined images of the original drawing.",
  "Regelkälla: PipeStudio och Swedish VVS. Ritningens egenskaper bedöms automatiskt. När ingen känd stil passar används generella regler och ritningens egna hänvisningar. Osäkra sträckor visas för granskning.": "Rule sources: PipeStudio and Swedish VVS. Drawing properties are assessed automatically. Unknown styles use general rules and the drawing's own references. Uncertain stretches remain available for review.",
  "Samlad röranalys": "Combined pipe analysis",
  "Analysera ritningen": "Analyze drawing",
  "Dimensionsregler och modellbedömning tillsammans": "Dimension rules and model assessment together",
  "Dimensionsförslag granskas av modellen med ritningens hänvisningar, topologi och stilregler. Obekräftade förslag kräver granskning.": "The model checks dimension proposals against drawing references, topology and style rules. Unconfirmed proposals require review.",
  "Oidentifierad rörgeometri utanför skrafferade områden": "Unidentified pipe geometry outside hatched areas",
  "Oidentifierad rörgeometri inom skrafferade områden": "Unidentified pipe geometry inside hatched areas",
  "Skrafferad geometri undantas enligt källreglerna. Detta verifierar inte hela ritningens träffsäkerhet.": "Hatched geometry is excluded by the source rules. This does not verify accuracy across the whole drawing.",
  "Automatiskt föreslagen": "Automatically suggested",
  "Vald manuellt": "Selected manually",
  "Regelkälla: PipeStudio och Swedish VVS. Vald stils regler används i modellbedömningen. Kontrollera stilvalet och rörens utbredning innan mängderna används.": "Rule sources: PipeStudio and Swedish VVS. The selected style's rules are used in model assessment. Check the style and pipe extents before using the quantities.",
  "Alla rör i märkta rörbuntar har inte hittats": "Some pipes in labelled bundles have not been found",
  "rör kopplade till beteckningen": "pipes linked to the designation",
  "Saknade rör räknas inte fram genom att multiplicera längden. Kontrollera bunten på ritningen.": "Missing pipes are not estimated by multiplying the length. Check the bundle on the drawing.",

  // --- blad, nivåer och vyer ------------------------------------------------------------------------------
  "Fil ▾": "File ▾",
  "+ Blad": "+ Sheet",
  "Nytt blad": "New sheet",
  "Inga egna blad ännu. Börja med ett tomt här ovanför.": "No sheets of your own yet. Start with an empty one above.",
  "Nivåer": "Levels",
  "Kopiera nivåns objekt till nivån ovanför": "Copy the level's objects to the level above",
  "Sektion A-A": "Section A-A",
  "Snittlinje y": "Section line y",
  "Ingenting i snittet.": "Nothing in the section.",
  "Fasad i stället": "Elevation instead",
  "Genomskinlighet i 3D": "Transparency in 3D",
  "Tråd": "Wireframe",
  "Visa PDF": "Show the PDF",
  "utskriven ritning": "printed drawing",
  "Öppna →": "Open →",
  "Mängda bladet →": "Take off the sheet →",
  "Inga revisioner än.": "No revisions yet.",
  "Källa": "Source",
  "Listan som CSV": "The list as CSV",

  // --- rita -----------------------------------------------------------------------------------------------
  "Ångra (Ctrl+Z)": "Undo (Ctrl+Z)",
  "Gör om (Ctrl+Y)": "Redo (Ctrl+Y)",
  "Ångra ritningen": "Undo the drawing",
  "Fångst": "Snap",
  "Fångst (F3)": "Snap (F3)",
  "Ortho (F8)": "Ortho (F8)",
  "Två punkter": "Two points",
  "Rektangulär": "Rectangular",
  "Cirkulär": "Circular",
  "Vänster": "Left",
  "Höger": "Right",
  "Lägg in": "Insert",
  "Skapa ett": "Create one",
  "höjd i mm": "height in mm",
  "– fri text –": "– free text –",
  "EI 60": "EI 60",
  "Disciplin att rita i": "Discipline to draw in",
  "pump, LA, WC…": "pump, AHU, WC…",

  // --- kollisioner och förslag ----------------------------------------------------------------------------
  "Inga kollisioner.": "No clashes.",
  "Godkänn": "Approve",
  "Godkänn alla": "Approve all",
  "Sök igen": "Search again",
  "Rita en fråga": "Draw a question",
  "Vad gäller frågan?": "What is the question about?",
  "t.ex. rita en vägg från (0,0) till (0,6000), 200 tjock, på Plan 0":
    "e.g. draw a wall from (0,0) to (0,6000), 200 thick, on Level 0",

  // --- import och mängder ---------------------------------------------------------------------------------
  "Ur en läst handling…": "From a read document set…",
  "Det som går att förstå blir byggobjekt, resten streck. DWG stöds inte - spara som DXF eller IFC.":
    "What can be understood becomes building objects, the rest strokes. DWG is not supported - save as DXF or IFC.",
  "Ur modellens egna mått. Servern räknar samma tal för exporten och kalkylen.":
    "From the model's own dimensions. The server computes the same numbers for the export and the costing.",
};
