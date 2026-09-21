# Etikettmodell från PipeStudio

`pipestudio-labels.onnx` är hämtad från den PipeStudio-kodbas som följde med uppdraget.
SHA-256: `3b3a97a0c047bf116b7fe9a90d523ccf5240801e56c0aac1bbd6f4cfae3b4bb8`.

Ingen ny modell har tränats. Installera valfria beroenden från
`backend/requirements-ml.txt` och sätt `VVS_LABEL_AUDIT=true` för lokala etikettförslag.
Modellen är avstängd som standard och får inte tilldela rörbeteckningar eller ändra mängder.
Förslagen visas separat för granskning; vektorgeometri och läst ritningstext ligger till grund för mängdningen.
