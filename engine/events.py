import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

@dataclass
class Event:
    name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: int = 0
    timestamp: float = field(default_factory=time.time)

class EventBus:
    """Thread/Async safe event bus for reacting to torrent events with strict ordering."""
    
    def __init__(self):
        self._handlers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._lock = asyncio.Lock()
        self._global_event_id = 0

    async def subscribe(self, event_name: str, handler: Callable[[Event], Any]) -> None:
        async with self._lock:
            if event_name not in self._handlers:
                self._handlers[event_name] = []
            self._handlers[event_name].append(handler)

    async def publish(self, event_name: str, payload: Dict[str, Any] | None = None) -> None:
        async with self._lock:
            self._global_event_id += 1
            event = Event(
                name=event_name,
                payload=payload or {},
                event_id=self._global_event_id,
                timestamp=time.time()
            )
            handlers = self._handlers.get(event_name, [])
        
        for handler in handlers:
            # If the handler is async, we should await it, but for simplicity of a generic bus
            # we can use asyncio.create_task or await if asyncio.iscoroutinefunction.
            # Assuming sync handlers for fast tracking, or explicit tasks for background ops.
            if asyncio.iscoroutinefunction(handler):
                asyncio.create_task(handler(event))
            else:
                handler(event)
