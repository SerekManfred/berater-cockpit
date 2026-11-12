// Fachliche Festwerte, die (noch) nicht im Konditionen-Datensatz stehen.
// Sie ändern sich selten, gehören aber mittelfristig in die Konditionen-Zentrale (Phase 1b).
module.exports = {
  stand: "2026-11-09",
  quelle_tma_em: "Technische Mindestanforderungen BEG EM (BAFA), Stand 2026",
  quelle_eh: "BEG WG, Technische Mindestanforderungen Effizienzhaus (KfW)",

  // U-Wert-Anforderungen BEG EM je Bauteil
  tma_em: [
    ["Außenwand", "U ≤ 0,20 W/(m²K)"],
    ["Dach, Dachschräge", "U ≤ 0,14 W/(m²K)"],
    ["Oberste Geschossdecke", "U ≤ 0,14 W/(m²K)"],
    ["Bodenflächen gegen Erdreich / unbeheizt, Kellerdecke", "U ≤ 0,25 W/(m²K)"],
    ["Fenster, Fenstertüren", "Uw ≤ 0,95 W/(m²K)"],
    ["Lüftung mit Wärmerückgewinnung", "Wärmebereitstellungsgrad ≥ 80 % bei ≤ 0,45 W/(m³/h) bzw. ≥ 75 % bei ≤ 0,35 W/(m³/h)"],
  ],

  // Effizienzhaus-Stufen: Primärenergiebedarf Qp und Transmissionsverlust H'T in % des Referenzgebäudes
  eh_stufen: {
    EH40EE: { name: "Effizienzhaus 40 EE", qp: 40, ht: 55 },
    EH55EE: { name: "Effizienzhaus 55 EE", qp: 55, ht: 70 },
    EH70EE: { name: "Effizienzhaus 70 EE", qp: 70, ht: 85 },
    EH85EE: { name: "Effizienzhaus 85 EE", qp: 85, ht: 100 },
    DenkmalEE: { name: "Effizienzhaus Denkmal EE", qp: 160, ht: 175 },
  },

  ee_klasse: "EE-Klasse: mindestens 65 % des Wärmebedarfs aus erneuerbaren Energien, unvermeidbarer Abwärme und/oder Wärmerückgewinnung aus Lüftungsanlagen",

  kumulierung: [
    ["KfW 266 + BEG EM (BAFA)", true, "Umbaukosten nur in KfW 266, energetische Kosten nur in BEG EM"],
    ["KfW 266 + BEG WG (KfW 261)", true, "Ausdrücklich vorgesehen; keine Doppelanrechnung derselben Kosten"],
    ["BEG EM + BEG WG", false, "Ausgeschlossen; Sperrfrist 3 Jahre in beide Richtungen"],
    ["BEG EM + Ergänzungskredit 358/359", true, "Kredit zusätzlich zum Zuschuss"],
    ["BEG + § 35c EStG (gleiche Maßnahme)", false, "Steuerbonus nur für nicht geförderte Maßnahmen selbstgenutzter Wohnungen"],
    ["KfW 266 + § 35a EStG", false, "Laut Merkblatt 266 ausgeschlossen"],
  ],

  haftung: "Alle Angaben nach bestem Wissen auf Basis der zum angegebenen Stand gültigen Förderbedingungen, ohne Gewähr. Fördermittel stehen unter Haushaltsvorbehalt. Maßgeblich sind die zum Zeitpunkt der Antragstellung gültigen Richtlinien, Merkblätter und die Bestätigung durch KfW/BAFA.",
};
