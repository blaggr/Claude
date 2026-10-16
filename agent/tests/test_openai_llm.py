"""OpenAI backend tests — no network, using a scripted fake OpenAI client.

Proves the OpenAILLM translates the Anthropic-shaped tool schemas + the loop's
last_outputs into OpenAI function-calling and back, driving the identical agent
loop to a real paper fill. Also covers the OpenAI->Claude->keyword classifier
chooser and availability detection.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.agent import run_session
from agent.broker import LocalPaperBroker
from agent.llm import OpenAILLM
from agent.memory import Memory
from agent.positions import OpenPositions
import agent.tools as tools


# --- a scripted stand-in for the openai client -----------------------------
def _msg(content=None, tool_calls=None):
    tcs = None
    if tool_calls:
        tcs = [types.SimpleNamespace(
            id=tc["id"], type="function",
            function=types.SimpleNamespace(name=tc["name"], arguments=tc["arguments"]))
            for tc in tool_calls]
    return types.SimpleNamespace(content=content, tool_calls=tcs)


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        msg = self.script.pop(0)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])


class FakeOpenAIClient:
    def __init__(self, script):
        self.chat = types.SimpleNamespace(completions=FakeCompletions(script))


def test_openai_llm_drives_loop_to_a_fill(tmp_path):
    mem = Memory(state_dir=str(tmp_path))
    brk = LocalPaperBroker(start_cash=10_000.0, state_dir=str(tmp_path))
    pos = OpenPositions(state_dir=str(tmp_path))
    script = [
        _msg(tool_calls=[{"id": "t1", "name": "get_quotes",
                          "arguments": '{"symbols": ["GLD"]}'}]),
        _msg(tool_calls=[{"id": "t2", "name": "place_order",
                          "arguments": '{"symbol": "GLD", "side": "buy", "qty": 2, "reason": "haven"}'}]),
        _msg(content="Done — small gold hedge (paper)."),
    ]
    llm = OpenAILLM(client=FakeOpenAIClient(script))
    res = run_session(news=["headline"], llm=llm, broker=brk, memory=mem,
                      allow_network=False, positions=pos)
    assert res.final_text.startswith("Done")
    filled = [o for o in res.orders if o.get("status") == "filled"]
    assert filled and filled[0]["symbol"] == "GLD"
    assert brk.positions()["GLD"]["qty"] >= 1
    # the fake saw a tool-result fed back before the 2nd and 3rd calls
    create_calls = llm.client.chat.completions.calls
    assert len(create_calls) == 3
    roles_last = [m["role"] for m in create_calls[-1]["messages"]]
    assert "tool" in roles_last           # tool results were threaded back


def test_openai_tool_schema_conversion():
    from agent.tools import TOOL_SCHEMAS
    conv = OpenAILLM._to_openai_tools(TOOL_SCHEMAS)
    assert all(t["type"] == "function" for t in conv)
    assert conv[0]["function"]["name"] == TOOL_SCHEMAS[0]["name"]
    assert conv[0]["function"]["parameters"] == TOOL_SCHEMAS[0]["input_schema"]


def test_availability_and_classifier_chooser(monkeypatch):
    import news_trade_engine as nte
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert OpenAILLM.available() is True
    assert tools._choose_classifier() is nte.classify_openai
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert OpenAILLM.available() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert tools._choose_classifier() is nte.classify_llm
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert tools._choose_classifier() is nte.classify   # keyword fallback
