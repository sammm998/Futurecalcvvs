# Lokal handstyrning

MediaPipe Tasks Vision 1.0.1, Google, Apache-2.0.
JavaScript och WASM kopieras oförändrade från npm-paketet @mediapipe/tasks-vision.
Officiell handmodell: https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
Dokumentation och modellkort: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker

Kamerabilder analyseras i en lokal worker. Inga bilder skickas av handdetektorn.
Version och SHA-256 finns i manifest.json. Endast uttrycklig bilddelning i samtalspanelen skickar en kamerabild till OpenAI.
