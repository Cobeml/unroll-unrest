"""No-registry team deployment; credentials exist only in env and Secret stdin."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).parent
APP='street-twin'
FILES=['main.py','vss.py','service.py','observations.py','recommendations.py','spatial.py','bottlenecks.py','analysis.py',
       'policy.py','spatial_reasoning.py','ride_demo.py','index.html','style.css','app.js','cockpit.js','ride.html','ride.css','ride.js','requirements.txt']
BINARY_FILES=['street-preview.jpg','bottleneck-preview.jpg','traffic-preview.jpg','ride-preview.jpg']

def kubectl(namespace, *args, document=None):
    result=subprocess.run(['kubectl','-n',namespace,*args],
        input=json.dumps(document) if document is not None else None,
        text=True,capture_output=True)
    if result.returncode:
        # Never echo kubectl stderr: an admission failure may repeat Secret data.
        raise RuntimeError('Kubernetes operation failed: '+args[0])
    return result.stdout

def apply(namespace, document):
    args=['apply','--server-side','--field-manager=street-twin'] if document['kind']=='ConfigMap' else ['apply']
    kubectl(namespace,*args,'-f','-',document=document)
    print(document['kind']+' applied: '+document['metadata']['name'],flush=True)

def deploy():
    namespace=os.environ.get('VSS_USERNAME','')
    if not re.fullmatch(r'team-[0-9]+',namespace):
        raise RuntimeError('Team namespace is not configured.')
    if not all(os.environ.get(k) for k in ['VSS_URL','VSS_PASSWORD']):
        raise RuntimeError('VSS runtime configuration is incomplete.')
    host='video-lab-'+namespace+'.cosmos.vastdata.com'
    existing=json.loads(kubectl(namespace,'get','ingress','-o','json'))
    for ingress in existing.get('items',[]):
        if ingress['metadata']['name']==APP:
            continue
        for rule in ingress.get('spec',{}).get('rules',[]):
            for path in rule.get('http',{}).get('paths',[]):
                if path['path'].startswith('/app'):
                    raise RuntimeError('Another app owns /app; no existing app was changed.')
    # The VM's configured hostname may be private to its hosts file. Discover
    # the same backend's in-namespace Service from its existing /api Ingress.
    backend_services=[]
    for ingress in existing.get('items',[]):
        for rule in ingress.get('spec',{}).get('rules',[]):
            for path in rule.get('http',{}).get('paths',[]):
                if path['path']=='/api':
                    backend_services.append(path['backend']['service'])
    vss_url=os.environ['VSS_URL']
    if len(backend_services)==1:
        service=backend_services[0]
        port=service['port'].get('number')
        if port:
            vss_url=f"http://{service['name']}:{port}"
    code={name:(ROOT/name).read_text() for name in FILES}
    binary={name:base64.b64encode((ROOT/name).read_bytes()).decode() for name in BINARY_FILES}
    if sum(len(v.encode()) for v in code.values())+sum(len(v) for v in binary.values())>900_000:
        raise RuntimeError('App code exceeds the deployment size budget.')
    # Vendored browser modules have their own ConfigMap; no CDN dependency at runtime.
    checksums=json.loads((ROOT/'vendor/checksums.json').read_text())
    import hashlib
    vendor={name:(ROOT/'vendor'/name).read_text() for name in checksums}
    if any(hashlib.sha256(vendor[name].encode()).hexdigest()!=checksums[name] for name in vendor):
        raise RuntimeError('Vendored browser module checksum mismatch.')
    if sum(len(v.encode()) for v in vendor.values())>900_000:
        raise RuntimeError('Browser modules exceed the deployment size budget.')
    # Derived maps use an app-only asset prefix; no ingestion buckets or video uploads.
    from spatial import SceneStore
    bucket=os.environ.get('STREETTWIN_SPATIAL_BUCKET') or os.environ['VASTDB_BUCKET']
    prefix='' if bucket.endswith('-street-twin-spatial') else 'street-twin/spatial/'
    os.environ['STREETTWIN_SPATIAL_PREFIX']=prefix
    # The workshop S3 VIP uses a private certificate, matching the SDK skill pattern.
    os.environ.setdefault('STREETTWIN_S3_VERIFY','false')
    try:
        store=SceneStore(bucket=bucket,prefix=prefix);store.ensure_bucket()
        if not store.index()['scenes']:store.put('index.json',json.dumps({'schema_version':1,'scenes':[]}).encode(),'application/json')
    except Exception:raise RuntimeError('Dedicated map storage could not be configured.') from None
    code_name=APP+'-code-'+hashlib.sha256(json.dumps([code,binary],sort_keys=True).encode()).hexdigest()[:10]
    vendor_name=APP+'-vendor-'+hashlib.sha256(json.dumps(vendor,sort_keys=True).encode()).hexdigest()[:10]
    apply(namespace,{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':code_name},'data':code,'binaryData':binary})
    apply(namespace,{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':vendor_name},'data':vendor})
    # Use data rather than stringData so apply remains idempotent; no secret file is written.
    runtime={k:os.environ[k] for k in ['VSS_URL','VSS_USERNAME','VSS_PASSWORD']}
    runtime['VSS_URL']=vss_url
    runtime.update({k:os.environ[k] for k in ['S3_ENDPOINT','ACCESS_KEY','SECRET_KEY']})
    runtime['STREETTWIN_SPATIAL_BUCKET']=bucket
    runtime['STREETTWIN_SPATIAL_PREFIX']=prefix
    runtime['STREETTWIN_S3_VERIFY']=os.environ['STREETTWIN_S3_VERIFY']
    secret={k:base64.b64encode(v.encode()).decode() for k,v in runtime.items()}
    apply(namespace,{'apiVersion':'v1','kind':'Secret','metadata':{'name':APP+'-vss-creds'},'type':'Opaque','data':secret})
    labels={'app':APP}
    apply(namespace,{'apiVersion':'apps/v1','kind':'Deployment',
      'metadata':{'name':APP,'labels':labels},'spec':{'replicas':1,'selector':{'matchLabels':labels},
        'template':{'metadata':{'labels':labels},'spec':{'containers':[{
            'name':'app','image':'python:3.12-slim','imagePullPolicy':'IfNotPresent',
            'ports':[{'containerPort':8080}],
            'env':[{'name':k,'valueFrom':{'secretKeyRef':{'name':APP+'-vss-creds','key':k}}} for k in secret]+[
                {'name':'STREETTWIN_PUBLIC_PATH','value':'/app/'}],
            'workingDir':'/code','volumeMounts':[{'name':'code','mountPath':'/code','readOnly':True},{'name':'vendor','mountPath':'/code/vendor','readOnly':True}],
            'command':['sh','-c'],
            'args':['pip install --no-cache-dir -q -r requirements.txt && exec gunicorn --bind 0.0.0.0:8080 --workers 1 --threads 8 --timeout 180 main:app'],
            'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'cpu':'1','memory':'512Mi'}},
            'readinessProbe':{'httpGet':{'path':'/health','port':8080},'initialDelaySeconds':5,'periodSeconds':5},
            'livenessProbe':{'httpGet':{'path':'/health','port':8080},'initialDelaySeconds':45,'periodSeconds':15},
          }],'volumes':[{'name':'code','configMap':{'name':code_name}},{'name':'vendor','configMap':{'name':vendor_name}}]}}}})
    apply(namespace,{'apiVersion':'v1','kind':'Service','metadata':{'name':APP,'labels':labels},
        'spec':{'selector':labels,'ports':[{'name':'http','port':80,'targetPort':8080}],'type':'ClusterIP'}})
    apply(namespace,{'apiVersion':'networking.k8s.io/v1','kind':'Ingress',
        'metadata':{'name':APP,'labels':labels,'annotations':{
            'nginx.ingress.kubernetes.io/rewrite-target':'/$2',
            'nginx.ingress.kubernetes.io/use-regex':'true',
            'nginx.ingress.kubernetes.io/proxy-read-timeout':'180',
            'nginx.ingress.kubernetes.io/proxy-send-timeout':'180'}},
        'spec':{'ingressClassName':'nginx','rules':[{'host':host,'http':{'paths':[
            {'path':'/app(/|$)(.*)','pathType':'ImplementationSpecific',
             'backend':{'service':{'name':APP,'port':{'number':80}}}}
        ]}}]}})
    kubectl(namespace,'rollout','restart','deployment/'+APP)
    # The caller polls status so no command blocks progress updates for minutes.
    print('Deployment started. Verify rollout and /app before demo.',flush=True)

if __name__=='__main__':
    try:
        deploy()
    except (RuntimeError,KeyError,ValueError,OSError) as error:
        print(str(error) if isinstance(error,RuntimeError) else 'Deployment unavailable.',file=sys.stderr)
        sys.exit(1)
