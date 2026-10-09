"""Opt-in acceptance of a real completed selected-parent run; no new GPU submission."""
import os
from playwright.sync_api import sync_playwright
base=os.environ.get('UNFOLD_TEST_BASE','http://127.0.0.1:8128/')
job_id=os.environ.get('UNFOLD_TEST_RUN','ba9c06b77f5fb8517391c4c4')
errors=[]
def fits(page):
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth && document.documentElement.scrollHeight<=innerHeight')
 assert page.evaluate("[...document.querySelectorAll('.report-content,.workspace,.run-layout')].filter(e=>e.offsetParent).every(e=>e.scrollHeight<=e.clientHeight+2)")
with sync_playwright() as p:
 b=p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=False,args=['--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
 page=b.new_page(viewport={'width':1440,'height':900});page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'runs/'+job_id,wait_until='domcontentloaded')
 page.get_by_role('link',name='Explore this street').wait_for(timeout=30000)
 for v in [{'width':1440,'height':900},{'width':390,'height':600}]:page.set_viewport_size(v);fits(page)
 page.set_viewport_size({'width':1440,'height':900})
 job=page.request.get(base+'api/runs/'+job_id).json()
 assert job['status']=='complete' and job['analysis_status']=='complete'
 # Repeated selection uses the same durable job and does not rerun the GPU.
 again=page.request.post(base+'api/runs',data={'segment_id':job['selected_segment_id']}).json()
 assert again['id']==job_id and again['status']=='complete'
 page.get_by_role('link',name='Explore this street').click();page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 assert page.evaluate('window.UnfoldDemo.sceneId')==job['scene_id']
 assert page.locator('#vid').is_visible()
 assert page.locator('#vid').get_attribute('src')==base+'api/rides/'+job['scene_id']+'/video'
 page.wait_for_function('document.getElementById("vid").readyState>=2',timeout=30000)
 page.locator('#go').click()
 page.wait_for_function('document.getElementById("vid").currentTime>5.5',timeout=30000)
 page.locator('#play').click()
 page.evaluate('window.UnfoldDemo.seek(10)')
 page.wait_for_function('Math.abs(document.getElementById("vid").currentTime-10)<0.1',timeout=30000)
 page.wait_for_function('document.getElementById("clock").textContent.startsWith("10.0")',timeout=30000)
 assert len(page.evaluate('window.UnfoldDemo.findings'))==3
 assert page.locator('.recommendation').count()==2
 page.locator('#insight-next').click();assert page.locator('.recommendation').count()==1
 page.locator('#insight-prev').click()
 page.screenshot(path='/tmp/unfold-new-archive-story.png');fits(page)
 page.set_viewport_size({'width':390,'height':600});fits(page);assert page.locator('#vid').is_visible()
 page.locator('.recommendation').first.click();page.wait_for_function('!!window.UnfoldDemo',timeout=60000)
 for v in [{'width':1440,'height':900},{'width':390,'height':844},{'width':390,'height':600}]:
  page.set_viewport_size(v)
  for tab in ['Action','Statistics','Frames','Video','Review','Source','Cosmos']:
   page.get_by_role('tab',name=tab,exact=True).click();fits(page)
   if tab=='Source':assert 'excluded from citations' in page.locator('#report-content').inner_text()
 page.set_viewport_size({'width':1440,'height':900});page.get_by_role('tab',name='Cosmos',exact=True).click();page.locator('#cosmos-analysis').click()
 page.wait_for_selector('.analysis-copy',timeout=30000);fits(page)
 page.screenshot(path='/tmp/unfold-new-archive-analysis.png')
 page.reload(wait_until='domcontentloaded');page.wait_for_function('!!window.UnfoldDemo',timeout=60000);fits(page)
 assert not errors,errors
 print('Real selected-parent run: verified import, reused job, 3 findings, source gap, Cosmos, pages and no-scroll checks passed.',flush=True)
 b.close()
