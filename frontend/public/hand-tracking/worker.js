/* MediaPipe runs off the UI thread. Frames never leave this origin. */
importScripts('/hand-tracking/vision_bundle.js');
let detector;
self.onmessage = async ({ data }) => {
  try {
    if (data.type === 'init') {
      const files = await Vision.FilesetResolver.forVisionTasks('/hand-tracking/wasm');
      detector = await Vision.HandLandmarker.createFromOptions(files, {
        baseOptions: { modelAssetPath: '/hand-tracking/hand_landmarker.task', delegate: 'CPU' },
        runningMode: 'VIDEO', numHands: 2,
        minHandDetectionConfidence: 0.65, minHandPresenceConfidence: 0.65, minTrackingConfidence: 0.65
      });
      self.postMessage({ type: 'ready' });
    } else if (data.type === 'frame' && detector) {
      try {
        const result = detector.detectForVideo(data.image, data.time);
        self.postMessage({ type: 'hands', landmarks: result.landmarks, time: data.time });
      } finally { data.image.close(); }
    }
  } catch (_) { self.postMessage({ type: 'error' }); }
};
