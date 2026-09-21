"""Interactive local setup. The API key is never echoed or printed."""
import argparse
import getpass
import json
import os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def save_config(path, api_key, model):
    path=Path(path);path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary=tempfile.mkstemp(prefix='.openai-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f:
            json.dump({'api_key':api_key,'model':model},f)
            f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def main():
    parser=argparse.ArgumentParser(description='Konfigurera OpenAI för den lokala VVS-appen')
    parser.add_argument('--data-dir',type=Path,default=ROOT/'.local')
    args=parser.parse_args()
    print('Nyckeln sparas endast lokalt. Inmatningen visas inte på skärmen.')
    key=getpass.getpass('OpenAI API-nyckel: ').strip()
    if not key:raise SystemExit('Ingen nyckel angavs; inget ändrat.')
    model=input('Modellnamn [gpt-6-astra]: ').strip() or 'gpt-6-astra'
    from openai import OpenAI
    try:
        # A tiny real request checks both credentials and model inference access.
        client=OpenAI(api_key=key,timeout=45,max_retries=0)
        response=client.responses.create(model=model,store=False,max_output_tokens=1024,
            input='Connection test. Reply OK.')
        if response.status!='completed':raise RuntimeError('incomplete')
    except Exception:
        raise SystemExit('Anslutningskontrollen misslyckades. Kontrollera nyckel, modellåtkomst och API-saldo. Inget sparat.') from None
    save_config(args.data_dir/'openai.json',key,model)
    print('Anslutningen är verifierad och sparad. Välj Modellbedömning eller Jämför båda i appen.')

if __name__=='__main__':main()
