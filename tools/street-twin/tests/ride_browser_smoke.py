"""Opt-in browser acceptance against real saved map, archive playback and discovery."""
import os
from playwright.sync_api import sync_playwright
base=os.environ.get('UNFOLD_TEST_BASE','http://127.0.0.1:8128/')
errors=[]
def fits(page):
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight'),'page scrolls'
 assert page.evaluate("[...document.querySelectorAll('.report-content,.workspace,.run-layout')].filter(e=>e.offsetParent).every(e=>e.scrollHeight<=e.clientHeight+2)"),'panel overflows'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=False,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
 page=browser.new_page(viewport={'width':1440,'height':900})
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base,wait_until='domcontentloaded',timeout=30000)
 page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 assert page.locator('#headline').inner_text()=='A hedge screens crossing 2.'
 assert page.locator('#error-banner').is_hidden()
 assert len(page.locator('.recommendation').all())==1
 assert 'Trim the hedge' in page.locator('.recommendation').inner_text()
 assert page.locator('#evidence-video').is_visible()
 assert page.locator('#vid').is_visible()
 assert page.locator('#vid').get_attribute('src').startswith(base)
 assert page.locator('#stage canvas').is_visible()
 assert page.evaluate('getComputedStyle(document.body).fontFamily').startswith('Georgia')
 assert page.evaluate('getComputedStyle(document.body).backgroundColor')=='rgb(244, 242, 235)'
 fits(page);page.screenshot(path='/tmp/unfold-fullscreen-story.png')
 page.locator('#go').click()
 page.wait_for_function('document.getElementById("vid").currentTime>1',timeout=30000)
 page.locator('#video-toggle').click();assert page.locator('#vid').is_hidden()
 page.wait_for_function('document.getElementById("vid").currentTime>1.5',timeout=30000)
 page.locator('#video-toggle').click();assert page.locator('#vid').is_visible()
 page.evaluate('document.getElementById("vid").pause();window.UnfoldDemo.seek(16.25)')
 page.wait_for_function('document.getElementById("vid").currentTime>16',timeout=30000)
 page.wait_for_timeout(300);assert '97%' in page.locator('#card').inner_text()
 page.screenshot(path='/tmp/unfold-fullscreen-crossing.png')
 page.get_by_role('button',name='Explore',exact=True).click()
 assert page.get_by_role('button',name='Explore',exact=True).get_attribute('aria-pressed')=='true'
 for viewport in [{'width':390,'height':844},{'width':390,'height':600}]:
  page.set_viewport_size(viewport);fits(page);assert page.locator('#vid').is_visible()
 page.set_viewport_size({'width':1440,'height':900})
 page.locator('.recommendation').click();page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 assert page.locator('#policy-report h1').inner_text()=='Trim the hedge at crossing 2'
 for viewport in [{'width':1440,'height':900},{'width':390,'height':844},{'width':390,'height':600}]:
  page.set_viewport_size(viewport)
  for name in ['Action','Statistics','Frames','Review','Source','Video']:
   page.get_by_role('tab',name=name,exact=True).click();fits(page)
   if name=='Review':
    first=page.locator('#report-content').inner_text()
    button=page.get_by_role('button',name='Next side')
    if button.is_disabled():button=page.get_by_role('button',name='Previous side')
    button.click()
    both=first+page.locator('#report-content').inner_text()
    assert 'rejected' in both and 'confirmed' in both;fits(page)
  page.get_by_role('tab',name='Action',exact=True).click()
 page.set_viewport_size({'width':1440,'height':900});page.get_by_role('tab',name='Video',exact=True).click()
 assert page.locator('#vid').is_visible()
 with page.expect_response(lambda r:'/api/detections/' in r.url,timeout=30000) as response:page.locator('#overlay-mode').click()
 assert response.value.json()['available']
 page.get_by_role('tab',name='Frames',exact=True).click();page.screenshot(path='/tmp/unfold-recommendation-frames.png')
 page.reload(wait_until='domcontentloaded');page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 assert page.locator('#policy-report').is_visible()
 page.get_by_role('link',name='Find risk clips').click()
 page.wait_for_selector('.candidate',timeout=60000)
 for viewport in [{'width':1440,'height':900},{'width':390,'height':844},{'width':390,'height':600}]:
  page.set_viewport_size(viewport);fits(page)
 page.locator('.candidate').first.click();assert page.locator('#preview-video').is_visible();fits(page)
 page.screenshot(path='/tmp/unfold-discovery-mobile.png')
 assert not errors,errors
 print('Fullscreen story, all recommendation tabs, indexed video/YOLO, deep links, discovery and mobile no-scroll checks passed.',flush=True)
 browser.close()
