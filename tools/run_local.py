"""Start the private local installation; no cloud credentials are needed."""
from pathlib import Path
import argparse,json,os,secrets,sys
ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765)
    p.add_argument('--data-dir',type=Path,default=ROOT/'.local');a=p.parse_args()
    data=a.data_dir.expanduser().resolve();data.mkdir(mode=0o700,parents=True,exist_ok=True)
    config=data/'settings.json'
    if not config.exists():
        fd=os.open(config,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as f:json.dump({'secret_key':secrets.token_urlsafe(48)},f)
    saved=json.loads(config.read_text())
    env={**os.environ,'VVS_OPENAI_CONFIG_FILE':str(data/'openai.json'),'VVS_SECRET_KEY':saved['secret_key'],'VVS_LOCAL_INSTALLATION':'true',
         'VVS_DATABASE_URL':'sqlite:///'+str(data/'vvs.db'),'VVS_STORAGE_ROOT':str(data/'storage'),
         'VVS_STATIC_DIR':str(ROOT/'frontend/dist'),'VVS_SECOND_READER':'false',
         'VVS_OCR_MODEL_DIR':os.environ.get('VVS_OCR_MODEL_DIR',str(data/'ocr-models')),
         'VVS_REVIEW_OCR':os.environ.get('VVS_REVIEW_OCR','false'),
         'VVS_OCR_ASSIST':os.environ.get('VVS_OCR_ASSIST','false'),'PYTHONPATH':str(ROOT/'engine')}
    python=ROOT/'.venv/bin/python'
    if not python.exists() or not (ROOT/'frontend/dist/index.html').exists():
        sys.exit('Kör först ./setup-local.sh i systemmappen.')
    os.chdir(ROOT/'backend')
    print(f'VVS-systemet: http://127.0.0.1:{a.port} (data sparas i {data})',flush=True)
    os.execve(python,[str(python),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(a.port)],env)
