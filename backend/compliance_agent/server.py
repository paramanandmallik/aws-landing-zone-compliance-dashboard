"""HTTP server for AgentCore Runtime.

AgentCore expects:
- GET /ping → 200 OK (health check)
- POST /invocations → agent response (main endpoint)
Port: 8080
"""

import json
import os
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Lazy agent initialization
_agent = None

def get_agent():
    global _agent
    if _agent is None:
        from backend.compliance_agent.agent import _build_agent
        _agent = _build_agent()
    return _agent


class AgentHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "healthy"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/invocations':
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length else '{}'
            
            try:
                payload = json.loads(body)
                text = payload.get('text', 'Evaluate governance posture.')
                
                logger.info('Invoking agent with: %s', text[:100])
                
                # Run agent in background thread — observations are written to DynamoDB as they're produced
                import threading
                def run_agent():
                    try:
                        agent = get_agent()
                        agent(text)
                        logger.info('Agent completed successfully')
                    except Exception as e:
                        logger.error('Agent failed: %s', e)
                
                t = threading.Thread(target=run_agent, daemon=True)
                t.start()
                
                # Return immediately — observations will appear in DynamoDB
                response = json.dumps({"status": "evaluation_started", "message": "Agent is evaluating. Observations will appear in DynamoDB."})
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(response.encode())
            except Exception as e:
                logger.exception('Failed to start agent')
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        logger.info(format, *args)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8080'))
    server = HTTPServer(('0.0.0.0', port), AgentHandler)
    logger.info('AgentCore HTTP server starting on port %d', port)
    server.serve_forever()
