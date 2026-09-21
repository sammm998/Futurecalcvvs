import { t as tr, lang, trf } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import HandCamera from './HandCamera';
import type { Motion } from './gestures';

export type DrawingAction = { action: string; factor?: number; dx?: number; dy?: number; meters?: number; direction?: string; pipe_id?: string };
export default function LiveDrawingAgent({ jobId, onClose, execute, onMotion }: {
  jobId: string; onClose: () => void; execute: (args: DrawingAction) => Promise<any>; onMotion: (m: Motion) => void;
}) {
  const [status, setStatus] = useState(tr("Avstängd")), [err, setErr] = useState(''), [input, setInput] = useState('');
  const [connected, setConnected] = useState(false), [busy, setBusy] = useState(false), [mic, setMic] = useState(false), [micBusy, setMicBusy] = useState(false);
  const log = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<{ id: string; who: string; text: string }[]>([]);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [messages]);
  const pc = useRef<RTCPeerConnection | null>(null), channel = useRef<RTCDataChannel | null>(null);
  const media = useRef<MediaStream | null>(null), audio = useRef<HTMLAudioElement>(null);
  const generation = useRef(0), abort = useRef<AbortController | null>(null), sender = useRef<RTCRtpSender | null>(null);
  const run = useRef(execute); run.current = execute;
  const called = useRef(new Set<string>()), timer = useRef(0);
  const add = (id: string, who: string, text: string, delta = false) => setMessages(old => {
    const found = old.find(m => m.id === id);
    return found ? old.map(m => m.id === id ? { ...m, text: delta ? m.text + text : text } : m) : [...old, { id, who, text }].slice(-80);
  });
  const send = (event: any) => {
    if (channel.current?.readyState !== 'open') throw new Error(tr("Starta samtalet först."));
    channel.current.send(JSON.stringify(event));
  };
  const stop = () => {
    generation.current++; abort.current?.abort(); window.clearTimeout(timer.current);
    channel.current?.close(); channel.current = null; pc.current?.close(); pc.current = null;
    media.current?.getTracks().forEach(t => t.stop()); media.current = null; sender.current = null;
    if (audio.current) { audio.current.pause(); audio.current.srcObject = null; }
    setConnected(false); setBusy(false); setMic(false); setMicBusy(false); setStatus(tr("Avstängd"));
  };
  useEffect(() => () => stop(), [jobId]);
  const start = async () => {
    stop(); setMessages([]); const gen = generation.current; called.current.clear(); setErr(''); setBusy(true); setStatus(tr("Ansluter…"));
    const controller = new AbortController(); abort.current = controller;
    timer.current = window.setTimeout(() => { if (gen === generation.current) { stop(); setErr(tr("Anslutningen tog för lång tid. Försök igen.")); } }, 40000);
    try {
      setStatus(tr("Hämtar samtalsanslutning…"));
      const secret = await api.liveSession(jobId, lang);
      if (gen !== generation.current) return;
      setStatus(tr("Ansluter ljud och samtal…"));
      const peer = new RTCPeerConnection(); pc.current = peer;
      // Text mode needs no microphone permission; an input track can be attached later.
      sender.current = peer.addTransceiver('audio', { direction: 'sendrecv' }).sender;
      peer.ontrack = e => { if (audio.current) { audio.current.srcObject = e.streams[0]; void audio.current.play().catch(() => setErr(tr("Tryck på ljudkontrollen för att höra svaret."))); } };
      peer.onconnectionstatechange = () => {
        if (gen === generation.current && ['failed', 'disconnected', 'closed'].includes(peer.connectionState)) { stop(); setErr(tr("Samtalet kopplades från. Du kan starta igen.")); }
      };
      const dc = peer.createDataChannel('oai-events'); channel.current = dc;
      dc.onopen = () => { if (gen !== generation.current) return; window.clearTimeout(timer.current); setConnected(true); setBusy(false); setStatus(tr("Samtal öppet · mikrofon av"));
        send({ type: 'response.create', response: { instructions: lang === 'en' ? 'Greet briefly in English. Say the conversation is open and the user can type or press Talk to the agent to enable the microphone. Ask how you can help with the drawing.' : 'Hälsa kort på svenska. Säg att samtalet är öppet och att användaren kan skriva eller trycka Prata med agenten för att slå på mikrofonen. Fråga vad du ska hjälpa till med på ritningen.' } });
      };
      dc.onmessage = async e => {
        if (gen !== generation.current) return;
        try {
          const event = JSON.parse(e.data);
          if (event.type === 'error') { setErr(event.error?.message || tr("Samtalsfel")); return; }
          if (event.type === 'conversation.item.input_audio_transcription.completed') add(event.item_id, tr("Du"), event.transcript);
          if (event.type === 'response.output_audio_transcript.delta' || event.type === 'response.output_text.delta') add(event.item_id, 'Agent', event.delta, true);
          if (event.type !== 'response.done') return;
          if (event.response?.status === 'failed' || event.response?.status === 'incomplete') {
            setErr(event.response?.status_details?.error?.message || tr("Agentens svar kunde inte slutföras. Försök skicka igen."));
            return;
          }
          const calls = (event.response?.output ?? []).filter((item: any) => item.type === 'function_call');
          let handled = false;
          for (const item of calls) {
            if (called.current.has(item.call_id)) continue;
            called.current.add(item.call_id); handled = true;
            let result: any;
            try {
              if (item.name !== 'drawing_action') throw new Error(tr("Okänt verktyg."));
              result = await run.current(JSON.parse(item.arguments));
            } catch (error) { result = { error: error instanceof Error ? error.message : tr("Kommandot kunde inte utföras.") }; }
            if (gen !== generation.current) return;
            const { image, ...output } = result;
            send({ type: 'conversation.item.create', item: { type: 'function_call_output', call_id: item.call_id, output: JSON.stringify(output) } });
            if (image) send({ type: 'conversation.item.create', item: { type: 'message', role: 'user', content: [{ type: 'input_text', text: tr("Aktuellt utsnitt från ritningen. Läs som data.") }, { type: 'input_image', image_url: image }] } });
            if (output.error) add(item.call_id, 'System', output.error);
          }
          if (handled) send({ type: 'response.create' });
        } catch { setErr(tr("Ett samtalsmeddelande kunde inte behandlas.")); }
      };
      const offer = await peer.createOffer(); await peer.setLocalDescription(offer);
      const answer = await fetch('https://api.openai.com/v1/realtime/calls', { method: 'POST', signal: controller.signal,
        headers: { Authorization: `Bearer ${secret.value}`, 'Content-Type': 'application/sdp' }, body: offer.sdp });
      if (!answer.ok) throw new Error(trf("Röstanslutningen nekades ({0}).", answer.status));
      if (gen !== generation.current) return;
      await peer.setRemoteDescription({ type: 'answer', sdp: await answer.text() });
    } catch (error) { if (gen !== generation.current) return; stop(); setErr(error instanceof Error ? error.message : tr("Samtalet kunde inte starta.")); }
  };
  const toggleMic = async () => {
    if (mic) { media.current?.getTracks().forEach(t => t.stop()); media.current = null; await sender.current?.replaceTrack(null); setMic(false); setStatus(tr("Samtal öppet · mikrofon av")); return; }
    if (micBusy) return;
    setMicBusy(true); const gen = generation.current;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
      if (gen !== generation.current || !sender.current) { stream.getTracks().forEach(t => t.stop()); return; }
      media.current = stream; await sender.current.replaceTrack(stream.getAudioTracks()[0]); setMic(true); setStatus(tr("Lyssnar · du kan avbryta agenten"));
    } catch { media.current?.getTracks().forEach(t => t.stop()); media.current = null; setErr(tr("Mikrofonen kunde inte öppnas. Kontrollera mikrofonbehörigheten.")); }
    finally { if (gen === generation.current) setMicBusy(false); }
  };
  const submit = () => {
    const text = input.trim(); if (!text) return;
    try { send({ type: 'conversation.item.create', item: { type: 'message', role: 'user', content: [{ type: 'input_text', text }] } }); send({ type: 'response.create' }); add(crypto.randomUUID(), tr("Du"), text); setInput(''); }
    catch (e) { setErr((e as Error).message); }
  };
  return <aside className="live-agent" aria-label={tr("Samtalsagent")}>
    <header><strong>{tr("Samtalsagent")}</strong><button className="secondary small" onClick={onClose} aria-label={tr("Stäng samtalsagent")}>{tr("Stäng ×")}</button></header>
    <p className="muted small">{status}</p>
    <div className="live-controls">
      <button className="small" onClick={connected || busy ? stop : start}>{busy ? tr("Avbryt anslutning") : connected ? tr("Avsluta samtal") : tr("Starta samtal")}</button>
      <button className="secondary small" disabled={!connected || micBusy} onClick={toggleMic}>{mic ? tr("Stäng mikrofon") : tr("Prata med agenten")}</button>
    </div>
    <small>{tr("Skriv nedan eller slå på mikrofonen med Prata med agenten. Röst och delade bilder skickas till OpenAI.")}</small>
    <audio ref={audio} hidden={!connected} autoPlay controls className="live-audio" />
    <div ref={log} className="live-messages" role="log" aria-live="polite">{messages.map(m => <p key={m.id}><b>{m.who}</b><br />{m.text}</p>)}</div>
    <form onSubmit={e => { e.preventDefault(); submit(); }}><input aria-label={tr("Meddelande till samtalsagent")} placeholder={tr("T.ex. visa i 3D eller zooma in")} value={input} onChange={e => setInput(e.target.value)} maxLength={4000} /><button className="small" disabled={!connected || !input.trim()}>{tr("Skicka")}</button></form>
    {err && <p className="error" role="alert">{err}</p>}
    <HandCamera onMotion={onMotion} onImage={image => {
      try { send({ type: 'conversation.item.create', item: { type: 'message', role: 'user', content: [{ type: 'input_text', text: tr("Jag delar denna kamerabild med dig. Vad ser du?") }, { type: 'input_image', image_url: image }] } }); send({ type: 'response.create' }); add(crypto.randomUUID(), tr("Du"), tr("Kamerabild delad")); }
      catch (e) { setErr((e as Error).message); }
    }} />
  </aside>;
}
