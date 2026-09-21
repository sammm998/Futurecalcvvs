"""Bounded background work with persistent job status."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from .storage import data_root, write, read, new_id, now, ident
POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='pipe-studio')
CAPACITY=threading.BoundedSemaphore(6)


def get(jid):
    r=read(data_root()/'tasks'/(ident(jid)+'.json'))
    if not r:
        raise ValueError('Unknown job')
    return r


def submit(kind, work, context=None):
    if not CAPACITY.acquire(blocking=False):
        raise ValueError('The work queue is full; try again shortly')
    jid=new_id('job'); path=data_root()/'tasks'/(jid+'.json')
    record={**(context or {}),'id':jid,'kind':kind,'status':'queued','created_at':now()}
    write(path,record)
    def progress(message):
        record.update(status='running',progress=message); write(path,record)
    def run():
        started=time.monotonic()
        from . import usage
        meter,usage_token=usage.begin()
        record["started_at"]=now()
        try:
            progress('Starting')
            result=work(progress)
            record.update(status='done',result=result,finished_at=now())
        except Exception as exc:
            import logging
            logging.getLogger('pipe-studio').exception('Job %s failed',jid)
            record.update(status='error',error=str(exc) if isinstance(exc,ValueError) else 'Analysis failed; see server logs',finished_at=now())
        finally:
            if kind in ('check-feedback','style-from-drawing'):
                record["usage"]=usage.finish(meter,usage_token)
            else:
                usage.finish(meter,usage_token)
            record["seconds"]=round(time.monotonic()-started,1)
            write(path,record); CAPACITY.release()
    POOL.submit(run)
    return dict(record)
