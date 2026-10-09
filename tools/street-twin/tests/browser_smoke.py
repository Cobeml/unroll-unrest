import sys,json,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from main import app
from playwright.sync_api import sync_playwright
clips=next(iter(json.loads((ROOT/'tests/fixtures/bottlenecks.json').read_text()).values()))
from test_spatial import make_bundle
from spatial import SceneStore,import_bundle
from bottlenecks import validate_findings
from test_bottlenecks import proposal
from recommendations import build_recommendations
from policy import policy_report
from unittest.mock import patch
errors=[]
temp=tempfile.TemporaryDirectory();root=Path(temp.name);run,raw=make_bundle(root)
store=SceneStore(root/'store');store.bucket=None
raw['view']={'file':'view.bin','nx':2,'ny':2,'frames':2,'res':.5,'x0':0,'y0':0}
(run/'app/view.bin').write_bytes(bytes([0,1,2,0,0,2,1,0]))
raw['objects'][0]['ends']=[{'side':'right','area':[[2,0],[3,0],[3,1],[2,1]],'covered':True,'frames':[{'k':0,'seen':.4,'counted':True},{'k':1,'seen':.95,'counted':True}]}]
(run/'app/ride.json').write_text(json.dumps(raw))
scene=import_bundle(run,store)
app.config['PUBLIC_PATH']='/app/'
from main import scenes as original_scenes
import main
main.scenes=store
reviews=build_recommendations(clips,validate_findings(json.dumps(proposal(clips)),clips))
job={'id':'a'*16,'status':'complete','recommendations':reviews,'clips':clips,'analyzed_parent_count':1,'warnings':[]}
report=policy_report({'clips':clips,'recommendations':reviews,'bottlenecks':[]},reviews[0]['id'])
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=False,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
 page=browser.new_page(viewport={'width':1440,'height':1000})
 page.on('pageerror',lambda e:errors.append(str(e)))
 def route(r):
  path=r.request.url.split('http://streettwin.test',1)[-1].split('?',1)[0]
  if path.startswith('/app/'):path=path[4:]
  data=None
  if path=='/api/metadata':data={'location':['new_york'],'camera_id':['nyc_bike_gopro-1'],'camera_locations':{'nyc_bike_gopro-1':['new_york']}}
  elif path in {'/api/analytics','/api/demo/bottleneck'}:data={'clips':clips,'recommendations':[],'sample_count':len(clips)}
  elif path=='/api/analysis':data=job
  elif path.startswith('/api/policy/'):data=report
  elif path.startswith('/api/evidence/'):data=next(c for c in clips if c['id']==path.rsplit('/',1)[-1])
  elif path.startswith('/api/detections/'):data={'available':False,'frames':[]}
  elif path.startswith('/api/stream/'):return r.fulfill(status=200,content_type='video/mp4',body=b'')
  if data is not None:return r.fulfill(json=data)
  with app.test_client() as c:
   response=c.get(path)
   r.fulfill(status=response.status_code,headers=dict(response.headers),body=response.data)
 page.route('**/*',route)
 page.goto('http://streettwin.test/app/?demo=bottleneck',wait_until='domcontentloaded')
 page.wait_for_function("document.getElementById('clip-index').textContent.includes('/')",timeout=15000)
 assert not errors,errors
 assert page.locator('#video').is_visible()
 page.wait_for_selector('#stage canvas',timeout=15000)
 assert page.locator('#map-empty').is_hidden()
 assert page.locator('#scene-bar').is_visible()
 assert page.locator('#scene-link-state').inner_text()=='Archive video separate from this map'
 page.wait_for_function("new URLSearchParams(location.search).has('scene_id')")
 assert 'demo=bottleneck' in page.url,'Map loading cleared the demo preset'
 page.get_by_role('button',name='Explore',exact=True).click()
 assert page.get_by_role('button',name='Explore',exact=True).get_attribute('aria-pressed')=='true'
 page.locator('#scene-scrub').fill('4')
 page.locator('#scene-play').click()
 page.wait_for_timeout(100)
 page.locator('#scene-play').click()
 assert '4.' in page.locator('#scene-clock').inner_text()
 assert len(page.locator('.policy-card').all())==2
 assert page.locator('#view-location').inner_text()=='New York'
 assert page.locator('body').evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(244, 242, 235)'
 page.screenshot(path='/tmp/streettwin-cockpit-desktop.png',full_page=True)
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(200)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'mobile overflow'
 assert page.locator('#video').is_visible()
 page.screenshot(path='/tmp/streettwin-cockpit-mobile.png',full_page=True)
 page.locator('.policy-card').first.click()
 page.wait_for_selector('#policy-title:text("Keep the riding path clear")')
 assert page.locator('#policy-video-slot #video').is_visible()
 assert len(page.locator('.citation').all())==2
 assert not errors,errors
 main.scenes=original_scenes
 temp.cleanup()
 browser.close()
 print('Desktop/mobile WebGL cockpit, map controls, CSS, policy routes and citations passed')
