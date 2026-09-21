import { useEffect, useRef, useState } from 'react';
import { HandGestures, pinchedHands, type Motion } from './gestures';

export default function HandCamera({ onMotion, onImage }: { onMotion: (m: Motion) => void; onImage: (url: string) => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [active, setActive] = useState(false), [ready, setReady] = useState(false), [err, setErr] = useState('');
  const [hands, setHands] = useState(0), [pinches, setPinches] = useState(0);
  const callback = useRef(onMotion); callback.current = onMotion;
  useEffect(() => {
    if (!active) return;
    let cancelled = false, stream: MediaStream | null = null, worker: Worker | null = null;
    let timer = 0, waiting = false;
    const gestures = new HandGestures();
    const stop = () => { cancelled = true; window.clearInterval(timer); worker?.terminate(); stream?.getTracks().forEach(t => t.stop()); if (video.current) video.current.srcObject = null; };
    const start = async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return; }
        video.current!.srcObject = stream; await video.current!.play();
        if (cancelled) return;
        worker = new Worker('/hand-tracking/worker.js');
        worker.onerror = () => { setErr('Handmodellen kunde inte starta.'); stop(); setActive(false); };
        worker.onmessage = ({ data }) => {
          if (cancelled) return;
          if (data.type === 'ready') {
            setReady(true);
            timer = window.setInterval(async () => {
              if (document.hidden || !video.current || video.current.readyState < 2) { gestures.reset(); return; }
              // An in-flight inference is not loss of tracking. Resetting here
              // erased every movement on cameras/CPUs slower than this timer.
              if (waiting) return;
              waiting = true;
              try {
                const image = await createImageBitmap(video.current);
                if (cancelled) { image.close(); return; }
                worker!.postMessage({ type: 'frame', image, time: performance.now() }, [image]);
              } catch { waiting = false; gestures.reset(); }
            }, 65);
          } else if (data.type === 'hands') {
            waiting = false;
            setHands(data.landmarks.length); setPinches(pinchedHands(data.landmarks).length);
            const motion = gestures.update(data.landmarks, data.time);
            if (motion && !document.hidden) callback.current(motion);
          } else if (data.type === 'error') { setErr('Handmodellen kunde inte läsa kameran.'); stop(); setActive(false); }
        };
        worker.postMessage({ type: 'init' });
      } catch { stop(); setErr('Kameran kunde inte öppnas. Kontrollera kamerabehörigheten.'); setActive(false); }
    };
    void start();
    return stop;
  }, [active]);
  return <div className="live-camera">
    <button className="secondary small" onClick={() => { setErr(''); setReady(false); setActive(!active); }}>{active ? 'Stäng kamera' : 'Starta handstyrning'}</button>
    {active && <>
      <video ref={video} muted playsInline className="hand-preview" />
      <small>{ready ? 'Nyp med en hand och dra för att flytta. Nyp med båda och sära för att zooma. Släpp för att stanna.' : 'Laddar handmodellen…'}</small>
      {ready && <small role="status">{hands} händer upptäckta · {pinches === 2 ? 'Zoom aktiv' : pinches === 1 ? 'Förflyttning aktiv' : 'Nyp ihop tumme och pekfinger för att styra'}</small>}
      <small>Kameran behandlas lokalt. Endast knappen nedan skickar en stillbild till samtalet.</small>
      <button className="secondary small" disabled={!ready} onClick={() => {
        if (!video.current) return;
        const c = document.createElement('canvas'); c.width = 640; c.height = 480;
        c.getContext('2d')?.drawImage(video.current, 0, 0, c.width, c.height);
        onImage(c.toDataURL('image/jpeg', 0.8));
      }}>Dela kamerabild i samtalet</button>
    </>}
    {err && <p role="alert" className="error">{err}</p>}
  </div>;
}
