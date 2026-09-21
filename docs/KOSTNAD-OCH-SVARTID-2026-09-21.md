# Kostnad och svarstid

Identiska modellförfrågningar inom samma analys delar nu ett pågående eller färdigt svar. Nyckeln omfattar hela begäran: modell, instruktioner, ritningsbilder, stilobservationer, svarsschema och resonemangsinställning. Ändrat underlag gör ett nytt anrop. Misslyckade svar återanvänds inte. Cachen delas inte mellan analyser eller användare.

Modellval, bildupplösning, granskningssteg och svarslängd är oförändrade. Återanvända svar räknas med noll nya token och markeras request_reused. Leverantörens rapporterade cached_tokens sparas separat. Besparingen beror på hur många identiska anrop som faktiskt uppstår; inga procenttal eller kronbelopp är verifierade ännu. En första unik begäran kostar lika mycket som tidigare.

19 riktade tester godkända för samtidiga anrop, ändrade underlag, fel och transportens cacheisolering.

Serverns senaste långsamma körning före uppdateringen tog cirka nio minuter och avbröts av OOM i REVIEWING ocr. Den tiden beskriver en misslyckad körning, inte normal svarstid. OCR-ändringen begränsar bildrutor och igenkänningsbatchar samt släpper sessioner. Ett lokalt fullständigt driftprov med OCR tog 174 sekunder och cirka 727 MB maximal RSS, men OCR-budgeten tog slut efter 31 av 48 rutor och rapporterades som partiell. Detta är inte en verifiering av full täckning eller av Railways minnesgräns.
