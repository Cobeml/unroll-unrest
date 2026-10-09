"""Opt-in real archive/map browser check. Set UNFOLD_TEST_BASE to the running app."""
import os
from playwright.sync_api import sync_playwright
base=os.environ.get('UNFOLD_TEST_BASE','http://127.0.0.1:8128/')
errors=[];failed=[]
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=False,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
 page=browser.new_page(viewport={'width':1440,'height':1000})
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('requestfailed',lambda r:failed.append(r.url.split('/api/')[-1].split('?')[0]))
 page.goto(base,wait_until='domcontentloaded',timeout=30000)
 page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 assert page.title()=='Unfold — Crosswalk Sightlines'
 assert page.locator('#error-banner').is_hidden()
 assert len(page.locator('.xi').all())==3
 assert 'hedge' in page.locator('#headline').inner_text()
 assert '5 m' in page.locator('#headline').inner_text()
 assert '10 m' in page.locator('#headline').inner_text()
 assert 'disagrees' in page.locator('.xi').nth(1).inner_text()
 assert len(page.locator('.recommendation').all())==1
 assert 'Trim the hedge' in page.locator('.recommendation').inner_text()
 assert page.locator('#stage canvas').is_visible()
 assert page.evaluate('getComputedStyle(document.body).fontFamily').startswith('Georgia')
 assert page.evaluate('getComputedStyle(document.body).backgroundColor')=='rgb(244, 242, 235)'
 page.screenshot(path='/tmp/unfold-demo-opening.png',full_page=True)
 page.locator('#go').click()
 page.wait_for_function('document.getElementById("vid").currentTime>1',timeout=30000)
 page.evaluate('document.getElementById("vid").pause();window.UnfoldDemo.seek(16.25)')
 page.wait_for_function('document.getElementById("vid").currentTime>16',timeout=30000)
 page.wait_for_timeout(400)
 assert 'hedge' in page.locator('#card').inner_text()
 page.screenshot(path='/tmp/unfold-demo-crossing.png',full_page=True)
 print('Matched indexed parent, crossing story, map, sightline strips, review disagreement and recommendation passed',flush=True)
 with page.expect_response(lambda r:'/api/detections/' in r.url,timeout=30000) as response:
  page.locator('#overlay-mode').click()
 data=response.value.json();assert data.get('available');assert len(data.get('frames',[]))>0
 page.wait_for_timeout(200)
 print('Archive YOLO frames:',len(data['frames']),flush=True)
 page.get_by_role('button',name='Look around',exact=True).click()
 assert page.get_by_role('button',name='Look around',exact=True).get_attribute('aria-pressed')=='true'
 page.locator('#seen').click();assert page.locator('#seen').get_attribute('aria-pressed')=='false'
 page.locator('#cloud').click();assert page.locator('#cloud').get_attribute('aria-pressed')=='false'
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'mobile overflow'
 page.screenshot(path='/tmp/unfold-demo-mobile.png',full_page=True)
 page.locator('.recommendation').click()
 page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 assert page.locator('#policy-report').is_visible()
 assert page.locator('#policy-report h1').inner_text()=='Trim the hedge at crossing 2'
 assert len(page.locator('.evidence-link').all())==2
 assert page.locator('#policy-report img').is_visible()
 page.screenshot(path='/tmp/unfold-demo-policy.png',full_page=True)
 page.reload(wait_until='domcontentloaded');page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 page.wait_for_function('document.getElementById("vid").currentTime>16',timeout=30000)
 assert page.locator('#policy-report').is_visible()
 assert not errors,errors
 print('Orbit/layers, mobile, recommendation page, evidence links and deep-link reload passed; failed requests:',len(failed),flush=True)
 browser.close()
