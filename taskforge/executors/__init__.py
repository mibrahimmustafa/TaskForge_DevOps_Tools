from taskforge.executors.base import BaseExecutor
from taskforge.executors.shell import ShellExecutor
from taskforge.executors.http import HTTPExecutor
from taskforge.executors.python_callable import PythonExecutor
from taskforge.executors.docker import DockerExecutor
from taskforge.jobs.models import ExecutorType

def get_executor(executor_type: ExecutorType) -> BaseExecutor:
    if executor_type == ExecutorType.SHELL:
        return ShellExecutor()
    elif executor_type == ExecutorType.HTTP:
        return HTTPExecutor()
    elif executor_type == ExecutorType.PYTHON:
        return PythonExecutor()
    elif executor_type == ExecutorType.DOCKER:
        return DockerExecutor()
    return ShellExecutor()

__all__ = [
    "BaseExecutor",
    "ShellExecutor",
    "HTTPExecutor",
    "PythonExecutor",
    "DockerExecutor",
    "get_executor",
]
