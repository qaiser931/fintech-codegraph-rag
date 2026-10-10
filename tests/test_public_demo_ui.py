"""Public demo never forwards role credentials to a visitor-chosen API host."""
from pathlib import Path
from unittest.mock import Mock
import pytest
from streamlit.testing.v1 import AppTest
from ui import api_client

APP = Path(__file__).resolve().parents[1] / 'ui/app.py'

@pytest.mark.parametrize('mode,button', [('Explore code','🔍 Explore code'),('Generate answer','🚀 Generate answer')])
def test_public_demo_binds_requests_to_server_target(monkeypatch, mode, button):
    monkeypatch.setenv('CODEGRAPH_PUBLIC_DEMO','1')
    monkeypatch.setenv('CODEGRAPH_API_URL','http://127.0.0.1:8001')
    data={'role':'Junior Dev','sources':[], 'citations':[], 'retrieved_items':[], 'call_path':[], 'answer':'ok', 'status':'INSUFFICIENT_EVIDENCE'}
    retrieve=Mock(return_value=data);generate=Mock(return_value=data)
    monkeypatch.setattr(api_client,'retrieve_api',retrieve)
    monkeypatch.setattr(api_client,'query_api',generate)
    at=AppTest.from_file(str(APP),default_timeout=10).run()
    assert not at.exception
    assert not at.text_input
    # Old session state must not replace the environment-supplied target.
    at.session_state['api_url']='https://attacker.example'
    at.session_state['result_scope']=('https://attacker.example','Junior Dev',mode)
    at.radio[0].set_value(mode).run()
    next(b for b in at.button if b.label==button).click().run()
    assert not at.exception
    call=retrieve if mode=='Explore code' else generate
    assert call.call_args.kwargs['api_url']=='http://127.0.0.1:8001'
    (generate if mode=='Explore code' else retrieve).assert_not_called()


def test_local_ui_retains_configurable_api_address(monkeypatch):
    monkeypatch.setenv('CODEGRAPH_PUBLIC_DEMO','0')
    at=AppTest.from_file(str(APP),default_timeout=10).run()
    assert not at.exception
    assert at.text_input[0].label=='FastAPI URL'
