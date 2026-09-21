"""Published vector engine API. Legacy /predict remains backwards compatible."""
from pathlib import Path
from hmac import compare_digest
from flask import Blueprint, jsonify, request
from .config import Config
from studio import tasks, styles
from studio.storage import data_root, new_id, read, write, ident

api=Blueprint('pipe_studio_api',__name__,url_prefix='/v2')


@api.before_request
def authenticate():
    if not Config.configured():
        return jsonify(error='API_KEY is not configured'),503
    if not compare_digest(request.headers.get('X-API-Key',''),Config.API_KEY):
        return jsonify(error='Invalid or missing X-API-Key'),401


@api.get('/styles')
def list_styles():
    return jsonify([{'id':s['draft']['id'],'name':s['draft']['name'],'active_version':s['active']}
                    for s in styles.list_styles() if s['active'] is not None])


@api.post('/analyses')
def analyze():
    style_id=request.args.get('style','auto')
    # assignmentMethod (required, never defaulted): 'llm' (Astra) or 'dimension' (flow-direction rules, no model)
    method=(request.args.get('assignmentMethod') or '').strip().lower().replace(' based','')
    binding={'llm': 'astra', 'dimension': 'flow'}.get(method)
    if binding is None:
        return jsonify(error="assignmentMethod is required: 'llm' or 'dimension'"),400
    style_version=None
    if style_id!='auto':
        try:
            style_version=styles.get_style(style_id)['version']
        except ValueError as exc:
            return jsonify(error=str(exc)),400
    upload=request.files.get('file')
    data=upload.read(Config.MAX_UPLOAD_BYTES+1) if upload else request.get_data(cache=False)
    if len(data)>Config.MAX_UPLOAD_BYTES:
        return jsonify(error='PDF exceeds upload limit'),413
    if not data.startswith(b'%PDF-'):
        return jsonify(error='Upload a PDF as multipart file or application/pdf'),400
    from studio.engine import analyze as run, api_result
    aid=new_id('analysis'); directory=data_root()/'analyses'/aid
    directory.mkdir(parents=True,exist_ok=True)
    source=directory/'drawing.pdf'; source.write_bytes(data)
    def work(progress):
        result=run(source,directory/'stages',style_id=style_id,style_version=style_version,binding=binding,
                   progress=lambda n,name:progress(f'{n}/9 {name}'))
        shaped=api_result(result); write(directory/'result.json',shaped)
        return {'analysis_id':aid,'result_url':'/v2/analyses/'+aid+'/result'}
    try:
        job=tasks.submit('production_analysis',work)
    except ValueError as exc:
        return jsonify(error=str(exc)),429
    write(directory/'job.json',{'job_id':job['id']})
    return jsonify(analysis_id=aid,job_id=job['id'],status='accepted',status_url='/v2/analyses/'+aid),202


@api.get('/analyses/<aid>')
def status(aid):
    try:
        ref=read(data_root()/'analyses'/ident(aid)/'job.json')
        if not ref:
            return jsonify(error='Unknown analysis'),404
        return jsonify(tasks.get(ref['job_id']))
    except ValueError as exc:
        return jsonify(error=str(exc)),400


@api.get('/analyses/<aid>/result')
def result(aid):
    try:
        data=read(data_root()/'analyses'/ident(aid)/'result.json')
        return (jsonify(data),200) if data else (jsonify(error='No completed result'),404)
    except ValueError as exc:
        return jsonify(error=str(exc)),400
