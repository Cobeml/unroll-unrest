import asyncio
import json
import os
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler,HTTPServer
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import mcp_bridge as bridge

class MCPTests(unittest.TestCase):
    def test_paged_frames_and_safe_error(self):
        frames=[{'time_sec':i/10,'detections':[]} for i in range(100)]
        with patch('mcp_bridge.api',return_value={'frames':frames}):
            result=bridge.get_detections('a'*20,0,5,offset=10,limit=3)
            self.assertEqual(len(result['frames']),3);self.assertEqual(result['next_offset'],13)
        with patch.dict(os.environ,{'STREETTWIN_API_BASE':'https://u:secret@example.org'}):
            with self.assertRaises(ValueError):bridge.api('spatial/scenes')
        with self.assertRaises(ValueError):bridge.get_clip_evidence('../secrets')
    def test_unlinked_scene_context_and_minimal_scene(self):
        with patch('mcp_bridge.api',return_value={'path':[{}]*1000,'objects':[{}]*100,'assets':{},'quality':{}}) as api:
            result=bridge.get_spatial_scene('scene')
            self.assertEqual(result['object_count'],100);self.assertNotIn('path',result)
        with patch('mcp_bridge.api',return_value={}) as api:
            bridge.get_spatial_context('scene',segment_id='a'*20)
            self.assertEqual(api.call_args.args[1],{'scene_id':'scene','segment_id':'a'*20})

class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_handshake_tool_list_and_call(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body=json.dumps({'scenes':[{'id':'test-run','linked':False}]}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
            def log_message(self,*a):pass
        server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'mcp_bridge.py')],env={**os.environ,'STREETTWIN_API_BASE':f'http://127.0.0.1:{server.server_port}/'})
        try:
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize();tools=(await session.list_tools()).tools
                    self.assertEqual(len(tools),15);self.assertTrue(all(t.annotations.readOnlyHint for t in tools))
                    self.assertFalse(any('upload' in t.name or 'deploy' in t.name for t in tools))
                    result=await session.call_tool('list_spatial_scenes',{})
                    self.assertFalse(result.isError);self.assertEqual(result.structuredContent['scenes'][0]['id'],'test-run')
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
