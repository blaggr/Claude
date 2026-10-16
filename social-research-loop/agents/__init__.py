"""Research-loop agents."""
from .base import Agent, LLMClient
from .librarian import Librarian
from .methodologist import Methodologist
from .analyst import Analyst
from .interpreter import Interpreter
from .writer import Writer
from .critic import Critic

# Stage name -> agent class. The orchestrator looks agents up here.
STAGE_AGENTS = {
    "frame": Librarian,
    "design": Methodologist,
    "analyze": Analyst,
    "interpret": Interpreter,
    "report": Writer,
}

__all__ = [
    "Agent",
    "LLMClient",
    "Librarian",
    "Methodologist",
    "Analyst",
    "Interpreter",
    "Writer",
    "Critic",
    "STAGE_AGENTS",
]
