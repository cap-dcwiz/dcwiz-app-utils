import time
import functools
import threading
import uuid
from typing import Optional, Callable, Any, Dict
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """
    A utility class for measuring performance of FastAPI endpoints and functions.

    Features:
    - Decorator mode for automatic endpoint timing
    - Manual mode with checkpoints for detailed analysis
    - Thread-safe operation
    - Support for nested function calls
    - Configurable logging levels
    """

    def __init__(self, name: Optional[str] = None, log_level: int = logging.INFO):
        """
        Initialize the performance tracker.

        Args:
            name: Optional name for this tracker instance
            log_level: Logging level for performance messages
        """
        self.name = name or f"perf_tracker_{uuid.uuid4().hex[:8]}"
        self.log_level = log_level
        self._local = threading.local()
        self._trackers: Dict[str, "PerformanceTracker"] = {}

    def _get_current_tracker(self) -> Optional["PerformanceTracker"]:
        """Get the current active tracker for this thread."""
        if not hasattr(self._local, "current_tracker"):
            return None
        return self._local.current_tracker

    def _set_current_tracker(self, tracker: Optional["PerformanceTracker"]):
        """Set the current active tracker for this thread."""
        self._local.current_tracker = tracker

    def start(self, operation_name: Optional[str] = None) -> str:
        """
        Start a new performance measurement session.

        Args:
            operation_name: Name for this measurement session

        Returns:
            Session ID for this measurement
        """
        session_id = uuid.uuid4().hex[:8]
        operation_name = operation_name or f"operation_{session_id}"

        if not hasattr(self._local, "sessions"):
            self._local.sessions = {}

        self._local.sessions[session_id] = {
            "name": operation_name,
            "start_time": time.time(),
            "checkpoints": [],
            "end_time": None,
            "total_time": None,
        }

        # Set this as the current tracker
        self._set_current_tracker(self)

        logger.log(
            self.log_level,
            f"[{self.name}] Started measuring: {operation_name} (ID: {session_id})",
        )
        return session_id

    def checkpoint(
        self, checkpoint_name: str, session_id: Optional[str] = None
    ) -> float:
        """
        Add a checkpoint to the current measurement session.

        Args:
            checkpoint_name: Name for this checkpoint
            session_id: Optional session ID (uses current if not provided)

        Returns:
            Time elapsed since start in seconds
        """
        # Try to get session ID from current tracker if not provided
        if session_id is None:
            current_tracker = self._get_current_tracker()
            if current_tracker and hasattr(current_tracker._local, "sessions"):
                # Use the most recent session
                session_id = list(current_tracker._local.sessions.keys())[-1]
            else:
                raise RuntimeError(
                    "No active performance session found. Call start() first."
                )

        if (
            not hasattr(self._local, "sessions")
            or session_id not in self._local.sessions
        ):
            raise ValueError(f"Session {session_id} not found")

        session = self._local.sessions[session_id]
        current_time = time.time()
        elapsed = current_time - session["start_time"]

        checkpoint_data = {
            "name": checkpoint_name,
            "time": current_time,
            "elapsed": elapsed,
        }

        session["checkpoints"].append(checkpoint_data)

        logger.log(
            self.log_level,
            f"[{self.name}] Checkpoint '{checkpoint_name}': {elapsed:.4f}s elapsed",
        )

        return elapsed

    def end(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        End a performance measurement session and return results.

        Args:
            session_id: Optional session ID (uses current if not provided)

        Returns:
            Dictionary containing performance results
        """
        # Try to get session ID from current tracker if not provided
        if session_id is None:
            current_tracker = self._get_current_tracker()
            if current_tracker and hasattr(current_tracker._local, "sessions"):
                # Use the most recent session
                session_id = list(current_tracker._local.sessions.keys())[-1]
            else:
                raise RuntimeError(
                    "No active performance session found. Call start() first."
                )

        if (
            not hasattr(self._local, "sessions")
            or session_id not in self._local.sessions
        ):
            raise ValueError(f"Session {session_id} not found")

        session = self._local.sessions[session_id]

        end_time = time.time()
        total_time = end_time - session["start_time"]

        session["end_time"] = end_time
        session["total_time"] = total_time

        # Clear current tracker if this was the active one
        current_tracker = self._get_current_tracker()
        if current_tracker == self:
            self._set_current_tracker(None)

        # Prepare results
        results = {
            "session_id": session_id,
            "operation_name": session["name"],
            "start_time": session["start_time"],
            "end_time": end_time,
            "total_time": total_time,
            "checkpoints": session["checkpoints"].copy(),
        }

        # Log summary
        logger.log(
            self.log_level,
            f"[{self.name}] Completed '{session['name']}': {total_time:.4f}s total",
        )

        # Log checkpoint summary if any
        if session["checkpoints"]:
            logger.log(
                self.log_level, f"[{self.name}] Checkpoints for '{session['name']}':"
            )
            for cp in session["checkpoints"]:
                logger.log(self.log_level, f"  - {cp['name']}: {cp['elapsed']:.4f}s")

        # Clean up session
        del self._local.sessions[session_id]

        return results

    @contextmanager
    def measure(self, operation_name: Optional[str] = None):
        """
        Context manager for measuring performance.

        Args:
            operation_name: Name for this measurement session
        """
        session_id = self.start(operation_name)
        try:
            yield session_id
        finally:
            self.end(session_id)

    def decorator(self, operation_name: Optional[str] = None):
        """
        Decorator for measuring function performance.

        Args:
            operation_name: Optional name for the operation (uses function name if not provided)
        """

        def decorator_func(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                name = operation_name or f"{func.__module__}.{func.__name__}"
                session_id = self.start(name)
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    self.end(session_id)

            return wrapper

        return decorator_func

    def fastapi_decorator(self, operation_name: Optional[str] = None):
        """
        Special decorator for FastAPI endpoints that handles async functions.

        Args:
            operation_name: Optional name for the operation (uses function name if not provided)
        """

        def decorator_func(func: Callable) -> Callable:
            # Check if the function is async using inspect
            import inspect

            is_async = inspect.iscoroutinefunction(func)

            if is_async:

                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    name = operation_name or f"{func.__module__}.{func.__name__}"
                    start_time = time.time()
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    finally:
                        end_time = time.time()
                        total_time = end_time - start_time
                        logger.log(
                            self.log_level,
                            f"[{self.name}] Completed '{name}': {total_time:.4f}s total",
                        )

                return async_wrapper
            else:

                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    name = operation_name or f"{func.__module__}.{func.__name__}"
                    start_time = time.time()
                    try:
                        result = func(*args, **kwargs)
                        return result
                    finally:
                        end_time = time.time()
                        total_time = end_time - start_time
                        logger.log(
                            self.log_level,
                            f"[{self.name}] Completed '{name}': {total_time:.4f}s total",
                        )

                return sync_wrapper

        return decorator_func


# Global instance for easy access
perf_tracker = PerformanceTracker("global")


# Convenience functions for global tracker
def start_performance(operation_name: Optional[str] = None) -> str:
    """Start a performance measurement session using the global tracker."""
    return perf_tracker.start(operation_name)


def checkpoint(checkpoint_name: str, session_id: Optional[str] = None) -> float:
    """Add a checkpoint using the global tracker."""
    return perf_tracker.checkpoint(checkpoint_name, session_id)


def end_performance(session_id: Optional[str] = None) -> Dict[str, Any]:
    """End a performance measurement session using the global tracker."""
    return perf_tracker.end(session_id)


def measure_performance(operation_name: Optional[str] = None):
    """Context manager for measuring performance using the global tracker."""
    return perf_tracker.measure(operation_name)


def performance_decorator(operation_name: Optional[str] = None):
    """Decorator for measuring function performance using the global tracker."""
    return perf_tracker.decorator(operation_name)


def fastapi_performance_decorator(operation_name: Optional[str] = None):
    """Decorator for measuring FastAPI endpoint performance using the global tracker."""
    return perf_tracker.fastapi_decorator(operation_name)
