"""Local lightweight speaker descriptors, not biometric identification."""
import numpy as np


def describe(audio, rate=16000):
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(x) < rate * .4 or not np.isfinite(x).all():
        return None
    # Limit computation to a representative 8 seconds per segment.
    x = x[:rate * 8]
    size = 640
    frames = np.array([x[i:i+size] for i in range(0, len(x)-size+1, 320)])
    rms = np.sqrt(np.mean(frames**2, axis=1))
    frames = frames[rms >= max(.002, np.percentile(rms, 35))]
    if len(frames) < 6:
        return None
    levels = 20*np.log10(np.maximum(np.sqrt(np.mean(frames**2, axis=1)), 1e-8))
    frames = frames - frames.mean(axis=1, keepdims=True)
    spec = abs(np.fft.rfft(frames*np.hanning(size), n=1024))**2
    freq = np.fft.rfftfreq(1024, 1/rate)
    edges = [100,250,400,600,900,1300,1900,2800,4000,6500]
    bands = np.array([np.log(np.maximum(spec[:,(freq>=a)&(freq<b)].mean(axis=1),1e-12)) for a,b in zip(edges,edges[1:])]).T
    bands -= bands.mean(axis=1, keepdims=True)
    profile = np.median(bands,axis=0)
    pitches=[]
    for frame in frames[::2]:
        corr=np.correlate(frame,frame,'full')[size-1:]
        lo,hi=rate//400,rate//75
        peak=lo+int(np.argmax(corr[lo:hi]))
        if corr[0]>0 and corr[peak]/corr[0]>.55:
            pitches.append(rate/peak)
    pitch=float(np.median(pitches)) if len(pitches)>=3 else None
    return {'dbfs':round(float(np.median(levels)),1),'pitch_hz':round(pitch,1) if pitch else None,
            'voice_profile': [round(float(v),3) for v in profile]}


def enrich(segments, audio, rate=16000):
    for s in segments:
        a=max(0,int(s['start']*rate)); b=min(len(audio),int(s['end']*rate))
        features=describe(audio[a:b],rate)
        if features: s.update(features)
    return segments


def distance(a,b):
    v=np.asarray(a['voice_profile'])-np.asarray(b['voice_profile'])
    d=float(np.sqrt(np.mean(v*v)))
    if a.get('pitch_hz') and b.get('pitch_hz'):
        d+= .8*abs(np.log2(a['pitch_hz']/b['pitch_hz']))
    if a.get('dbfs') is not None and b.get('dbfs') is not None:
        d+= .015*abs(a['dbfs']-b['dbfs'])
    return d


def propagate(segments):
    anchors={r:[s for s in segments if s.get('role')==r and s.get('role_source')=='text' and s.get('voice_profile')] for r in ('operator','customer')}
    if not all(anchors.values()): return segments
    separation=min(distance(a,b) for a in anchors['operator'] for b in anchors['customer'])
    if separation < .65: return segments
    for s in segments:
        if s.get('role')!='unknown' or not s.get('voice_profile'): continue
        ds=sorted((min(distance(s,a) for a in group),role) for role,group in anchors.items())
        if ds[0][0] < min(1.4,separation*.65) and ds[1][0]-ds[0][0] > .35:
            s['role']=ds[0][1]; s['role_source']='acoustic'
    return segments
